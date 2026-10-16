# GUION PARA VIDEO - Duracion objetivo: 4 minutos 20 segundos

Graba la pantalla sin mostrar `.env`, tokens o cadenas de conexion. No repitas acciones que ya estan ejecutadas si retrasan la grabacion: puedes mostrar el historial y hacer una operacion breve.

## 0:00 a 0:30 - Presentacion

"Este es BackupManager, un mini software de Base de Datos II para mostrar estrategias de respaldo con PostgreSQL. Esta aplicacion esta separada de mis otros proyectos y no usa SQL Server."

Mostrar el panel en Render.

## 0:30 a 1:10 - Codigo y base cloud

"El proyecto esta en un repositorio publico de GitHub. El backend es FastAPI y la base se encuentra en Neon. El endpoint health confirma la conexion con PostgreSQL."

Mostrar repo, carpeta app y `/health`. No mostrar URL de conexion.

## 1:10 a 2:15 - Funciones del sistema

"Puedo guardar, editar y eliminar registros. Hay un backup parcial de la tabla en JSON y otro completo de PostgreSQL. El completo usa pg_dump para generar un archivo .dump y el panel permite verificar SHA-256 y descargarlo."

Mostrar registros, crear o seleccionar un backup completo, click en Verificar y descarga.

## 2:15 a 3:15 - Automatizacion y restauracion REAL

"Ademas hay un workflow de GitHub Actions. Aqui se ejecuta pg_dump y despues pg_restore en un PostgreSQL temporal independiente. Si termina correctamente, el archivo se cifra y se conserva como artifact durante siete dias."

Mostrar workflow verde, paso de restauracion y artifact. El workflow ya debe haberse ejecutado.

## 3:15 a 3:55 - Despliegue automatico

"El otro workflow ejecuta las pruebas y solicita el despliegue a Render despues de un cambio en GitHub. El servicio queda disponible en esta URL publica."

Mostrar Actions CI/deploy y Render Live.

## 3:55 a 4:20 - Conclusion

"El resultado demuestra exportacion completa, comprobacion del archivo, restauracion aislada y automatizacion. En produccion tambien habria que contar con almacenamiento externo permanente y politicas de retencion."

Mostrar panel y enlaces en el articulo.

Si te falta una prueba, no la presentes como exitosa: configuralo primero y graba cuando ya haya funcionado.
