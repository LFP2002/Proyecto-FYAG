# SPEC-019C-1 — Solicitudes de materiales de Técnicos para Obras (FYAG Beta)

> **Estado:** CONTRATO FUNCIONAL RATIFICADO por el responsable, 21-11-2026. Solo fase 019C-1 (solicitudes y decisión de Supervisor); 019C-2 (mermas) sigue sin ratificar. Aprobación documental no acredita implementación, pruebas ni despliegue productivo.
>
> **Base de análisis:** main 00ee313a6610e24fade0efd44097920e5cac7af0; SPEC-019A/019B y SPEC-004B, 006B, 018/018C y 020A/B integradas. No modificar frontend ni otras SPEC. ChatGPT mantiene las SPEC; OpenCode solo implementará después de ratificación.

## 1. Necesidad y separación de fases

El backend ya permite que Supervisor autorice materiales y Bodeguero los despache, con costo interno único y trazable (019B). Falta permitir que un **Técnico participante de una Obra solicite material adicional**, para que Supervisor decida y Bodega ejecute por el flujo ya existente.

Esta fase **019C-1 incluye exclusivamente solicitudes y su aprobación/rechazo**. La merma física, pérdidas, clasificación de motivos y sus efectos sobre stock/valorización son **019C-2, aún no ratificada**. No implementar movimientos MERMA, descuentos de inventario, ajustes de costos ni adjuntos nuevos en 019C-1. No implementar proveedores, compras, chat ni frontend.

## 2. Flujo mínimo

1. El Técnico autenticado solicita artículo activo, cantidad positiva y justificación obligatoria, indicando una Obra donde sea participante **activo**. La Obra debe estar EN_PROCESO o SUSPENDIDA. El sistema conserva actor, fecha, artículo, unidad y cantidad original inmutables.
2. La solicitud inicia en PENDIENTE. **No reserva ni descuenta existencias, no comprueba precios, no crea GastoObra, Egreso ni autorización 019B en este momento.**
3. Supervisor consulta solicitudes y decide una única vez:
   - APROBAR: cantidad aprobada positiva, hasta la solicitada; motivo obligatorio. Crear **en la misma transacción** exactamente una operación AUTORIZACION_ENTREGA conforme al contrato de SPEC-019B, asociándola unívocamente con la solicitud y conservando al Supervisor como actor. Se admite aprobación parcial.
   - RECHAZAR: motivo obligatorio; sin autorización, stock ni costo.
4. Bodeguero consulta la autorización 019B normal y realiza despachos parciales mediante las rutas existentes, **sin acceso general nuevo a solicitudes de Técnico**. El sistema deduce la cantidad efectivamente despachada de los movimientos 019B, no de un contador editado en la solicitud.
5. La aprobación **no garantiza stock ni valorización**; el despacho sigue sujeto a las restricciones 019B. Si el Técnico deja de participar activamente antes de la aprobación, rechazar la aprobación (409), no convertir su antigua solicitud en facultad operativa actual.
6. Solicitudes y decisiones permanecen auditables incluso si el Técnico es desasignado, la Obra finaliza o el artículo se desactiva. Una decisión futura para una Obra no operativa no puede autorizar nuevos despachos. No cambiar ni bloquear la lógica histórica de cierre de Obras: una solicitud pendiente queda en el historial, sin producir movimientos ni costos.

## 3. Roles y proyecciones

| Acción | Técnico | Supervisor | Bodeguero | Gerencia | AF | TI |
| --- | --- | --- | --- | --- | --- | --- |
| Ver catálogo solicitables sin existencias ni costos | Sí | Sí | No requiere ruta nueva | Sí | No requiere ruta nueva | No |
| Crear solicitud | Solo participante activo en Obra operativa | No | No | No | No | No |
| Ver solicitudes | Solo propias, incluso históricas | Todas las operativas/históricas permitidas | No | Lectura | No | No |
| Aprobar/rechazar | No | Sí, en Obra operativa | No | No | No | No |
| Despachar/recibir | No | No | Solo con autorización 019B | No | No | No |

