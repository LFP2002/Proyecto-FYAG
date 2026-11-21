# SPEC-019A — auditoría e implementación backend

Rama exclusiva `feature/backend-019a-bodeguero-inventario`.
Base `f68339c2d147e40fcb1457fee379c64f30cc5298`.
Sin commit, push, PR, merge, despliegue ni frontend.

## Auditoría previa al código

Leídas SPEC-019 íntegra, SPEC-006B, SPEC-018 y SPEC-004B. Revisados modelos,
migraciones Usuarios 0005–0009, autenticación/versionado/credenciales/bloqueos,
servicios TI, permisos Comercial/Obras y convenciones DRF de Usuarios/Documentos.
SPEC-019 aún dice propuesta/no autorización: la petición actual autoriza solo
implementación 019A para revisión. Su colección/environment Postman se difiere
expresamente por instrucción actual; no se incluyen credenciales de prueba.
SPEC-018 y 004B conservan texto histórico anterior a implementaciones posteriores;
no se reescriben esas SPEC ni se usa ese texto para retirar protecciones vigentes.

Cinco roles estaban codificados en `Usuario.Rol`, su constraint y migración 0005.
Serializers TI, filtro `rol` y servicio `_role` usan el enum dinámicamente. Las
allowlists de negocio no son catálogos generales: permanecen cerradas, sin agregar
BODEGUERO a Obras, Finanzas, Documentos, Adjuntos, Alertas, Dashboard o Reportes.
Contratos OpenAPI históricos de auth conservan cinco roles: se entrega complemento
019A para el sexto rol, sin reescribir evidencia histórica.

Diseño: app independiente, sin FK a Obra/Gasto/Presupuesto ni precios. Saldo cero
creado por trigger al insertar artículo (también SQL/bulk). Ingresos transaccionales
con UUID global y lock asesor de idempotencia → Artículo → Existencia. No adquirir
mutex TI ni locks operativos de Obras. Revalidar actor persistido y sesión mediante
mecanismos 018; escrituras no confían en claims/flags. El libro calcula saldo SQL
atómicamente y será inmutable. Control diferido concilia saldo/libro al commit;
los permisos SQL privilegiados siguen requiriendo separación operacional.

## Arquitectura y cobertura de integridad

- `ArticuloInventario`: código único ASCII normalizado, nombre, descripción,
  unidad sin conversiones, activo y auditoría de alta/última modificación. No
  precio, saldo editable ni FK a Obra. No se agrega una política monetaria.
- `ExistenciaInventario`: OneToOne PROTECT, `NUMERIC(12,3)`, cero válido, rango
  finito 0..999999999.999. Trigger AFTER INSERT de artículo crea exactamente cero,
  incluso desde SQL/bulk. GET no inserta ni rellena ausencias.
- `MovimientoInventario`: INGRESO, UUID global UNIQUE, cantidad positiva,
  snapshots anterior/posterior coherentes, actor PROTECT y fecha servidor.
  Mutación bloqueada en ORM y trigger SQL BEFORE UPDATE/DELETE. FK protegidas;
  no endpoints de modificación/borrado ni registro en admin Django.
- Ingreso: lock asesor `pg_advisory_xact_lock(1900, hash32(UUID))` → artículo →
  existencia. Colisión hash solo serializa más; igualdad real se decide con UUID
  completo UNIQUE. Actor y carga normalizada forman identidad de replay. Roles y
  sesión revalidados después de esperar locks. Actor se relee sin adquirir mutex
  TI ni locks de Usuarios que inviertan el orden administrativo. Una petición ya
  autorizada puede finalizar concurrentemente con revocación posterior; no se
  promete cancelación retroactiva de trabajo confirmado.
- Alta/edición con código toman antes lock asesor namespace 1901 del código
  destino, luego fila de artículo si existe; sin adquirir ese lock después de
  artículo. Todos los servicios rechazan desconocidos y tipos no exactos.
- Trigger BEFORE INSERT del libro bloquea artículo → existencia y verifica activo,
  snapshot contra saldo y actor Bodeguero activo. AFTER INSERT aplica saldo; el
  servicio **no suma otra vez**. CHECK verifica rango/suma, UNIQUE UUID como defensa
  final. Fallo de movimiento revierte saldo. No se confía en lectura fuera de lock.
