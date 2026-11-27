import { ApiError } from '../auth/client.js';
import { decimalString, positiveInteger, readPage, strictObject } from './useApi.js';

export const FINANCIAL_STATES = ['PENDIENTE_FACTURACION', 'PENDIENTE_REGISTRO_SIN_COBRO', 'SIN_COBRO', 'DOCUMENTADO'];
const invalid = () => { throw new ApiError(502, 'Respuesta financiera incompatible con el contrato. Reconsulta antes de continuar.'); };
export function financialOrigin(value) {
  strictObject(value, ['obra','codigo_obra','presupuesto','codigo_presupuesto','cliente','moneda','monto_neto_aprobado','finalizado_en','cortesia']);
  strictObject(value.cliente, ['id','nombre_legal','tipo_identificacion','numero_identificacion','pais_identificacion','tipo_documento_extranjero']);
  if (!positiveInteger(value.obra) || !positiveInteger(value.presupuesto) || !positiveInteger(value.cliente.id)
      || typeof value.codigo_obra !== 'string' || typeof value.codigo_presupuesto !== 'string' || typeof value.cliente.nombre_legal !== 'string'
      || value.moneda !== 'CLP' || !decimalString(value.monto_neto_aprobado)
      || (value.finalizado_en !== null && typeof value.finalizado_en !== 'string')) invalid();
  if (value.cortesia !== null) {
    strictObject(value.cortesia, ['id','tipo']);
    if (!positiveInteger(value.cortesia.id) || value.cortesia.tipo !== 'SIN_COBRO') invalid();
  }
  return value;
}
export function financialDocument(value) {
  strictObject(value, ['id','naturaleza','origen','tipo_documento','folio_externo','fecha_emision','fecha_vencimiento','monto_neto','monto_impuesto','monto_total','referencia_respaldo','estado','registrado_por','registrado_en','revertido_por','revertido_en','motivo_reversion','referencia_rectificacion_externa','cobranza']);
  financialOrigin(value.origen);
  if (!positiveInteger(value.id) || value.naturaleza !== 'REGISTRO_ADMINISTRATIVO_DOCUMENTO_EXTERNO'
      || !['VIGENTE','REVERTIDO'].includes(value.estado) || !['FACTURA_AFECTA','FACTURA_EXENTA'].includes(value.tipo_documento)
      || !/^[0-9]+$/.test(value.folio_externo) || !['monto_neto','monto_impuesto','monto_total'].every((key) => decimalString(value[key]))) invalid();
  // Documentos revertidos tienen cobranza=null, no un saldo ficticio.
  if (value.cobranza !== null) {
    strictObject(value.cobranza, ['moneda','abonado','saldo','estado']);
    if (value.cobranza.moneda !== 'CLP' || !decimalString(value.cobranza.abonado) || !decimalString(value.cobranza.saldo)
        || !['PENDIENTE','PARCIAL','PAGADA','VENCIDA'].includes(value.cobranza.estado)) invalid();
  }
  return value;
}
export function financialPayment(value) {
  strictObject(value, ['id','naturaleza','documento','monto','fecha_pago','medio','referencia_respaldo','observacion','registrado_por','registrado_en','activo','anulado_por','anulado_en','motivo_anulacion','referencia_reversion_externa']);
  if (!positiveInteger(value.id) || !positiveInteger(value.documento) || !decimalString(value.monto)
      || value.naturaleza !== 'REGISTRO_ADMINISTRATIVO_DINERO_RECIBIDO' || typeof value.activo !== 'boolean'
      || !['TRANSFERENCIA','EFECTIVO','TARJETA','OTRO'].includes(value.medio)) invalid();
  return value;
}
export function financialEvent(value) {
  strictObject(value, ['id','documento','cierre_sin_cobro','pago','tipo','actor','motivo','datos_anteriores','datos_nuevos','creado_en']);
  if (!positiveInteger(value.id) || !positiveInteger(value.actor) || typeof value.tipo !== 'string' || typeof value.motivo !== 'string'
      || typeof value.creado_en !== 'string' || !value.datos_anteriores || !value.datos_nuevos) invalid();
  return value;
}
export function financialState(value, obra) {
  strictObject(value, ['origen','estado_financiero','documento_vigente','cierre_sin_cobro']);
  financialOrigin(value.origen);
  if (value.origen.obra !== Number(obra) || !FINANCIAL_STATES.includes(value.estado_financiero)) invalid();
  if (value.documento_vigente !== null) {
    financialDocument(value.documento_vigente);
    if (value.documento_vigente.origen.obra !== Number(obra) || value.documento_vigente.estado !== 'VIGENTE') invalid();
  }
  if (value.cierre_sin_cobro !== null) {
    strictObject(value.cierre_sin_cobro, ['id','cortesia','motivo_registro','registrado_por','registrado_en','eventos']);
    if (!positiveInteger(value.cierre_sin_cobro.id) || !positiveInteger(value.cierre_sin_cobro.cortesia)
        || typeof value.cierre_sin_cobro.motivo_registro !== 'string' || !Array.isArray(value.cierre_sin_cobro.eventos)) invalid();
    value.cierre_sin_cobro.eventos.forEach(financialEvent);
  }
  if ((value.estado_financiero === 'DOCUMENTADO') !== (value.documento_vigente !== null)
      || (value.estado_financiero === 'SIN_COBRO') !== (value.cierre_sin_cobro !== null)) invalid();
  return value;
}
export function financialPage(value, path, project, filters = null) {
  return { ...readPage(value, path, 25, filters), results: value.results.map(project) };
}
export const safeFinancialId = (value) => /^[1-9][0-9]*$/.test(String(value)) && positiveInteger(Number(value));
export function canRegisterWithoutCharge(state) {
  // Esta proyección no expone presupuesto.estado ni el cierre de costos;
  // su comprobación definitiva pertenece exclusivamente al servicio de Django.
  return state?.estado_financiero === 'PENDIENTE_REGISTRO_SIN_COBRO'
    && !!state.origen.finalizado_en && state.origen.cortesia?.tipo === 'SIN_COBRO';
}
