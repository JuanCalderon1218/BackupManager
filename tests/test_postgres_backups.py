import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./backupmanager_local.db")
os.environ["BACKUP_ADMIN_TOKEN"] = "test-secret-backupmanager"

from app import postgres_backups
from app.database import Base, get_db
from app.main import app

HEADERS = {"X-Admin-Token": "test-secret-backupmanager"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.sqlite'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)

    def db_override():
        with maker() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    monkeypatch.setenv("BACKUP_DIR",str(tmp_path / "backups"))
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_postgres_requires_configuration(client):
    result = client.get("/api/postgres/status").json()
    assert result["ready"] is False
    response = client.post("/api/postgres/backups",headers=HEADERS)
    assert response.status_code == 422
    assert "SQLite" in response.json()["detail"]


def test_admin_required_for_full_backup(client):
    assert client.post("/api/postgres/backups").status_code == 401
    assert client.post("/api/postgres/backups",headers={"X-Admin-Token":"wrong"}).status_code == 401


def test_pg_url_and_pooler_validation(monkeypatch):
    options = postgres_backups._parse_pg_url(
        "postgresql://student:p%40ss%3Aword@ep-test.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    assert options["PGPASSWORD"] == "p@ss:word"
    assert options["PGDATABASE"] == "neondb"
    assert options["PGCHANNELBINDING"] == "require"
    monkeypatch.setattr(postgres_backups,"is_sqlite",False)
    monkeypatch.setenv("BACKUP_DATABASE_URL","postgresql://u:p@ep-test-pooler.neon.tech/neondb?sslmode=require")
    with pytest.raises(postgres_backups.BackupError,match="pooler"):
        postgres_backups._direct_source()


def test_full_backup_create_verify_download_and_tamper(client,monkeypatch,tmp_path):
    monkeypatch.setattr(postgres_backups,"is_sqlite",False)
    monkeypatch.setenv("BACKUP_DATABASE_URL","postgresql://student:fake@ep-test.neon.tech/neondb?sslmode=require")
    client_dir = tmp_path / "clientbin"
    client_dir.mkdir()
    for binary in ("pg_dump","pg_restore"):
        (client_dir / binary).touch()
    monkeypatch.setenv("PG_BIN_DIR",str(client_dir))
    executed = []

    def fake_run(command,env=None,**kwargs):
        executed.append(command)
        if Path(command[0]).name == "pg_dump":
            archive = Path(command[command.index("--file") + 1])
            archive.write_bytes(b"PGDMPexample-database-archive")
            assert env["PGPASSWORD"] == "fake"
        return SimpleNamespace(returncode=0,stderr="",stdout="")

    monkeypatch.setattr(postgres_backups.subprocess,"run",fake_run)
    assert client.get("/api/postgres/status").json()["ready"]
    created = client.post("/api/postgres/backups",headers=HEADERS)
    assert created.status_code == 201, created.text
    info = created.json()
    assert info["size_bytes"] > 10
    bid = info["id"]
    assert len(client.get("/api/postgres/backups").json()) == 1
    assert client.post(f"/api/postgres/backups/{bid}/verify",headers=HEADERS).json()["verified"]
    saved = client.get(f"/api/postgres/backups/{bid}/download",headers=HEADERS)
    assert saved.status_code == 200
    assert saved.content.startswith(b"PGDMP")
    assert any(Path(c[0]).name == "pg_dump" for c in executed)
    assert any(Path(c[0]).name == "pg_restore" for c in executed)
    (tmp_path / "backups" / "postgres" / f"{bid}.dump").write_bytes(b"alterado")
    assert client.post(f"/api/postgres/backups/{bid}/verify",headers=HEADERS).status_code == 422


def test_record_edit_and_staging_safety(client,monkeypatch,tmp_path):
    created = client.post('/api/records',headers=HEADERS,json={"name":"Servidor web","category":"Red","quantity":1})
    assert created.status_code == 201
    record_id = created.json()["id"]
    updated = client.put(f"/api/records/{record_id}",headers=HEADERS,json={"name":"Servidor cambiado","category":"Red","quantity":3})
    assert updated.status_code == 200
    assert updated.json()["quantity"] == 3
    monkeypatch.setattr(postgres_backups,"is_sqlite",False)
    monkeypatch.setenv("BACKUP_DATABASE_URL","postgresql://user:pw@ep-test.neon.tech/neondb?sslmode=require")
    monkeypatch.setenv("RESTORE_DATABASE_URL","postgresql://user:pw@ep-test.neon.tech/neondb?sslmode=require")
    with pytest.raises(postgres_backups.BackupError,match="coincide"):
        postgres_backups.restore_to_staging("full_20261016T120000Z_aabbccdd","abc")
