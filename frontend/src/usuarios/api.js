import { ApiError, USER_ROLES } from '../auth/client.js';
import { validatePage } from '../comercial/api.js';
import { ACCESS_STATE_LABELS, ACCESS_EVENT_LABELS, validAccessSnapshot, RECOVERY_SOURCE, RECOVERY_TYPE, RECOVERY_AUTHORITY, INFRA_SOURCE, INFRA_TYPE, INFRA_AUTHORITY, validInfraDetails } from '../integrations/audit.js';

export const canManageUsers = (role) => role === 'ADMINISTRADOR_TI';
const id = (pk) => {
  if (!Number.isSafeInteger(pk) || pk <= 0) throw new ApiError(400, 'ID no válido.');
  return pk;
};
export const userPath = (pk) => `/api/usuarios/${pk === undefined ? '' : `${id(pk)}/`}`;
export function usersPath(page = 1, { rol = '', activo = '', buscar = '', resumen = false } = {}) {
  const params = new URLSearchParams({ page: String(id(page)) });
  if (rol) {
    if (!USER_ROLES.includes(rol)) throw new ApiError(400, 'Rol no válido.');
    params.set('rol', rol);
  }
  if (activo) {
    if (!['true', 'false'].includes(activo)) throw new ApiError(400, 'Estado no válido.');
    params.set('activo', activo);
  }
  if (buscar) {
    if(typeof buscar!=='string'||buscar.trim().length>150||!buscar.trim()||/[\x00-\x1f]/.test(buscar)) throw new ApiError(400,'Búsqueda no válida.');
    params.set('buscar',buscar.trim());
  }
  if(resumen)params.set('resumen','true');
  return `${userPath()}?${params}`;
}
export const historyPath = (pk, page = 1) => `${userPath(pk)}historial/?page=${id(page)}`;
export function readUser(data) {
  if (!data || !Number.isSafeInteger(data.id) || data.id <= 0 || !USER_ROLES.includes(data.rol)
      || typeof data.is_active !== 'boolean' || ['username', 'email', 'first_name', 'last_name', 'date_joined'].some((key) => typeof data[key] !== 'string')) {
    throw new ApiError(502, 'Respuesta de usuario inesperada.');
  }
  const account=Object.fromEntries(['id','username','email','first_name','last_name','rol','is_active','date_joined'].map(key=>[key,data[key]]));
  if (Object.hasOwn(data, 'correo_verificado_en') || Object.hasOwn(data, 'correo_pendiente')) {
    if ((data.correo_verificado_en !== null && typeof data.correo_verificado_en !== 'string') || typeof data.correo_pendiente !== 'string') {
      throw new ApiError(502, 'Estado de correo inesperado.');
    }
    account.correo_verificado_en = data.correo_verificado_en;
    account.correo_pendiente = data.correo_pendiente;
  }
  if(Object.hasOwn(data,'estado_credencial')){
    if(!['PERSONAL','INICIAL','RECUPERACION','NO_DISPONIBLE'].includes(data.estado_credencial)||typeof data.cambio_obligatorio!=='boolean'||data.cambio_obligatorio!==(data.estado_credencial!=='PERSONAL'))throw new ApiError(502,'Estado de credencial inesperado.');
    account.estado_credencial=data.estado_credencial;
    account.cambio_obligatorio=data.cambio_obligatorio;
  }
  if(Object.hasOwn(data,'estado_acceso')){
    if(typeof data.estado_acceso!=='string'||(data.bloqueado_hasta!==null&&typeof data.bloqueado_hasta!=='string'))throw new ApiError(502,'Estado de acceso inesperado.');
    account.estado_acceso=data.estado_acceso;account.bloqueado_hasta=data.bloqueado_hasta;
  }
  return account;
}
export function readUsers(data) {
  const page = validatePage(data, userPath());
  const result={count:page.count,next:page.next,previous:page.previous,results:page.results.map(readUser)};
  if(Object.hasOwn(data,'resumen')){
    const r=data.resumen;
    if(!r||!['total','activas','inactivas','temporales'].every(k=>Number.isSafeInteger(r[k])&&r[k]>=0)||r.activas+r.inactivas!==r.total||r.temporales>r.total)throw new ApiError(502,'Resumen de cuentas inesperado.');
    result.resumen={total:r.total,activas:r.activas,inactivas:r.inactivas,temporales:r.temporales};
  }
  return result;
}
export function readHistory(data, pk) {
  const page = validatePage(data, `${userPath(pk)}historial/`);
  const fields = new Set(['email', 'username', 'first_name', 'last_name', 'rol', 'is_active']);
  const snapshot = (data) => Object.fromEntries(Object.entries(data || {}).filter(([key, value]) => fields.has(key) && typeof value === (key === 'is_active' ? 'boolean' : 'string')));
  const types = ['CREACION', 'EDICION', 'ACTIVACION', 'DESACTIVACION', 'CAMBIO_ROL', 'ESTABLECER_CLAVE', 'CAMBIO_CLAVE_PROPIA', 'CREACION_CREDENCIAL_TEMPORAL', 'REEMISION', 'CAMBIO_INICIAL', 'CORREO_SOLICITADO', 'CORREO_VERIFICADO', 'CORREO_CAMBIADO'];
  for (const e of page.results) {
    if (e && Object.hasOwn(ACCESS_EVENT_LABELS,e.tipo)) {
      if (!/^EVENTO_ACCESO:[1-9][0-9]*$/.test(e.id) || e.usuario_objetivo !== pk || e.actor !== null || e.actor_identidad_origen !== 'SISTEMA'
        || typeof e.creado_en !== 'string' || !validAccessSnapshot(e.datos_anteriores) || !validAccessSnapshot(e.datos_nuevos)) throw new ApiError(502, 'Historial de usuarios inesperado.');
      continue;
    }
    if (e?.tipo === RECOVERY_TYPE || e?.tipo === INFRA_TYPE) {
      const infra = e.tipo === INFRA_TYPE;
      if (typeof e.id !== 'string' || !new RegExp(`^${infra ? INFRA_SOURCE : RECOVERY_SOURCE}:[1-9][0-9]*$`).test(e.id)
          || e.usuario_objetivo !== pk || e.actor !== null || e.actor_identidad_origen !== (infra ? INFRA_AUTHORITY : RECOVERY_AUTHORITY)
          || (infra && (!validInfraDetails(e.datos_nuevos) || typeof e.motivo !== 'string' || !e.motivo.trim()))
          || typeof e.creado_en !== 'string' || (e.acceso_anterior !== null && !Object.hasOwn(ACCESS_STATE_LABELS, e.acceso_anterior))) {
        throw new ApiError(502, 'Historial de usuarios inesperado.');
      }
      continue;
    }
    if (!e || !Number.isSafeInteger(e.id) || e.id <= 0 || !Number.isSafeInteger(e.actor) || e.actor <= 0
        || !types.includes(e.tipo) || typeof e.motivo !== 'string' || typeof e.creado_en !== 'string') throw new ApiError(502, 'Historial de usuarios inesperado.');
  }
  return { count: page.count, next: page.next, previous: page.previous, results: page.results.map((e) => Object.hasOwn(ACCESS_EVENT_LABELS,e.tipo) ? ({
    id:e.id, tipo:e.tipo, actor:null, actor_identidad_origen:'SISTEMA', usuario_objetivo:pk, creado_en:e.creado_en, motivo:'',
    acceso_anterior:e.datos_anteriores.acceso_estado, acceso_nuevo:e.datos_nuevos.acceso_estado, datos_anteriores:{}, datos_nuevos:{},
  }) : [RECOVERY_TYPE, INFRA_TYPE].includes(e.tipo) ? ({
    id: e.id, tipo: e.tipo, actor: null, actor_identidad_origen: e.actor_identidad_origen, usuario_objetivo: pk,
    acceso_anterior: e.acceso_anterior, motivo: e.tipo === INFRA_TYPE ? e.motivo : '', creado_en: e.creado_en, datos_anteriores: {},
    datos_nuevos: e.tipo === INFRA_TYPE ? {operador: e.datos_nuevos.operador, referencia: e.datos_nuevos.referencia} : {},
  }) : ({
    id: e.id, tipo: e.tipo, actor: e.actor, motivo: e.motivo, creado_en: e.creado_en,
    ...(e.tipo === 'REEMISION' && validAccessSnapshot(e.datos_anteriores) && validAccessSnapshot(e.datos_nuevos) ? {acceso_anterior:e.datos_anteriores.acceso_estado, acceso_nuevo:e.datos_nuevos.acceso_estado} : {}),
    datos_anteriores: ['ESTABLECER_CLAVE', 'CAMBIO_CLAVE_PROPIA', 'CREACION_CREDENCIAL_TEMPORAL', 'REEMISION', 'CAMBIO_INICIAL'].includes(e.tipo) ? {} : snapshot(e.datos_anteriores),
    datos_nuevos: ['ESTABLECER_CLAVE', 'CAMBIO_CLAVE_PROPIA', 'CREACION_CREDENCIAL_TEMPORAL', 'REEMISION', 'CAMBIO_INICIAL'].includes(e.tipo) ? {} : snapshot(e.datos_nuevos),
  })) };
}
