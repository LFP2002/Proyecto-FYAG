import { ApiError, USER_ROLES } from '../auth/client.js';
import { validatePage } from '../comercial/api.js';

export const canManageUsers = (role) => role === 'ADMINISTRADOR_TI';
const id = (pk) => {
  if (!Number.isSafeInteger(pk) || pk <= 0) throw new ApiError(400, 'ID no válido.');
  return pk;
};
export const userPath = (pk) => `/api/usuarios/${pk === undefined ? '' : `${id(pk)}/`}`;
export function usersPath(page = 1, { rol = '', activo = '' } = {}) {
  const params = new URLSearchParams({ page: String(id(page)) });
  if (rol) {
    if (!USER_ROLES.includes(rol)) throw new ApiError(400, 'Rol no válido.');
    params.set('rol', rol);
  }
  if (activo) {
    if (!['true', 'false'].includes(activo)) throw new ApiError(400, 'Estado no válido.');
    params.set('activo', activo);
  }
  return `${userPath()}?${params}`;
}
export const historyPath = (pk, page = 1) => `${userPath(pk)}historial/?page=${id(page)}`;
export function readUser(data) {
  if (!data || !Number.isSafeInteger(data.id) || data.id <= 0 || !USER_ROLES.includes(data.rol)
      || typeof data.is_active !== 'boolean' || ['username', 'email', 'first_name', 'last_name', 'date_joined'].some((key) => typeof data[key] !== 'string')) {
    throw new ApiError(502, 'Respuesta de usuario inesperada.');
  }
  return Object.fromEntries(['id', 'username', 'email', 'first_name', 'last_name', 'rol', 'is_active', 'date_joined'].map((key) => [key, data[key]]));
}
export function readUsers(data) {
  const page = validatePage(data, userPath());
  return { count: page.count, next: page.next, previous: page.previous, results: page.results.map(readUser) };
}
export function readHistory(data, pk) {
  const page = validatePage(data, `${userPath(pk)}historial/`);
  const fields = new Set(['email', 'username', 'first_name', 'last_name', 'rol', 'is_active']);
  const snapshot = (data) => Object.fromEntries(Object.entries(data || {}).filter(([key, value]) => fields.has(key) && typeof value === (key === 'is_active' ? 'boolean' : 'string')));
  const types = ['CREACION', 'EDICION', 'ACTIVACION', 'DESACTIVACION', 'CAMBIO_ROL', 'ESTABLECER_CLAVE', 'CAMBIO_CLAVE_PROPIA'];
  for (const e of page.results) {
    if (!e || !Number.isSafeInteger(e.id) || e.id <= 0 || !Number.isSafeInteger(e.actor) || e.actor <= 0
        || !types.includes(e.tipo) || typeof e.motivo !== 'string' || typeof e.creado_en !== 'string') throw new ApiError(502, 'Historial de usuarios inesperado.');
  }
  return { count: page.count, next: page.next, previous: page.previous, results: page.results.map((e) => ({
    id: e.id, tipo: e.tipo, actor: e.actor, motivo: e.motivo, creado_en: e.creado_en,
    datos_anteriores: /CLAVE/.test(e.tipo) ? {} : snapshot(e.datos_anteriores),
    datos_nuevos: /CLAVE/.test(e.tipo) ? {} : snapshot(e.datos_nuevos),
  })) };
}
