# SPEC-008 — Auditoría global federada: informe previo a integración

Rama: `feature/backend-008-auditoria-global`, creada desde `origin/main`. Contrato consultado en `docs/spec-008-011-contratos-backend-restantes`; esa rama y sus SPEC no se modifican ni se declara aprobado el PR documental #26. Estado: implementación local para revisión, **no integrada en main**. Sin frontend, MongoDB, tablas globales duplicadas ni alteraciones de servicios de negocio.

## 1. Alcance y arquitectura

Endpoint nuevo: **GET `/api/auditoria/eventos/`**, también HEAD y OPTIONS autenticados. Solo lectura de PostgreSQL. Integra exactamente ocho modelos persistidos; no inventa historial de Clientes, logins, emisión JWT ni accesos a PII que no se registraban.

| Fuente | Modelo | Recurso exacto | Actor |
|---|---|---|---|
| PRESUPUESTO_EVENTO | PresupuestoEvento | PRESUPUESTO: presupuesto_id | registrado_por_id |
| OBRA_EVENTO | ObraEvento | OBRA: obra_id | registrado_por_id |
| PARTICIPANTE_EVENTO | ObraParticipanteEvento | PARTICIPANTE: participante_id | registrado_por_id |
| CATEGORIA_SERVICIO_EVENTO | CategoriaServicioEvento | CATEGORIA_SERVICIO: categoria_id | registrado_por_id |
| TURNO_EVENTO | TurnoObraEvento | TURNO: turno_id | registrado_por_id |
| COSTO_OBRA_EVENTO | CostoObraEvento | GASTO/gasto_id, CONTROL_COSTOS/control_id o CORTESIA/cortesia_id | registrado_por_id |
| FINANZAS_EVENTO | FinanzasEvento | DOCUMENTO/documento_id, CIERRE_SIN_COBRO/cierre_sin_cobro_id o PAGO/pago_id | actor_id |
| USUARIO_EVENTO | UsuarioEvento | USUARIO: usuario_objetivo_id | actor_id |

Todos usan `creado_en`. `evento_id` siempre es la PK del evento y `id` público es `<fuente>:<evento_id>`, sin colisiones entre tablas. Costo y Finanzas exigen exactamente una FK pertinente; nunca se suplanta esa PK con la de Obra. Presupuesto **no** tiene columna tipo: CREACION si estado_anterior es null, CAMBIO_ESTADO en otro caso; sus snapshots públicos se derivan exclusivamente de esos estados persistidos.

Responsabilidades:

- Adaptadores: metadatos cerrados de fuente, tipos y FK, queries filtradas, columnas mínimas y keyset por fuente.
- Permisos: rol persistido, actividad/versión, selección de fuentes antes de MAX, lecturas o serialización.
- Serializers: validación de query, rangos civiles, proyecciones explícitas, reutilización de sanitización de Usuario/Finanzas y formato de salida.
- Cursor: firma, TTL fijo, identidad/sesión, filtros, límite, corte, watermarks y última clave.
- Servicio: coordina queries acotadas, fusiona por orden total y crea la página/cursor siguiente.
- Vista: HTTP, errores y correlación segura, JSON, no-store.

## 2. Archivos

Nuevos:

- `backend/apps/auditoria/adapters.py`.
- `backend/apps/auditoria/cursors.py`.
- `backend/apps/auditoria/tests/base.py`, `tests/test_api.py`, `tests/test_concurrencia.py`.
- `backend/docs/openapi/SPEC-008-v1.json` (OpenAPI 3.1.0, contrato API v1.0.0).
- Este informe: `backend/docs/SPEC-008-IMPLEMENTACION.md`.

Modificados:

- `backend/apps/auditoria/permissions.py`, `serializers.py`, `services.py`, `views.py`, `urls.py` (esqueletos previos sin API).
- `backend/config/urls.py`: única integración de ruta `/api/auditoria/`.

No cambian modelos ni migraciones, dominios Comercial/Obras/Finanzas/Usuarios, permisos o serializers de origen, frontend, dependencias, CORS, CSRF, JWT, cookies, scripts ni configuración de bases de datos. No se implementa SPEC-009/010/011.

