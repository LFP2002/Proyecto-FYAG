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

## QA pre-merge PR #44 — laboratorio independiente (17-11-2026)

Para esta revisión **no usar** los comandos históricos de «QA aislado» ni combinar
los compose anteriores. `compose.yaml` declara nombres fijos y volúmenes FYAG;
`compose.adjuntos-qa.yaml` conecta por defecto al scanner de una red externa.
Cambiar solo `--project-name` no elimina esos riesgos.

`compose.premerge-qa.yaml` es standalone: PostgreSQL 18 y Mongo 8 autenticado en
tmpfs, ClamAV 1.5.4 propio, red interna sin redes externas ni puertos host,
almacenes efímeros `/qa`, código bind de solo lectura, sin `.env` del repositorio.
No ejecuta migraciones sobre FYAG ni inicia reconciliadores ajenos. Las suites
usan `test_fyag_pr44_qa` y Mongo `fyag_documentos_test` de ese servidor exclusivo.
Ejecutar secuencialmente: las suites comparten únicamente su Mongo QA.

### Reproducción PowerShell desde la raíz

```powershell
$qaEnv = Join-Path $env:LOCALAPPDATA 'Temp\opencode\fyag-pr44-qa.env'
# Para una nueva ejecución usar también otro nombre de archivo/proyecto.
if (Test-Path $qaEnv) { throw 'No sobrescribir secretos de un laboratorio existente' }
$keys = 'QA_POSTGRES_PASSWORD','QA_MONGO_ROOT_PASSWORD','QA_MONGO_PASSWORD','QA_DJANGO_SECRET','QA_JWT_SECRET'
[IO.File]::WriteAllLines($qaEnv, @($keys | ForEach-Object { $_ + '=' + [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N') }))
$project = 'fyag-pr44-qa-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$qa = @('--env-file',$qaEnv,'-f','compose.premerge-qa.yaml','-p',$project)
docker compose @qa up -d --build --wait --wait-timeout 420
docker compose @qa ps
# Inspeccionar redes, tmpfs, mounts y ausencia de puertos, sin imprimir Config.Env.
docker compose @qa exec -T backend python manage.py check
docker compose @qa exec -T backend python manage.py makemigrations --check --dry-run
docker compose @qa exec -T backend python manage.py test apps.adjuntos apps.finanzas --noinput
docker compose @qa exec -T backend python manage.py test --noinput
```

No invocar `down -v`, prune ni borrar volúmenes. `stop` de PostgreSQL/Mongo
**pierde intencionadamente su tmpfs QA**, no datos FYAG: guardar solo evidencia
no sensible antes de detener este laboratorio. No publicar `$qaEnv`, tokens,
capturas de sesión ni logs de cuerpos documentales.

### Validación de navegador pendiente, con servicios QA reales

Las pruebas backend con motores reales no prueban integración React/navegador.
El recorrido siguiente requiere operador; no se declara aprobado por preparar
estos comandos. No ejecutar a la vez que la suite SQL/Mongo.

1. Arrancar una instancia web **del mismo laboratorio**, con puerto aleatorio
   enlazado solo a loopback. HTTP/DEBUG se limita a QA; producción sigue HTTPS.

```powershell
$ui = "$project-ui"
docker compose @qa run -d --name $ui --publish '127.0.0.1::8000' -e DJANGO_DEBUG=True -e DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5174 backend python manage.py runserver 0.0.0.0:8000 --noreload
$binding = docker port $ui 8000/tcp
$port = ($binding.Trim() -split ':')[-1]
docker exec $ui python manage.py migrate --noinput
```

2. Bootstrap de cinco cuentas sintéticas **solo si SQL QA está vacío**. Introducir
   clave temporal en prompt oculto; no guardarla en código, CLI ni informe.

```powershell
docker exec -it $ui python manage.py shell -c "from getpass import getpass; from django.db import connection; from apps.usuarios.models import Usuario; assert connection.settings_dict['NAME']=='fyag_pr44_qa' and connection.settings_dict['HOST']=='postgres'; assert not Usuario.objects.exists(), 'No sobrescribir cuentas'; password=getpass('Clave efimera QA: '); assert len(password)>=12; [Usuario.objects.create_user(username='qa-'+role.lower(), email='qa-'+role.lower()+'@example.test', password=password, rol=role, is_active=True) for role in Usuario.Rol.values]"
```

3. Crear config Vite temporal externo; no cambiar el proxy habitual hacia un
   backend real ni escribir secretos en variables VITE. Conservar Host/Origin.

```powershell
$front = (Resolve-Path frontend).Path.Replace('\','/')
$viteQA = Join-Path $env:LOCALAPPDATA 'Temp\opencode\fyag-pr44-vite.config.mjs'
@"
import { createRequire } from 'node:module';
const require = createRequire('$front/package.json');
const react = require('@vitejs/plugin-react');
export default { root: '$front', plugins: [react()], server: { host: '127.0.0.1', port: 5174, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:$port', changeOrigin: false } } } };
"@ | Set-Content -Encoding utf8 $viteQA
# En consola separada, dejarlo escuchando solo en loopback:
Push-Location frontend
npm run dev -- --config $viteQA
Pop-Location
```

4. Abrir `http://127.0.0.1:5174` en perfil de navegador QA sin sesión FYAG. Usar
   cuentas `qa-{rol_en_minusculas}@example.test`. Crear datos exclusivamente
   sintéticos por UI y registrar IDs que devuelva Django:

