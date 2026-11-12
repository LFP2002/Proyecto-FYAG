# SPEC-008 — Auditoría global federada, exclusivamente de lectura

**Estado: especificada para implementación por OpenCode; NO implementada ni integrada.** Este documento forma parte del [PR #26](https://github.com/LFP2002/Proyecto-FYAG/pull/26) (solo documentación). **No existe** `/api/auditoria/eventos/` en `main`. El contrato público se congela antes de programar el frontend. La programación, migraciones, pruebas ejecutables y commits de código corresponden a OpenCode, sujeto a revisión.

## 1. Estado, contexto comprobado y precedencia

Proyecto FYAG (Django 5, DRF, PostgreSQL, autenticación JWT versionada). `main` ya contiene eventos por dominio, sus permisos y endpoints de historial independientes, pero `apps.auditoria` no tiene API registrada en `backend/config/urls.py`. Esta SPEC añade únicamente una **lectura federada**; su implementación no depende de MongoDB ni sustituye la auditoría por origen.

**Precedencia:** prevalecen las restricciones de identidad y acceso de SPEC-002A/002B y SPEC-006B/006C, y las reglas de proyección de SPEC-003, SPEC-004/004B y SPEC-007. Una divergencia se documenta y revisa antes de codificar, nunca se resuelve entregando más información.

## 2. Objetivo y entregables

Ofrecer a los perfiles autorizados una secuencia temporal de eventos heterogéneos sin consultar cada módulo desde React, con filtros estables, autorización por fuente, paginación y tratamiento seguro de información. Entregables: endpoint DRF de solo lectura, normalizadores/adaptadores, permisos, tests PostgreSQL, OpenAPI versionado, documentación de integración y colección Postman revisada. No incluye UI ni exportación.

## 3. Principios e invariantes de integridad

1. `PostgreSQL` es la fuente única de los eventos ya persistidos; la API no hace doble escritura, migraciones retrospectivas ni replica auditoría en MongoDB.
2. Cada app de dominio es dueña de sus eventos. El módulo `apps.auditoria` **únicamente lee, normaliza, filtra y compone**; no modifica ninguna entidad ni añade efectos laterales a `GET`.
3. Permiso **antes de consultar, paginar, serializar o contar**. No aumentar la visibilidad de snapshots, evidencias o datos financieros que el rol no puede leer en las APIs de origen. Revalidar `Usuario.rol` activo persistido y `sesion_version`.
4. Eventos históricos pertenecen al pasado y son inmutables desde esta API. Ninguna operación de auditoría reconstruye hechos ausentes ni suplanta un registro oficial de seguridad.
5. El contrato de error y respuesta será estable y documentado; el frontend solo consume JSON. Los datos sintéticos del ejemplo no pueden incorporarse como fixtures del backend productivo.

## 4. Modelo de lectura, adaptadores y normalización

| `fuente` exacta | Modelo existente | `modulo` | `recurso_tipo` | ID del recurso | Actor | `tipo` público |
|---|---|---|---|---|---|---|
| `PRESUPUESTO_EVENTO` | `PresupuestoEvento` | COMERCIAL | PRESUPUESTO | `presupuesto_id` | `registrado_por_id` | `CREACION` si `estado_anterior is None`, en otro caso `CAMBIO_ESTADO` |
| `OBRA_EVENTO` | `ObraEvento` | OBRAS | OBRA | `obra_id` | `registrado_por_id` | `tipo` persistido |
| `PARTICIPANTE_EVENTO` | `ObraParticipanteEvento` | OBRAS | PARTICIPANTE | `participante_id` | `registrado_por_id` | `tipo` persistido |
| `CATEGORIA_SERVICIO_EVENTO` | `CategoriaServicioEvento` | OBRAS | CATEGORIA_SERVICIO | `categoria_id` | `registrado_por_id` | `tipo` persistido |
| `TURNO_EVENTO` | `TurnoObraEvento` | OBRAS | TURNO | `turno_id` | `registrado_por_id` | `tipo` persistido |
| `COSTO_OBRA_EVENTO` | `CostoObraEvento` | OBRAS | GASTO / CONTROL_COSTOS / CORTESIA | FK no nula correspondiente | `registrado_por_id` | `tipo` persistido |
| `FINANZAS_EVENTO` | `FinanzasEvento` | FINANZAS | DOCUMENTO / CIERRE_SIN_COBRO / PAGO | FK no nula correspondiente | `actor_id` | `tipo` persistido |
| `USUARIO_EVENTO` | `UsuarioEvento` | USUARIOS | USUARIO | `usuario_objetivo_id` | `actor_id` | `tipo` persistido |

Para `CostoObraEvento` y `FinanzasEvento`, la relación no nula identifica un único recurso exacto según las restricciones actuales. **No usar** la palabra genérica “COSTO” o “FINANZAS” como `recurso_tipo` ni mostrar el ID del `obra` como si fuera el ID del gasto. Se permite incorporar el `obra` relacionado en otra revisión de contrato, pero nunca confundirlo con `recurso_id`.

`evento_id` es la PK del modelo origen; `id` público es `<fuente>:<evento_id>`, por ejemplo `OBRA_EVENTO:215`. Conservar un campo separado `recurso_id`, que **no** identifica el evento. Timestamps de origen: `creado_en`. `motivo` faltante o vacío se normaliza a `""`, no se inventa el motivo.

**Cobertura explícitamente parcial:** no existe `ClienteEvento` como historial completo de Clientes; tampoco bitácora duradera de login, emisión JWT ni todas las lecturas de PII. No marcar auditoría “completa” más allá de las ocho fuentes definidas.

## 5. Matriz de autorización y visibilidad

| Rol | Fuentes y profundidad permitida |
|---|---|
| `GERENCIA` | PRESUPUESTO, OBRAS y FINANZAS. En eventos de TURNO, restringir al mínimo operativo; no exponer snapshots de revisión/tarifas que la vista de turno de Gerencia oculta |
| `SUPERVISOR_OBRAS` | Únicamente OBRAS; incluye costos operativos permitidos para Supervisor |
| `ADMINISTRATIVO_FINANZAS` | Solo FINANZAS, con los campos que ya permite `FinanzasEventoSerializer`; no eventos operativos ni control de costos |
| `ADMINISTRADOR_TI` | Exclusivamente USUARIOS, usando la misma sanitización de `UsuarioEventoSerializer` (contraseñas siempre snapshots vacíos) |
| `TECNICO` | Sin acceso a la API global; conserva los endpoints operativos ya autorizados |

Siempre aplicar **lista blanca** de claves de snapshots por `fuente + rol`; nunca pasar `datos_anteriores` ni `datos_nuevos` tal como provienen de `JSONField` sin proyección explícita. Los valores económicos usan strings decimales precisos si se incluyen. Las fuentes con actor inactivo conservan `actor` (ID) para trazabilidad, sin exponer email, hash ni rol de ese usuario.

El campo `actor_etiqueta` es un nombre de visualización mínimo de atribución laboral: nombre y apellido si constan o alias en otro caso. No incluir email, RUT, teléfono ni flags de usuario. Verificar que esa atribución es visible al rol autorizado; si no lo es, `actor_etiqueta=null` sin provocar una consulta a `/api/usuarios/`.

Todas las subconsultas y proyecciones se ajustan por rol **en el backend**, sin confiar en la barra de navegación React, encabezados arbitrarios, querys de cliente o `is_superuser`.

## 6. Contrato REST público v1

`GET /api/auditoria/eventos/`

Métodos válidos: GET, HEAD, OPTIONS. GET sin efectos laterales; `POST/PATCH/PUT/DELETE` responden 405. Requiere JWT vigente; 401 sin identidad, 403 para `TECNICO` y para un `modulo` fuera del rol. Una consulta filtrada por recurso inexistente **o fuera del ámbito** no permite inferir existencia; devolver resultados vacíos o 404 según política uniforme documentada; nunca mostrar metadata del recurso.

Query exacta:

| Campo | Restricción |
|---|---|
| `modulo` | COMERCIAL / OBRAS / FINANZAS / USUARIOS; omisión: todas las fuentes del rol |
| `fuente` | Una de las 8 fuentes exactas de la tabla; requiere autorización |
| `tipo` | Cadena de evento válida en fuente seleccionada; si hay varios tipos entre fuentes, filtrar literalmente sin crear un enum falso |
| `actor` | Entero positivo <=9223372036854775807 |
| `recurso_tipo` | Uno del catálogo del punto 2; debe concordar con fuentes permitidas |
| `recurso_id` | Entero positivo; requiere `recurso_tipo` |
| `desde`, `hasta` | `YYYY-MM-DD`; fechas civiles inclusivas en `America/Santiago`; sin parámetros: últimos 30 días civiles; rango máximo 366 días, desde <= hasta |
| `limit` | Entero 1–50, default 25 |
| `cursor` | Token opaco firmado, con expiración, asociado a actor/rol/versión de sesión, filtros y corte |

**Si se pasa `cursor`**, debe ser **el único parámetro de consulta**. Todos los filtros originales, el límite y los watermarks se recuperan del cursor firmado, no se repiten ni se modifican. Cualquier combinación de `cursor` con otro parámetro recibe `400` (`cursor_invalido`). Rechazar nombres desconocidos, valores repetidos, fechas malformadas y límites extremos (400). La fecha final de un periodo se implementa usando el inicio civil del día siguiente en `America/Santiago`, no sumando 86.400 segundos (DST).

Formato 200, ejemplo **no real**:

~~~json
{
  "results": [
    {
      "id": "OBRA_EVENTO:215",
      "evento_id": 215,
      "fuente": "OBRA_EVENTO",
      "modulo": "OBRAS",
      "recurso_tipo": "OBRA",
      "recurso_id": 72,
      "tipo": "CAMBIO_ESTADO",
      "actor": 9,
      "actor_etiqueta": "Supervisor de turno",
      "motivo": "Suspensión solicitada",
      "creado_en": "2026-11-11T18:30:00-03:00",
      "datos_anteriores": {"estado": "EN_PROCESO"},
      "datos_nuevos": {"estado": "SUSPENDIDA"}
    }
  ],
  "next_cursor": null,
  "has_more": false,
  "fecha_corte": "2026-11-11T18:32:00-03:00",
  "zona_horaria": "America/Santiago"
}
~~~

`actor_etiqueta` puede ser null si su obtención no está autorizada; todos los demás campos mantienen su tipo. Una lista sin datos retorna `200 {"results":[],"next_cursor":null,"has_more":false,"fecha_corte":"...","zona_horaria":"America/Santiago"}`. No declarar un `count` exacto global sin medir su costo; la UI pagina por `next_cursor`.

## 7. Concurrencia, paginación y consistencia PostgreSQL

El orden total será: `creado_en DESC, fuente ASC, evento_id DESC`. El adaptador obtiene por fuente solo las filas necesarias del rango autorizado, con consultas y proyecciones acotadas; fusiona resultados determinísticamente. No materializar todo el histórico en memoria ni resolver cada evento con queries N+1.

Un cursor firmado y con TTL de 15 minutos debe incluir filtros normalizados, `fecha_corte`, actor/rol/versión, última clave de orden, y **watermarks de PK por fuente** tomados al iniciar la navegación. Las páginas posteriores jamás incorporarán registros con PK superior al watermark ni posteriores a fecha_corte. Validar firma, caducidad, y cambio de identidad/rol/sesión, responder `400 {"code":"cursor_invalido","detail":"..."}` sin secretos.

**Límite de consistencia declarado:** un watermark de secuencia más fecha de corte NO garantiza snapshot transaccional de varias solicitudes HTTP si otra transacción reservó ID antes de la primera página y confirma después. Por ello este contrato garantiza orden estable y ausencia de duplicados de los elementos publicados, **no** promete cobertura exacta de transacciones concurrentes aún no confirmadas; al actualizar el feed, el cliente inicia una nueva consulta. Si el producto exige completitud point-in-time, se deberá diseñar materialización o un mecanismo específico, no falsificar un snapshot SQL prolongado. Documentar pruebas para esa diferencia.

## 8. Errores y validación

- `200` lectura válida (incluso sin registros).
- `400` query desconocida, duplicada, formato, rango, cursor corrupto/expirado o filtros incoherentes; `code` estable para cursor.
- `401` JWT ausente, caducado o revocado.
- `403` rol sin acceso global, fuente o módulo fuera de ámbito.
- `405` métodos no admitidos.
- `5xx` se registran con ID de correlación en servidor, nunca exponiendo SQL, headers Authorization, cookies o secretos.

La API de auditoría no tendrá operaciones de creación, edición, restauración ni borrado de eventos.

## 9. Arquitectura, dependencias y migraciones

- `apps.auditoria/views.py`: validación de filtros, permisos, respuesta; autenticar mediante `VersionedJWTAuthentication` por configuración DRF.
- `apps.auditoria/services.py`: coordinador de consultas, merge de ocho fuentes, keyset/cursor; mantener adaptadores de fuente separados para testear reglas de redacción.
- `apps.auditoria/serializers.py`: esquema unificado de lectura, snapshots por whitelists y proyecciones según rol. Para Usuario y Finanzas reutilizar explícitamente las funciones de sanitización existentes o sus invariantes.
- `apps.auditoria/permissions.py`: roles y visibilidad de módulo y fuente; sin bypass administrativo global.
- `apps.auditoria/urls.py` conectado en `config.urls` solo cuando exista la implementación real.
- **No migraciones nuevas obligatorias** en esta fase: se basa en modelos ya existentes. Un índice adicional requiere profiling/EXPLAIN y migración independiente justificada. No introducir tablas nuevas por comodidad.

## 10. Matriz mínima de pruebas y criterios de aceptación

1. Fixtures de las ocho fuentes, incluyendo `PRESUPUESTO_EVENTO` sin `tipo`, eventos de Costo con GASTO/CONTROL_COSTOS/CORTESIA y Finanzas con DOCUMENTO/CIERRE/PAGO; ID público sin colisiones.
2. Cada rol ve exactamente lo autorizado, **sin** snapshots de otra fuente; user con `is_staff/is_superuser` no escala, actor histórico inactivo no desaparece.
3. `UsuarioEvento` para cambios de clave tiene snapshots vacíos; G jamás ve el cambio de contraseña TI; S jamás recibe datos bancarios/financieros; T devuelve 403.
4. Prueba 401, 403, 405, fechas DST, filtros omitidos, repetidos, IDs inválidos, rango >366 días, `recurso_id` sin tipo, `limit` fuera de rango, cursor corrupto, expiro, identidad y filtros distintos.
5. Múltiples fuentes comparten `creado_en`; comprobar orden total sin duplicados; keyset + watermark y nuevas escrituras concurrentes; documentar límite de transacciones confirmadas tarde.
6. Pruebas de minimización: no exportar `password`, `token`, `authorization`, campos de evidencia privada ni datos que el serializer original ocultaba.
7. No se crean ni modifican filas al consultar; pruebas de rendimiento sin N+1 ni memoria proporcional al total del histórico.
8. Validar `manage.py check`, `makemigrations --check --dry-run`, migraciones y suite Django/PostgreSQL completas, Backend CI, documentación de respuestas e instrucciones operativas, Postman completo ejecutado por el usuario.
9. OpenCode entrega diff, informe, pruebas reales y limitaciones **para revisión antes de commit o PR**. Cada commit y PR posterior deberá describir el trabajo ejecutado; el merge se hace solo tras autorización explícita.

**Definición de terminado:** endpoint real integrado en `main` después de aprobación, CI + Postman sin fallas y contrato fijo consumible por el equipo frontend. Esta SPEC, por sí misma, es solo diseño.

## 11. Fuera de alcance

No hay escrituras, correcciones, eliminación de eventos, generación de eventos globales, login-history retroactivo, recolección de accesos/descargas, exportación PDF/CSV/XLSX, réplicas MongoDB, reporting financiero ni cambios en la lógica de dominio. El registro de cambios de Clientes es incompleto y no debe comunicarse de otro modo.

## 12. Entrega y flujo de integración

1. Revisar esta SPEC con el responsable y establecer contrato estable antes de programar.
2. **OpenCode implementa** en rama de código separada desde `main`, sin modificar el PR documental ni el frontend. Puede corregir documentación contractual solo mediante cambio explícito y revisado.
3. OpenCode ejecuta pruebas locales y **entrega un informe técnico completo de lo realizado**: archivos, decisiones, migraciones, contratos, evidencias, riesgos y cobertura. No afirmar pruebas no ejecutadas.
4. Con revisión favorable, OpenCode realiza commits descriptivos, push y PR de implementación con descripción completa. ChatGPT revisa el diff real, seguridad, migraciones, contratos y GitHub Actions en el repositorio, sin asumir que CI pasó.
5. Cuando corresponda, ChatGPT entrega **colección Postman completa**, importable y sin credenciales. El responsable ejecuta Postman y comunica resultados. Resolver errores en la rama y repetir comprobaciones antes de fusionar.
6. El merge requiere **autorización explícita** del responsable, revisión y CI aprobado. Solo entonces modificar estado a «implementada e integrada». Informar cualquier SPEC subida a GitHub y el comando de actualización local de su rama.

## 13. Fuentes internas verificadas

- `backend/config/{settings.py,urls.py}`, `backend/apps/auditoria/`.
- `backend/apps/comercial/models.py`, `backend/apps/comercial/serializers_presupuestos.py`.
- `backend/apps/obras/{models.py,serializers.py,serializers_turnos.py,serializers_costos.py,serializers_gastos.py,permissions.py}`.
- `backend/apps/finanzas/{models.py,serializers_documentos.py,permissions.py}`.
- `backend/apps/usuarios/{models.py,serializers_usuarios.py,authentication.py}`.
- SPEC-002A/002B, SPEC-003, SPEC-004/004B, SPEC-006B/006C, SPEC-007 y `.github/workflows/backend-ci.yml`.
