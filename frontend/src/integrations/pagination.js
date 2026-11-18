import { API_ORIGIN } from '../auth/config.js';

// Solo interpretar: nunca se usa esta URL como destino de fetch.
// Las pantallas extraen la página y reconstruyen su ruta y filtros locales.
export function paginationURL(link, path) {
  const frontendOrigin = globalThis.location?.origin || 'http://localhost';
  if (typeof link !== 'string' || !link || /[\s\\#]/.test(link)
      || !/^\/api\/[a-zA-Z0-9/_-]+\/$/.test(path)) throw new Error('Página inválida.');
  const url = new URL(link, `${frontendOrigin}${path}`);
  if (![frontendOrigin, API_ORIGIN].filter(Boolean).includes(url.origin)
      || url.username || url.password || url.hash || url.pathname !== path
      || [...url.searchParams.keys()].some((key) => url.searchParams.getAll(key).length !== 1 || !url.searchParams.get(key))) {
    throw new Error('Página no confiable.');
  }
  return url;
}

export function samePageFilters(url, filters) {
  const actual = new URLSearchParams(url.search); actual.delete('page');
  const expected = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== '' && value != null) expected.set(key, String(value));
  actual.sort(); expected.sort();
  return actual.toString() === expected.toString();
}
