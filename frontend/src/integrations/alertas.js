import {strictObject,positiveInteger} from './useApi.js';

const RULES = {
  PRESUPUESTO_PENDIENTE_FINANZAS: { responsable:'ADMINISTRATIVO_FINANZAS', lectores:['ADMINISTRATIVO_FINANZAS'], recurso:'PRESUPUESTO', severidad:'MEDIA', label:'Presupuesto pendiente de Finanzas' },
  OBRA_SUSPENDIDA: { responsable:'SUPERVISOR_OBRAS', lectores:['SUPERVISOR_OBRAS','GERENCIA'], recurso:'OBRA', severidad:'ALTA', label:'Obra suspendida' },
  TURNO_PENDIENTE_REVISION: { responsable:'SUPERVISOR_OBRAS', lectores:['SUPERVISOR_OBRAS'], recurso:'TURNO', severidad:'MEDIA', label:'Turno pendiente de revisión' },
  COBRANZA_VENCIDA: { responsable:'ADMINISTRATIVO_FINANZAS', lectores:['ADMINISTRATIVO_FINANZAS','GERENCIA'], recurso:'DOCUMENTO', severidad:'ALTA', label:'Cobranza vencida' },
};
const typesFor = role => Object.keys(RULES).filter(type=>RULES[type].lectores.includes(role));
const STATES = ['PENDIENTE', 'ATENDIDA', 'RESUELTA', 'TODAS'];
const alertKeys = ['id','tipo','estado','severidad','rol_destinatario','rol_responsable','destinatarios','es_legada','generacion','recurso_tipo','recurso_id','recurso_codigo','obra','titulo','descripcion','creado_en','atendida_por','atendida_en','motivo_atencion','resuelta_en','acciones_permitidas'];
function alertRow(row, role) {
  strictObject(row, alertKeys);
  const rule = Object.hasOwn(RULES,row.tipo) ? RULES[row.tipo] : null;
  if (!positiveInteger(row.id) || !positiveInteger(row.recurso_id) || !positiveInteger(row.generacion)
    || !rule || !rule.lectores.includes(role) || row.es_legada !== false
    || !['PENDIENTE','ATENDIDA','RESUELTA'].includes(row.estado) || row.severidad !== rule.severidad
    || row.recurso_tipo !== rule.recurso || row.rol_destinatario !== role || row.rol_responsable !== rule.responsable
    || !Array.isArray(row.destinatarios) || row.destinatarios.length !== rule.lectores.length
    || new Set(row.destinatarios).size !== rule.lectores.length || row.destinatarios.some(r=>!rule.lectores.includes(r))
    || typeof row.titulo !== 'string' || typeof row.descripcion !== 'string' || !Array.isArray(row.acciones_permitidas)
    || row.acciones_permitidas.length > 1 || row.acciones_permitidas.some(action=>action!=='ATENDER')
    || (row.acciones_permitidas.length && (role!==rule.responsable || row.estado!=='PENDIENTE'))) throw new Error('Alerta inválida o no autorizada.');
  if (row.recurso_codigo !== null && typeof row.recurso_codigo !== 'string') throw new Error('Código de recurso inválido.');
  if (row.obra !== null && !positiveInteger(row.obra)) throw new Error('Obra inválida.');
  return row;
}
function safePage(path, page, filters = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== '' && value != null) query.set(key, value);
  if (page > 1) query.set('page', String(page));
  return `${path}${query.size ? `?${query}` : ''}`;
}
function summaryShape(value, role) {
  strictObject(value, ['generado_en','zona_horaria','por_estado','activas','por_tipo','sincronizacion']);
  strictObject(value.por_estado, ['PENDIENTE','ATENDIDA','RESUELTA']);
  strictObject(value.sincronizacion, ['ultima_correcta_en','desactualizada']);
  if (value.zona_horaria !== 'America/Santiago' || !Number.isSafeInteger(value.activas)
      || Object.values(value.por_estado).some((count) => !Number.isSafeInteger(count) || count < 0)
      || typeof value.sincronizacion.desactualizada !== 'boolean' || !value.por_tipo || typeof value.por_tipo !== 'object') throw new Error('Resumen de alertas inválido.');
  const allowed = typesFor(role);
  if (Object.keys(value.por_tipo).some((type) => !allowed.includes(type))) throw new Error('El resumen contiene tipos fuera del rol.');
  for (const item of Object.values(value.por_tipo)) { strictObject(item, ['PENDIENTE','ATENDIDA','RESUELTA']); if (Object.values(item).some((count) => !Number.isSafeInteger(count) || count < 0)) throw new Error('Conteo inválido.'); }
  return value;
}


export {RULES,typesFor,STATES,alertRow,safePage,summaryShape};
