# Adjuntos: operación, escaneo y recuperación

## Despliegue local sin borrar datos ni cambiar claves

1. Revisar rama/diff, respaldos y espacio libre. Mantener `.env` existente; nunca
   copiar placeholders encima de contraseñas reales. Añadir solo variables nuevas
   de `.env.example` si hay overrides. Docker Linux es requerido por O_NOFOLLOW/dirfd.
2. Construir: `docker compose build backend migraciones adjuntos_reconciliador`.
3. Recrear exclusivamente Mongo para añadir montaje del esquema, manteniendo
   `mongodb_data`: `docker compose up -d --no-deps mongodb`.
4. Bootstrap explícito SOLO ampliación 012B (autentica con variables existentes):
   `docker compose exec -T mongodb mongosh --quiet /opt/fyag/database/adjuntos_mongodb.js`.
   Repetir es seguro; ante documentos incompatibles se detiene sin limpiar.
5. `docker compose run --rm migraciones` aplica la migración Django oficial nueva.
   No hay alteraciones de tablas financieras o de evidencias.
6. `docker compose up -d --no-deps backend clamav adjuntos_reconciliador`.
   El backend no depende de health del scanner: una caída solo rechaza subidas.
7. `docker compose exec -T clamav clamdcheck.sh` y
   `docker compose exec -T backend python manage.py diagnosticar_adjuntos`.

`adjuntos_data` no publica rutas ni puertos. Scanner tampoco tiene puerto host;
INSTREAM por red Docker, sin acceso a PostgreSQL, Mongo o volúmenes de archivos.
La red Docker no es equivalente a red de producción segmentada; no agregar servicios
no confiables a esa red. Imagen fijada `clamav/clamav:1.5.4-debian` con firmas
incluidas; desarrollo permite FreshClam, QA lo desactiva para repetibilidad.
Controlar estado, fecha/cantidad de firmas y logs FreshClam. Actualizar imagen/firmas
con revisión, nunca desactivar análisis para resolver indisponibilidad.

## QA aislado

`docker compose --profile test up -d mongodb_test clamav_test`

`docker compose exec -T backend python manage.py test apps.adjuntos --noinput`

`docker compose exec -T backend python manage.py check`

`docker compose exec -T backend python manage.py makemigrations --check --dry-run`

`docker compose exec -T backend python manage.py test --noinput`

El runner exige credenciales QA independientes ya configuradas, DB Mongo
`fyag_documentos_test`, almacén temporal propio y scanner `clamav_test`. SQL utiliza
la DB de test de Django, nunca limpia la base local. Ejecutar suites secuencialmente
para no interferir con DB de tests. EICAR se construye en memoria y nunca se guarda
en el repositorio ni se trata de malware ejecutable. Las únicas eliminaciones de
fixtures corresponden a QA aislado y temporales creados por la prueba.

GitHub Actions utiliza PostgreSQL efímero, Mongo autenticado QA y ClamAV sin red
ni puerto host, accedido por socket Unix privado del runner. Bootstrap se ejecuta
dos veces antes de suite completa. No se ha ejecutado CI remoto sin publicación.

## Diagnóstico y reinicios

`python manage.py diagnosticar_adjuntos` siempre es dry-run: cuenta registros,
faltantes/corruptos, huérfanos y staging pendiente. No hay flag de borrar o reparar.
Revisar espacio/inodos, permisos 0600/0700, mount y hash antes de escalar incidentes.
No convertir un faltante en DISPONIBLE copiando un archivo distinto.

`python manage.py reconciliar_adjuntos_mongodb` realiza una pasada repetible;
`--continuo --intervalo 60` reintenta Mongo con backoff hasta 60 s. No tiene watermark
irreversible: captura commits fuera de orden en pasadas siguientes y conserva notas.
Una falla del esquema 012B no altera el reconciliador 012A.

En corte abrupto puede quedar staging o archivo sin SQL. Conservarlo y diagnosticar;
no usar scripts de limpieza, `down -v`, `volume rm` ni recreación de volúmenes.
Para reiniciar servicios conservando datos, usar `docker compose restart` con la
lista explícita de servicios. Comprobar IDs/hash/descarga/notas antes y después.

## Respaldo coordinado

1. Detener nuevas mutaciones (ventana de mantenimiento): backend y workers de
   escritura. No confiar en tres snapshots tomados mientras continúan commits.
2. Respaldar PostgreSQL (`pg_dump -Fc` de la DB), Mongo (`mongodump` autenticado,
   ambas colecciones, sin incluir claves en CLI/logs) y el volumen `adjuntos_data`
   completo con archivos/staging, permisos y manifest SHA-256. Mantener además
   respaldos 012A/evidencias conforme al procedimiento existente.
3. Guardar manifest externo con fecha/base de código/versión de esquema/checksums
   y límites de consistencia. No guardar secretos o backups en Git/OneDrive público.
4. Reanudar backend/workers; registrar RPO/RTO y ubicación protegida.

## Restauración y prueba (solo destino QA nuevo)

