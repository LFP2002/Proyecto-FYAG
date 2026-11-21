# SPEC-020 — Gerencia de solo lectura, decisión comercial y alertas selectivas

> **Estado: contrato funcional ratificado para diseño; implementación pendiente.** 21-11-2026. Los criterios acordados son: Gerencia consulta y supervisa sin escribir en dominios de negocio; Administrativo/Finanzas gestiona clientes y decide los presupuestos; Supervisor de Obras administra categorías de servicio y metadatos técnicos; cada área atiende sus alertas y el sistema las resuelve cuando desaparece su causa; Gerencia solo recibe incidencias críticas o escaladas. **Los umbrales cuantitativos no han sido ratificados y no deben inventarse.**
>
> **Fuentes prevalentes:** código y migraciones vigentes de `main`, SPEC-003A/003B, 004/004B, 006B/018, 009, 012/012B y 019A; esta SPEC modifica exclusivamente las reglas señaladas y conserva el historial. SPEC-015 y demás contratos del frontend requieren coordinación posterior; **no modificar `frontend/` sin autorización**.

## 1. Objetivo, principios y decisiones

Separar inequívocamente tres capacidades: **consultar información**, **ejecutar acciones de negocio** y **recibir notificaciones**. Un permiso de lectura no confiere facultad para atender, aprobar o cambiar estados. La atribución se decide en backend con rol y sesión persistidos, no por botones, flags de Django, claims JWT, visibilidad de rutas o grupos.

- **Gerencia:** acceso de lectura a los recursos ya autorizados en cada dominio, indicadores, auditoría autorizada, reportes/exportaciones y descargas. Sin POST/PATCH/PUT/DELETE de negocios, sin aprobaciones o rechazos y sin acuse de alertas. Operaciones personales de autenticación (cambiar la propia contraseña, renovar/cerrar sesión) siguen permitidas; no se clasifican como mutaciones de negocio.
- **Administrativo/Finanzas (AF):** crea/edita/activa/desactiva clientes, confecciona y decide el circuito interno de presupuestos, y conserva sus facultades actuales en Finanzas.
- **Supervisor de Obras (S):** crea/edita/activa/desactiva categorías de servicios y edita metadatos de evidencias técnicas. Mantiene sus facultades operativas previas.
- **Técnico, Bodeguero y Administrador TI:** sin concesiones nuevas; Bodega conserva solamente inventario según 019A; TI solo administración de cuentas y seguridad ya habilitada, no lectura de negocio.

La lectura de Gerencia no supone acceso irrestricto a cualquier registro sensible: se conservan los scopes y filtros de dominio existentes. El backend debe denegar por rol **en permisos de API y en servicios de dominio**; asegurar que acciones custom/OPTIONS no permitan eludir controles. No convertir GET en escritura.

## 2. Fases y dependencias de integración

**020A — Permisos y transición comercial (un PR de backend con cambio de comportamiento atómico):**

1. Clientes, categorías de servicio y anotaciones de metadatos pasan a la matriz ratificada.
2. El flujo de aprobación presupuestaria pasa a AF, preservando presupuestos e historiales existentes. Gerencia pierde su capacidad de aprobar/rechazar **en la misma integración**; no puede quedar un presupuesto pendiente sin camino de decisión.
3. Ajustar las alertas de presupuestos para que AF reciba las pendientes conforme al nuevo flujo, y retirar `ATENDER` de Gerencia de manera efectiva. Conservar visibilidad gerencial de incidentes graves ya existentes.
4. Actualizar pruebas, validaciones, migraciones necesarias y contratos existentes. **Nada de frontend ni modificación de las cuentas o roles persistidos.**

**020B — Alertas por responsabilidad, criticidad y escalamiento (otro PR independiente, posterior a 020A):**