| Secuencia manual | Comprobación exigida |
| --- | --- |
| TI/G/AF/S/T: login, logout, sesión/refresh y navegación | Sin token persistente; menús/401/403/404 coherentes; no acceso heredado |
| AF crea cliente/presupuesto e ítems; G aprueba y crea categoría; AF registra decisión cliente; S crea Obra/participantes | Transiciones y valores del servidor; sin privilegios saltados |
| S inicia Obra; T inicia/cierra turno con foto; S revisa; S registra gastos, declara rubros/valida costos y finaliza | Evidencias, decimales, separación Gastos/Costos y bloqueos reales |
| AF elige Obra elegible, registra documento/pago, anula pago y revierte documento con motivos/referencias | Un POST por intención, relecturas y saldo del backend; no pagos activos al revertir |
| AF sube respaldo antes de revertir; G lee; AF edita nota CAS; luego revierte | Histórico conserva listado/detalle/descarga/GET notas; PATCH directo AF 409 y revisión intacta; G PATCH 403; carga nueva 409 |
| S/T suben informes según estado/membresía; S/G editan 012A | Sin ampliación RBAC; dos pestañas misma revisión => un ganador y 409 |
| Ejecutar reconciliadores en instancia UI después de subir fotos/adjuntos | `docker exec $ui python manage.py reconciliar_documentos_mongodb` y `... reconciliar_adjuntos_mongodb`; notas no desaparecen |
| Scanner QA detenido durante subida y reiniciado | `docker compose @qa stop clamav`, POST devuelve 503 sin fila; descarga previa funciona; `docker compose @qa start clamav`, esperar healthy antes de repetir explícitamente |
| Auditoría por rol, módulos/filtros/cursor; Dashboard G; Alertas G/S | Fuentes autorizadas, datos actuales, no mostrar cifras anteriores ante error; ejecutar `docker exec $ui python manage.py reconciliar_alertas --once` |
| Reportes G/AF, CSV/XLSX/PDF | Catálogo restringido; archivos abren, MIME/nombre correctos y totales coinciden con JSON; AF sin Obras/Rentabilidad |
| 375, 768 y 1280 px, teclado y zoom | Sin desbordes de página; tabla desplazable, foco/etiquetas/feedback legibles; registrar capturas solo sintéticas |

Para split-origin real se requiere además un origen **HTTPS QA** y CORS/CSRF
explícitos del servidor, cookies seguras y `VITE_API_BASE_URL` correspondiente.
No relajar trusted origins ni usar cuentas productivas para simularlo. Las
regresiones automáticas de paginación verifican esa configuración de Vite con
respuestas sintéticas: no certifican despliegue HTTPS/CORS/cookies real.

Al finalizar, detener únicamente `$ui` y `docker compose @qa stop`; no detener
`fyag_backend`, `fyag_postgres`, `fyag_mongodb` ni sus workers/scanner originales.

### Ejecución real de navegador de cierre (17-11-2026)

Se utilizó Edge headless instalado, CDP nativo Node (sin dependencias E2E), perfil
externo exclusivo, Vite 127.0.0.1:5174 y backend exclusivo QA. Docker no asignó
puerto al contenedor en la red interna; un relay TCP propio, sin credenciales,
conectó esa red a `fyag-pr44-browser-access`, publicando solo 127.0.0.1:60198.
PostgreSQL/Mongo/scanner nunca publicaron puertos ni usaron redes/volúmenes FYAG.
No se usó `--no-sandbox` ni se desactivó la verificación TLS ni se relajó CSRF.

Evidencia externa (datos sintéticos, sin valores de tokens/cookies/contraseñas):
`C:\Users\jugue\AppData\Local\Temp\opencode\fyag-pr44-browser-final`.
`results.json` conserva cada caso y requests (método/ruta/status); `extra.json`
amplía verificaciones; PNG por rol/tamaño; `scanner-probe.json`,
`mongo-probe.json`, `export-inspection.json` y `downloads/browser-fetch.*`.
Los scripts auxiliares y configuración también están fuera del repositorio;
el archivo secreto efímero está separado y **no** es evidencia publicable.

| Caso real | Resultado / evidencia y límite |
| --- | --- |
| Login, recarga y logout G/AF/S/T/TI por formulario | OK; login 200, refresh 200 y `/me` 200; logout y recarga anónima. `results.json` |
| Sesión/JWT/CSRF | localStorage/sessionStorage vacíos en cinco roles; access solo en memoria. Inspección ampliada: `fyag_refresh` HttpOnly, Strict, `/api/auth/`; csrf HttpOnly, Strict. Secure=false en este HTTP QA, no aprobación productiva. POST logout sin CSRF real 403 (`extra.json`) |
| Navegación por botones | AF: seis módulos, G: ocho, S: tres. TI Usuarios y roles/Auditoría confirmado en `extra.json`: primer runner buscaba incorrectamente «Usuarios». T: login/interfaz propia, recorrido Mis turnos pendiente |
| Paginación | G/AF cartera y documentos página 2 con GET reales; no se atribuye cobertura a todas las paginaciones de módulos |
| Operación QA por UI | AF registra pago 10.00 en documento #1, POST 201 y relecturas. Alta comercial/cierre completo no se realizaron por UI; fixtures fueron preparación con helpers de pruebas |
| Adjuntos históricos/PDF | G/AF descarga privada 200 PDF 431 bytes y GET notas; PATCH G403/AF409. Son fetch auxiliares desde navegador, no clic de descarga |
| CAS vigente | Dos fetch autenticados con misma revisión => 200/409, revisión final 1 (`results.json`). Edición/doble pestaña por controles UI pendiente |
| RBAC | Fetch reales: documentos/reportes G/AF200, S/T/TI403; Usuarios TI200/resto403; informe G/S/T200, AF/TI403. Matriz registrada, no es una auditoría exhaustiva de endpoints |
| Imagen privada | S/T fetch PNG privado 200, 81 bytes; no se afirma descarga por botón |
| Exportaciones por botones | G Obras/AF Cobranzas: CSV/XLSX/PDF responden 200. Directorio de descargas por botón vacío: **PARCIAL**, el PASS instrumental solo certificó solicitudes; no acredita entrega/archivo abierto |
| Exportaciones por fetch auxiliar | Cobranzas CSV 3897 B, XLSX 7993 B, PDF 25420 B guardados fuera del repo. Parseo real CSV/XLSX/pypdf; CSV 27 filas, bruto 58869.45, abonado 10.00, saldo 58859.45; PDF 2 páginas con texto. Revisión visual en Excel/visor y cotejo completo JSON aún pendiente |
| Servicios caídos | Scanner QA detenido realmente: nueva carga fetch503 `scanner_no_disponible`, listado200/count1 y descarga200, sin fila extra. Mongo QA detenido realmente: notas503, listado200/count1 y descarga200. Ambos arrancados luego; no se afirma restauración de BSON tras reinicio de tmpfs |
| Fallo de red UI | CDP offline real + Actualizar: error controlado, sin KPIs/filas previas de cartera; el listado administrativo independiente conserva su snapshot anterior. Captura `offline-cobranzas.png`; recuperar conexión produce GET200 (`extra.json`) |
| Consola | Sin excepciones JS instrumentadas. Sí hay mensajes de red esperados 401 al restaurar anónimo y 403/409/503 de pruebas negativas, y offline; no se declara consola literalmente vacía |
| 375/768/1280 | Capturas por rol. Auditoría G/AF/S y pantalla T sin desborde en casos capturados; no todos los módulos. **FALLO TI Usuarios**: scrollWidth929 a375 y933 a768; a1280 no desborda. Confirmación `TI-users-confirm-*.png` |