- La API de solicitudes **no** otorga al Técnico acceso a existencias, movimientos de Bodega, precio neto, promedio, costos, gasto vinculado, pagos o egresos.
- La vista de catálogo solicitable expone exclusivamente id, codigo, nombre y unidad de artículo activo. Si hay un artículo sin stock o valoración, puede solicitarse igualmente: la aprobación no mueve inventario.
- En la respuesta del Técnico se expone únicamente su solicitud, la decisión, la cantidad aprobada, el motivo de decisión y el ID de autorización vinculada; no entregar costo, saldo, movimiento ni datos internos económicos.
- El listado del Supervisor y Gerencia utiliza solo la información autorizada. No proporcionar access global por is_staff/is_superuser, roles dentro de JWT ni pertenencia inferida por ID.
- Revalidar rol, actividad, sesión_version, estado de credencial y bloqueo persistidos en servicios, incluida la revalidación tras esperas reales. En listados, el filtro de Técnico se aplica a la consulta SQL, nunca solo en la respuesta.

## 4. Modelo y persistencia

Modelo candidato SolicitudMaterialObra con:
- Obra, artículo, unidad histórica, técnico solicitante, cantidad_solicitada NUMERIC(12,3), justificacion.
- Estado PENDIENTE / APROBADA / RECHAZADA.
- Cantidad_aprobada opcional, motivo_decision, decidido_por y decidido_en cuando proceda.
- Vínculo uno-a-uno a OperacionMaterial AUTORIZACION_ENTREGA solo en APROBADA; no crear dos autorizaciones por solicitud.
- UUID de idempotencia de creación, carga normalizada/huella y actor.
- Fecha y usuario de servidor; sin edición ni eliminación pública.
- Evento(s) inmutables de decisión/creación, con actor, fecha, motivo y enlaces verificables. Se admite diseño de libro append-only y estado proyectado en vez de actualizar el registro histórico si mejora integridad.

Constraints para coherencia de estado/decisión, rango, actor y enlace. Incorporar protecciones PostgreSQL relevantes para que una actualización SQL directa no cambie autor, obra, artículo, unidad, cantidad, o autorización de una solicitud ya decidida. No falsificar aprobaciones ni generar vínculos huérfanos.

No alterar tablas/migraciones pasadas. Solo migraciones nuevas aditivas. Conservar todas las filas y reglas 019B. La autorización generada sigue siendo una operación 019B con UUID propia; cualquier reintento de decisión debe retornar el mismo resultado, sin duplicar autorización. No reutilizar el UUID de una solicitud para ejecutar un segundo efecto distinto.

## 5. API propuesta

Prefijo /api/inventario/, trailing slash:

- GET articulos-solicitables/: Técnico, Supervisor y Gerencia. Artículos activos, búsqueda por codigo/nombre, paginación 25; exclusivamente id/codigo/nombre/unidad.
- GET solicitudes-materiales/: Técnico (solo propias), Supervisor y Gerencia; orden estable por ID o fecha+ID, paginación 25, filtros estrictos para Obra/artículo/estado; Técnico no puede pedir solicitudes de otros mediante query params.
- POST solicitudes-materiales/: solo Técnico; JSON cerrado obra (ID), articulo (ID), cantidad (string hasta tres decimales), justificacion (texto requerido), clave_idempotencia (UUID).
- GET solicitudes-materiales/{id}/: mismos lectores y scope; recursos ajenos al Técnico devuelven 404 sin filtrar existencia.
- POST solicitudes-materiales/{id}/decidir/: solo Supervisor; JSON cerrado decision APROBAR/RECHAZAR, cantidad_aprobada solo si APROBAR, motivo obligatorio, clave_idempotencia UUID. No aceptar precio, costo, actor, unidad, fecha, estado derivado ni vínculo a una autorización ajena.

Idempotencia: primer POST 201 (creación) o 200 (decisión, según convención DRF que se documente), replay idéntico 200 con Idempotency-Replayed=true; mismo UUID con otro actor/payload/acción devuelve 409; decisiones divergentes sobre una solicitud ya decidida devuelven 409. Un replay no reejecuta 019B ni cambia su historial. Crear contrato preciso y probarlo en OpenAPI/Postman.

