# SPEC-009 — Alertas reales y atención auditable

**Estado: definida para implementación por OpenCode; NO implementada ni integrada.** La aplicación alertas está vacía; estas rutas son un contrato propuesto, no endpoints actuales.

## 1. Estado, contexto y precedencia

La aplicación `apps.alertas` está creada como esqueleto, pero no implementa modelos de alertas, servicios ni URLs conectadas a `config.urls`. Preservar los estados y validaciones de Comercial, Obras y Finanzas; SPEC-003/004/007 prevalecen como fuentes de verdad, y SPEC-006B determina las autorizaciones. No interpretar esta SPEC como una implementación existente.

## 2. Objetivo, alcance y reglas de alerta
El prototipo React afirma detectar desviación entre costo y avance mayor a diez puntos, pero el backend NO tiene una medición persistida y validada de porcentaje de avance. Está prohibido fabricar ese dato a partir de costos, horas o fixtures. La desviación quedará fuera del MVP hasta definir formalmente cómo se registra y valida el avance de Obra.

Tipos de alerta v1, derivados únicamente de reglas presentes en los modelos:
- PRESUPUESTO_PENDIENTE_GERENCIA: presupuesto en PENDIENTE_GERENCIA; Gerencia.
- OBRA_SUSPENDIDA: obra en SUSPENDIDA; Gerencia y Supervisor.
- TURNO_PENDIENTE_REVISION: turno en PENDIENTE_REVISION; solo Supervisor.
- COBRANZA_VENCIDA: documento VIGENTE con saldo mayor a cero y vencimiento anterior al día de Santiago, según la consulta oficial de Finanzas; solo Gerencia.

No exponer detalles financieros al Supervisor. TI, AF y Técnico sin nueva bandeja de Alertas, sin cambiar sus rutas de negocio existentes. No enviar correos/push ni generar notificaciones automáticas externas.

## 3. Matriz de roles y visibilidad

| Rol | Consulta / atiende | Contenido |
|---|---|---|
| GERENCIA | Sí, alertas destinadas a G | Estados de presupuesto/obra y cobranza vencida, sin datos ajenos |
| SUPERVISOR_OBRAS | Sí, alertas destinadas a S | Estados operativos de Obras y turnos; nunca saldo/documento financiero |
| ADMINISTRATIVO_FINANZAS | No | Conserva `/api/finanzas/cobranzas/` propio |
| TECNICO | No | Conserva `/api/obras/mis-obras/` propio |
| ADMINISTRADOR_TI | No | Solo administración de Usuarios |

Comprobar actor activo y `Usuario.rol` persistido para toda lectura y escritura. Sin bypass por `is_superuser`, rol del token ni navegación React.

## 4. Modelo de datos, integridad y ciclo de vida
Se requiere registro nuevo en alertas con ID, tipo, recurso_tipo, recurso_id, generación del episodio, estado PENDIENTE/ATENDIDA/RESUELTA, creado_en, atendida_por, atendida_en, motivo_atencion y resuelta_en. Unique constraint (tipo,recurso_tipo,recurso_id,generacion). La atención solo significa reconocimiento, jamás ejecución de una operación de negocio; no cambiar estados de Obra/turno/presupuesto/documento desde esta API.

Crear una alerta por episodio real; resolver al desaparecer la condición de origen y crear una generación nueva si reaparece. Generación basada en transición de negocio identificable, no en una edición irrelevante. GET estrictamente read-only, sin crear o reconciliar filas silenciosamente. Implementar mecanismo idempotente de actualización al commit y/o reconciliación supervisada; los cambios de fecha de la cobranza deben detectarse sin depender de que un usuario abra el listado. Reintentos y carreras no pueden duplicar episodios ni atenciones.