El runner inicial registra 55 comprobaciones, 52 PASS/3 FAIL; **no es aprobación
global**: la navegación TI se confirmó después, sus dos desbordes son reales,
exportaciones son parciales y T no recorrió turnos. Conservar resultados crudos,
no convertir esos límites en aprobaciones. Los clics se ejecutaron sobre controles
DOM y formularios reales, no se certifica interacción física completa de ratón,
teclado, lector de pantalla o zoom.

Las detenciones de contenedor tmpfs son destructivas solo para datos QA efímeros;
no equivalen a recuperación durable. La prueba anterior de recuperación con
volúmenes separados sigue siendo histórica, no reejecutada en este laboratorio.

#### Pendientes manuales exactos antes de aprobar

1. Corregir Usuarios TI: entrar con TI, abrir **Usuarios y roles**, medir
   `document.documentElement.scrollWidth <= innerWidth` a375/a768; tabla debe
   desplazar dentro de su región, no la página. Repetir a1280, teclado y zoom200%.
2. Con nuevo laboratorio standalone vacío y cuentas sintéticas, ejecutar en orden
   las filas de la matriz manual anterior (alta AF, aprobación G/cliente AF, Obra
   y participantes S, turno/foto T, revisión/gastos/cierre S, factura/pago/anulación/
   reversión AF). Guardar IDs reales y requests; no atribuir fixtures a UI.
3. AF: abrir documento vigente → **Consultar respaldos documentales**, subir PDF
   real por file picker, editar nota; abrir segunda pestaña antes de guardar:
   guardar en una, luego en otra => conflicto409 y reconsulta obligatoria.
   Revertir tras anular pagos activos; confirmar lectura histórica y ausencia de
   controles de escritura, descarga PDF/PNG por botón, y PATCH directo409.
4. G/AF: **Reportes**, seleccionar cada tipo permitido, fijar Desde/Hasta válidos,
   navegar Siguiente/Anterior y pulsar **Descargar CSV/XLSX/PDF**. Confirmar archivo
   realmente recibido, abrirlo en Excel/visor, cotejar filas/totales contra JSON
   del mismo filtro. AF no debe ofrecer Obras/Rentabilidad. Investigar por qué
   Edge headless no materializó las descargas por botón; no inferir éxito del200.
5. Completar paginación de Clientes/Presupuestos/Obras/Alertas/Auditoría/historiales,
   filtros, Mis turnos T, adjuntos e informes por UI a los tres anchos. Capturar
   formularios/tablas/errores y foco; no basta una pantalla por rol.
6. Proveer dos orígenes HTTPS QA autorizados, configurar CORS/CSRF y
   `VITE_API_BASE_URL` específicos sin desactivar protecciones: repetir sesión,
   refresh/logout, Secure/HttpOnly/SameSite, orígenes negativos y paginación
   absoluta entre orígenes. HTTP loopback no satisface este requisito.
7. Si se exige recuperación de notas, usar laboratorio durable dedicado, respaldar
   BSON y detener el proceso/conectividad (no destruir tmpfs), recuperar y comparar
   revisión/BSON/hash antes/después. No reutilizar ni borrar volúmenes FYAG.

Cierre del laboratorio: Vite y Edge propios detenidos tras verificar config/perfil;
contenedores `fyag-pr44-final-browser`, `fyag-pr44-browser-relay` y proyecto
`fyag-pr44-final-20261117` detenidos. No se eliminaron contenedores/redes/volúmenes
ni se detuvieron servicios FYAG ajenos. Datos tmpfs no son respaldo recuperable;
la evidencia y el respaldo Git externos se conservan. `evidence-manifest.json`
registra SHA-256 de 37 archivos externos (excluye perfil y secreto).

## Seguimiento funcional PR #44 y reanudación tras interrupción — 17-11-2026

Esta sección **actualiza el dictamen de los apartados históricos anteriores**,
sin eliminarlos. Los fallos responsive y la falta de entrega de descargas ya no
son pendientes actuales. El incremento sigue **NO APTO** por confianza TLS no
acreditada, decisión de riesgo pendiente y cobertura integral UI todavía parcial.

### Conservación, laboratorio y fases

HEAD continúa en `efa33327eca2285496d871f482660867926ea2e9`, rama exclusiva del
PR, main intacto y staging vacío. Respaldo inicial íntegro (19 archivos y bundle);
respaldo del seguimiento `fyag-pr44-followup-backup-20261117-184824` verificado;
nuevo respaldo de reanudación
`C:\Users\jugue\AppData\Local\Temp\opencode\fyag-pr44-resume-backup-20261117-205533`
con 19 archivos entonces presentes y hashes comprobados. README/documentación
posteriores son adiciones propias. Ningún commit, push, merge, reset o rebase.

| Fase solicitada | Estado real |
| --- | --- |
| Protección | Completada, respaldos conservados y verificados |
| Usuarios TI responsive | Corregido y regresión real repetida después de reanudar |
| Descargas reales | Cinco tipos guardados desde botones; parseo real y negativos instrumentados |
| HTTPS/CORS/cookies | Funcional HTTPS same-site comprobado con excepción SPKI; confianza CA pendiente |
| Recorrido por rol | Acciones principales ampliadas; faltan los casos integrales detallados al final |
| Concurrencia y picomatch | Garantía revisada sin arquitectura nueva; advisory sigue abierto sin aceptación |
| Validación final | Frontend completo repetido; checks Django actuales; suite874 conservada sobre idéntico backend |

Al reanudar, PostgreSQL/Mongo/ClamAV y ambos relays del proyecto exclusivo
`fyag-pr44-followup` estaban running (motores healthy). El contenedor backend
ejecutaba su comando de espera, **no** servidores web. PostgreSQL tenía0tablas,
Mongo0adjuntos y `/qa` estaba vacío: el reinicio había eliminado los tmpfs.
Esto es comportamiento del laboratorio efímero, no pérdida de datos FYAG.
La evidencia fuera de Docker seguía disponible y no se sobrescribió.

Se migró solo `fyag_pr44_qa` en host `postgres` de esa red y se reconstruyeron
fixtures **mínimos**, con guard de base vacía/reanudación conocida: cinco actores
de negocio, TI y26cuentas inactivas sin clave utilizable para paginación, una Obra
con costos/turno preparados mediante helpers y un informe PNG. No se repitieron
facturas/pagos/anulaciones/reversiones ni altas/cambios de cuentas ya confirmados
por UI en la ejecución previa. Los nuevos IDs son otro ciclo del laboratorio,
no continuidad de sus antiguos IDs. Estado final nuevo:32usuarios, Obra#1
FINALIZADA, responsable#5, un adjunto y Mongo revisión0; **0documentos,0pagos y
0cierres sin cobro** (`resume/qa-state.txt`). El snapshot de costos preparado por
helpers **no** se atribuye a operaciones UI; el relevo, revalidación de su nueva
versión y finalización posteriores sí se hicieron por interfaz.

