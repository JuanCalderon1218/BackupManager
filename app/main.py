"""Small FastAPI service for managing records and testing database recovery."""

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import backups, postgres_backups
from app.database import AuditEvent, Base, FullBackup, Record, engine, get_db, is_sqlite

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(application: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="BackupManager | Control de respaldos",
    description="Registros, respaldo de tabla JSON y respaldo completo PostgreSQL con pg_dump.",
    version="2.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class RecordInput(BaseModel):
    name: str = Field(min_length=2, max_length=90)
    category: str = Field(min_length=2, max_length=50)
    quantity: int = Field(ge=0, le=1000000)


class RecordOutput(RecordInput):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


def require_admin(x_admin_token: str | None = Header(default=None)):
    configured = os.getenv("BACKUP_ADMIN_TOKEN", "")
    if not configured:
        raise HTTPException(status_code=503, detail="Configura BACKUP_ADMIN_TOKEN.")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, configured):
        raise HTTPException(status_code=401, detail="Token incorrecto.")


def add_audit(session: Session, action: str, detail: str):
    session.add(AuditEvent(action=action, detail=detail))


def _get_full_backup(session: Session, backup_id: str) -> FullBackup:
    if not postgres_backups.VALID_ID.fullmatch(backup_id):
        raise HTTPException(status_code=422, detail="Identificador incorrecto.")
    backup = session.get(FullBackup, backup_id)
    if backup is None:
        raise HTTPException(status_code=404, detail="Copia no encontrada.")
    return backup


def _backup_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=410, detail="El archivo ya no esta disponible. Descarga la copia tras crearla.")
    return HTTPException(status_code=422, detail=str(exc))


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health(session: Session = Depends(get_db)):
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Base de datos sin conexion")
    return {"status": "ok", "database": "sqlite_local" if is_sqlite else "postgresql"}


@app.get("/api/records", response_model=list[RecordOutput])
def list_records(session: Session = Depends(get_db)):
    return session.scalars(select(Record).order_by(Record.id.desc()).limit(200)).all()


@app.post("/api/records", response_model=RecordOutput, status_code=201, dependencies=[Depends(require_admin)])
def create_record(payload: RecordInput, session: Session = Depends(get_db)):
    row = Record(**payload.model_dump())
    session.add(row)
    session.flush()
    add_audit(session, "REGISTRO", f"Creado #{row.id}: {row.name}")
    session.commit()
    session.refresh(row)
    return row


