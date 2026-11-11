// Origen explícito de confianza, no URL controlada por una respuesta de API.
export function trustedOrigin(value = '') {
  if (!value) return '';
  const url = new URL(value);
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))
      || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('VITE_API_BASE_URL debe ser un origen HTTPS sin ruta ni credenciales.');
  }
  return url.origin;
}
export const API_ORIGIN = trustedOrigin(import.meta.env?.VITE_API_BASE_URL || '');