Crear proyecto Compose/DB/volúmenes nuevos y credenciales QA propias. Nunca apuntar
restore al PostgreSQL/Mongo/volúmenes locales existentes. Restaurar juntos SQL,
Mongo y adjuntos_data del mismo punto de mantenimiento. Arrancar con la misma
versión de código/esquema, ejecutar checks y diagnóstico, comparar IDs/tamaños/hash,
descargas autorizadas y notas/revisiones CAS. Ejecutar reconciliador dos veces;
comprobar que conserva notas y que 012A sigue accesible. Reiniciar contenedores QA
y comparar de nuevo; documentar resultado y tiempos. No borrar el respaldo origen.

SQL aislado no recupera bytes ni notas. Mongo aislado no otorga identidad SQL.
El reconciliador reconstruye técnicos, no descripciones perdidas ni archivos.
Si un archivo no coincide con el hash SQL, conservar copia para investigación y
restaurar solo desde un backup verificado bajo procedimiento humano autorizado.

### Laboratorio reproducible incluido

`compose.adjuntos-qa.yaml` crea un proyecto separado sin puertos host. Usar un
nombre de proyecto **nuevo** para cada ejecución (`-p fyag012bqa_<identificador>`),
exportar `FYAG_ADJUNTOS_QA_PASSWORD` efímera y conservarla solo en sesión/gestor
seguro; no escribirla en Git ni regenerarla al reabrir un volumen ya creado.
Necesita `clamav_test` saludable en la red indicada por
`FYAG_ADJUNTOS_QA_SCANNER_NETWORK` (default `proyecto-fyag_default`). Las claves
Mongo QA son las ya configuradas, sin alterar las de desarrollo.

Con el mismo `-p` y `-f compose.adjuntos-qa.yaml` en todos los comandos:

1. `up -d --build` y `exec -T app_qa python manage.py migrate --noinput`.
2. `exec -T app_qa python manage.py shell -c "from apps.adjuntos.qa_recuperacion import ejecutar; ejecutar(preparar=True)"`.
   Crea un PDF aceptado, nota CAS revisión 1, evidencia/proyección 012A y manifest;
   guarda tar de volúmenes. Se niega si el laboratorio ya contiene usuarios/manifest.
3. No hay API/worker de escritura en este laboratorio (app duerme). Ejecutar
   `exec -T postgres_qa pg_dump -U fyag_adjuntos_qa -d fyag_adjuntos_qa -Fc -f /backup/postgres.dump`.
4. `exec -T mongo_qa mongosh --quiet /opt/fyag/database/qa_respaldo_adjuntos.js`.
   Script opt-in solo QA, password mediante archivo temporal 0600, sin eco/CLI secreto.
5. `--profile restore up -d --build postgres_restore_qa mongo_restore_qa app_restore_qa`.
6. `exec -T postgres_restore_qa pg_restore --no-owner -U fyag_adjuntos_qa -d fyag_adjuntos_qa /backup/postgres.dump`.
7. `exec -T -e FYAG_QA_RESTAURAR=1 mongo_restore_qa mongosh --quiet /opt/fyag/database/qa_respaldo_adjuntos.js` (sin drop).
8. Extraer `/backup/adjuntos.tar` y `/backup/evidencias.tar` en `/var/lib/fyag`
   dentro de `app_restore_qa` **solo si ambos destinos están vacíos**. Usar Python
   `tarfile.extractall(..., filter='data')`, preservando el origen intacto.
9. `exec -T app_restore_qa python manage.py shell -c "from apps.adjuntos.qa_recuperacion import ejecutar; ejecutar()"`.
10. `restart postgres_qa mongo_qa app_qa postgres_restore_qa mongo_restore_qa app_restore_qa`.
    Repetir verificación en ambas apps; compara ID, hash descargado, descripción,
    revisión, evidencia 012A y su hash/proyección. Cada verificación reconcilia dos veces.
11. Opcional: `exec -T app_qa python manage.py shell -c "from apps.adjuntos.qa_recuperacion import rollback_rutas; rollback_rutas()"`.
    Simula deshabilitar rutas 012B conservando tablas/colección/bytes; 012A continúa,
    y al reactivar se verifica nuevamente el manifest. No es un downgrade de tablas.

Respaldos se conservan en `<proyecto>_backup_qa`; motores/volúmenes origen y restore
permanecen para revisión. Se pueden **detener** servicios QA para liberar memoria,
sin `down -v`, sin eliminar volúmenes ni tocar los servicios locales originales.

## Rollback sin pérdida

Detener worker 012B y deshabilitar rutas nuevas regresando al código anterior
autorizado; conservar tabla, colección y volumen para retorno posterior. No usar
`migrate adjuntos zero` si existen filas o se necesita preservar historial. No borrar
colección/volumen ni retirar privilegios 012A. Mantener respaldos y registrar
uploads aceptados desde el backup. Reaplicar versión compatible y reconciliar
permite retomar servicio sin reset de notas. Rollback de código no deshace cargas.