@app.put("/api/records/{record_id}", response_model=RecordOutput, dependencies=[Depends(require_admin)])
def update_record(record_id: int, payload: RecordInput, session: Session = Depends(get_db)):
    row = session.get(Record, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    add_audit(session, "EDICION", f"Actualizado registro #{record_id}")
    session.commit()
    session.refresh(row)
    return row


@app.delete("/api/records/{record_id}", dependencies=[Depends(require_admin)])
def delete_record(record_id: int, session: Session = Depends(get_db)):
    row = session.get(Record, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    session.delete(row)
    add_audit(session, "ELIMINACION", f"Eliminado registro #{record_id}")
    session.commit()
    return {"deleted": record_id}


@app.post("/api/seed", dependencies=[Depends(require_admin)])
def seed_demo(session: Session = Depends(get_db)):
    for name, category, quantity in [
        ("Servidor de aplicaciones", "Infraestructura", 3),
        ("Base de datos principal", "Servicios", 1),
        ("Estaciones de trabajo", "Equipos", 12),
        ("Dispositivos de red", "Redes", 7),
    ]:
        session.add(Record(name=name, category=category, quantity=quantity))
    add_audit(session, "CARGA", "Se agregaron 4 registros de ejemplo")
    session.commit()
    return {"inserted": 4}


# A small logical copy useful for showing row-level recovery.
@app.get("/api/backups")
def list_backups():
    return backups.list_snapshots()


@app.post("/api/backups", dependencies=[Depends(require_admin)])
def create_backup(session: Session = Depends(get_db)):
    try:
        result = backups.create_snapshot(session)
    except OSError:
        raise HTTPException(status_code=503, detail="No se pudo guardar el archivo JSON")
    add_audit(session, "JSON", f"Exportacion de records: {result['record_count']} filas")
    session.commit()
    return result


@app.get("/api/backups/{snapshot_id}/download", dependencies=[Depends(require_admin)])
def download_backup(snapshot_id: str):
    try:
        filepath = backups.get_snapshot_file(snapshot_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    except backups.InvalidSnapshot as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return FileResponse(filepath, filename=filepath.name, media_type="application/json")


@app.post("/api/backups/{snapshot_id}/restore", dependencies=[Depends(require_admin)])
def restore_backup(snapshot_id: str, session: Session = Depends(get_db)):
    try:
        amount = backups.restore_snapshot(session, snapshot_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    except backups.InvalidSnapshot as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    add_audit(session, "RESTORE", f"Tabla records recuperada: {amount} filas")
    session.commit()
    return {"restored": amount, "id": snapshot_id, "scope": "records_table_only"}


# Complete PostgreSQL dump (schema + data, not just the records table).
@app.get("/api/postgres/status")
def postgres_status():
    return postgres_backups.status()


@app.get("/api/postgres/backups")
def list_full_backups(session: Session = Depends(get_db)):
    rows = session.scalars(select(FullBackup).order_by(FullBackup.created_at.desc()).limit(40)).all()
    result = []
    for row in rows:
        try:
            available = postgres_backups._file_for(row.id).is_file()
        except postgres_backups.BackupError:
            available = False
        result.append({
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "size_bytes": row.size_bytes,
            "sha256": row.sha256,
            "available": available,
        })
    return result


@app.post("/api/postgres/backups", dependencies=[Depends(require_admin)], status_code=201)
def create_full_backup(session: Session = Depends(get_db)):
    try:
        result = postgres_backups.create_full_backup()
    except postgres_backups.BackupError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OSError:
        raise HTTPException(status_code=503, detail="No se pudo escribir el respaldo en disco.")
    backup = FullBackup(
        id=result["id"], filename=result["id"] + ".dump",
        size_bytes=result["size_bytes"], sha256=result["sha256"],
        created_at=result["created_at"],
    )
    session.add(backup)
    add_audit(session, "PG_DUMP", f"Copia PostgreSQL completa: {backup.id}")
    session.commit()
    return {"id": backup.id, "sha256": backup.sha256, "size_bytes": backup.size_bytes}


@app.post("/api/postgres/backups/{backup_id}/verify", dependencies=[Depends(require_admin)])
def verify_full_backup(backup_id: str, session: Session = Depends(get_db)):
    backup = _get_full_backup(session, backup_id)
    try:
        postgres_backups.verified_file(backup.id, backup.sha256)
    except (postgres_backups.BackupError, FileNotFoundError) as exc:
        raise _backup_error(exc)
    add_audit(session, "VERIFICACION", f"SHA-256 y archivo pg_restore correctos: {backup.id}")
    session.commit()
    return {"id": backup.id, "verified": True, "sha256": backup.sha256}


@app.get("/api/postgres/backups/{backup_id}/download", dependencies=[Depends(require_admin)])
def download_full_backup(backup_id: str, session: Session = Depends(get_db)):
    backup = _get_full_backup(session, backup_id)
    try:
        path = postgres_backups.verified_file(backup.id, backup.sha256)
    except (postgres_backups.BackupError, FileNotFoundError) as exc:
        raise _backup_error(exc)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.post("/api/postgres/backups/{backup_id}/restore-test", dependencies=[Depends(require_admin)])
def restore_full_backup_to_staging(backup_id: str, session: Session = Depends(get_db)):
    backup = _get_full_backup(session, backup_id)
    try:
        amount = postgres_backups.restore_to_staging(backup.id, backup.sha256)
    except (postgres_backups.BackupError, FileNotFoundError) as exc:
        raise _backup_error(exc)
    add_audit(session, "PG_RESTORE", f"Restauracion aislada en staging: {amount} registros")
    session.commit()
    return {"restored_rows": amount, "destination": "staging"}


@app.get("/api/events")
def list_events(session: Session = Depends(get_db)):
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(30)).all()
    return [{"id": item.id, "action": item.action, "detail": item.detail,
             "created_at": item.created_at.isoformat()} for item in rows]


@app.get("/api/summary")
def summary(session: Session = Depends(get_db)):
    count = session.scalar(select(func.count()).select_from(Record)) or 0
    full = session.scalar(select(func.count()).select_from(FullBackup)) or 0
    return {
        "records": count,
        "full_backups": full,
        "snapshots": len(backups.list_snapshots()),
        "database": "SQLite (local)" if is_sqlite else "PostgreSQL",
    }
