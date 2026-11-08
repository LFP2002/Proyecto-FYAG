import { ApiError } from '../auth/client.js';
const id = (value) => {
  if (!Number.isSafeInteger(value) || value <= 0) throw new ApiError(400, 'ID no válido.');
  return value;
};
export const clientPath = (pk) => `/api/clientes/${pk === undefined ? '' : `${id(pk)}/`}`;
export const budgetPath = (pk) => `/api/presupuestos/${pk === undefined ? '' : `${id(pk)}/`}`;
export function pagePath(path, page = 1) { return `${path}?page=${id(page)}`; }
export function validatePage(data, path) {
  if (!Array.isArray(data?.results) || !Number.isSafeInteger(data.count) || data.count < 0) throw new ApiError(502, 'Paginación inesperada.');
  for (const link of [data.next, data.previous]) {
    if (!link) continue;
    const base = globalThis.location?.origin || 'http://localhost';
    const url = new URL(link, base);
    // DRF omite ?page=1 en previous al volver a la primera página.
    if (url.origin !== base || url.pathname !== path || !/^[1-9][0-9]*$/.test(url.searchParams.get('page') ?? '1')) throw new ApiError(502, 'Enlace de paginación no seguro.');
  }
  return data;
}
export const itemPath = (pk, item) => `${budgetPath(pk)}items/${item === undefined ? '' : `${id(item)}/`}`;
