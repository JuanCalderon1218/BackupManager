# GUIA PARA TERMINAR BACKUPMANAGER - BASE DE DATOS II

Esta guia se puede seguir sin saber configurar servidores. No inventes capturas ni resultados: solo publica lo que ya comprobaste. En total tienes: una app, repositorio publico, despliegue automatizado, base cloud, articulo individual, video y ZIP.

## PARTE A. Comprobar la app nueva (10-15 min de trabajo manual, segun tu equipo)

1. Cierra la ventana de la version anterior que esta ejecutando Uvicorn (Ctrl+C).
2. Extrae el ZIP actualizado en una NUEVA carpeta para no mezclar versiones.
3. Abre la nueva carpeta `BackupManager_Entrega` en VS Code.
4. Ejecuta `INICIAR_EN_WINDOWS.bat` y abre http://127.0.0.1:8000.
5. Abre `.env` y ubica `BACKUP_ADMIN_TOKEN`. Su valor se escribe en la barra izquierda de la web.
6. Abre **Registros**, agrega un registro, pulsa **Editar**, cambia la cantidad, guarda y comprueba.
7. Crea la copia JSON en **Respaldos**. Agrega otro registro; luego restaura el JSON y confirma que vuelve el conjunto anterior.

Esto demuestra CRUD y una copia parcial. Todavia NO demuestra respaldo completo PostgreSQL porque usa SQLite local.

## PARTE B. Crear PostgreSQL en Neon

1. Entra a https://console.neon.tech y abre una cuenta.
2. Pulsa **New Project**. Nombre: `backupmanager-db2`. Si Neon lo permite, selecciona **PostgreSQL 17**; el Dockerfile y los workflows usan el cliente 17.
3. Crea el proyecto y busca **Connect**.
4. En esa ventana **desactiva Connection pooling** (sin `-pooler` en la URL).
5. Copia la cadena que empieza con `postgresql://` y que incluye una clave. Guardala PRIVADAMENTE en un bloc de notas local temporal o directamente en `.env`. Nunca la pongas en GitHub o en el articulo.
6. Abre el archivo `.env` de tu proyecto. Cambia estas lineas con la misma URL de Neon:

```dotenv
DATABASE_URL=postgresql://TU_USUARIO:TU_CLAVE@TU_SERVIDOR/neondb?sslmode=require
BACKUP_DATABASE_URL=postgresql://TU_USUARIO:TU_CLAVE@TU_SERVIDOR/neondb?sslmode=require
BACKUP_ADMIN_TOKEN=UN_TOKEN_LARGO_QUE_SOLO_TU_CONOZCAS
```

7. Guarda `.env`, cierra la consola de FastAPI con Ctrl+C y ejecuta otra vez `INICIAR_EN_WINDOWS.bat`.
8. Abre http://127.0.0.1:8000/health. Debes obtener `"status":"ok"` y `"database":"postgresql"`. Las tablas se crean automaticamente al iniciar.
9. Vuelve a la web y crea unos registros. Ahora se guardan en Neon, no en SQLite.
10. En Windows, el respaldo completo del panel requiere **pg_dump 17** instalado. Si no lo tienes, no te detengas: el Dockerfile ya incluye esa herramienta para Render, y GitHub Actions tambien. Puedes continuar al despliegue.

**No compartas capturas del archivo `.env` ni de la URL completa.**

## PARTE C. Subir el software a un repositorio GitHub PUBLICO

1. Crea un repositorio en https://github.com/new, nombre `backupmanager-bd2`, tipo **Public**. No agregues README desde GitHub.
2. Terminal de VS Code, ubicada en la carpeta `BackupManager_Entrega`:

```powershell
git init
git add .
git status --short
git commit -m "BackupManager BD2: control de backups PostgreSQL"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/backupmanager-bd2.git
git push -u origin main
```

3. Sustituye `TU_USUARIO` por tu usuario verdadero. Si ya agregaste un remote antes, usa `git remote -v` para comprobarlo antes de repetir el comando.
4. Abre tu repo publico y comprueba que aparecen `app/`, `Dockerfile`, `.github/workflows/` y `README.md`.
5. Verifica que `.env`, `.venv` y `backups/` **NO aparecen en GitHub**. Ejecuta `git ls-files .env`: debe quedar vacio.

El primer job de despliegue puede fallar hasta configurar el secret del hook. Eso no significa que la aplicacion este mal.

## PARTE D. Publicar la app en Render

1. Entra a https://dashboard.render.com y vincula GitHub.
2. Pulsa **New > Blueprint** (o New > Web Service > Docker) y selecciona `backupmanager-bd2`.
3. El repositorio incluye `render.yaml` y `Dockerfile`. En el plan Free, si esta disponible, la app se dormira por inactividad y sus archivos temporales se borraran al reiniciarse.
4. Al pedir variables de entorno, configura EXACTAMENTE:

```text
DATABASE_URL             = LA_URL_DIRECTA_DE_NEON
BACKUP_DATABASE_URL      = LA_MISMA_URL_DIRECTA_DE_NEON
BACKUP_ADMIN_TOKEN       = EL_TOKEN_PRIVADO_LARGO
```

5. En Render, crea/guarda el servicio. El despliegue inicial puede ser manual desde la consola de Render.
6. Cuando el servicio muestre **Live**, abre la URL publica de Render y luego agrega `/health` al final.
7. Debes ver JSON con `"database":"postgresql"`. Si no, revisa las variables en Render y los Logs.
8. En la pagina publica, agrega un registro y haz clic en **Respaldos > Crear backup .dump**. Debe generarse y descargarse un archivo `.dump`. **Guardalo fuera de Render**.
9. Pulsa **Verificar** en la fila del dump y confirma el mensaje de integridad. Toma capturas del estado PostgreSQL, del archivo generado y de la verificacion.