- Constraint trigger diferido concilia `saldo = SUM(cantidad)` al commit. Actualizar
  saldo directamente sin libro se revierte al confirmar, aunque el valor sea
  no negativo. Existencia no se borra ni cambia de artículo; artículo no se borra,
  código/unidad no cambian con movimientos. Sin variables de sesión de bypass.

**Cobertura SQL real y límites:** triggers cubren DML normal con constraints
habilitados, incluidos SQL/bulk inserts. No impiden DBA, TRUNCATE, deshabilitar
triggers o cambiar funciones; separar privilegios y respaldos antes de producción.
Autenticación JWT/estado 018 y normalización completa del texto son del servicio,
no se replican como protocolo de autenticación SQL. Auditoría de actor/fecha la
fija el servicio; SQL valida actor de ingreso activo/rol, no conocimiento del
secreto humano. PostgreSQL NUMERIC(12,3) coerciona la escala antes del CHECK: SQL
directo podría redondear una entrada con más decimales. API/servicio la **rechazan**
sin redondeo; no afirmar detección del literal SQL original. Conciliar SUM por
artículo es O(historial); index FK ayuda, pero se requiere perfil de carga y plan
de reconciliación escalable antes de volúmenes altos, sin relajar invariantes.

## Migraciones y compatibilidad

1. `usuarios.0010_bodeguero`: remove/add de `usuarios_rol_valido` y choices, después
   de 0009. No reescribe cuentas, versiones, hashes, actividad ni auditoría.
2. `inventario.0001_initial`: tres tablas/constraints/índices/FK, sin fixtures;
   dependencia swappable de Usuario, como las apps existentes. No depende del
   nuevo rol para crear tablas vacías; ambos planes completos deben aplicarse antes
   de servir API. Esto preserva tests históricos que revierten Usuarios sin tener
   que borrar inventario como dependencia del enum. No se alteran 0005–0009.
3. `inventario.0002_integridad_libro`: funciones/triggers SQL del libro y saldo.

Upgrade probado desde Usuarios 0009 sin inventario: cinco roles anteriores,
hashes/versión/actividad/estado/eventos intactos; inventario vacío, sexto rol nuevo
con estados 018 creados por triggers heredados. Instalación limpia probada en QA.
Reverse técnico existe, pero no se autoriza ejecutarlo sobre datos reales: quitar
0010 con cuentas Bodeguero presentes aborta por constraint, no las recategoriza;
retirar tablas/triggers destruiría evidencia/controles. Preferir roll-forward y
respaldo probado; no hacer rollback productivo automáticamente.

Prueba histórica de paginación Usuarios adaptada por la sexta fixture: count
32→33 y segunda página 7→8. Se mantienen tamaño 25, orden y todos los filtros;
se amplía la denegación TI a Bodeguero. No se borran ni reducen aserciones. Ningún
permiso operativo ajeno se amplía. Los tests 018 iterativos del enum ahora cubren
también Bodega y siguen formando parte de la regresión.
Durante las pruebas iniciales se corrigieron rutas equivocadas de los tests nuevos
(`/adjuntos/` y `/auditoria/`, que no son los listados reales); se ensayaron luego
las rutas registradas y se mantuvo la exigencia de 403, sin cambiar permisos para
convertir un 404 en acceso. El CHECK SQL de unidad también rechaza blancos puros,
además de validar minúsculas/trim. No se amplía el adaptador de Auditoría global:
el libro autorizado de inventario se consulta en su propio endpoint.

## API y decisiones sujetas a ratificación

Ver [consumo](SPEC-019A-CONSUMO.md) y [OpenAPI](openapi/SPEC-019A-v1.json).
GET/POST artículos, GET/PATCH detalle, GET existencias/movimientos y POST ingresos;
páginas 25, filtros explícitos, 201 nuevo/200 replay, 400/401/403/404/405/409.
Referencia y motivo de ingreso opcionales en 019A, sin respaldo fiscal inventado.
Solo Bodega escribe; G/S/AF leen; T/TI denegados incluso staff/superuser.