1. Estado único y auditable de incidencia, con visibilidad selectiva por destinatario; dejar de representar el mismo problema mediante estados de atención divergentes por rol.
2. Buzón gerencial de notificación limitado a criticidad/riesgo; información operacional agregada disponible en Dashboard sin convertirla en notificaciones individuales.
3. Escalamiento automático solamente cuando existan criterios funcionales explícitos, verificables y ratificados. Sin umbrales económicos o plazos arbitrarios.
4. Compatibilidad de lectura/historial API para usuarios actuales, pruebas de migración y reconciliador de recuperación. Extensión frontend en otro trabajo expresamente autorizado.

**Fuera del alcance:** 019B/C (despachos, solicitudes, merma, costo/stock), crear alertas por futuros procesos no implementados, mensajería, notificación por correo/push, cambiar los costos de Obras, cambiar autenticación 018/C2, un sistema de aprobación multinivel, nuevas relaciones con proveedores, limpieza general del repositorio.

## 3. Matriz de autorizaciones objetivo

| Dominio / acción | Gerencia | Administrativo/Finanzas | Supervisor | Otros |
| --- | --- | --- | --- | --- |
| Clientes: listar y consultar | Sí | Sí | No | Sin cambio |
| Clientes: crear, editar, activar, desactivar | **No** | **Sí** | No | No |
| Presupuestos: consultar e historial | Sí | Sí | Sin ampliar | Sin ampliar |
| Presupuestos: crear, ítems, revisiones, enviar, anular | **No** | **Sí** | No | No |
| Presupuestos: aprobar/rechazar internamente | **No** | **Sí** | No | No |
| Categorías de servicio: listar, detalle e historial | Sí | Sin ampliar | Sí | Sin ampliar |
| Categorías: crear, renombrar, activar, desactivar | **No** | No | **Sí** | No |
| Metadatos de evidencia: GET | Sí | Sin ampliar | Sí | Sin ampliar |
| Metadatos de evidencia: PATCH | **No** | No | **Sí** | No |
| Alertas: leer las autorizadas | Sí, solo críticas/escaladas en bandeja | Solo las propias | Solo las propias | Sin ampliar |
| Alertas: marcar atendida | **No** | Solo propias | Solo propias | Sin ampliar |
| Alertas: forzar resolución, borrar o alterar origen | **No** | No | No | No |
| Obras, turnos, gastos, costos, inventario, finanzas | **Lectura existente** | Sin cambio | Sin cambio | Sin cambio |
| Reportes, Dashboard, auditoría y descargas autorizadas | **Lectura/exportación existente** | Sin cambio | Sin cambio | Sin cambio |

En 020A se admite conservar temporalmente la representación de alertas legadas de SPEC-009; la consolidación de su modelo y filtro gerencial definitivo se completa en 020B. **No significa que Gerencia pueda atender alertas durante la transición.** Toda facultad nueva de S/AF debe limitarse a su dominio; no se deriva automáticamente de acceso a otra aplicación.

## 4. Presupuestos: nueva autoridad sin falsificar historia

### 4.1 Contrato para presupuestos nuevos

La máquina de 003B se conserva en lo esencial: BORRADOR, revisión interna obligatoria, decisión, envío al cliente, decisión del cliente, anulación/revisión controladas. Sustituir la revisión de Gerencia por la de Finanzas en los presupuestos **nuevos**:

```text
BORRADOR -> PENDIENTE_FINANZAS -> APROBADO_FINANZAS -> ENVIADO_CLIENTE
                                 \
                                  -> RECHAZADO_FINANZAS (terminal)
ENVIADO_CLIENTE -> APROBADO_CLIENTE | RECHAZADO_CLIENTE
```