Validación: IDs positivos BIGINT, string Decimal estricto, textos normalizados sin caracteres de control ni vacíos; 400 esquema, 401 sesión, 403 rol, 404 referencia inaccesible, 405 método, 409 estado/remanente/concurrencia. No exponer mensajes SQL ni indicar cantidades valorizadas al Técnico. Respuestas private, no-store y Vary: Authorization.

## 6. Transacciones, integridad y carrera crítica

- Respetar **UUID/idempotencia → Presupuesto → Obra → solicitud/participante → artículo → estado 019B**; conservar la semántica de bloqueos de _obra_bloqueada. **Nunca adquirir por primera vez lock de Presupuesto u Obra después de poseer lock de artículo**.
- La aprobación debe invocar/reutilizar el núcleo de autorización 019B dentro de la misma transacción, con orden global seguro, sin llamar ingenuamente a un servicio que adquiera locks asesores en orden inverso. Si el contrato anterior imposibilita reutilización directa, extraer de forma acotada un núcleo privado común con pruebas, sin reescribir 019B.
- Tanto la solicitud/decisión como la autorización 019B tienen actor y fecha propios. El Técnico no puede hacerse pasar por Supervisor; Supervisor nunca aparece como solicitante. No escribir pagos ni gastos en la decisión.
- Serializar dos decisiones simultáneas, dos UUID diferentes contra la misma solicitud, decisión frente a finalización, decisión frente a desasignación del Técnico, cambio de rol/sesión durante espera. La base impone unicidad de vínculo y preserva integridad incluso ante escritura SQL impropia.
- Los datos históricos del Técnico siguen legibles dentro de su scope después de desasignación; un Técnico ajeno nunca accede a esa historia.

## 7. Pruebas y entrega

- Funcionales: creación por Técnico participante en Obra operativa; rechazo de no participante/Obra finalizada; aprobación completa y parcial; rechazo; visibilidad histórica; listado y filtro; artículo inactivo.
- Integración: decisión aprobada genera **una sola** AUTORIZACION_ENTREGA 019B; Bodega despacha normalmente y se genera un único GastoObra por despacho; la solicitud no crea ni Egreso ni pagos; flujo económico restante intacto.
- Seguridad: matriz seis roles, sesión revocada, no is_superuser bypass, Técnico solo lo suyo, catálogo sin existencias ni precios, 404 de recursos ajenos, payload estricto, GET sin escrituras.
- Carreras PostgreSQL con conexiones independientes y bloqueo observado: doble decisión, replay simultáneo de UUID, decisión versus desasignación, autorización frente a finalización y pérdida de sesión durante espera. Sin deadlocks, autorización doble o costos duplicados.
- Migraciones de base limpia y upgrade con datos previos 019B/021. Regresión dirigida y completa; check, makemigrations --check --dry-run, OpenAPI, Postman esenciales. Las pruebas documentales de informe son realizadas por compañeros y no son puerta del desarrollo. No usar datos productivos ni fixture que dependa de conteos globales.
- Implementar en rama exclusiva feature/backend-019c1-solicitudes-materiales desde main actualizado, **tras integrar este contrato documental en main**. Commit y push, sin PR ni merge; revisión de ChatGPT y CI obligatorios.
- No modificar frontend/, specs/ (responsabilidad exclusiva de ChatGPT), migraciones antiguas, permisos comerciales, seguridad heredada, inventario contable, archivos de IA, ni introducir scripts/dumps/logs temporales.

## 8. 019C-2: merma pendiente de ratificación

Antes de iniciar 019C-2 debe decidirse expresamente: tipos de pérdida/merma, motivo/evidencia obligatorios, quién autoriza, cuándo afecta al stock, origen y valor del costo (incluida merma en Bodega versus después de despacho a Obra), impacto sobre gasto/cierre y conciliación financiera. No inventar un tipo MERMA, no usar salidas sin Obra como si fueran despachos 019B y no equiparar pérdidas con egresos de dinero.

La futura fase se separará en SPEC/PR propios aprobados; no arrastrar complejidad adicional a solicitudes.