Para revisión funcional antes de merge: matriz propuesta; normalización y formato
ASCII de código; longitud/unidades sin conversiones; referencia/motivo opcionales;
UUID global ligada al actor y sin expiración; replay sobre artículo desactivado;
catálogo con auditoría de última modificación (no API de versionado de catálogo).
Sin valorización, despacho, devolución, merma o costo de Obra. No se habilitan
funciones productivas ni se dan por cerradas decisiones pendientes de SPEC-018.

## Archivos

Creada app `backend/apps/inventario/`: `__init__.py`, `apps.py`, `models.py`,
`permissions.py`, `services.py`, `serializers.py`, `views.py`, `urls.py`;
`migrations/__init__.py`, `0001_initial.py`, `0002_integridad_libro.py`;
`tests/__init__.py`, `test_inventario.py`, `test_migraciones.py`, `test_contrato.py`.
Creada `backend/apps/usuarios/migrations/0010_bodeguero.py`.
Modificados solo enum/constraint de `usuarios/models.py`, la prueba de Usuarios
indicada y registro de app/ruta en `backend/config/settings.py` y `urls.py`.
Documentos nuevos: este informe, `SPEC-019A-CONSUMO.md`,
`openapi/SPEC-019A-v1.json`. No Postman/environment por instrucción actual.

## QA y resultados

Lab dedicado **nuevo** `fyag-spec019a-20261120`: standalone
`compose.premerge-qa.yaml` y override/env externos en temporal aprobado
`C:\Users\jugue\AppData\Local\Temp\opencode\fyag-spec019a-20261120`.
Sin compose principal, puertos host ni bases institucionales; PostgreSQL/Mongo
efímeros, Mongo autenticado y ClamAV propios; backend bind readonly, red interna.
DB `fyag_spec018c_c2_qa` en **PostgreSQL 019A nuevo**, no reutilizado de 018;
nombre exigido por gate de tests C2. Test DB `test_fyag_spec018c_c2_qa`.
Secrets aleatorios externos, cuentas @example.test; sin datos reales en migraciones.

Comandos reproducibles dentro de ese lab (no sustituir contenedor por principal):

```powershell
docker exec fyag-spec019a-20261120-backend-1 python manage.py check
docker exec fyag-spec019a-20261120-backend-1 python manage.py makemigrations --check --dry-run
docker exec fyag-spec019a-20261120-backend-1 python manage.py migrate --noinput
docker exec fyag-spec019a-20261120-backend-1 python manage.py migrate --check
docker exec fyag-spec019a-20261120-backend-1 python manage.py test apps.inventario --noinput
docker exec fyag-spec019a-20261120-backend-1 python manage.py test apps.usuarios --noinput
docker exec fyag-spec019a-20261120-backend-1 python manage.py test --noinput
git diff --check
```

Resultados finales sobre código congelado:

| Comprobación | Resultado real |
| --- | --- |
| Inventario dirigido | **30/30 OK, 3.214 s**, salida 0. Incluye migración, contrato y siete carreras/conciliación PostgreSQL. |
| Usuarios completo | **246/246 OK, 28.764 s**, salida 0. Conserva pruebas de autenticación, credenciales, C1/C2/C3 y última TI. |
| Backend completo | **1070/1070 OK, 265.493 s**, salida 0. 1040 heredadas + 30 nuevas; sin skips informados; DB test eliminada normalmente. |
| Django check | 0 incidencias. |
| makemigrations --check --dry-run | Sin cambios de modelos pendientes. |
| migrate --check | Sin migraciones pendientes en QA dedicada. |
| Instalación limpia / upgrade | Aplicación real QA hasta Usuarios 0010 e Inventario 0002 OK; upgrade histórico y conservación de datos en suite. |
| SQL | Siete triggers habilitados; conciliación diferida, snapshots, actor, rango e inmutabilidad ensayados. |
| OpenAPI | 3.1 válido con validador externo; rutas/enum comprobados en test y tres respuestas reales conformes al schema. |

