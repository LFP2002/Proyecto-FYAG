# MongoDB documental — SPEC-012A

PostgreSQL sigue siendo autoridad de usuarios, relaciones, evidencias y negocio.
MongoDB almacena únicamente fichas de evidencias y anotaciones documentales. No
contiene imágenes, PDF, rutas privadas, datos tributarios ni réplicas de Auditoría
o Alertas. Los bytes siguen en el volumen privado de Obras.

## Configuración local

Copiar las variables nuevas de `.env.example` a `.env` **privado e ignorado**.
Generar cuatro claves independientes (root/aplicación de desarrollo y QA), por
ejemplo con `python -c "import secrets; print(secrets.token_urlsafe(36))"` en una
terminal privada; nunca pegarlas en tickets, Git ni capturas. Las contraseñas
vacías del ejemplo deben reemplazarse localmente. No usar credenciales cloud.

- `MONGO_INITDB_ROOT_USERNAME/PASSWORD`: solo bootstrap de Mongo.
- `FYAG_MONGO_HOST/PORT/DB/USER/PASSWORD`: cliente Django; DB `fyag_documentos`.
- `FYAG_MONGO_TEST_ROOT_USER/PASSWORD`, `FYAG_MONGO_TEST_USER/PASSWORD`: solo QA.
- QA opcional: `FYAG_MONGO_TEST_HOST/PORT`, default `mongodb_test:27017`.

Compose publica Mongo únicamente en `127.0.0.1:${MONGO_HOST_PORT}`. La aplicación
usa la red Docker, no ese puerto. Backend, migraciones y workers no requieren
salud de Mongo para arrancar; las credenciales root de desarrollo se sobreescriben
vacías en sus entornos. El backend de desarrollo recibe credenciales QA porque
permite ejecutar tests; no trasladar ese env_file completo a producción.

### Volumen nuevo

```bash
docker compose up -d --build
docker compose exec -T mongodb mongosh --quiet /opt/fyag/database/health_mongodb.js
docker compose exec -T backend python manage.py verificar_mongodb
docker compose exec -T backend python manage.py reconciliar_documentos_mongodb
```

La imagen oficial crea root en un volumen nuevo; después ejecuta
`10-fyag.js` (montaje de `usuarios_mongodb.js`). Crea el rol de aplicación,
usuario, colección, validador e índice. No se inicia bootstrap desde Django.

### Volumen antiguo inicializado sin usuarios

**Agregar variables root NO crea usuarios en ese volumen.** Antes de cambiar el
contenedor, inventariar, clasificar datos y respaldarlos fuera de Git. No eliminar
el volumen para sortear el problema. Si aún está corriendo sin auth, copiar los
scripts y el esquema canónico a un directorio temporal privado del contenedor y
ejecutar `usuarios_mongodb.js` mediante `docker exec` con variables de bootstrap
pasadas desde entorno, `FYAG_MONGO_BOOTSTRAP_EXISTING=1`, las rutas
`FYAG_MONGO_SCRIPTS_DIR` y `FYAG_MONGO_SCHEMA` correctas. Solo se admite esta ruta
explícita local antes de activar auth; **nunca exponerla por red**. Después
recrear con el Compose endurecido (`--auth`) y comprobar rechazo anónimo.

Si el volumen ya tiene usuarios, usar la identidad administrativa existente.
Si las credenciales son desconocidas, detenerse: no deshabilitar auth ni borrar
usuarios/datos automáticamente. Respaldar antes de cualquier transición.

### Bootstrap repetible autenticado

```bash
docker compose exec -T mongodb mongosh --quiet /opt/fyag/database/usuarios_mongodb.js
```

Usa credenciales del entorno del contenedor, no argumentos con contraseña. Una
ejecución explícita vuelve a fijar el rol acotado y la clave configurada de la
identidad de aplicación: coordinar la rotación con los workers. Nunca imprime
claves. La colección existente se valida antes de `collMod`; datos incompatibles
detienen el procedimiento sin borrarlos. Inspeccionarlos/restaurarlos solo con
autorización y respaldo. Los índices antiguos ajenos no se eliminan por sorpresa.

## Esquema e índices

Fuente canónica: `backend/apps/documentos/esquema.json`, montada en Mongo en
`/opt/fyag/esquema.json`. Los tres nombres de scripts existentes se conservan:

- `init_mongodb.js`: bootstrap documental sin tocar otras colecciones.
- `indices_mongodb.js`: índice `(obra_id ASC, creado_en DESC, evidencia_id DESC)`.
- `validaciones_mongodb.js`: wrapper idempotente del bootstrap canónico.
- `usuarios_mongodb.js`: root/bootstrap separado del cliente de aplicación.
- `health_mongodb.js`: autenticación, ping y lectura autorizada con salida 0/1.

