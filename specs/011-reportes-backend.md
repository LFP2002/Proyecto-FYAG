# SPEC-011 — Reportes y exportaciones reales

**Estado: especificada, NO implementada.** apps.reportes es aún un esqueleto; los botones PDF/Excel/CSV del antiguo prototipo no exportan archivos reales. Esta API estabiliza las necesidades del futuro frontend.

## Matriz RBAC
GERENCIA: reportes obras, rentabilidad y cobranzas (consulta y exportación). ADMINISTRATIVO_FINANZAS: solo cobranzas. SUPERVISOR_OBRAS, TECNICO, ADMINISTRADOR_TI: acceso denegado. La proyección financiera AF nunca contendrá costos internos, tarifas, evidencias privadas ni rentabilidad. No permitir bypass por flags heredados Django.

## Endpoints contractuales
- GET /api/reportes/catalogo/ — tipos y formatos permitidos para el actor.
- GET /api/reportes/obras/ — G, filas paginadas.
- GET /api/reportes/rentabilidad/ — G, filas paginadas.
- GET /api/reportes/cobranzas/ — G/AF, filas paginadas.
- GET /api/reportes/{tipo}/exportar/?formato=csv|xlsx|pdf&desde=YYYY-MM-DD&hasta=YYYY-MM-DD — archivo real.

Lista JSON: count,next,previous,results,totales,periodo,moneda,fecha_corte; 25 resultados por página, los totales son de TODO el filtro y no solo de la página. Periodo default mes calendario actual en Santiago; rango máximo 366 días; desde y hasta deben ir juntos. Filtros opcionales cliente (PK positiva), estado (whitelist por tipo), y fecha_base para obras (CREACION/FINALIZACION); estrictos, sin duplicados ni desconocidos. No permitir page en exportación ni formato en JSON. El estado de Obra se interpreta actual, no histórico reconstruido.

- obras: fecha_base=CREACION (default) usa creado_en; FINALIZACION usa finalizado_en.
- rentabilidad: solo FINALIZADA con CierreCostosObra inmutable, filtro por finalizado_en; presupuesto_neto menos costo_real_neto = margen_neto; incluir indicador de cortesía SIN_COBRO, sin confundir margen con ingreso/cobro efectivo.
- cobranzas: documentos VIGENTE por fecha_emision; folio externo sin perder ceros, fecha_vencimiento, monto_total bruto, abonado activo, saldo y estado derivado desde la consulta de Finanzas. Nunca sumar pagos anulados ni sumar un pago como documento adicional.

Ejemplo de fila de rentabilidad (datos de muestra):

~~~json
{
  "obra": 37, "codigo_obra": "OB-000037",
  "cliente": 18, "cliente_nombre": "Empresa ejemplo",
  "finalizado_en": "2026-11-11T14:00:00-03:00",
  "moneda": "CLP", "presupuesto_neto": "1250000.00",
  "costo_real_neto": "900000.00", "margen_neto": "350000.00",
  "tiene_cortesia_sin_cobro": false
}
~~~

Se deben congelar nombres, nulabilidad y schemas de filas para cada tipo antes de que frontend implemente. Montos siempre strings Decimal con dos decimales, sin floats ni notación científica.

## Exportación real y control de riesgos
CSV: UTF-8, delimitador documentado, comillas/CRLF seguros, neutralización de inyección de fórmulas Excel en entradas de usuario (=, +, -, @ y controles); importes negativos válidos no deben transformarse en fórmulas. XLSX: OOXML genuino, sin macros ni fórmulas inyectadas; importes con más de 15 dígitos significativos como texto exacto para no perder precisión. PDF: documento legible con zona/periodo/corte/moneda, tablas con saltos de página, sin simular DTE del SII.

Para 200 export devolver MIME exacto, Content-Disposition attachment y nosniff. Máximo 10.000 filas por export sincrónica; 413 con code exportacion_demasiado_grande si excede, 429 para throttle según política, nunca 500 por agotamiento no controlado. Datos temporales privados y limpieza garantizada. Registrar metadata de exportación autorizada en auditoría sin almacenar el archivo ni duplicar PII.

El frontend deberá descargar con fetch autenticado y Blob: el cliente actual procesa JSON; adaptar el **frontend** al transporte binario sin solicitar cambios a los endpoints pactados. No enviar access JWT por URL ni publicar links de exportación desprotegidos.

## QA
Contrastar JSON vs CSV/XLSX/PDF para idénticos filtros, totales de todas las páginas, exactitud financiera y permisos por rol. Tests de BOM/acento, folios con ceros, gran precisión, celdas formula-injection, sin registros, límites 10.000, content-type, content-disposition, 400/401/403/404/405/413/429, concurrencia de pagos/reversiones y no duplicación económica. CI backend Django/PostgreSQL y Postman (más inspección de binarios) antes de marcar “listo”. Si solo se entrega CSV y no PDF/XLSX, SPEC-011 sigue parcial, no completa.