HTTP QA se repuso en8000, TLS WSGI QA en8001. Ambos relays se comprobaron con200;
puertos reasignados solo loopback55243/55244; sin puertos host para motores,
sin redes ni volúmenes principales. TLS al relay negocia TLSv1.3 pero la cadena
es autofirmada, no confiable. Vite de reanudación fue5176 con proxy correcto,
no el antiguo destino56358. No reutilizar puertos efímeros anotados tras reiniciar:
resolver siempre `docker port <relay> 8000/tcp`. La configuración TLS QA externa
no altera `settings.py` ni acepta headers de proxy como prueba de HTTPS.

### Evidencia y matriz obligatoria

Raíz externa: `%LOCALAPPDATA%\Temp\opencode\fyag-pr44-followup`.
`functional-results.json` conserva también intentos fallidos del runner;
`functional-retest.json` y `operational2.json` registran sus revalidaciones.
La nueva evidencia está en `resume/`, separada de los casos ya confirmados.
No publicar `qa.env`, `tls-key.pem`, perfiles ni valores de tokens/cookies.

**OK UI** significa controles React/formularios y requests backend reales.
**INYECCIÓN** significa fallo controlado CDP, no fallo real del servicio.
**PARCIAL** no equivale a aprobado. Los nombres de evidencia siguientes son
relativos a esa raíz externa.

| Módulo | Rol | Acción | Esperado | Real | Evidencia | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| Sesión | G/S/AF/T/TI | Login, recarga y logout | JWT efímero, refresh y cierre reales | Formularios y refresh200; logout y restauración anónima | `functional-*.json`, evidencia anterior `fyag-pr44-browser-final/results.json` | OK UI |
| Usuarios | TI | Listado375/768/1280 | Sin scroll del documento | Antes929/360 y933/753; después360/360,753/753,1265/1265 (scroll/client) | `responsive-before.json`, `responsive-after.json`, `resume/responsive-regression/` | OK UI |
| Usuarios | TI | Teclado, texto largo, formulario | Scroll interno con foco, controles visibles | ArrowRight desplaza región enfocada; texto sintético/formulario no desbordan | `frontend/qa/usuarios-responsive.mjs`, JSON/PNG de regresión | OK navegador |
| Usuarios | TI | Crear inactiva | POST201 único y estado Inactiva | Confirmado tras corregir alias inválido de fixture | `functional-retest.json` | OK UI |
| Usuarios | TI | Activar/desactivar, rol, credencial ajena |200 y auditoría sin clave expuesta | Confirmados; rol Supervisor y posterior baja | `functional-retest.json` | OK UI |
| Usuarios | TI | Filtros, auto-baja/rol propio | Filtrado remoto y botones protegidos | Rol/activo consultados; autooperaciones deshabilitadas | `functional-retest.json` | OK UI |
| Usuarios | TI | Paginación y restauración | Página2 y filtros resetean a1 | GET página2 200, filtros técnicos inactivos, recarga autenticada | `resume/remaining-results.json` | OK UI |
| Dashboard/Presupuestos/Obras | G | Abrir módulos | GET200 sin escrituras heredadas | Navegación real y endpoints Dashboard200 | `functional-results.json` | OK lectura UI |
| Alertas/Auditoría | G/S/TI | Abrir vistas autorizadas | Fuentes según rol | Vistas y lecturas reales; TI fuente Usuarios | `functional-results.json`, `functional-retest.json` | OK lectura UI |
| Obras/participantes | S | Consultar principal/historial | Backend autoritativo, sin baja del principal | Consultas reales y marca de responsable | `functional-results.json` | OK UI |
| Obras/participantes | S | Relevar responsable | POST200, membresías actualizadas | Relevo#4→#5 confirmado una vez | `resume/remaining-results.json` | OK UI |
| Mis Obras | T | Obra/turno, apertura y cierre con foto |201/200, pendiente revisión | Turno iniciado/cerrado por UI con archivo real | `functional-results.json` | OK UI |
| Evidencias | T | Descargar foto de turno | Archivo privado guardado | Browser completed `evidencia-*.png` | `functional-results.json`, `download-parsing.json` | OK UI |
| Informes | T/S | Leer/editar anotaciones | PATCH200, pertenencia vigente | T actualiza; S lee valor del textarea tras reconciliar | `functional-results.json`, `operational2.json` | OK UI |
| Mis Obras | T | Actualizar después del relevo |404 sin ficha retenida | GET404 y «El recurso ya no está disponible», sin datos previos | `resume/remaining-results.json`, `tecnico-desasignado.png` | OK UI; véase nota del runner |
| Turnos | S | Revisar turno y tarifa |200 y Validado | Tarifa8000.00 enviada desde formulario, estado Validado | `functional-results.json` | OK UI |
| Gastos/Costos | S | Gasto, declaración, validación |201/PATCH200/200 y relecturas | Material2.000×100.00, rubros y validación confirmados | `operational2.json` | OK UI |
| Costos/Obra | S | Relevo y finalización | Invalidar versión; impedir cierre sin validar | Versión5 bloqueó cierre; validación nueva y finalizar200 | `resume/finalize-results.json` | OK UI |
| Finanzas | G | Leer documentos/adjuntos | Solo lectura y descarga | No ofrece registro; PDF reporte y adjunto descargados | `functional-results.json` | OK UI |
| Finanzas | AF | Elegible y documento externo |201 único y relecturas | Folio91001 creado por formulario | `functional-retest.json` | OK UI, no repetido al reanudar |
| Pagos | AF | Registrar/anular/revertir |201/200/200 y saldo/estado reconsultados | Confirmados, documento REVERTIDO y aviso de histórico | `functional-retest.json` | OK UI, no repetido |
| Sin cobro | AF | Cierre administrativo |201 y SIN_COBRO | Confirmado por formulario y relecturas | `functional-results.json` | OK UI, no repetido |
| Adjuntos | AF | Subir PDF y editar nota |201 y PATCH200 tras proyección eventual | Carga201; notas inicialmente409 pendientes; tras reconciliar PATCH200 | `functional-results.json`, `operational2.json` | OK UI |
| Adjuntos/CAS | AF | Dos pestañas, misma revisión | Un200/un409, no sobreescribir | Dos controles React reales; segundo409 y bloqueo | `operational2.json` | OK UI |
| Cobranzas/Documentos | G/AF | Página2 | URL interna reconstruida, GET200 | Confirmado; también absoluta https en split-origin | Evidencia previa y `https-results.json` | OK UI |
| Reportes | AF | CSV/XLSX/PDF por botones | Headers correctos, archivo guardado y parseable | CSV3898B, XLSX8013B, PDF25408B; completed y parseo real | `downloads-results.json`, `download-parsing.json` | OK UI |
| Respaldos | AF | PDF/PNG por botones | Privados, MIME/nombre y bytes correctos | documento.pdf431B, foto.png81B; completed y parseo real | `downloads-results.json`, `download-parsing.json` | OK UI |
| Descargas | AF |401/403/red/redirect | Error visible, sin archivo ni fuga URL |401 renueva una vez y termina sesión; demás errores sin archivo, redirect externo no seguido | `download-negative.json` | OK INYECCIÓN CDP |
| Scanner caído | S | Subir PNG por formulario |503 fail closed, sin fila extra |503; adjuntos permanecen1 y descarga por botón200/completed | `resume/service-scanner.json`, `qa-state.txt` | OK fallo real UI |
| Mongo inaccesible | S | Anotaciones y descarga | Notas503, SQL/archivo200 | Mongo pausado, notas503 y descarga PNG200/completed; unpause notas200/revisión0 | `resume/service-mongo.json`, `service-recovered.json` | OK fallo real UI |
| HTTPS same-site | AF | Login/refresh/logout/CSRF | Cookies seguras y autorización de origen | Login/refresh200, CSRF omitido403, Secure/HttpOnly/Strict | `https-results.json` | OK funcional, TLS PARCIAL |
| CORS | AF | Credenciales, preflight y headers | Allow-Origin explícito, no wildcard | OPTIONS200; credentials true; Content-Disposition expuesto y CSV descargado | `https-results.json` | OK funcional, TLS PARCIAL |
| Origen ajeno | Sin rol | Fetch desde otro sitio | CORS bloqueado | Navegador bloqueó http127→httpslocalhost no autorizado | `https-results.json` | OK negativo CORS; no atribuir solo a Strict |
| Confianza TLS | Todos | Navegar sin excepción | Cadena confiable y nombre válido | ERR_CERT_AUTHORITY_INVALID; excepción SPKI solo QA | `tls-without-exception.json`, `https-results.json` | BLOQUEADO |
| RBAC completo | Todos | Matriz de todos los endpoints/errores por UI | Backend niega de forma efectiva | Matriz previa fetch real y suites; no todos los negativos por controles UI | Evidencia previa + suites | PARCIAL |
| Integral comercial/operativo | G/AF/S | Alta cliente→presupuesto→aprobaciones→alta Obra, catálogo y todas las variantes | Recorrido entero por UI | Lecturas y fixtures no acreditan esas escrituras ni todas sus paginaciones | Matriz manual anterior | PENDIENTE |