- AF es el único rol que crea y realiza las transiciones comerciales, incluido aprobar/rechazar internamente. Rechazar exige motivo; aprobar debe respetar los controles y el snapshot congelado de 003B. No agregar umbrales según el monto ni saltarse revisión interna.
- Nombres candidatos de nuevas acciones HTTP, con slash final: `enviar-finanzas/`, `aprobar-finanzas/`, `rechazar-finanzas/`. Actualizar serializers, servicios, documentación contractual, rutas y pruebas conjuntamente. No reutilizar nombres `aprobar-gerencia` para realizar acciones de AF silenciosamente.
- El modelo debe seguir usando Decimal exacto, estados terminales, idempotencia preexistente de transiciones, restricciones de aprobación del cliente y protección de presupuestos usados por Obras. No conferir al usuario interno acceso directo a campos de estado, autor, totales ni a la política de aprobación.
- **Separación de tareas:** no imponer la exigencia de dos empleados AF distintos ni autorizaciones por monto sin ratificación; preservar la trazabilidad de `registrado_por` para que el riesgo de autoaprobación sea visible. Podrá especificarse posteriormente una política de doble aprobación.

### 4.2 Compatibilidad y conservación

En `main` los estados persistentes son `PENDIENTE_GERENCIA`, `APROBADO_GERENCIA`, `RECHAZADO_GERENCIA`; existe `requiere_aprobacion_gerencia=True` protegido por constraint SQL. No cambiar simplemente el rol permitido dejando nombres de estado o un booleano que atribuyan falsamente una autorización gerencial.

- Conservar los valores históricos y sus eventos append-only, autores, fechas y relaciones con Obras.
- Dar a registros legados en `PENDIENTE_GERENCIA` **una salida válida operada por AF** usando las nuevas acciones, registrando la transición real desde el estado histórico al nuevo destino, sin inventar aprobación de Gerencia.
- Los legados `APROBADO_GERENCIA` conservan la posibilidad ya válida de enviar al cliente por AF. `RECHAZADO_GERENCIA` sigue terminal; no reescribir eventos ni historiales para aparentar revisión de Finanzas.
- Distinguir correctamente la política histórica y la nueva, mediante campo/migración o mecanismo equivalente comprobable, sin exigir `requiere_aprobacion_gerencia=True` para presupuestos de la política nueva. Si se añade `politica_aprobacion`, los registros anteriores se migran como `GERENCIA_LEGADA` y los nuevos se crean `FINANZAS`, solo desde el backend.
- Migraciones **aditivas, reversibilidad evaluada y sin pérdida de datos**. No alterar migraciones históricas. Evitar cambios masivos a presupuestos ya aprobados, rechazados o asociados a una Obra. Estado de la fila, eventos y fuente de autoridad deben seguir coherentes.
- Los antiguos endpoints de autorización gerencial no deben ejecutar mutaciones después del cambio: retirar o responder 403/405 de forma consistente; informar contrato y evitar que el frontend antiguo ofrezca una acción que ya no existe. No anunciar compatibilidad de escritura que contradiga la política.

## 5. Cambios por dominio en 020A

**Clientes:** ajustar `apps.comercial.permissions.PuedeGestionarClientes` para comprobar método/acción: Gerencia GET/HEAD/OPTIONS autorizados, AF puede escribir. Cubrir POST/PATCH/activar/desactivar, denegaciones directas, 405 y actualización de fixtures. Mantener validación de identificaciones y datos históricos.

**Categorías:** en `apps.obras.permissions.PuedeOperarCategorias` y servicios de categorías, pasar create/partial_update/activar/desactivar de G a S. Gerencia sigue leyendo catálogo e historial; prevenir bypass al invocar servicios directamente. No cambiar permisos de Obras, turnos, gasto o costos.

**Metadatos:** `apps.documentos` hoy permite PATCH a G y S. Restringir escritura a S tanto en API como en servicio, con control de revisión/concurrencia CAS, autorización SQL/Mongo y auditoría intactos. Gerencia GET conservado. No confundir con `apps.adjuntos`, donde Gerencia ya tiene lectura/descarga sin edición.

