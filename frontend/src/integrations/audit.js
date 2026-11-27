import { civilRange, isoDate, todayInSantiago } from './dates.js';

export const AUDIT_MODULES = {
  GERENCIA: ['COMERCIAL', 'OBRAS', 'FINANZAS'], SUPERVISOR_OBRAS: ['OBRAS'],
  ADMINISTRATIVO_FINANZAS: ['FINANZAS'], ADMINISTRADOR_TI: ['USUARIOS'],
};
export const MODULE_SOURCES = {
  COMERCIAL: ['PRESUPUESTO_EVENTO'],
  OBRAS: ['OBRA_EVENTO', 'PARTICIPANTE_EVENTO', 'CATEGORIA_SERVICIO_EVENTO', 'TURNO_EVENTO', 'COSTO_OBRA_EVENTO'],
  FINANZAS: ['FINANZAS_EVENTO'], USUARIOS: ['USUARIO_EVENTO', 'RECUPERACION_CORREO_EVENTO', 'RECUPERACION_TI_EVENTO', 'EVENTO_ACCESO'],
};
export const RECOVERY_SOURCE = 'RECUPERACION_CORREO_EVENTO';
export const RECOVERY_TYPE = 'RECUPERACION_CORREO';
export const RECOVERY_AUTHORITY = 'TITULARIDAD_CORREO';
export const INFRA_SOURCE = 'RECUPERACION_TI_EVENTO';
export const INFRA_TYPE = 'RECUPERACION_TI_INFRA';
export const INFRA_AUTHORITY = 'INFRAESTRUCTURA';
export const ACCESS_SOURCE = 'EVENTO_ACCESO';
export const ACCESS_EVENT_LABELS = Object.freeze({BLOQUEO_TEMPORAL:'Bloqueo temporal', BLOQUEO_TI:'Bloqueo hasta recuperación', EXPIRACION:'Vencimiento del bloqueo'});
export const validAccessSnapshot = (data) => !!data && Object.keys(data).length === 1 && Object.hasOwn(data, 'acceso_estado') && Object.hasOwn(ACCESS_STATE_LABELS, data.acceso_estado);
export const validInfraDetails = (data) => !!data && Object.keys(data).length === 2
  && ['operador', 'referencia'].every(key => Object.hasOwn(data, key) && typeof data[key] === 'string' && data[key].length > 0);
export const ACCESS_STATE_LABELS = Object.freeze({NORMAL:'Normal', BLOQUEO_TEMPORAL:'Bloqueo temporal', REQUIERE_TI:'Requiere TI'});
export const AUDIT_SOURCES = Object.values(MODULE_SOURCES).flat();
export function auditSources(role, module = '') {
  const modules = AUDIT_MODULES[role] || [];
  return modules.filter((name) => !module || name === module).flatMap((name) => MODULE_SOURCES[name])
    .filter((source) => role !== 'SUPERVISOR_OBRAS' || source !== 'CATEGORIA_SERVICIO_EVENTO');
}
export function validAuditRange({ desde, hasta }, today = todayInSantiago()) {
  if ((desde && !isoDate(desde)) || (hasta && !isoDate(hasta))) return false;
  // Defaults del serializer de auditoría: hasta=hoy, desde=hasta-29 días.
  const end = hasta || today;
  if (end === '9999-12-31' || !isoDate(end)) return false;
  const start = desde || new Date(Date.parse(`${end}T00:00:00Z`) - 29 * 86400000).toISOString().slice(0, 10);
  return civilRange(start, end);
}