## 3. RBAC y discrepancias reales resueltas sin ampliar permisos

| Rol | Fuentes accesibles |
|---|---|
| GERENCIA | Presupuesto, Obra, Participante, Categoría, Turno, Costo y Finanzas; nunca Usuarios |
| SUPERVISOR_OBRAS | Obra, Participante, Turno y Costo |
| ADMINISTRATIVO_FINANZAS | Solo Finanzas |
| ADMINISTRADOR_TI | Solo Usuarios |
| TECNICO | 403, también OPTIONS |

Se usa la autenticación global VersionedJWTAuthentication, sin aceptar cookies como identidad del endpoint ni claims/flags como elevación. Se releen únicamente id/rol/actividad/versión del principal antes de coordinar las fuentes. JWT revocado/expirado o usuario inactivo → 401. Un principal que ya no tiene acceso global recibe 403; con rol global válido pero cursor de otra identidad/rol/versión, 400 cursor_invalido.

**Categorías:** `PuedeOperarCategorias` reserva historial a Gerencia; Supervisor solo tiene lectura del catálogo. Por precedencia de los permisos de origen, Supervisor no recibe CATEGORIA_SERVICIO_EVENTO y una solicitud explícita de esa fuente devuelve 403. No se modifica el dominio para ampliar permisos.

**Turnos:** la premisa textual de SPEC-008 de que la vista de Gerencia oculta tarifas no coincide con el código real: `_turno_serializer` usa TurnoSupervisorSerializer para todos los roles distintos de Técnico. No se corrige ni altera ese endpoint en este incremento. La auditoría global aplica el mínimo operativo más estrecho exigido por SPEC-008: Gerencia no recibe snapshots de tarifas/revisión económica, aunque el origen actual permita más información. Esta diferencia queda expresamente documentada, no se hereda el serializer amplio.

**Actor:** todas las fuentes conservan actor ID, incluso si está inactivo. Solo TI, que sí puede consultar cuentas, recibe nombre/apellido o alias del actor en UsuarioEvento; se obtiene con join de columnas mínimas, sin `/api/usuarios/` ni N+1. En otras fuentes se devuelve actor_etiqueta=null, ya que disponer de un actor ID no acredita permiso general para identificar a cualquier empleado. Es atribución con nombre actual, no una fotografía histórica del nombre.

## 4. Lista blanca efectiva

Se aplica igual filtro de claves/tipos a datos_anteriores y datos_nuevos, jamás JSONField crudo:

- Presupuesto: estado derivado de las columnas históricas; anterior vacío para creación.
- Obra (G/S): estado, categoria_servicio, tecnico_responsable, fecha_programada, iniciado_en, finalizado_en, cancelado_en.
- Participante (G/S): tecnico, activo, asignado_por/en, desasignado_por/en, origen_registro.
- Categoría (G): nombre, activo.
- Turno (G): iniciado_en, terminado_en, modo_cierre, cerrado_por, duracion_segundos.
- Turno (S): lo anterior más estado_revision, descripcion_trabajo, duracion_ajustada_segundos, costo_hora_neto, revisado_por/en, observacion_revision. Nunca fotos, nombres internos de archivos ni URLs privadas.
- Costo/GASTO (G/S): tipo, cantidad, cantidad_devuelta, costo_unitario_neto, fecha_gasto, vigente.
- Costo/CONTROL_COSTOS (G/S): materiales_estado, otros_estado, costos_validados, validado_por/en.
- Costo/CORTESIA (G/S): tipo, autorizado_por/en.
- Finanzas (G/AF): whitelist y tipos de FinanzasEventoSerializer, con comprobación adicional de formato/precisión de monto, monto_neto, monto_impuesto y monto_total. Sin UUID/huella de idempotencia, credenciales, costos operativos ni datos bancarios completos.
- Usuarios (TI): sanitización de UsuarioEventoSerializer: email, username, first_name, last_name, rol, is_active. Eventos de contraseña tienen ambos snapshots vacíos, incluso si una fila anómala contiene claves aparentemente permitidas.

