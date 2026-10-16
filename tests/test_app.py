import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./backupmanager_local.db")
os.environ["BACKUP_ADMIN_TOKEN"] = "test-secret-backupmanager"

from app import backups
from app.database import Base, get_db
from app.main import app

TOKEN_HEADERS = {"X-Admin-Token": "test-secret-backupmanager"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.sqlite3'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def db_override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(backups, "BACKUP_DIR", tmp_path / "backups")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_home_and_docs(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "BackupManager" in home.text
    assert client.get("/docs").status_code == 200


def test_requires_admin_token(client):
    assert client.post("/api/seed").status_code == 401
    assert client.post("/api/backups", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_seed_backup_modify_restore(client):
    assert client.get("/api/records").json() == []
    seeded = client.post("/api/seed", headers=TOKEN_HEADERS)
    assert seeded.status_code == 200
    assert seeded.json()["inserted"] == 4
    snapshot = client.post("/api/backups", headers=TOKEN_HEADERS)
    assert snapshot.status_code == 200
    sid = snapshot.json()["id"]
    assert snapshot.json()["record_count"] == 4
    assert len(client.get("/api/backups").json()) == 1

    added = client.post(
        "/api/records", headers=TOKEN_HEADERS,
        json={"name": "Dato temporal", "category": "Prueba", "quantity": 2}
    )
    assert added.status_code == 201
    assert len(client.get("/api/records").json()) == 5

    restored = client.post(f"/api/backups/{sid}/restore", headers=TOKEN_HEADERS)
    assert restored.status_code == 200
    assert restored.json()["restored"] == 4
    rows = client.get("/api/records").json()
    assert len(rows) == 4
    assert all(row["name"] != "Dato temporal" for row in rows)
    events = client.get("/api/events").json()
    assert any(item["action"] == "RESTORE" for item in events)


def test_download_and_integrity_verification(client, tmp_path):
    result = client.post("/api/backups", headers=TOKEN_HEADERS).json()
    sid = result["id"]
    download = client.get(f"/api/backups/{sid}/download", headers=TOKEN_HEADERS)
    assert download.status_code == 200
    assert download.json()["scope"] == "records_table_only"
    saved = backups.BACKUP_DIR / f"{sid}.json"
    saved.write_text('{"tampered":true}', encoding="utf-8")
    items = client.get("/api/backups").json()
    assert items[0]["verified"] is False
    response = client.post(f"/api/backups/{sid}/restore", headers=TOKEN_HEADERS)
    assert response.status_code == 422


def test_reject_path_traversal_and_invalid_data(client):
    assert client.get('/api/backups/..%2Fsecrets/download', headers=TOKEN_HEADERS).status_code in (404, 422)
    response = client.post('/api/records', headers=TOKEN_HEADERS, json={
        'name': '', 'category': 'A', 'quantity': -1
    })
    assert response.status_code == 422
