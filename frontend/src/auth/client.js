// Access y CSRF solo en esta instancia en memoria. La cookie de refresh la
// administra el navegador; nunca se lee desde JavaScript ni se devuelve un token.
import { API_ORIGIN, trustedOrigin } from './config.js';
export const USER_ROLES = Object.freeze([
  'GERENCIA', 'ADMINISTRATIVO_FINANZAS', 'SUPERVISOR_OBRAS', 'TECNICO',
  'ADMINISTRADOR_TI',
]);

export class ApiError extends Error {
  constructor(status, message, retryAfter = null, { fieldErrors = {}, code = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.retryAfter = retryAfter;
    this.fieldErrors = fieldErrors;
    this.code = code;
  }
}

function messageFor(status) {
  return ({
    400: 'Revisa los datos ingresados.',
    401: 'Credenciales inválidas o sesión no disponible.',
    403: 'Solicitud rechazada. Verifica tus permisos o vuelve a intentarlo.',
    404: 'El recurso ya no está disponible.',
    405: 'Esta operación no está permitida.',
    409: 'El recurso cambió o no permite esta acción. Vuelve a consultar antes de continuar.',
    429: 'Demasiados intentos. Espera antes de volver a intentar.',
  })[status] || 'No fue posible completar la solicitud. Inténtalo nuevamente.';
}

export function createAuthClient({ fetchImpl = (...args) => fetch(...args), apiOrigin = API_ORIGIN } = {}) {
  const origin = trustedOrigin(apiOrigin);
  let access = null;
  let csrf = null;
  let epoch = 0;
  let csrfFlight = null;
  let refreshFlight = null;
  let loginFlight = null;
  let logoutFlight = null;
  let restoreFlight = null;
  let snapshot = Object.freeze({ status: 'restoring', user: null, notice: null });
  const listeners = new Set();

  function emit(status, user = null, notice = null) {
    snapshot = Object.freeze({ status, user, notice });
    listeners.forEach((listener) => listener());
  }

  function assertCurrent(version) {
    if (version !== epoch) throw new ApiError(401, 'La sesión cambió. Inicia sesión nuevamente.');
  }

  function clear(notice = null) {
    epoch += 1;
    access = null;
    emit('anonymous', null, notice);
  }

  async function http(path, { method = 'GET', body, token, csrfToken, headers = {}, signal } = {}) {
    // No enviar credenciales a URLs externas, ni seguir redirecciones de API.
    if (typeof path !== 'string' || !path.startsWith('/api/') || path.includes('\\') || path.startsWith('/api//')
        || !new URL(path, 'https://request.invalid').pathname.startsWith('/api/')) {
      throw new ApiError(400, 'La ruta debe pertenecer a la API del mismo origen.');
    }
    const requestHeaders = new Headers(headers);
    requestHeaders.delete('Authorization');
    requestHeaders.delete('X-CSRFToken');
    requestHeaders.set('Accept', 'application/json');
    if (body !== undefined) requestHeaders.set('Content-Type', 'application/json');
    if (token) requestHeaders.set('Authorization', `Bearer ${token}`);
    if (csrfToken) requestHeaders.set('X-CSRFToken', csrfToken);
    let response;
    try {
      response = await fetchImpl(origin ? `${origin}${path}` : path, {
        method, headers: requestHeaders, credentials: origin ? 'include' : 'same-origin', redirect: 'error',
        cache: 'no-store', signal, ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
    } catch {
      throw new ApiError(0, 'No hay conexión con el servidor. Comprueba tu conexión e inténtalo nuevamente.');
    }
    if (!response.ok) {
      let fields = {}, code = null;
      // Solo campos públicos de validación; nunca HTML, trazas o tokens.
      if ([400, 409].includes(response.status) && !path.startsWith('/api/auth/')) {
        try {
          const data = await response.json();
          const allowed = new Set(['tipo_cliente', 'tipo_identificacion', 'numero_identificacion', 'pais_identificacion', 'tipo_documento_extranjero', 'nombre_legal', 'nombre_contacto', 'correo', 'telefono', 'cliente', 'descripcion', 'cantidad', 'unidad', 'precio_unitario', 'orden', 'motivo', 'non_field_errors', 'detail']);
          if (path.startsWith('/api/obras/') || path.startsWith('/api/categorias-servicio/')) {
            for (const field of ['presupuesto', 'categoria_servicio', 'tecnico_responsable', 'tecnico', 'fecha_programada', 'nombre', 'estado', 'activo', 'ordering', 'fecha_programada_desde', 'fecha_programada_hasta', 'page']) allowed.add(field);
          }
          if (path.startsWith('/api/usuarios/')) {
            for (const field of ['email', 'username', 'first_name', 'last_name', 'rol', 'password', 'nueva_clave', 'activo', 'page']) allowed.add(field);
          }
          const safe = (v) => typeof v === 'string' && v.length <= 500 && !/[<>\x00-\x1f]|traceback|bearer|token|password|sql|constraint/i.test(v);
          for (const [key, value] of Object.entries(data || {})) {
            const values = Array.isArray(value) ? value : [value];
            if (allowed.has(key) && values.length <= 10 && values.every(safe)) fields[key] = values;
          }
          if (['presupuesto_utilizado', 'estado_incompatible'].includes(data?.code) || (data?.code === 'sin_cambios' && (path.startsWith('/api/obras/') || path.startsWith('/api/categorias-servicio/')))) code = data.code;
          if (path.startsWith('/api/usuarios/') && ['ultima_ti', 'ultima_gerencia', 'autooperacion_protegida', 'asignaciones_pendientes', 'sin_cambios', 'version_agotada'].includes(data?.code)) code = data.code;
        } catch { /* Respuesta no pública: conservar mensaje genérico. */ }
      }
      throw new ApiError(response.status, messageFor(response.status), response.headers.get('Retry-After'), { fieldErrors: fields, code });
    }
    if (response.status === 204) return null;
    try {
      return await response.json();
    } catch {
      throw new ApiError(502, 'El servidor devolvió una respuesta inesperada.');
    }
  }

  function csrfToken({ force = false } = {}) {
    if (!force && csrf) return Promise.resolve(csrf);
    if (csrfFlight) return csrfFlight;
    const pending = http('/api/auth/csrf/').then((data) => {
      if (typeof data?.csrfToken !== 'string' || !data.csrfToken) throw new ApiError(502, 'No fue posible obtener la protección CSRF.');
      csrf = data.csrfToken;
      return csrf;
    }).finally(() => { if (csrfFlight === pending) csrfFlight = null; });
    csrfFlight = pending;
    return pending;
  }

  function profile(data) {
    if (!data || !Number.isInteger(data.id) || data.id <= 0 || !USER_ROLES.includes(data.role)
        || typeof data.username !== 'string' || typeof data.email !== 'string') {
      throw new ApiError(403, 'No fue posible verificar la identidad y el rol de la cuenta.');
    }
    return Object.freeze({ id: data.id, username: data.username, email: data.email, role: data.role });
  }

  async function identify(token, version) {
    if (typeof token !== 'string' || !token) throw new ApiError(502, 'No fue posible iniciar la sesión.');
    const user = profile(await http('/api/auth/me/', { token }));
    assertCurrent(version);
    return user;
  }

  function renew({ restoring = false } = {}) {
    if (refreshFlight) return refreshFlight;
    const version = epoch;
    const previousUser = snapshot.user;
    const pending = (async () => {
      const protection = await csrfToken();
      assertCurrent(version);
      const data = await http('/api/auth/refresh/', { method: 'POST', body: {}, csrfToken: protection });
      assertCurrent(version);
      const user = await identify(data?.access, version);
      if (previousUser && previousUser.id !== user.id) throw new ApiError(401, 'La identidad de la sesión cambió.');
      access = data.access;
      emit('authenticated', user);
      return access;
    })().catch((error) => {
      if (version === epoch) clear(restoring && error.status === 401 ? null :
        (error.status === 401 ? 'Tu sesión terminó. Inicia sesión nuevamente.' : error.message));
      throw error;
    }).finally(() => { if (refreshFlight === pending) refreshFlight = null; });
    refreshFlight = pending;
    return pending;
  }

  // El backend ya revocó access/refresh al confirmar el PATCH del correo propio.
  // No intentar refresh/logout con tokens obsoletos ni reconsultar datos protegidos.
  function sessionInvalidatedByEmailChange() {
    if (snapshot.status !== 'authenticated' || !snapshot.user) return false;
    clear('Correo actualizado correctamente. Inicia sesión con tu nuevo correo electrónico.');
    return true;
  }

  function restore() {
    // También deduplica el doble efecto de React.StrictMode al montar.
    if (!restoreFlight) restoreFlight = snapshot.status === 'restoring'
      ? renew({ restoring: true }).catch(() => null) : Promise.resolve(snapshot.user);
    return restoreFlight;
  }

  function login({ email, password }) {
    if (logoutFlight) return Promise.reject(new ApiError(400, 'Espera a que termine el cierre de sesión.'));
    if (loginFlight) return loginFlight;
    // No iniciar una nueva rotación mientras se está restaurando la cookie.
    const previousRefresh = refreshFlight;
    const version = ++epoch;
    access = null;
    emit('authenticating');
    const pending = (async () => {
      if (previousRefresh) await previousRefresh.catch(() => null);
      assertCurrent(version);
      if (typeof email !== 'string' || !email.trim() || typeof password !== 'string' || !password) {
        throw new ApiError(400, 'Ingresa el correo y la contraseña.');
      }
      const protection = await csrfToken({ force: true });
      assertCurrent(version);
      const data = await http('/api/auth/login/', {
        method: 'POST', body: { email: email.trim().toLowerCase(), password }, csrfToken: protection,
      });
      assertCurrent(version);
      if (typeof data?.csrfToken !== 'string' || !data.csrfToken) throw new ApiError(502, 'No fue posible verificar la protección CSRF.');
      csrf = data.csrfToken; // Login rota CSRF: no reutilizar el token anterior.
      const user = await identify(data.access, version);
      access = data.access;
      emit('authenticated', user);
      return user;
    })().catch((error) => {
      if (version === epoch) clear(error.message);
      throw error;
    }).finally(() => { if (loginFlight === pending) loginFlight = null; });
    loginFlight = pending;
    return pending;
  }

  function logout() {
    if (logoutFlight) return logoutFlight;
    const pendingAuth = [loginFlight, refreshFlight].filter(Boolean);
    const version = ++epoch;
    access = null;
    emit('logging-out'); // Retirar identidad y contenido antes de esperar la red.
    const pending = (async () => {
      // Una respuesta tardía puede haber rotado la cookie HttpOnly. Revocar
      // después de esas respuestas, sin permitir que restauren la identidad.
      await Promise.allSettled(pendingAuth);
      const protection = await csrfToken({ force: true });
      await http('/api/auth/logout/', { method: 'POST', body: {}, csrfToken: protection });
      if (version === epoch) emit('anonymous');
      return true;
    })().catch(() => {
      if (version === epoch) emit('anonymous', null,
        'Sesión cerrada en este navegador. No se pudo confirmar la revocación remota; vuelve a intentar cerrar sesión.');
      return false;
    }).finally(() => { if (logoutFlight === pending) logoutFlight = null; });
    logoutFlight = pending;
    return pending;
  }

  async function request(path, options = {}) {
    const version = epoch;
    const sentAccess = access;
    if (!sentAccess) throw new ApiError(401, 'Inicia sesión para continuar.');
    try {
      const data = await http(path, { ...options, token: sentAccess });
      assertCurrent(version);
      return data;
    } catch (error) {
      assertCurrent(version);
      if (error.status !== 401) throw error; // Un 403 nunca se disfraza de expiración.
    }
    // Un 401 tardío de otra petición puede llegar después de completar refresh.
    // En ese caso reutilizar el token nuevo, sin otra rotación de cookie.
    if (access === sentAccess) await renew();
    assertCurrent(version);
    try {
      const data = await http(path, { ...options, token: access });
      assertCurrent(version);
      return data;
    } catch (error) {
      if (error.status === 401 && version === epoch) clear('Tu sesión terminó. Inicia sesión nuevamente.');
      throw error;
    }
  }

  return Object.freeze({
    getSnapshot: () => snapshot,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    restore, login, logout, request, sessionInvalidatedByEmailChange,
  });
}

export const authClient = createAuthClient();