**Interpretación de intentos fallidos conservados:** alias TI con espacios obtuvo
400 correcto; el retest usó un alias válido. El runner buscaba labels incluyendo
opciones de select y leyó `innerText` en vez del valor del textarea: se corrigió
la instrumentación, no React. Las notas de un adjunto recién subido devolvieron
409 hasta ejecutar el reconciliador QA, conforme a proyección eventual. Una prueba
dos pestañas esperó RAF en pestaña de fondo; se añadió bringToFront y pasó.
`resume/remaining-results.json` marca FAIL en el grupo desasignación/finalización:
su GET404 y ficha retirada **sí** están registrados; el fallo posterior fue intentar
un control de Supervisor todavía deshabilitado. Finalización se comprobó por
separado, sin repetir el relevo, incluyendo el bloqueo correcto por versión de
costos invalidada. No borrar esos intentos ni convertir toda la agrupación en PASS.

No se detectaron excepciones JavaScript de aplicación instrumentadas en los
recorridos confirmados. Los errores de red esperados400/401/403/404/409/503 y de
inyección se conservan. Esto no afirma ausencia de errores en flujos no recorridos.

### Validaciones finales y bloqueos

- `npm ci`:71instalados/72auditados; lock sin cambios. Se resolvió un primer
  EPERM de esbuild deteniendo solo Vite propio; reinstalación posterior correcta,
  sin elevar privilegios ni cambiar la política que bloqueó el postinstall.
- Última repetición `npm test`: **204/204,0fallos,3602.6882ms**.
- `npm run build`: **OK,1.90s,99módulos**, JS `index-CDZdNGTo.js`370.95kB,
  CSS `index-DD1aDEOP.css`254.58kB. Inventario adicional92módulos runtime,
  cero módulos Vite/picomatch/fdir/tinyglobby; mismo asset.
- Audit completo **4high/salida1**; runtime **0/salida0**. npm latest4.0.7,
  advisory oficial `first_patched_version=null`, actualizado17-11-2026.
- Django check y dry-run migraciones actuales: sin problemas/sin cambios.
  **874OK/244.157s** pertenece a la suite previa completa: SHA-256 de los tres
  archivos propios backend runtime/tests idénticos al respaldo y ningún otro
  runtime backend modificado. No se volvió a ejecutar la suite destructiva sobre
  fixtures del navegador; no hubo cambios backend en este seguimiento.

**Pendientes bloqueantes:** (1) responsable debe decidir aceptación temporal de
picomatch o esperar parche; propuesta de condiciones/plazo en SPEC-014, sin firma
ni aceptación implícita; (2) repetir HTTPS con certificado/cadena QA confiable,
sin excepción; (3) completar la fila integral comercial/operativa y todas las
variantes/paginaciones/anchos requeridos que siguen parciales. No quedan el fallo
responsive TI ni la entrega básica de cinco descargas como defectos abiertos.
El contrato de concurrencia mantiene la ventana SQL/Mongo documentada, no se
promete serialización entre motores ni se amplía arquitectura para ocultarla.

Para completar (3), seguir las filas manuales anteriores desde AF cliente y
presupuesto, aprobación G, decisión cliente AF, alta Obra/participantes S y
catálogo, usando fixtures nuevos con IDs registrados. No repetir folio91001,
pago/anulación/reversión ni cuentas ya confirmados como si fueran pendientes;
tras pérdida de tmpfs son evidencia histórica, no órdenes de reconstrucción.
Repetir filtros/páginas y teclado/zoom de cada módulo a375/768/1280 y anotar
explícitamente los estados que no tengan datos suficientes para otra página.