Ejecución intermedia Inventario/Usuarios: 273/273 OK, 32.187 s, antes de los tres últimos
casos de concurrencia/contrato. Otra ejecución intermedia aprobó 30 Inventario /
246 Usuarios / 1070 backend; se repite tras reforzar la unidad no blanca en el
CHECK SQL y generar las contraseñas de fixtures solo en memoria. No atribuir
resultados anteriores a esa revisión final.
Check sin incidencias, makemigrations sin cambios, aplicación limpia hasta 0010 y
0002 OK. OpenAPI 3.1 validado con validador externo, sin dependencia nueva del
proyecto. Suite incluye SQL real, rollback, seis roles, cuentas anteriores,
idempotencia y carreras observadas con conexiones separadas/pg_blocking_pids y
timeouts; sin sleeps usados como demostración de bloqueo.

CI externo, navegador y Postman **NO EJECUTADOS**; no hay commit publicado que
pueda atribuirse a CI de esta entrega. Se entregan cambios locales para revisión.
Logs externos UTF-8 capturados desde subprocess con códigos de salida comprobados:
`inventario-final-v2.log`, `usuarios-final-v2.log`, `backend-final-v2.log`. Los
mensajes de denegación 403 de Adjuntos, token de usuario inactivo y fallos simulados
de Reportes pertenecen a pruebas negativas; no significan fallos de unittest.
SHA256 de esos logs, respectivamente:

- `a5046dc4b8b787670020aba6d2ffe472776ea8d67de03536cc8814df5ead48ff`.
- `5eb339ce083f2dd2e40e9b8536656edabe16da405ca2e1e1a3bc15a7618d0ec6`.
- `e7778dbccfc1e9cdbce7ae1ffbe1af336d5b17441edf3401da429a9fa6d08ae2`.

Integridad final: manifiesto de **348 archivos Python/JSON** congelado antes de
las suites finales; tras ellas solo documentación Markdown. **254 archivos
protegidos** cotejados por SHA256 (frontend, SPEC, Obras/Finanzas/Comercial y
migraciones históricas de Usuarios). Sin cambios en lógica financiera ni datos
institucionales. Escaneo de los **23 archivos** de entrega sin hallazgos de claves
privadas, JWT/GitHub literales ni secretos efímeros QA; es un escaneo acotado, no
garantía absoluta. `git diff --check` sin errores; enlaces locales válidos.

Estado de entrega: cuatro archivos versionados modificados y 19 nuevos, todos
bajo `backend/`; **sin staging, commit, push, PR o merge**. HEAD sigue en
`f68339c2d147e40fcb1457fee379c64f30cc5298`; main local
`b28e1d1b7358f73b6cf932ec54a32a1507d889ed` intacto. No hay SHA nuevo de entrega.
Laboratorio 019A se detiene al cerrar, sin retirar otros contenedores ni borrar
volúmenes/historial. Cambios pendientes de revisión humana, no de publicación.

Validación adicional real en QA: smoke Django/DRF (sin Runner/navegador) creó
artículo/ingreso y consultó existencia; las tres respuestas fueron validadas contra
sus esquemas OpenAPI 3.1 con jsonschema externo. Se forzaron constraints inmediatas
y se revirtió toda la transacción; no dejó fixtures ni movimientos persistidos.
Catálogo SQL verificó siete triggers habilitados y conciliación diferida por
defecto. Inventario QA principal sigue vacío; la prueba no inventa stock histórico.

## Recomendaciones y límites antes de una aprobación futura

- Revisar la matriz candidata, formatos/unidades, reglas de referencia/motivo y
  ámbito de replay por actor; no ampliar módulos ajenos por este sexto rol.
- Dimensionar conciliación SUM por artículo, locks/esperas, conexiones y cuotas
  para carga real. La concurrencia ensayada no certifica capacidad productiva.
- Aprobar privilegios SQL separados, respaldo/retención del libro y roll-forward;
  ninguna reparación automática de saldos o edición de historial.
- Definir 019B/019C por separado antes de movimientos negativos o relaciones con
  Obras. Conservar orden global Presupuesto → Obra → Gasto existente; una futura
  integración deberá diseñar orden común sin introducir locks inversos.
- Postman/environment posteriores por ChatGPT, CI solo cuando se autorice un SHA
  publicable y revisión humana antes de merge. No declarar CI ejecutada aquí.
- No se aplicaron flags productivos, configuraciones de servicios principales,
  nuevas políticas de costos ni cambios de credenciales/recuperación de SPEC-018.
