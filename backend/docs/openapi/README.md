# Índice OpenAPI FYAG

Los archivos son contratos parciales por entrega, no una API monolítica. Para una
ruta compartida, aplicar el contrato específico posterior **solo en métodos,
campos, proyecciones y perfiles que modifica**. Un contrato de vista gerencial
no amplía permisos de escritura ni sustituye la vista operativa general. Consultar
SPEC y URLconf para resolver discrepancias; no publicar propuestas como vigentes.

En Compose productivo la API y `/ws/chat/` comparten el origen HTTPS de la SPA;
no usar los servidores de ejemplo de QA como destinos de producción. `live` y
`ready` son probes internos, no rutas públicas. Respaldo, purga y recuperación
excepcional TI son operaciones de infraestructura, no endpoints HTTP.

| Área | Contratos y precedencia |
| --- | --- |
| Autenticación y credenciales | [018A](SPEC-018A-v1.json) para credencial temporal y primer cambio; [018C C2](SPEC-018C-C2-v1.json) añade estados y recuperación TI **solo en QA aislado**. [Propuesta C2](SPEC-018C-C2-propuesta.json) histórica. [Verificación 027](SPEC-027-verificacion-v1.yaml) complementa la proyección TI y reemplaza el cambio inmediato de correo; los demás incrementos de [SPEC-027](../../../specs/027-aprovisionamiento-recuperacion-seguridad.md) no se habilitan por este contrato. |
| Primera cuenta TI | [Setup 027](SPEC-027-setup-v1.yaml): la SPA consulta el estado mínimo y abre el asistente si hay una instalación nunca inicializada y sin usuarios. El estado no revela ni concede una clave; la CLI autorizada la emite fuera de HTTP. Alta sin sesión automática. |
| Recuperar contraseña | [Recuperación 027](SPEC-027-recuperacion-v1.yaml): solicitud opaca (`202` no acredita entrega) y confirmación por correo verificado, con revocación y sin sesión automática. El envío requiere el entorno SMTP/cola autorizado. |
| Bloqueos SPEC-027 | [Bloqueos productivos](SPEC-027-bloqueos-v1.yaml) complementa 018A y Recuperación 027; el perfil productivo requiere activación explícita y no sustituye las guardas QA C2. [Auditoría 008](SPEC-008-v1.json) e [historial 018A](SPEC-018A-v1.json) definen la proyección privada de TI. La recuperación excepcional TI es CLI, no un endpoint HTTP. |
| Obras, supervisor y gerencia | [004 Supervisor](SPEC-004-SUPERVISOR-v1.json), [004C](SPEC-004C-v1.json), [004 Gerencia](SPEC-004-supervision-gerencial-v1.json); [008](SPEC-008-v1.json), [009](SPEC-009-v1.json), [010](SPEC-010-v1.json) y [011](SPEC-011-v1.json) por alcance. [Obras resumen Finanzas](obras-resumen-finanzas-v1.json) complementa la proyección operativa. |
| Documentos y cobranzas | [012](SPEC-012-v1.json) metadatos, [012B](SPEC-012B-v1.json) complementa con adjuntos privados; [014 Gerencia](SPEC-014-supervision-gerencial-v1.json) y [búsqueda de cobranzas](cobranzas-busqueda-v1.json) para sus proyecciones. |
| Materiales y obras | [019A](SPEC-019A-v1.json), [019B](SPEC-019B-v1.json), [019C-1](SPEC-019C-1-v1.json), [019C-2](SPEC-019C-2-v1.json), [019D](SPEC-019D-v1.json), [019E](SPEC-019E-v1.json); [019F](SPEC-019F-v1.yaml) prevalece en integración comercial/materiales y cierre donde los modifica. [Disponibilidad 019F](SPEC-019F-disponibilidad-v1.json), [019C-1 Supervisor](SPEC-019C-1-supervisor-v1.json), [019C-2 Supervisor](SPEC-019C-2-supervisor-v1.json), [019 Gerencia](SPEC-019-supervision-gerencial-v1.json) e [Inventario Finanzas](inventario-finanzas-v1.json) complementan con vistas específicas. |
| Egresos y gastos | [021](SPEC-021-v1.json), [021 Gerencia](SPEC-021-supervision-gerencial-v1.json) y [origen de gastos](gastos-origen-v1.json); aplicar 019F solo en las operaciones de costos/materiales que cambió. |
| Chat | [023A](SPEC-023A-v1.json) base; [023B](SPEC-023B-v1.json) complementa tickets, tiempo real y archivos, y prevalece donde los modifica. Los avisos WebSocket no reemplazan la lectura autorizada REST. Los mensajes y sus adjuntos caducados se excluyen aunque [la purga física](../../../docs/RETENCION-CHAT.md) aún no se haya ejecutado. |
| Comercial | [024](SPEC-024-v1.json) base; [019F](SPEC-019F-v1.yaml) para integración de materiales/precio comercial y sus transiciones; [seguimiento 024 Gerencia](SPEC-024-seguimiento-gerencial-v1.json) es de lectura. No interpretar una etiqueta histórica como cambio de decisión ni de actor. |
| Otros módulos | [025A](SPEC-025A-v1.json) y [025B](SPEC-025B-v1.json), por ruta y perfil de cada contrato. |

Se conservan las propuestas, contratos anteriores y evidencias de cada entrega. Para contratos ejecutables
con Postman, usar solo cuentas sintéticas en el [laboratorio QA](../../../README.md#qa-pre-merge).