Cierre de esta reanudación: **se conservan activos los contenedores QA** que el
usuario había reiniciado, para no volver a destruir sus tmpfs. PostgreSQL, Mongo
y ClamAV healthy; backend HTTP/TLS y relays QA comprobados. Edge del perfil QA,
Vite propios y el proxy Node antiguo (puertos obsoletos) quedaron detenidos.
No queda una UI Vite escuchando: para inspeccionar de nuevo, desde `frontend/`
iniciar `npm run dev -- --config "$env:LOCALAPPDATA\Temp\opencode\fyag-pr44-followup\resume\vite.config.mjs"`
y abrir `http://127.0.0.1:5176` con cuentas exclusivamente QA. Antes comprobar el
puerto actual del relay y no reutilizar secretos para ningún otro entorno.
La confianza TLS continúa pendiente; no reusar la excepción SPKI en un navegador
habitual. Último fetch origin: HEAD/remoto0/0; main y staging intactos.
La revisión final encontró **16modificados +4nuevos**, cero secretos QA en esos
archivos y contrato OpenAPI válido. `resume/final-review.json` contiene rutas y
hashes backend; el manifiesto SHA-256 externo excluye secretos/perfil/clave TLS.

## TLS estricto: inspección y autorización pendiente — cierre PR #44

Inspección nueva sin excepciones, Edge **157.0.4341.60**, perfil nuevo exclusivo
`fyag-pr44-closeout-20261117-212424/profile`. No se usaron flags de excepción,
`ignoreHTTPSErrors`, callbacks de aceptación TLS ni cambios en almacenes.

- Orígenes previstos: frontend `https://localhost:5443`, API
  `https://localhost:6443`: orígenes distintos y **mismo sitio schemeful HTTPS**.
  Los proxies5443/6443 estaban detenidos; la API TLS se inspeccionó directamente
  por el relay loopback55244. El recorrido UI nuevo usó HTTP127.0.0.1:5178,
  sin presentarlo como HTTPS aprobado. No se atribuye una cadena a un listener
  frontend inexistente; su configuración previa usaba el mismo certificado.
- Cadena efectivamente presentada por la API: **un certificado autofirmado**,
  subject/issuer `CN=localhost`, SAN `DNS:localhost, IP:127.0.0.1`, vigencia
  `2026-11-17T21:56:27Z` a `2026-11-19T21:56:27Z`.
- SHA-256 público:
  `E95733AC393428AB63ADD933471DF9BD219793E3E22FC17FD2EBCDD7DB51B9E3`.
  El certificado antiguo tiene `CA:TRUE`; **no importarlo como raíz** para simular
  una PKI correcta. Hace falta separar CA y certificado servidor con SAN válidos.
- OpenSSL `s_client -verify_return_error -showcerts` terminó1 con error18
  self-signed certificate. Edge limpio devuelve `ERR_CERT_AUTHORITY_INVALID`.
  No se ejecutaron login/refresh HTTPS como prueba aprobada sobre esta conexión.
- Edge moderno usa verificador y Microsoft Root Store incorporados para confianza
  pública y consulta raíces instaladas localmente en Windows. Se consultaron
  `CurrentUser\Root` y `LocalMachine\Root` en modo lectura: sin raíz coincidente
  localhost/FYAG/mkcert. La comprobación negativa real de Edge prevalece sobre una
  mera búsqueda de nombres. No se alteraron políticas.
  Fuente: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-security-cert-verification

Evidencia externa: `tls-leaf.json`, `tls-presented-chain.json`,
`tls-trust-readonly.json`, `edge-process.json` y `edge-tls-strict.json` en el
directorio `fyag-pr44-closeout-20261117-212424`. **Esta parte se detiene** hasta
intervención autorizada; el recorrido HTTP QA independiente puede continuar.

### Procedimiento del operador — NO ejecutado por el agente

**Decisión posterior del responsable (17-11-2026): NO se autoriza instalar una CA
raíz, modificar almacenes de confianza ni desactivar verificaciones TLS.** El
procedimiento propuesto a continuación se conserva como antecedente, no como
autorización vigente para ejecutarlo. TLS confiable queda pendiente de despliegue.

Alternativa preferida si existe: solicitar al administrador un certificado QA
emitido por una CA ya confiable para Edge, con SAN localhost/127.0.0.1/::1 y su
cadena. No incorporar certificados, claves o CA a Git, patch o ZIP del PR.

Para CA de desarrollo local: el responsable debe autorizar expresamente el uso
de mkcert y **la importación en CurrentUser\Root**. La instalación de la herramienta
también corresponde al operador por un canal aprobado; el agente no la instala.
No ejecutar `mkcert -install` indiscriminadamente (puede gestionar más almacenes).
Con mkcert ya disponible, el operador puede preparar, revisar y autorizar:

```powershell
# Preparación local; NO implica aprobación para modificar el almacén.
$qaTls = Join-Path $env:LOCALAPPDATA 'Temp\opencode\fyag-pr44-trusted-tls'
New-Item -ItemType Directory -Path $qaTls -ErrorAction Stop
mkcert -cert-file "$qaTls\server-cert.pem" -key-file "$qaTls\server-key.pem" localhost 127.0.0.1 ::1
$caRoot = (mkcert -CAROOT).Trim()
$rootPublic = Join-Path $caRoot 'rootCA.pem'
certutil -dump $rootPublic
certutil -hashfile $rootPublic SHA256
certutil -dump "$qaTls\server-cert.pem"

# PARAR: revisar CA, SAN, vigencia, cadena y huella; registrar autorización.
# SOLO DESPUÉS de autorización expresa del usuario/operador:
Import-Certificate -FilePath $rootPublic -CertStoreLocation Cert:\CurrentUser\Root
```

Nunca distribuir `rootCA-key.pem` ni `server-key.pem`. No usar la CA local como
evidencia de confianza pública de producción. Registrar la huella de la raíz
importada y su alcance. Si la política del equipo impide importarla, solicitar
intervención del administrador; no elevar privilegios ni cambiar políticas.