Importes válidos se presentan como strings de dos decimales; cantidades tres y duraciones seis. No se convierten a float ni se redondea un snapshot inválido: NaN/Infinity, exponente, exceso de escala/magnitud, bool donde corresponde int o campos desconocidos se omiten. No se recalculan precios, impuestos, costos, saldos ni ingresos.

Motivo se conserva de la fuente o se normaliza a cadena vacía si falta valor. No se inventa texto ni se aplica una clasificación DLP de contenido libre: los operadores deben seguir sin introducir secretos en motivos/observaciones de origen.

## 5. Contrato HTTP y uso

200 incluye exactamente `results`, `next_cursor`, `has_more`, `fecha_corte`, `zona_horaria`; no count. Cada resultado contiene id, evento_id, fuente, modulo, recurso_tipo, recurso_id, tipo, actor, actor_etiqueta, motivo, creado_en y ambos snapshots. Fechas de salida con offset de America/Santiago. Cache-Control: private, no-store.

Filtros exactos: modulo, fuente, tipo, actor, recurso_tipo, recurso_id, desde, hasta, limit y cursor.

- Catálogos cerrados; tipo se valida contra los tipos reales de las fuentes seleccionadas y se aplica literalmente, no mediante un enum inventado.
- actor/recurso_id: entero positivo hasta 9223372036854775807; recurso_id exige recurso_tipo.
- Parámetros desconocidos, repetidos, valores vacíos no admitidos o incoherencias fuente/módulo/recurso → 400.
- Fuente/módulo no autorizados → 403 antes de consultar sus tablas o calcular watermarks.
- Recursos inexistentes o fuera de la intersección autorizada sin fuente/módulo incompatibles explícitos → 200 vacío; no se consulta existencia ni se devuelve metadata del recurso. Una combinación explícita incompatible de filtros es 400 independientemente de que el ID exista.
- desde/hasta civiles ISO inclusivos. Sin hasta: hoy Santiago; sin desde: hasta menos 29 días. Sin ambos: últimos 30 días civiles. Máximo 366 días **inclusivos**. Fechas futuras no inventan eventos: sigue aplicando corte del servidor.
- El fin SQL es el inicio civil del día siguiente, resolviendo la medianoche inexistente del salto DST; no se suman 86400 segundos. Se prueban días de 23 y 25 horas, inicio inclusivo y fin exclusivo.
- limit 1–50, default 25. Con cursor debe enviarse **únicamente cursor**, una sola vez. No repetir limit ni filtros originales.
- GET/HEAD/OPTIONS para perfiles autorizados; POST/PUT/PATCH/DELETE → 405. Sin identidad válida → 401. OPTIONS no entrega datos de eventos.
- Cursores inválidos/expirados → `400 {"code":"cursor_invalido","detail":"..."}`.
- 5xx devuelve mensaje genérico, UUID correlacion y X-Correlation-ID; el logger dedicado guarda solo correlación y clase de error, nunca SQL, str(exc), traceback con filas, cursor, Authorization, cookies ni snapshots.

Ejemplos de consumo sin secretos:

```text
GET /api/auditoria/eventos/?modulo=OBRAS&limit=25
GET /api/auditoria/eventos/?fuente=COSTO_OBRA_EVENTO&recurso_tipo=GASTO&recurso_id=<ID_real>
GET /api/auditoria/eventos/?fuente=PRESUPUESTO_EVENTO&tipo=CAMBIO_ESTADO&desde=2026-01-01&hasta=2026-12-31
GET /api/auditoria/eventos/?cursor=<next_cursor_devuelto_por_servidor>
```

Usar Bearer del login existente. No colocar JWT en querystring ni compartir cursores en logs/capturas. El frontend futuro solo utiliza los resultados y next_cursor; no combina ocho endpoints ni implementa reglas de autorización o orden.

## 6. Paginación, concurrencia y rendimiento

Orden total: **creado_en DESC, fuente ASC, evento_id DESC**. En cada fuente se consulta en fecha/PK descendentes; el merge aplica orden ASCII fijo de fuentes en Python y datetimes precisos, sin epoch float ni dependencia de collation SQL.

