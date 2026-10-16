# BackupManager - Control de respaldos PostgreSQL

Mini software nuevo e independiente para una practica de **Base de Datos II**. No utiliza Microsoft SQL Server ni depende de otros proyectos.

## Para que sirve

BackupManager administra un inventario pequeno en una base de datos y permite comprobar dos formas de protegerlo:

| Operacion | Que hace realmente | Limitacion |
| --- | --- | --- |
| Crear / editar / eliminar | Guarda datos en PostgreSQL (o SQLite local) | El modo SQLite solo sirve para desarrollo local |
| Exportacion JSON | Copia la tabla `records` y calcula SHA-256 | No respalda todas las tablas |
| Restaurar JSON | Sustituye los datos de la tabla `records` con una transaccion | Es una restauracion parcial |
| Backup completo PostgreSQL | Ejecuta `pg_dump -Fc`, comprueba que el archivo es legible y calcula SHA-256 | Requiere PostgreSQL 17, URL directa y cliente pg_dump |
| Descargar `.dump` | Entrega un respaldo completo a un administrador autenticado | Hay que guardar el archivo fuera del servidor |
| Verificar `.dump` | Valida hash SHA-256 y estructura del archivo con `pg_restore --list` | No equivale a una restauracion exitosa |
| Probar restore opcional | Usa `pg_restore` en una base de prueba independiente | Requiere `RESTORE_DATABASE_URL` |
| Backup automatico | GitHub Actions ejecuta pg_dump, restaura en PostgreSQL temporal y cifra el archivo | Los artifacts se retienen 7 dias |
| Deploy automatico | GitHub Actions ejecuta pytest y solicita un despliegue a Render | Requiere configurar el deploy hook |

La API se construye con **FastAPI + SQLAlchemy**. Para la nube usa **Neon PostgreSQL** y **Render**. El codigo se publica en **GitHub** y las automatizaciones utilizan **GitHub Actions**.

## Primero, ejecutar en Windows

1. Descomprime el ZIP en una carpeta nueva y abre esa carpeta en VS Code.
2. Haz doble clic en `INICIAR_EN_WINDOWS.bat` o abre la terminal en la carpeta y ejecuta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

3. Abre http://127.0.0.1:8000.
4. Escribe el valor de `BACKUP_ADMIN_TOKEN` del archivo `.env` en el campo de la izquierda.
5. En **Registros**, agrega datos. En **Respaldos**, crea un JSON y comprueba la restauracion.

En SQLite local, el boton de respaldo PostgreSQL permanece desactivado porque no seria un backup real de PostgreSQL. Esto es deliberado.

## Activar los backups completos de PostgreSQL

Crea un proyecto **PostgreSQL 17** en Neon y copia su URL de conexion **directa** (sin `-pooler`). En tu archivo local `.env` escribe:

```dotenv
DATABASE_URL=postgresql://USUARIO:CLAVE@HOST/neondb?sslmode=require
BACKUP_DATABASE_URL=postgresql://USUARIO:CLAVE@HOST/neondb?sslmode=require
BACKUP_ADMIN_TOKEN=TU_TOKEN_LARGO_PRIVADO
BACKUP_DIR=./backups
RESTORE_DATABASE_URL=
```

Los valores del ejemplo son ficticios: coloca tu URL real en privado. Reinicia FastAPI. El endpoint `/health` debe mostrar `"database":"postgresql"`.

La copia completa desde el panel requiere `pg_dump` y `pg_restore` **version 17**. En Render ya se incluyen mediante el Dockerfile. En Windows, instala las herramientas cliente PostgreSQL 17 o establece `PG_BIN_DIR=C:\Program Files\PostgreSQL\17\bin` en `.env`.

La copia del panel se guarda momentaneamente en `backups/postgres` y se descarga cuando termina. **En Render gratis el disco es efimero y el archivo se puede perder al reiniciar el servicio.** Descarga el respaldo inmediatamente. La automatizacion de GitHub Actions genera una copia cifrada independiente en GitHub, disponible durante 7 dias. No es almacenamiento definitivo.

## Publicar y automatizar

La guia con clics exactos esta en **`docs/GUIA_PASO_A_PASO.md`**.

### Secrets para GitHub Actions

- `RENDER_DEPLOY_HOOK_URL`: desde Render, Settings > Deploy Hook.
- `BACKUP_DATABASE_URL`: URL PostgreSQL **directa** desde Neon.
- `BACKUP_ENCRYPTION_PASSWORD`: contrasena larga exclusiva del backup cifrado.

### Variables de entorno para Render

- `DATABASE_URL`: URL Neon PostgreSQL (directa o pooled).
- `BACKUP_DATABASE_URL`: URL Neon PostgreSQL **directa**, para `pg_dump`.
- `BACKUP_ADMIN_TOKEN`: token largo y privado del administrador.
- `RESTORE_DATABASE_URL` (opcional): URL de una base PostgreSQL **DIFERENTE**, exclusiva para restauracion de prueba. Nunca usar la base original.

### API destacada

- `GET /health`: conexion a base de datos.
- `GET /api/records` y `POST/PUT/DELETE /api/records`: datos.
- `POST /api/backups`: exportacion de una tabla a JSON.
- `POST /api/backups/{id}/restore`: restaura solamente la tabla records.
- `GET /api/postgres/status`: requisitos de pg_dump.
- `POST /api/postgres/backups`: crea archivo PostgreSQL completo.
- `GET /api/postgres/backups`: historial.
- `GET /api/postgres/backups/{id}/download`: descargar .dump.
- `POST /api/postgres/backups/{id}/verify`: verificar integridad y legibilidad.
- `POST /api/postgres/backups/{id}/restore-test`: restaurar en base separada, si esta configurada.
- `/docs`: Swagger UI de la API.

Todas las operaciones sensibles requieren `X-Admin-Token` con el valor de `BACKUP_ADMIN_TOKEN`. Nunca uses el token de ejemplo en la nube.

## Probar antes de entregar

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas del codigo no sustituyen una comprobacion real en Neon, Render y GitHub Actions. Antes de publicar el articulo, comprueba que realmente aparecen una copia `.dump` descargada y una ejecucion verde de `pg_restore` en GitHub Actions.

## Advertencias

- Nunca subas `.env`, claves, tokens, dumps o datos personales al repositorio publico.
- No restaures un dump completo en produccion. Configura una base de ensayo separada o usa el workflow aislado.
- El limite del panel es 50 MB y es para practica. No es un servicio empresarial de backup.
- La regla 3-2-1, retencion duradera, incremental, PITR, WAL y alertas automatizadas son conceptos estudiados pero no todos estan implementados aqui.
- La bitacora es basica; no reemplaza un sistema de auditoria centralizado.

## Documentos de entrega

- `docs/GUIA_PASO_A_PASO.md`: instrucciones ordenadas para terminar la tarea.
- `docs/ARTICULO_DEVTO.md`: borrador de articulo, por personalizar con capturas reales.
- `docs/GUION_VIDEO.md`: video de menos de 5 minutos.
- `docs/ENLACES_ENTREGA.txt`: enlaces finales para comprimir en ZIP.

## Documentacion tecnica

- https://www.postgresql.org/docs/17/app-pgdump.html
- https://www.postgresql.org/docs/17/app-pgrestore.html
- https://neon.com/docs/manage/backup-pg-dump
- https://docs.github.com/en/actions
- https://render.com/docs/deploy-hooks
