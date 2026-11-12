# SPEC-010 — Dashboard gerencial basado en datos reales

**Estado: definida para implementación por OpenCode; NO implementada ni integrada.** La vista Dashboard del prototipo React no se encuentra integrada a API real. Implementar read models en apps.dashboard, sin modificar entidades o reglas de finanzas/obras.

## 1. Estado, contexto y objetivo

El módulo `apps.dashboard` existe pero carece de endpoints implementados. El Dashboard de React contiene cifras demostrativas y permanece fuera de la integración real. Este contrato proveerá consultas agregadas fiables para un frontend desacoplado y no deberá alterar el modelo de costos ni la fuente financiera.

## 2. Matriz de autorización y fuentes
Solo GERENCIA activa: GET/HEAD/OPTIONS. AF/S/T/TI => 403; no autenticado 401. Privilegio real validado por rol persistido, no menú ni flags Django.

Fuentes existentes: Obra y estados; Presupuesto con monto_neto aprobado; CierreCostosObra inmutable, ligado a Obra FINALIZADA; DocumentoCobro VIGENTE; PagoDocumento activo; consultas oficiales de cartera/saldo/estados de apps.finanzas.consultas_cobranzas. Ninguna métrica incorpora porcentaje de avance, porque no hay modelo de avance validado.

**Definiciones financieras:** presupuesto_neto y costo_real_neto de cierre permiten margen_real_neto = presupuesto_neto - costo_real_neto, exclusivamente en Obras finalizadas con cierre. No llamar «margen proyectado» a datos de obras en ejecución. El monto_documentado corresponde al importe bruto de documento externo, mientras pagado corresponde a abonos confirmados fuera de FYAG; nunca sumar ambos ni compararlos con presupuesto neto sin indicar base. Un cierre SIN_COBRO no equivale a ingreso. No emitir cifras tributarias ni afirmar pagos bancarios ejecutados por la app.

## 3. Contrato REST y ejemplos
- GET /api/dashboard/resumen/?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
- GET /api/dashboard/serie-obras/?meses=6
- GET /api/dashboard/obras-activas/?page=1

Filtros fecha civil Santiago, ambos extremos juntos, inclusivos, máximo 366 días, default seis meses civiles hasta hoy. meses entero 1–12. Página DRF 25, orden estable; parámetros desconocidos/duplicados o fecha invertida 400. Endpoints solo lectura; POST/PATCH/PUT/DELETE 405.

Respuesta de resumen sintética para fijar nombres/tipos:

~~~json
{
  "generado_en": "2026-11-11T18:30:00-03:00",
  "zona_horaria": "America/Santiago", "moneda": "CLP",
  "periodo": {"desde": "2026-06-01", "hasta": "2026-11-11"},
  "operacion": {
    "obras_por_estado_actual": {"PLANIFICADA": 0, "EN_PROCESO": 0, "SUSPENDIDA": 0, "FINALIZADA": 0, "CANCELADA": 0},
    "presupuestos_pendientes_gerencia_actual": 0,
    "obras_finalizadas_periodo": 0
  },
  "rentabilidad_cerrada_periodo": {
    "obras_con_cierre": 0, "presupuesto_neto": "0.00",
    "costo_real_neto": "0.00", "margen_real_neto": "0.00"
  },
  "cobranza_actual": {
    "documentos_vigentes": 0, "monto_documentado_bruto": "0.00",
    "abonado": "0.00", "saldo": "0.00", "saldo_vencido": "0.00"
  }
}
~~~

El periodo aplica a las métricas denominadas periodo por fecha finalizado_en; conteos estado_actual y cobranza_actual son una fotografía del momento actual, aunque exista filtro de periodo. **Nunca** presentarlas como histórico reconstruido.

Serie devuelve exactamente meses puntos mensuales consecutivos ascendentes: {"metrica":"OBRAS_FINALIZADAS","zona_horaria":"America/Santiago","puntos":[{"mes":"2026-11","cantidad":0}]}; cada mes corresponde a finalizado_en, no a fecha de creación. Obras activas devuelve count,next,previous,results con id,codigo,cliente,cliente_nombre,categoria_nombre,estado,tecnico_responsable,tecnico_nombre,fecha_programada,presupuesto_neto; no añadir avance_pct, costo provisional como cierre ni margen inventado.

## 4. Cálculo, filtros, validación y concurrencia

Filtrar y agregar en PostgreSQL; limitar trabajo y evitar N+1. Todos los importes salen como strings decimales exactos; no recalcular en React. La información «actual» se presenta explícitamente distinta de la «filtrada por periodo». Un `CierreCostosObra` ausente en una Obra finalizada no se interpreta como costo cero. Para `cobranza_actual`, reutilizar `con_cobranza` y sus invariantes.

## 5. Arquitectura y migraciones

Read model de `apps.dashboard` sobre `apps.obras`, `apps.comercial` y `apps.finanzas`. Preferir adaptadores de consulta y servicio; sin nuevos modelos persistentes ni migraciones por defecto. Añadir rutas en `config.urls` únicamente en el PR de código, no en la documentación.

## 6. Matriz de pruebas y criterios de aceptación
Reutilizar consultas económicas originales y agregaciones Django/PostgreSQL, nunca float ni cómputos en React. Las cadenas monetarias tienen dos decimales exactos (ej. "0.00"), pudiendo ser negativo el margen. No ocultar inconsistencia de cierre con cero. Tests de periodos vacíos, grandes montos, cortesías, filtros, DST Santiago, concurrencia financiera, exactitud frente a APIs de origen y casos 401/403/405. Auditar rendimiento, N+1, uso de índices y salida bounded. Los feeds de Alertas y Auditoría se cargan desde sus APIs separadas para no acoplar el Dashboard a nuevos servicios. Backend CI y Postman obligatorios.

## 7. Fuera de alcance

No gestión de costos, cobros, registro de pagos, alertas, creación de reportes, definición de porcentaje de avance ni métricas proyectadas sin base validada. No UI. Alertas y auditoría se consumen en endpoints independientes si están implementados.

## 8. Entrega y flujo de integración

OpenCode implementa en rama separada con pruebas PostgreSQL y entrega informe técnico de cambios y ejecución real **antes de commit/push**. Tras revisión, commits y PR descriptivos; ChatGPT revisa código/CI en GitHub y entrega Postman cuando corresponda; usuario lo ejecuta; merge solo con autorización explícita. Notificar cada SPEC publicada para actualizar copia local.

## 9. Fuentes verificadas

`backend/apps/{dashboard,comercial,obras,finanzas}/`, `backend/config/urls.py`, SPEC-003/004/007, SPEC-006B.