Primera consulta: filtros autorizados y corte timezone.now; MAX PK por fuente autorizada y consultas limit+1 acotadas por esas marcas/corte. Siguientes: mismas marcas, corte y filtros del cursor firmado, más keyset estricto posterior a la última clave publicada. No se consulta una fuente prohibida para contar o decidir has_more. La memoria queda acotada por fuentes*(limit+1), como máximo 408 candidatos para el registro de ocho fuentes, sin materializar el histórico. No hay queries por cada evento; el test comprueba como cota 16 consultas para Gerencia (principal/revalidación + 7 MAX + 7 páginas) y LIMIT 2 con limit=1.

Cursor con signing de Django, salt propio y versión interna; vinculado al principal/rol/sesion_version, filtros normalizados y límite, corte, marcas por fuente y última clave completa. Firma no significa cifrado: es opaco para el cliente, no una credencial. Caducidad de 15 minutos **desde el corte original**, sin extender TTL al pedir otra página. Cambios de configuración/esquema de cursor o clave de firma requieren reiniciar navegación. No se almacena cursor ni snapshot global en BD o caché.

La secuencia de PK y fecha_corte no equivale a un snapshot SQL entre requests. Las pruebas de conexiones independientes demuestran:

1. Filas nuevas con PK mayor al watermark no entran, incluso si se retrofecha su timestamp.
2. Una transacción que reserva PK antes del primer GET y confirma después puede aparecer detrás del keyset si está dentro de la marca.
3. Esa misma confirmación tardía puede omitirse si su orden ya quedó delante del último elemento publicado; una consulta nueva sí la recupera.

No hay duplicados de elementos publicados ni retrocesos de orden; no se promete completitud point-in-time. No se bloquea a los escritores ni se mantienen transacciones HTTP abiertas entre páginas. Para completitud estricta haría falta otro contrato/materialización revisado.

**Rendimiento residual:** LIMIT acota transferencia/memoria, no garantiza que el plan SQL evite escanear/ordenar muchas filas. No se añadieron índices ni paquetes: falta evidencia de volumen real que justifique migraciones. Antes de producción de alto volumen, medir EXPLAIN/ANALYZE sobre rangos/actores/recursos representativos y evaluar índices compuesto creado_en/PK y/o FK/fecha por fuente en una migración independiente aprobada. No se declaran latencias de producción no medidas.

## 7. Pruebas y resultados reales

Regresión final completada sobre el último estado del código. PostgreSQL real en Docker; datos sintéticos exclusivamente como fixtures en BD temporal, jamás como respuestas programadas ni seed productivo.

| Comando | Resultado |
|---|---|
| `docker compose exec -T backend python manage.py check` | System check identified no issues (0 silenced) |
| `docker compose exec -T backend python manage.py makemigrations --check --dry-run` | No changes detected |
| `docker compose exec -T backend python manage.py migrate --plan` | No planned migration operations |
| `docker compose exec -T backend python manage.py test apps.auditoria --noinput` | 29 pruebas, 10.492 s, OK; nueva comprobación final con --keepdb: 29 pruebas, 11.504 s, OK |
| `docker compose exec -T backend python manage.py test --noinput` | Regresión final secuencial: 673 pruebas, 139.645 s, OK (primera regresión: 128.440 s, OK) |
| `git diff --check` | Sin errores de whitespace; advertencias LF/CRLF de Git en Windows |

La creación de BD de pruebas ejecuta las migraciones existentes desde cero; no se aplican migraciones a una base productiva ni se modifica esquema por este incremento. La primera ejecución detectó tres fallos de fixtures concurrentes porque ObraEvento no admite datos_nuevos vacío: se corrigió la fixture, no el dominio. Un intento posterior de lanzar dos suites simultáneas chocó con la misma BD de tests; se repitió la regresión secuencialmente. **No ejecutar suites en paralelo sobre el mismo nombre de BD.**