**Alertas en transición:** el tipo `PRESUPUESTO_PENDIENTE_GERENCIA` refleja el estado histórico de 003B y actualmente pertenece a la bandeja de G. Crear una señal de revisión para AF vinculada a presupuestos tanto nuevos como legados pendientes, sin mantener una solicitud operativa de aprobación dirigida a G. Proteger el historial anterior (no borrar/reescribir eventos). Introducir lectura y atención de AF únicamente para la alerta de presupuesto que le corresponda; la extensión a sus otras incidencias se define en 020B. Retirar cualquier autorización de Gerencia sobre POST `/api/alertas/{id}/atender/` en vistas, servicio y `acciones_permitidas`. Conservar la resolución automática por reconciliación; no fabricar resoluciones manuales.

**Seguridad y API:** negar cambios aunque el cliente envíe un claim `GERENCIA` o el usuario tenga `is_superuser`; verificar estados de sesión actuales de 018, roles persistidos y controles de acceso por recurso. Mantener errores y filtros de 003A/003B/009; no convertir denegaciones en 404 filtrando recursos antes de autorizar. Preservar historial/autoría.

## 6. Alertas en 020B: incidencias, destinatarios y ruido

### 6.1 Propiedad y estados

Una **incidencia de negocio** se identifica por tipo/recurso/episodio, y tiene estado autoritativo único `PENDIENTE -> ATENDIDA -> RESUELTA`. El área dueña puede marcar atención con motivo y actor; esto no altera el recurso original ni equivale a resolverlo. **Solamente el reconciliador del backend** pasa a RESUELTA cuando se extingue la condición de origen. No crear un endpoint de cierre forzado ni permitir borrar historial.

La **entrega/visibilidad** es independiente del estado: una misma incidencia puede ser consultada por su responsable y por Gerencia sin tener dos estados divergentes. Preservar por migración o adaptación compatible las alertas/historiales de SPEC-009, hoy separadas por `rol_destinatario`. No descartar filas ni suplantar actores; duplicados históricos pueden permanecer como episodios de legado consultables. Si el cambio exige esquema nuevo, documentar correspondencia y pruebas antes de migrar datos; sin reconstrucción ficticia. Mantener aislamiento: leer un aviso no concede acceso de escritura al recurso original.

### 6.2 Enrutamiento sobre tipos existentes

| Condición actual | Responsable de atención | Notificación inmediata a Gerencia |
| --- | --- | --- |
| Presupuesto pendiente de revisión | AF | **No** |
| Obra suspendida | Supervisor | **Sí** |
| Turno pendiente de revisión | Supervisor | **No** |
| Cobranza vencida | AF | **Sí** |

`OBRA_SUSPENDIDA` y `COBRANZA_VENCIDA` se consideran relevantes para Gerencia en el catálogo actual. Sus responsables siguen siendo quienes modifican la obra o registran pago/cobranza. No conceder a G capacidad de marcar atención sobre su vista. Una alerta nueva de Finanzas no implica exposición de sus documentos a Supervisión, y viceversa.

En fases futuras (fuera de 020), aplicar la misma regla a stock insuficiente, solicitudes, entregas y mermas **solo cuando exista un origen persistido real y una regla ratificada**; no generar alertas simuladas por la mera mención de esos nombres.

### 6.3 Escalamiento y resumen

- Gerencia recibe un aviso operativo adicional **solo cuando** haya riesgo o vencimiento/escalamiento verificable conforme a política ratificada. No enviar todas las notificaciones a G por defecto.
- El umbral de días, monto, porcentaje de desviación, reincidencia y prioridad se define en una futura decisión de negocio; **no fijar valores arbitrarios ni habilitar reglas inventadas en 020B**. Dejar un punto de extensión explícito sin ejecuciones ficticias.
- Dashboard gerencial puede consultar contadores agregados (pendientes por área, críticas, atendidas, resueltas y salud de reconciliación) sin inundar la bandeja. Respetar permisos y ausencia de datos sensibles. No contar varias entregas de la misma incidencia como múltiples problemas.
- Sin notificación externa, correo, push, websocket ni trabajo de UI por defecto. Las notificaciones son registros consultables por las APIs existentes/adaptadas.
- La proyección sigue siendo postcommit y reconciliable (cadencia operativa vigente de 009, recuperación tras fallo, sin efectos laterales en GET), con operaciones transaccionales, concurrencia segura y orden de locks documentado.

