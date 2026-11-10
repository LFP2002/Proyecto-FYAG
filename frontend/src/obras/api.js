import { ApiError } from '../auth/client.js';
import { validatePage } from '../comercial/api.js';
import { filterErrors, validId } from './domain.js';
export const idPath = (value) => {
  if (!Number.isSafeInteger(value) || value <= 0) throw new ApiError(400, 'Identificador no válido.');
  return String(value);
};
export const obraPath = (id) => `/api/obras/${id === undefined ? '' : `${idPath(id)}/`}`;
export const categoryPath = (id) => `/api/categorias-servicio/${id === undefined ? '' : `${idPath(id)}/`}`;
export const memberPath = (obra, member) => `${obraPath(obra)}participantes/${idPath(member)}/desasignar/`;
export function collectionPath(path, page = 1, filters = {}) {
  const allowed = path === obraPath() || path === '/api/obras/mis-obras/'
    ? ['estado', 'cliente', 'tecnico_responsable', 'categoria_servicio', 'fecha_programada_desde', 'fecha_programada_hasta', 'ordering']
    : path === categoryPath() || /^\/api\/obras\/\d+\/participantes\/$/.test(path) ? ['activo'] : [];
  if (!validId(page)) throw new ApiError(400, 'Página inválida.');
  const query = new URLSearchParams({ page: String(page) });
  for (const [key, value] of Object.entries(filters)) {
    if (!allowed.includes(key)) throw new ApiError(400, 'Filtro no permitido.');
    if (value !== '' && value !== null && value !== undefined) query.set(key, String(value));
  }
  if (allowed.includes('estado') && Object.keys(filterErrors(filters)).length) throw new ApiError(400, 'Revisa los filtros.');
  if (query.has('activo') && !['true', 'false'].includes(query.get('activo'))) throw new ApiError(400, 'Filtro de actividad inválido.');
  return `${path}?${query}`;
}
export function readPage(data, path) {
  const result = validatePage(data, path);
  if (result.results.length > 25) throw new ApiError(502, 'Paginación inesperada.');
  return result;
}