Cobertura de las 29 pruebas: ocho fuentes y refs tipadas, tipo derivado de presupuesto, cinco roles y flags/claims sin escalamiento, categoría de Supervisor denegada, tarifas/evidencias restringidas, User/Fin sanitizados, actor inactivo, errores/filtros, defaults y 366 días, DST/bordes, empates, default25/max50, cursor manipulado/repetido/expirado, identidad distinta con igual rol, cambio real de rol/versión, JWT revocado/expirado/inactivo, 401/403/405/HEAD/OPTIONS, GET sin writes, error correlacionado sin secretos, cota de consultas y tres escenarios PostgreSQL concurrentes. OpenAPI se comprueba contra catálogos, parámetros y campos del serializer; no se afirma certificación por un validador OpenAPI externo.

No se ejecuta frontend porque no cambia. Postman debe revisarse/ejecutarse posteriormente por el responsable; no se declara aprobado ni se inventan resultados de GitHub Actions antes de ejecutarse.

## 8. Compatibilidad, despliegue y rollback

No se alteran autenticación versionada, refresh, rotación, blacklist, CSRF, CORS, importes, asignaciones, cierres, pagos ni historial de origen. No se llama a métodos de dominio que creen controles de costos u otros objetos al consultar. La API es compatible con backend separado del frontend: rutas JSON y Bearer existentes, fechas explícitas, cursores opacos y sin necesidad de acceso directo a PostgreSQL/Atlas desde React.

Desplegar el código revisado con la misma clave Django en todas las instancias para cursores válidos durante navegación. Actualizar la consulta del cliente ante TTL o cambio de sesión. Mantener DEBUG=False y políticas de logs/proxy que no registren secretos ni querystrings completas de cursores. Este incremento no modifica esa infraestructura ni finge despliegue remoto.

Rollback: retirar el include de `/api/auditoria/` o volver a la versión anterior del backend; no hay tabla ni migración a revertir y no se pierden eventos. Los cursores de una versión retirada dejan de utilizarse. No borrar filas de los dominios ni reconstruir hechos inexistentes.

## 9. Revisión y procedimiento Postman

1. Revisar primero diff, este informe y OpenAPI, incluyendo la política conservadora de categorías/turnos/etiquetas; no se aprueba ni modifica automáticamente el contrato documental #26.
2. Login existente por rol con CSRF/cookie segura para auth y access Bearer para auditoría. No exportar variables con contraseñas, tokens ni cookies.
3. G: consultar fuentes de negocio; USUARIO_EVENTO/USUARIOS → 403. TI: solo UsuarioEvento; fuentes de negocio → 403. AF: solo Finanzas. S: Obra/Participante/Turno/Costo, no Categoría. T: 403 global.
4. Verificar tipo de presupuesto y que recurso_id de Gasto/Pago es su FK real, no la PK de Obra ni del evento.
5. Filtrar por actor, recurso y fechas; vacío es 200 uniforme. Probar desconocidos, duplicados, rango>366, fechas inválidas, recurso_id sin tipo, limit0/51 y combinaciones incoherentes → 400.
6. Consultar con limit pequeño y continuar enviando solo cursor. Confirmar orden, IDs únicos, mismo corte, ausencia de count y fin next_cursor=null. Mezclar cursor con limit/filtros o manipularlo → cursor_invalido. Renovar JWT sin cambiar identidad/rol/versión permite continuar dentro del TTL; revocar sesión exige nuevo login y nueva navegación.
7. Comprobar snapshots sin secretos y mínimos de Gerencia en Turno; contraseñas de Usuarios con dos objetos vacíos; actor inactivo conserva ID, etiqueta nula cuando no consta permiso.
8. HEAD sin cuerpo, OPTIONS autorizado, POST/PUT/PATCH/DELETE 405 para rol autorizado; sin token/expirado/revocado 401. No cambia ningún registro por consultar.
9. Ejecutar la colección Postman revisada por ChatGPT/responsable y reportar Passed/Failed; las carreras de confirmación tardía se reproducen en TransactionTestCase, no mediante sleeps en Postman.

La implementación solo será «integrada» después de revisión, CI y Postman aceptados y merge autorizado. No se realiza merge a main.