## 7. Pruebas y criterios de aceptación

**020A — obligatorio antes de PR:**
1. Matriz completa de seis roles por acción y endpoint; Gerencia obtiene GET permitido, 403 a cualquier escritura de negocio. TI/staff/superuser o token con rol alterado no pueden ampliar permisos.
2. Cliente: AF crea/edita/activa/desactiva, G solo consulta, historial y validaciones existentes sin regresión.
3. Categorías: S gestiona, G solo consulta; prueba de invocación directa a servicios con G sin permisos.
4. Documentos/Mongo: S edita CAS, G lee y no edita incluso invocando servicio; trazabilidad conservada.
5. Presupuestos nuevos: AF ejecuta flujo completo, Gerencia no aprueba/rechaza, rechazo exige motivo, aprobación del cliente sigue separada, y los guardas de Obras permanecen.
6. Presupuestos legados: fixture anterior a la migración en cada estado relevante, actor/eventos originales intactos, transición permitida de pendientes sin intervención de G, presupuestos aprobados/históricos consumibles, sin falsificar política ni eventos.
7. Alertas: AF ve/atiende solicitud propia, G no la atiende; se conserva lectura de incidencia grave, se reconcilian sin efectos colaterales sobre dominios; resultados HTTP y acciones permitidas coherentes.
8. Migración desde `main` sobre PostgreSQL existente y desde instalación vacía, `makemigrations --check`, suite regresión completa, concurrencia bajo transacciones/locks reales y CI GitHub. No manipular la base institucional.

**020B — obligatorio:**
1. Misma incidencia/episodio, un estado y atención compartidos entre vistas autorizadas; lectura gerencial sin `ATENDER`.
2. Destinatario responsable correcto y notificación gerencial únicamente para tipos graves vigentes o escalamiento explícitamente ratificado.
3. Historia legada preservada, migración aditiva comprobada, sin atribuir atención humana al sistema ni multiplicar conteos por destinatario.
4. Reconciliador idempotente, recuperación ante callbacks perdidos, cambio de día civil Chile, carreras, no escritura en GET y paginación/filtrado sin fuga entre roles.
5. Regresión completa, documentación OpenAPI vigente y CI.

**Cada fase:** implementación local por OpenCode, commit/push en rama propia, revisión directa en GitHub, PR, CI y merge **solo con autorización expresa**. Postman esencial y environment legible para los compañeros al cierre, sin exigir su ejecución. No generar ZIP, parches, READMEs, informes de implementación redundantes ni artefactos temporales dentro del repositorio; la SPEC es la documentación funcional primaria.

## 8. Despliegue seguro y límites

- No activar parcialmente la prohibición de aprobaciones de G dejando filas `PENDIENTE_GERENCIA` sin transición nueva para AF. Ordenar migración, código y publicación como cambio coherente, con controles de rollback y respaldo.
- No modificar `main` durante implementación, ni alterar `frontend/`, código de inventario, datos reales, historial o migraciones anteriores.
- Contratos del frontend, Swagger/OpenAPI y suites Postman anteriores pueden requerir actualización funcional de las acciones afectadas, pero conservar solo los artefactos vigentes necesarios. Documentar el cambio de API para el equipo React dentro de esta SPEC y del PR; evitar informes adicionales.
- No usar el rol Gerencia como sustituto de aprobadores faltantes: si una operación requiere decisión, debe existir un responsable AF/S autorizado y trazable.