## 5. Contrato REST, filtros y respuestas
- GET /api/alertas/?estado=PENDIENTE&tipo=...&page=1 — paginación DRF 25.
- GET /api/alertas/resumen/ — conteos por tipo y estado, filtrados al rol.
- GET /api/alertas/{id}/ — detalle con mínimo de campos.
- GET /api/alertas/{id}/historial/ — trazabilidad de atención.
- POST /api/alertas/{id}/atender/ — JSON exacto {"motivo":"Atención coordinada"}; retorna alerta actualizada (200).

Filtros de lista: estado, tipo, recurso_tipo y recurso_id (positivo), desde y hasta (YYYY-MM-DD, rango <=366 días), page. Orden por -creado_en,-id; parámetros desconocidos/duplicados o fechas invertidas dan 400. Un ID fuera del ámbito da 404. Actor real proviene del JWT; no se recibe en JSON.

Ejemplo de elemento, **no dato real**:

~~~json
{
  "id": 18, "tipo": "TURNO_PENDIENTE_REVISION", "estado": "PENDIENTE",
  "severidad": "MEDIA", "recurso_tipo": "TURNO", "recurso_id": 83,
  "obra": 12, "titulo": "Turno pendiente de revisión",
  "descripcion": "Revisión de Supervisor requerida",
  "creado_en": "2026-11-11T14:10:00-03:00",
  "atendida_por": null, "atendida_en": null,
  "motivo_atencion": null, "resuelta_en": null,
  "acciones_permitidas": ["ATENDER"]
}
~~~

Severidad fija por tipo, no calculada desde indicadores inexistentes. POST sin motivo => 400; segunda atención => 409 alerta_ya_atendida; origen resuelto => 409 alerta_resuelta; alerta desactualizada => 409 alerta_desactualizada. Nunca hay PUT/DELETE físicos.

## 6. Errores, concurrencia y reconciliación

Además de conflictos específicos `409`: 400 para filtros o body inválidos, 401 sesión inválida, 403 rol sin acceso global, 404 alerta ajena/inexistente y 405 métodos no implementados. Dos escritores concurrentes no deben crear duplicaciones y una atención no debe resolver ni mutar la entidad de origen. Los servicios deben evitar ciclos de importación y bloqueos invertidos entre dominios; un proceso de reconciliación eventual se supervisa y ejecuta idempotentemente.

## 7. Arquitectura recomendada

Implementar en `apps.alertas/{models.py,services.py,serializers.py,permissions.py,views.py,urls.py,tests/}`, con migración incremental nueva para entidades de alerta/atención y constraint de deduplicación. Reusar APIs de consulta y cálculos oficiales sin introducir cálculos de avance ficticio. Conectar rutas en `backend/config/urls.py` solo cuando la implementación y pruebas estén listas.

## 8. Matriz mínima de pruebas
PostgreSQL con dos escritores concurrentes, doble POST, reaparición del problema, vencimiento/cruce de medianoche zona Santiago, cobro completo/anulación de pago, documento revertido, filtros, error 401/403/404/405 y permisos incluso con is_superuser. Pruebas de que GET no muta base de datos. La matriz de tipos/receptores se somete a aprobación funcional antes de programar.

## 9. Fuera de alcance

No hay avance porcentual verificado; no alertas de desviación costo-avance, mensajería push/SMS/email, tareas de frontend ni modificación de Obras/Presupuestos/Finanzas por una acción de atención.

## 10. Entrega y flujo de integración

OpenCode implementa en rama separada, ejecuta tests y entrega **informe técnico completo de lo realizado**; después de su revisión, commits y push descriptivos. ChatGPT audita el PR en GitHub y CI, entrega colección Postman si corresponde, el responsable la ejecuta y comunica resultados. Merge exclusivamente autorizado; actualizar estado de la SPEC tras integración verificada. Se avisará cuando la documentación sea subida y requiera `git pull`.

## 11. Fuentes verificadas

`backend/apps/{alertas,comercial,obras,finanzas}/`, `backend/config/urls.py`, SPEC-003/004/007, SPEC-006B, workflow Backend CI.