Después de esa intervención: apuntar **solo** los servidores TLS QA externos a
server-cert.pem/server-key.pem y cadena correspondiente, reiniciar esos procesos
propios (sin detener motores tmpfs) y resolver puertos de relays otra vez.
Mantener CORS permitido exactamente para `https://localhost:5443`, CSRF trusted
origin explícito, DEBUG=False y cookies Strict/Secure/HttpOnly. Reiniciar Edge
con perfil QA limpio sin excepciones de certificado ni desactivaciones de TLS.
Repetir login, recarga/refresh, CSRF válido/inválido, OPTIONS/CORS con credenciales,
Authorization, headers expuestos, paginación absoluta https y logout/revocación.
Registrar ausencia de Page.navigate.errorText y errores de certificado en CDP,
cadena/SAN/issuer/protocolo de `Network.responseReceived.securityDetails` y
descargas reales sin tokens en URL. Un200 obtenido ignorando TLS no es evidencia.

Al terminar, retirar la raíz **solo con aprobación y huella exacta registrada**:
inspeccionar primero `Cert:\CurrentUser\Root\<HUELLA_APROBADA>` y, únicamente si
corresponde a esta CA QA, el operador puede ejecutar
`Remove-Item 'Cert:\CurrentUser\Root\<HUELLA_APROBADA>'`. No borrar otras raíces.

## Cierre dirigido del recorrido UI pendiente — 17-11-2026

Actualiza la fila integral pendiente de la matriz anterior. Se completó un
recorrido nuevo **enteramente por controles React**, sin atribuir fixtures a
escrituras UI. Evidencia externa: `fyag-pr44-closeout-20261117-212424`.
Marcador estable `QA44-CIERRE-212424`; journal con IDs y pasos RUNNING/PASS que
impide reintentar automáticamente una escritura incierta o confirmada.

Al empezar seguían disponibles los32usuarios y la Obra#1 finalizada de la última
reanudación, con **0documentos/0pagos**. No se reconstruyeron ni repitieron las
operaciones financieras históricas. Por continuidad del recorrido nuevo se
registraron **exactamente una factura y un pago nuevos**: folio441117212424,
documento#1/Obra#2, pago#1 por5.00. Los IDs se reutilizan entre ciclos efímeros:
este marcador/folio no es el antiguo91001. El journal y las cantidades de POST
permiten diferenciarlos y verificar no duplicación.

| Tramo / rol | Esperado | Real y evidencia | Estado |
| --- | --- | --- | --- |
| Cliente AF | Alta201 sin datos reales | Cliente#2 por formulario, identificación SIN_IDENTIFICACION | OK UI |
| Presupuesto AF | Borrador e ítem, enviar a Gerencia | PRE-000002, neto10000.00, ítem1.000×10000.00, unidad servicio; POST y relecturas | OK UI |
| Aprobaciones G/AF | Decisión Gerencia y cliente sin saltos | G aprueba; AF envía al cliente y registra aprobación | OK UI |
| Catálogo G | Categoría real para alta | Categoría#9 creada por UI; renombre/desactivar/activar y su historial también confirmados | OK UI |
| Obra S | Alta desde presupuesto aprobado e iniciar | OB-000002 creada por UI, principal#4, inicio200 | OK UI |
| Participantes S | Alta de miembro distinto del principal | Técnico#5 asignado por UI, POST201 y listado real | OK UI |
| Turno/foto T | Abrir/cerrar en la misma Obra | Turno#2 abierto201, cerrado200 con PNG real | OK UI |
| Revisión S | Tarifa string y estado validado |8000.00, revisión200 del turno#2 | OK UI |
| Gastos/control S | Registro decimal y declaración/validación | Material2.000×100.00; otros NO_APLICA justificado; control y validar200 | OK UI |
| Finalización S | Solo después de validación vigente | Obra#2 FINALIZADA mediante confirmación React y POST200 | OK UI |
| Documento AF | Elegibilidad derivada de la misma Obra | Folio441117212424, neto10000.00/impuesto1900.00/total11900.00, POST201 único | OK UI |
| Pago AF | Intención única y saldo reconsultado | Pago5.00, POST201 único y relecturas | OK UI |
| Cobranza/reporte AF | Mismos filtros/entidad/importes | Cliente#2: documentado11900.00, abonado5.00, saldo11895.00 en UI y CSV | OK UI |
| Archivo de continuidad | Recibido desde botón y totales coherentes | CSV1003B, Browser completed, parseo:1fila, folio correcto y esos totales | OK UI |
|409 comercial AF | No anular presupuesto ya utilizado | Intento único409; Actualizar no repite POST y conserva APROBADO_CLIENTE | OK negativo real UI |
|012A S | Editar evidencia reconciliada y reconsultar | Formulario real, PATCH200, «Vista general» conservada tras relectura | OK UI |
| Presupuestos/Obras/Reportes | Página2 si hay más de25 | Fixtures idempotentes de26presupuestos/Obras para lectura; página2 real200 de los tres módulos | OK UI |
| Filtros/actualización | Respetar el contrato de cada módulo | Presupuestos filtra **localmente la página**, aviso explícito; Obras y Reportes usan filtros servidor y conservan página al actualizar | OK UI |
| Auditoría G | Cursor real y filtros | Límite10, cursor siguiente200, filtrar recurso PRESUPUESTO#2 y actualizar | OK UI |
| Catálogo S | Lectura sin escrituras/historial de G | Controles de renombre/baja ausentes, sin request de historial en sesión S | OK negativo UI |
| Cortesía S | Acción antes preparada solo por fixture | Obra#29 nueva preparada exclusivamente para este caso, cortesía registrada por botón | OK UI |
| Rentabilidad G | No inventar segunda página | Una Obra finalizada del cliente: consulta200 y Siguiente deshabilitado | OK / paginación N/A |
|375/768/1280 | Formularios y vistas sin desborde global |36medidas del recorrido principal y21adicionales, todas scrollWidth=clientWidth, PNG por caso | OK navegador |

`journey-journal.json` conserva13pasos aprobados y las escrituras; cada archivo
`journey-{commercial,obra,turno,costos,finance}.json` conserva requests saneados.
`journey-verified.json` comprueba1POST de documento y1POST de pago, IDs y CSV.
`pending-pre.json`, `pending-post.json`, `pending-catalog-audit.json`,
`pending-supervisor-readonly.json` y `pending-report-pages.json` contienen las
11combinaciones nuevas aprobadas. El primer chequeo S de catálogo incluyó por
error requests previos de G en el mismo acumulador y falló: el retest restringió
la observación a la sesión S, sin repetir las tres escrituras de categoría.
También se corrigió un selector de fila que coincidía primero con la cartera y
no con la administración del documento; el journal impidió repetir la factura.
Son correcciones de instrumentación, **no defectos de React**.

