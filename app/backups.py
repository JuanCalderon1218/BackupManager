"""Application-level JSON snapshots of the demo records table.

These snapshots are NOT full PostgreSQL database backups. Use the GitHub
Actions pg_dump workflow for a full database backup.
"""

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import Record

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "./backups"))
VALID_ID = re.compile(r"^snap_\d{8}T\d{6}Z_[a-f0-9]{8}$")


class InvalidSnapshot(Exception):
    pass


def _files(snapshot_id: str) -> tuple[Path, Path]:
    if not VALID_ID.fullmatch(snapshot_id):
        raise InvalidSnapshot("Identificador de respaldo no valido")
    return BACKUP_DIR / f"{snapshot_id}.json", BACKUP_DIR / f"{snapshot_id}.sha256"


def create_snapshot(session: Session) -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    records = session.scalars(select(Record).order_by(Record.id)).all()
    now = datetime.now(timezone.utc)
    snapshot_id = f"snap_{now.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}"
    path, digest_path = _files(snapshot_id)
    data = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "scope": "records_table_only",
        "records": [
            {
                "id": rec.id,
                "name": rec.name,
                "category": rec.category,
                "quantity": rec.quantity,
                "created_at": rec.created_at.isoformat(),
            }
            for rec in records
        ],
    }
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    with path.open("xb") as file:
        file.write(payload)
    try:
        digest_path.write_text(digest + "\n", encoding="ascii")
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return {
        "id": snapshot_id,
        "created_at": now.isoformat(),
        "record_count": len(records),
        "size_bytes": len(payload),
        "verified": True,
        "sha256": digest,
    }


def _read_verified(snapshot_id: str) -> dict:
    path, digest_path = _files(snapshot_id)
    if not path.is_file() or not digest_path.is_file():
        raise FileNotFoundError("Respaldo no encontrado")
    payload = path.read_bytes()
    checksum = digest_path.read_text(encoding="ascii").strip()
    if not secrets.compare_digest(hashlib.sha256(payload).hexdigest(), checksum):
        raise InvalidSnapshot("El checksum SHA-256 no coincide")
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise InvalidSnapshot("JSON del respaldo no valido") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise InvalidSnapshot("Version de respaldo no compatible")
    if data.get("scope") != "records_table_only" or not isinstance(data.get("records"), list):
        raise InvalidSnapshot("Contenido del respaldo incorrecto")
    seen = set()
    for row in data["records"]:
        if not isinstance(row, dict):
            raise InvalidSnapshot("Registro de respaldo incorrecto")
        if not isinstance(row.get("id"), int) or row["id"] <= 0 or row["id"] in seen:
            raise InvalidSnapshot("ID de registro incorrecto o duplicado")
        seen.add(row["id"])
        if not isinstance(row.get("name"), str) or not 1 <= len(row["name"]) <= 90:
            raise InvalidSnapshot("Nombre incorrecto")
        if not isinstance(row.get("category"), str) or not 1 <= len(row["category"]) <= 50:
            raise InvalidSnapshot("Categoria incorrecta")
        if type(row.get("quantity")) is not int or not 0 <= row["quantity"] <= 1000000:
            raise InvalidSnapshot("Cantidad incorrecta")
        try:
            datetime.fromisoformat(row["created_at"])
        except (TypeError, ValueError) as exc:
            raise InvalidSnapshot("Fecha incorrecta") from exc
    return data


def list_snapshots() -> list[dict]:
    if not BACKUP_DIR.is_dir():
        return []
    result = []
    for path in BACKUP_DIR.glob("snap_*.json"):
        snapshot_id = path.stem
        if not VALID_ID.fullmatch(snapshot_id):
            continue
        try:
            data = _read_verified(snapshot_id)
            verified = True
            record_count = len(data["records"])
            created_at = data["generated_at"]
        except (InvalidSnapshot, FileNotFoundError, OSError, TypeError):
            verified = False
            record_count = None
            created_at = None
        result.append({
            "id": snapshot_id,
            "created_at": created_at,
            "record_count": record_count,
            "size_bytes": path.stat().st_size,
            "verified": verified,
        })
    return sorted(result, key=lambda entry: entry["id"], reverse=True)


def get_snapshot_file(snapshot_id: str) -> Path:
    _read_verified(snapshot_id)
    return _files(snapshot_id)[0]


def restore_snapshot(session: Session, snapshot_id: str) -> int:
    data = _read_verified(snapshot_id)
    # This only replaces the demo table. PostgreSQL schema and audit logs survive.
    # SQL transaction guarantees no partial restore if an insert fails.
    session.execute(delete(Record))
    for entry in data["records"]:
        session.add(Record(
            id=entry["id"],
            name=entry["name"],
            category=entry["category"],
            quantity=entry["quantity"],
            created_at=datetime.fromisoformat(entry["created_at"]),
        ))
    session.flush()
    return len(data["records"])
