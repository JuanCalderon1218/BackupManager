"""Physical PostgreSQL exports for a small educational backup console.

A dump stored on a web service is TEMPORARY unless external persistent storage
is configured. The scheduled GitHub workflow stores encrypted off-host copies.
"""

import hashlib
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from app.database import is_sqlite

MAX_BACKUP_BYTES = 50 * 1024 * 1024
VALID_ID = re.compile(r"^full_\d{8}T\d{6}Z_[0-9a-f]{8}$")


class BackupError(Exception):
    pass


def _parse_pg_url(raw: str) -> dict[str, str]:
    url = raw.replace("postgresql+psycopg://", "postgresql://", 1)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    info = urlsplit(url)
    if info.scheme != "postgresql" or not info.hostname or not info.username or not info.path.strip("/"):
        raise BackupError("Se necesita una URL PostgreSQL valida.")
    try:
        port = str(info.port or 5432)
    except ValueError as exc:
        raise BackupError("Puerto PostgreSQL incorrecto.") from exc
    params = parse_qs(info.query)
    config = {
        "PGHOST": info.hostname,
        "PGPORT": port,
        "PGUSER": unquote(info.username),
        "PGDATABASE": unquote(info.path.lstrip("/")),
        "PGPASSWORD": unquote(info.password or ""),
        "PGSSLMODE": params.get("sslmode", ["require"])[0],
        "PGCONNECT_TIMEOUT": "15",
    }
    if "channel_binding" in params:
        config["PGCHANNELBINDING"] = params["channel_binding"][0]
    return config


def _direct_source() -> dict[str, str]:
    if is_sqlite:
        raise BackupError("Primero conecta la aplicacion a PostgreSQL; SQLite no permite pg_dump.")
    url = os.getenv("BACKUP_DATABASE_URL", "").strip()
    if not url:
        raise BackupError("Falta BACKUP_DATABASE_URL (conexion directa de Neon).")
    data = _parse_pg_url(url)
    if "-pooler" in data["PGHOST"]:
        raise BackupError("Usa la URL directa de Neon, no la URL con -pooler.")
    return data


def _binary(name: str) -> str:
    custom = os.getenv("PG_BIN_DIR", "").strip()
    executable = f"{name}.exe" if os.name == "nt" else name
    selected = str(Path(custom) / executable) if custom else shutil.which(executable)
    if not selected or not Path(selected).is_file():
        raise BackupError(f"No se encuentra {name}. Instala las herramientas cliente PostgreSQL 17 o usa el Dockerfile del proyecto.")
    return selected


def _run(command: list[str], env: dict[str, str], timeout: int = 150) -> None:
    try:
        process = subprocess.run(
            command,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BackupError("La operacion supero el tiempo maximo permitido.") from exc
    except OSError as exc:
        raise BackupError("No se pudo iniciar la herramienta PostgreSQL.") from exc
    if process.returncode != 0:
        # Do not expose subprocess stderr: client errors may contain private hostnames.
        raise BackupError("Fallo la herramienta PostgreSQL. Revisa la conexion, permisos y version del cliente.")


def _directory() -> Path:
    folder = Path(os.getenv("BACKUP_DIR", "./backups")) / "postgres"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def _file_for(backup_id: str) -> Path:
    if not VALID_ID.fullmatch(backup_id):
        raise BackupError("Identificador de backup incorrecto.")
    return _directory() / f"{backup_id}.dump"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_full_backup() -> dict:
    source = _direct_source()
    dump_tool = _binary("pg_dump")
    restore_tool = _binary("pg_restore")
    now = datetime.now(timezone.utc)
    backup_id = f"full_{now.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}"
    final_path = _file_for(backup_id)
    partial_path = final_path.with_suffix(".part")
    descriptor = os.open(partial_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        _run([dump_tool, "--format=custom", "--no-owner", "--no-acl", "--file", str(partial_path)], source)
        size = partial_path.stat().st_size
        if size == 0 or size > MAX_BACKUP_BYTES:
            raise BackupError("El respaldo esta vacio o supera el limite de 50 MB de esta aplicacion.")
        _run([restore_tool, "--list", str(partial_path)], {})
        digest = checksum(partial_path)
        os.replace(partial_path, final_path)
        return {
            "id": backup_id,
            "created_at": now,
            "size_bytes": size,
            "sha256": digest,
        }
    finally:
        partial_path.unlink(missing_ok=True)


def verified_file(backup_id: str, expected_digest: str) -> Path:
    path = _file_for(backup_id)
    if not path.is_file():
        raise FileNotFoundError("El archivo ya no esta en el servidor.")
    if not secrets.compare_digest(checksum(path), expected_digest):
        raise BackupError("El archivo cambio: SHA-256 no coincide.")
    _run([_binary("pg_restore"), "--list", str(path)], {})
    return path


def staging_ready() -> bool:
    return bool(os.getenv("RESTORE_DATABASE_URL", "").strip())


def status() -> dict:
    if is_sqlite:
        message = "Modo local SQLite. Conecta Neon para activar los respaldos completos."
    elif not os.getenv("BACKUP_DATABASE_URL"):
        message = "Agrega BACKUP_DATABASE_URL (conexion directa de Neon)."
    else:
        try:
            _direct_source()
            _binary("pg_dump")
            _binary("pg_restore")
            message = "Listo para generar un respaldo completo PostgreSQL."
        except BackupError as exc:
            message = str(exc)
    return {
        "ready": message.startswith("Listo"),
        "restore_ready": staging_ready(),
        "message": message,
        "storage_note": "El archivo en Render es temporal. Descargalo al crearlo; el workflow de Actions guarda copias cifradas durante 7 dias.",
    }


def restore_to_staging(backup_id: str, expected_digest: str) -> int:
    source = _direct_source()
    staging_url = os.getenv("RESTORE_DATABASE_URL", "").strip()
    if not staging_url:
        raise BackupError("Falta RESTORE_DATABASE_URL: crea otra base separada para las pruebas.")
    destination = _parse_pg_url(staging_url)
    if "-pooler" in destination["PGHOST"]:
        raise BackupError("La URL de recuperacion debe ser directa (sin -pooler).")
    src_host = source["PGHOST"].replace("-pooler", "")
    dst_host = destination["PGHOST"].replace("-pooler", "")
    if src_host == dst_host and source["PGPORT"] == destination["PGPORT"] and source["PGDATABASE"] == destination["PGDATABASE"]:
        raise BackupError("La base de restauracion coincide con la base original. Operacion rechazada.")
    path = verified_file(backup_id, expected_digest)
    _run([
        _binary("pg_restore"),
        "--clean", "--if-exists", "--exit-on-error", "--single-transaction",
        "--no-owner", "--no-acl", "--dbname", destination["PGDATABASE"], str(path),
    ], destination, timeout=180)
    try:
        import psycopg
        with psycopg.connect(staging_url, connect_timeout=15) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM public.records")
                restored = cursor.fetchone()[0]
    except Exception as exc:
        raise BackupError("El restore termino, pero no pudo comprobar la tabla de registros.") from exc
    return restored