Los26presupuestos/Obras paginables y la Obra de cortesía son fixtures controlados,
idempotentes por marcador y limitados a esta DB QA; sus estados aprobados y altas
no se cuentan como acciones UI. Clientes no ofrece paginación contractual en su
endpoint array. Listados con menos de25filas o sin página siguiente se registran
como no aplicables, no se fabrican datos que violen límites de adjuntos/estados.

No se volvieron a ejecutar casos con evidencia válida: cinco descargas, cierre
AF SIN_COBRO, reversión/lectura histórica, desasignación T, CAS dos pestañas,
fallos reales scanner/Mongo y negativos401/403/red de descarga se reutilizan
con sus límites explícitos de la matriz anterior y código idéntico. La matriz
RBAC de servidor previa incluye fetch auxiliar y suites: **no se renombra como
prueba desde un botón inexistente**. Este cierre cubre el recorrido priorizado
y las combinaciones enumeradas, no todas las combinaciones matemáticas posibles
de endpoint×rol×error. No se han descubierto defectos funcionales nuevos.

En este cierre no cambió código productivo, dependencias, tests ni configuración
Django del repositorio. Se reutilizan204/204 (3602.6882ms), build1.90s y874/874
(244.157s) únicamente tras comparar archivos relevantes/commit con lo probado.
Nuevo: pruebas CDP aquí enumeradas, inspección TLS estricta y audits: completo
4high/salida1, runtime0/salida0. Git diff --check y verificación del paquete
binario se registran al entregar. El registro formal picomatch de SPEC-014 está
preparado, **PENDIENTE de firma**, no aceptado.

**Dictamen actual: NO APTO.** El recorrido priorizado UI pendiente ya tiene
evidencia; quedan dos decisiones/intervenciones humanas: cadena TLS confiable
y revalidación HTTPS sin excepciones, y aprobación/rechazo explícito del riesgo
picomatch (o parche oficial verificable). Autorizar la CA no acepta picomatch,
y aceptar ese riesgo no certifica TLS. No publicar ni sacar el PR de Draft.

### Material de revisión sin publicación

En el directorio externo de cierre, subcarpeta `review/`:

- `PR44-local-all.binary.patch`: diff Git `--binary --full-index` contra HEAD
  efa33327, con todos los cambios tracked **y los cuatro archivos nuevos**.
- `PR44-new-files.zip`: exclusivamente los cuatro nuevos necesarios, rutas
  relativas del proyecto; permite inspección separada, no contiene fixtures QA.
- `PR44-summary.md` y `SHA256SUMS`: listado de archivos y huellas de artefactos.

El patch se construye con índice temporal, no con el staging real, y se verifica
aplicándolo a otro índice temporal inicializado desde HEAD. Ningún archivo de
trabajo, rama o índice real se reemplaza. El ZIP se valida contra los bytes de
sus cuatro fuentes. No aplicar automáticamente en este árbol ya modificado:
el patch ya incluye los nuevos, por lo que ZIP y patch no son dos capas a repetir.
Se excluyen credenciales, claves/certificados TLS, perfiles, dumps, bases y datos
del laboratorio. La evidencia de navegador se conserva separadamente fuera del
repositorio, no dentro del ZIP de incorporación.

## Decisión del responsable y publicación para auditoría — 17-11-2026

Esta decisión actualiza los estados históricos anteriores, sin borrar evidencia:

- **Picomatch ACEPTADO TEMPORALMENTE**, exclusivamente desarrollo y QA, por
  autorización expresa del responsable del proyecto en conversación del17-11-2026.
  Riesgo residual vigente; revisión semanal; caducidad propuesta17-12-2026
  (30días) con nueva evaluación del responsable. No hay firma digital ni ticket
  inventados. Registro formal y condiciones: SPEC-014 §«Registro formal de decisión
  autorizada». Mantener4high visibles; no audit fix --force ni lock alterado para
  ocultarlos; actualizar al existir corrección oficial verificada.
- **TLS no modificado ni aprobado para despliegue.** No se autoriza instalar CA
  raíz en Windows, cambiar almacenes confiables ni desactivar validaciones. El QA
  funcional y los casos históricos con SPKI no acreditan confianza TLS. Validar una
  cadena confiable sin excepciones sigue siendo requisito pendiente de despliegue.
- **Se autoriza publicar código para auditoría**, mediante commit y push normal
  solo a `feature/frontend-005c-integracion-modulos`, en el PR#44 existente Draft.
  No se autoriza merge, push a main, force push, eliminar ramas, nuevo PR ni Ready
  for Review. Publicación no equivale a aprobación de producción o merge.

Antes de publicar se repiten npm ci/test/build, auditorías runtime y completa,
Django check/dry-run y pruebas backend en un proyecto QA nuevo exclusivo
`fyag-pr44-publish-20261117`, sin usar el Mongo ni las bases de fixtures navegador.
Las SPEC y scripts QA reutilizables se conservan; secretos, TLS, dumps, artefactos
y datos del laboratorio permanecen fuera de Git.

### Resultado de la validación repetida previa a publicación

- `npm ci`: OK, 71 paquetes instalados/72 auditados; package/lock sin cambios.
  Aviso de postinstall esbuild bloqueado por política local, sin impedir test/build.
- `npm test`: **204/204 OK**, 0 fallos, 3697.3954 ms.
- `npm run build`: **OK en 2.03 s**, 99 módulos; JS `index-CDZdNGTo.js`
  370.95 kB y CSS `index-DD1aDEOP.css` 254.58 kB.
- `npm audit --omit=dev`: **0 vulnerabilidades**, salida 0.
- `npm audit --json`: **4 high**, salida 1, exclusivamente la cadena
  picomatch/fdir/tinyglobby/vite de GHSA-fc5q-39xc-vjpf aceptada temporalmente.
  Sin vulnerabilidades nuevas; no se declara audit completo aprobado ni corregido.
- Django `check`: sin incidencias; `makemigrations --check --dry-run`: sin cambios.
  Migraciones aplicadas solo a la nueva QA; `migrate --check`: OK.
- Suite backend completa: **874 pruebas OK en 222.740 s**; base de test destruida
  normalmente. PostgreSQL/Mongo exclusivos en tmpfs, red interna y sin puertos host.
- Revisión de los 20 archivos: sin secretos, claves privadas, dumps ni artefactos
  QA; se conservan contratos, SPEC y scripts reutilizables.

Esta ejecución no repite operaciones financieras de navegador ni modifica los
servicios/bases/volúmenes FYAG principales o el laboratorio de navegador existente.
La confianza TLS permanece intacta y pendiente de validación para despliegue.
GitHub Actions se verificará tras el push; estos resultados son locales, no CI.