**Si el boton no se habilita:** abre el mensaje de configuracion en el panel. Lo habitual es que falte `BACKUP_DATABASE_URL`, que la URL sea pooled o que el cliente de PostgreSQL no este disponible.

## PARTE E. Automatizar despliegue con GitHub Actions

1. En Render abre tu servicio > **Settings** y busca **Deploy Hook**. Copia su URL **secreta**.
2. En GitHub: repo > **Settings > Secrets and variables > Actions > New repository secret**.
3. Crea el secret `RENDER_DEPLOY_HOOK_URL` pegando el hook de Render.
4. En GitHub abre la pestana **Actions**.
5. Abre **CI y despliegue Render**, presiona **Run workflow** y ejecuta en la rama `main`.
6. Comprueba que **Pruebas FastAPI** termine verde y que **Desplegar en Render** termine verde.
7. Vuelve a Render para comprobar que el despliegue solicitado finalizo en **Live**. El resultado verde de Actions confirma la solicitud, no el fin del despliegue.

Guarda una captura del workflow terminado y otra del sitio en Render.

## PARTE F. Automatizar backup PostgreSQL y probar RESTAURACION REAL

1. En GitHub Settings > Secrets and variables > Actions agrega:

```text
BACKUP_DATABASE_URL        = LA_URL_DIRECTA_DE_NEON (sin -pooler)
BACKUP_ENCRYPTION_PASSWORD = UNA_CLAVE_LARGA_SOLO_PARA_CIFRADO
```

2. En **Actions**, abre **Backup PostgreSQL cifrado y prueba de restauracion** y pulsa **Run workflow**.
3. Espera el resultado final. El workflow usa `pg_dump -Fc` para exportar toda la base, luego `pg_restore` hacia un PostgreSQL 17 temporal del propio workflow.
4. Comprueba que los pasos **Crear copia completa**, **Restaurar copia en base temporal**, **Cifrar dump** y **Guardar artefacto** aparezcan verdes.
5. En la pagina de esa ejecucion, busca **Artifacts** y descarga o muestra el artifact cifrado (retencion 7 dias).
6. Toma una captura del paso de restauracion. Es la mejor evidencia de que la recuperacion realmente funciona.
7. La automatizacion programada se ejecuta diariamente, pero para esta tarea usa **Run workflow** para obtener el resultado antes de entregar.

El artefacto de GitHub es temporal. Para un sistema productivo haria falta almacenamiento privado permanente, retencion y politicas de restauracion.

## PARTE G. Articulo individual en Dev.to

1. Entra a https://dev.to y crea cuenta.
2. Abre `docs/ARTICULO_DEVTO.md` en VS Code.
3. Copia el contenido en Dev.to > Write a Post.
4. Escribe tu nombre o firma como autor e incluye tu experiencia real: que conectaste, que error tuviste (si hubo) y como lo solucionaste.
5. Reemplaza todos los campos `[ENLACE...]` y `[CAPTURA...]` por evidencias verdaderas. No dejes placeholders.
6. Inserta al menos: repo GitHub, app Render, dump descargado, workflow de pg_restore exitoso y deploy automatizado.
7. Publica y copia la URL publica del articulo.
8. Cada integrante del grupo publica su propio articulo, aunque utilicen el mismo repositorio si el docente lo permite.

## PARTE H. Video de menos de 5 minutos

1. Abre `docs/GUION_VIDEO.md`.
2. Graba pantalla usando OBS o Xbox Game Bar, sin mostrar credenciales.
3. Muestra la app, la base PostgreSQL, el dump, la verificacion y Actions de restauracion / despliegue.
4. No excedas cinco minutos. Recomendado: 4:00 a 4:30.
5. Publica en YouTube y copia su URL publica (no privada).

## PARTE I. Enviar Telegram y subir ZIP

1. Abre `docs/ENLACES_ENTREGA.txt` y completa GitHub, Render, Actions, Dev.to y YouTube.
2. Enviale al grupo de Telegram los enlaces del articulo y video, como exige el docente.
3. En PowerShell, dentro de la carpeta principal:

```powershell
Compress-Archive -Path .\docs\ENLACES_ENTREGA.txt -DestinationPath .\Entrega_BackupManager_Enlaces.zip -Force
```

4. Sube ese ZIP a la tarea.

## Lista de control final

- [ ] App publicada en Render y conectada a Neon PostgreSQL
- [ ] Repo publico GitHub sin secretos
- [ ] Backup completo .dump generado desde el panel (y descargado)
- [ ] Workflow backup+restore verde y artifact cifrado
- [ ] Workflow CI/deploy verde y Render Live
- [ ] Articulo personal publicado en Dev.to
- [ ] Video publico de 5 minutos o menos
- [ ] Links en Telegram y ZIP entregado

## Conceptos para explicar al profesor

**Backup completo:** exportacion de esquema y datos a `.dump` con pg_dump. **Backup parcial:** exportacion JSON solo de `records`. **SHA-256:** detecta cambios en el archivo; no es una prueba de restauracion. **Restauracion:** pg_restore reconstruye el respaldo en una base aislada. **Automatizacion:** GitHub Actions ejecuta el workflow manualmente o por cron. **Despliegue automatico:** GitHub Actions solicita a Render una nueva implementacion luego de pasar las pruebas. **Limitacion:** Render Free usa disco efimero; GitHub artifact dura 7 dias. No se afirma que ya exista un repositorio o despliegue hasta hacerlo de verdad.
