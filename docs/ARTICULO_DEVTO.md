# Como implemente respaldos de PostgreSQL con FastAPI y GitHub Actions

> BORRADOR INDIVIDUAL. Publicar solo cuando hayas realizado las pruebas y agregado tus propias capturas. Quita esta linea en Dev.to. Escribe con tus palabras las partes que realmente realizaste.

## El problema que quise resolver

Para esta practica de Base de Datos II tenia que explicar una estrategia de backups, subir una aplicacion a GitHub, desplegarla automaticamente y mostrar la construccion en un video. Decidi trabajar con **PostgreSQL**, sin usar SQL Server, y hacer una herramienta pequena a la que llame **BackupManager**.

Queria que el proyecto no solo mostrara informacion sobre backups, sino que tuviera operaciones reales: agregar registros, exportarlos, verificar archivos y comprobar si una copia completa puede recuperarse.

- **Codigo fuente:** [ENLACE_GITHUB]
- **Aplicacion:** [ENLACE_RENDER]
- **Video:** [ENLACE_YOUTUBE]

## Que es un backup y que estrategias existen

Un **backup completo** busca conservar el contenido necesario para reconstruir el estado respaldado de una base de datos. En PostgreSQL uso `pg_dump -Fc` para exportar el esquema y los datos de una base a un archivo custom `.dump`.

Tambien existen los **backups incrementales** (guardan los cambios respecto de una copia anterior) y **diferenciales** (guardan cambios desde la ultima copia completa, segun la herramienta). En PostgreSQL, para recuperacion a un momento especifico pueden utilizarse respaldos fisicos y WAL/PITR. **No implemente WAL ni PITR en este software**; son alternativas para un entorno de produccion.

Dos terminos importantes son **RPO**, la perdida de datos maxima aceptable, y **RTO**, el tiempo maximo tolerado para volver a operar. En la practica, ademas de decidir cada cuanto respaldar, hay que pensar donde conservar los archivos y como probarlos.

## Tecnologias utilizadas

Use **FastAPI** para las rutas del backend, **SQLAlchemy** para los registros, **PostgreSQL en Neon** como base cloud, **Render** para la aplicacion publica y **GitHub Actions** para las automatizaciones.

[CAPTURA: estructura real del repositorio GitHub]

La aplicacion tiene un inventario sencillo para trabajar con datos controlados. Desde el panel puedo crear, editar y eliminar registros. En la seccion de backups distingo dos opciones:

1. **Copia parcial en JSON.** Exporta exclusivamente la tabla `records`, guarda un SHA-256 y permite volver a cargar esos registros.
2. **Copia completa PostgreSQL.** Ejecuta `pg_dump` y descarga un archivo `.dump` con el esquema y datos de la base. El archivo puede verificarse con SHA-256 y `pg_restore --list`.

La integridad del archivo no equivale a una recuperacion exitosa. Por eso use una tercera comprobacion: restaurarlo en un PostgreSQL temporal independiente desde GitHub Actions.

[CAPTURA: registros y boton Crear backup .dump]

[CAPTURA: historial de backups y verificacion SHA-256]

## Conexion a PostgreSQL y funcionamiento

Cree la base en Neon y obtuve una URL de conexion. Para `pg_dump` utilice la URL **directa**, sin el endpoint de pooler, tal como indica la documentacion de Neon. La cadena se configura como secreto, nunca dentro del repositorio publico.

[CAPTURA: resultado de /health donde se lea postgresql, SIN credenciales]

El comando principal de la copia es:

```bash
pg_dump --format=custom --no-owner --no-acl --file respaldo.dump
```

Los datos de conexion se reciben mediante variables de entorno privadas. Cuando termina, se calcula SHA-256 y se puede descargar el archivo. El almacenamiento del servidor Render gratuito es temporal, asi que no se debe confiar en que ese archivo permanezca guardado ahi.

## Automatizacion y prueba de restauracion

Configure dos workflows en `.github/workflows/`:

- **CI y despliegue:** ejecuta las pruebas del backend. Si pasan, usa un deploy hook para solicitar una nueva version del servicio en Render.
- **Backup PostgreSQL:** exporta una copia completa con `pg_dump`, restaura esa copia con `pg_restore` en una base aislada, verifica que la tabla `records` se haya recuperado y cifra el archivo antes de subirlo como artifact de GitHub Actions.

[CAPTURA: workflow de respaldo con resultado verde, despues de ejecutarlo]

[CAPTURA: paso de pg_restore y consulta de registros restaurados]

El artifact se retiene siete dias. Esta retencion permite evidenciar el trabajo, pero no reemplaza un almacenamiento de backups duradero en un sistema real.

## Lo que comprobe y que mejoraria

**Prueba realizada:** [ESCRIBE AQUI LOS PASOS QUE HICISTE EN LA WEB Y EL RESULTADO REAL. EJEMPLO: agregue 4 registros, guarde una copia, modifique un dato y comprobe...]

**Dificultad encontrada:** [CUENTA UN ERROR REAL QUE HAYAS TENIDO, O ELIMINA ESTA LINEA SI NO HUBO]

**Mejoras futuras:** guardar los archivos en un bucket privado independiente, establecer politicas de retencion, cifrado con claves rotables, alertas cuando un backup falla y recuperacion a punto en el tiempo si el proveedor lo permite.

## Conclusion

La practica me ayudo a distinguir **tener un archivo de backup** de **comprobar que se puede restaurar**. Con PostgreSQL, `pg_dump` produce la copia logica, `pg_restore` permite reconstruirla y GitHub Actions facilita que estas operaciones se ejecuten sin depender de hacerlo manualmente cada vez.

Para un sistema real harian falta politicas de retencion y almacenamiento fuera del servidor, pero como ejercicio permite revisar tanto la creacion de respaldos como la recuperacion y el despliegue automatizado.

## Referencias

- PostgreSQL. *pg_dump*. https://www.postgresql.org/docs/17/app-pgdump.html
- PostgreSQL. *pg_restore*. https://www.postgresql.org/docs/17/app-pgrestore.html
- Neon. *Backups with pg_dump*. https://neon.com/docs/manage/backup-pg-dump
- GitHub. *GitHub Actions*. https://docs.github.com/en/actions
- Render. *Deploy Hooks*. https://render.com/docs/deploy-hooks

---

**ANTES DE PUBLICAR:** reemplaza todos los enlaces y las capturas por resultados reales. No publiques credenciales ni afirmes un deploy o restore que no hayas comprobado.