Ya no se crean/alteran `auditoria_eventos` ni `alertas_eventos`. Si existen de
scripts viejos, no se borran ni reciben escrituras de negocio. No se crea índice
por etiquetas porque no hay filtro por etiquetas en 012A.

Validador BSON estricto, error ante rechazo, sin propiedades extra, Int64 para
identificadores/tamaño, fechas UTC, esquema v1, ID determinista, límite 16 KiB.
El tamaño BSON de atributos también está acotado; la API añade el límite exacto
de 4 KiB JSON UTF-8 compacto y reglas semánticas/normalización. Accesos directos
administrativos no sustituyen esas reglas API. Django rechaza BSON corrupto en
lectura con 503 sin exponerlo. No usar bypass_document_validation fuera de QA.

Rol de aplicación: find/insert/update/listIndexes exclusivamente sobre
`documentos_metadata` y listCollections de la DB para comprobar el validador.
Sin delete, administración de usuarios, collMod, drop, createIndex o acceso a
otras colecciones. Bootstrap es responsabilidad separada del operador.

## Reconciliación y disponibilidad

```bash
docker compose exec -T backend python manage.py verificar_mongodb
docker compose exec -T backend python manage.py reconciliar_documentos_mongodb
docker compose logs --tail 20 documentos_reconciliador
```

Worker independiente: `reconciliar_documentos_mongodb --continuo`, intervalo 60 s,
lotes de 200, backoff de 1 a 60 s en fallos Mongo, SIGTERM/SIGINT y cierre del
cliente. `--intervalo` permite 1-3600 s. No se ejecuta al importar ni en runserver.
Reinicia desde PK 0 en cada ciclo: recupera commits fuera de orden y no depende
de un high-water-mark irreversible. Upsert `$set` técnico + `$setOnInsert` de
anotaciones vacías; nunca resetea anotaciones existentes. No hace DELETE remoto.
Detención a mitad de ciclo: repetirlo completa lo pendiente.

Proyección eventual (hasta próximo ciclo exitoso); GET/PATCH detalle pendiente
devuelve 409 `metadata_pendiente_sincronizacion`, sin sincronización incidental en
una petición. Mongo caído/credenciales inválidas/índice o esquema incompatible:
503, no lista vacía de éxito. Módulos SQL no consultan Mongo. No hay callbacks en
finalizar/subsanar turno ni escrituras remotas bajo bloqueos SQL.

## Pruebas y CI

```bash
docker compose --profile test up -d mongodb_test
docker compose exec -T mongodb_test mongosh --quiet /opt/fyag/database/health_mongodb.js
docker compose exec -T backend python manage.py test apps.documentos --noinput
docker compose exec -T backend python manage.py test --noinput
```

`mongodb_test` usa tmpfs, credenciales independientes y ninguna publicación host.
El runner fija DB `fyag_documentos_test`; si faltan credenciales/bootstrap QA,
falla en lugar de usar desarrollo o saltar pruebas. Tests destructivos de BSON,
índices y CAS solo operan en esa DB efímera. No ejecutar suites simultáneas ni
`--parallel`: las pruebas Mongo comparten colección QA. La regresión existente
usa `test_fyag_db` PostgreSQL y no datos de desarrollo.

Backend CI genera secretos efímeros en el runner, los enmascara, arranca Mongo
con auth/tmpfs, ejecuta bootstrap repetido, suite y cierre del contenedor. No
contacta volúmenes locales ni ejecuta limpieza de desarrollo.

## Limpieza local y rollback

La autorización de limpieza solo cubre datos FYAG locales clasificados. No usar
`down -v`. Inventariar context/proyecto/mounts reales, contar archivos/evidencias,
respaldar PostgreSQL con pg_dump custom y Mongo con mongodump archive, generar
manifiesto de hashes y verificar lectura/restauración. Conservar credenciales de
usuarios administrativos (hashes SQL), migraciones, permisos y esquema. No
versionar dumps ni manifiestos con datos privados. El detalle de la ejecución o
de su no ejecución figura en `backend/docs/SPEC-012-IMPLEMENTACION.md`.

Rollback de código: detener worker documental y retirar rutas/configuración
012A; mantener datos Mongo/SQL y archivos privados. No desactivar autenticación
al volver a una imagen anterior ni borrar volúmenes. Conservar backup y fuente
del validador v1; cambiar de esquema solo tras validar/restaurar datos en entorno
aislado. Las anotaciones son autoridad Mongo: no se regeneran desde SQL si se
pierden; incluirlas siempre en la política de respaldo.
