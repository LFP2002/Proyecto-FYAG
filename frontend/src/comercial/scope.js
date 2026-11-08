import { ApiError } from '../auth/client.js';

// Un scope por pantalla/sesión. Nunca reintenta una escritura.
// El límite también cubre una espera de refresh cuyo fetch no recibe el signal
// comercial. Su resultado tardío queda descartado, no se declara éxito.
function bounded(operation, signal) {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(new ApiError(0, 'Solicitud cancelada o sin respuesta a tiempo. Reconsulta antes de continuar.'));
    if (signal.aborted) { aborted(); return; }
    signal.addEventListener('abort', aborted, { once: true });
    try {
      Promise.resolve(operation(signal)).then(resolve, reject).finally(() => signal.removeEventListener('abort', aborted));
    } catch (error) { signal.removeEventListener('abort', aborted); reject(error); }
  });
}
export function createScope({ timeoutMs = 30000 } = {}) {
  let alive = true, writing = false, uncertain = false;
  const controllers = new Set();
  const generations = new Map();
  return {
    get locked() { return writing || uncertain; },
    get uncertain() { return uncertain; },
    reconciled() { uncertain = false; },
    dispose() { alive = false; controllers.forEach((c) => c.abort()); },
    async read(key, operation, apply) {
      const generation = (generations.get(key) || 0) + 1;
      generations.set(key, generation);
      const controller = new AbortController(); controllers.add(controller);
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const result = await bounded(operation, controller.signal);
        if (alive && generations.get(key) === generation) { apply(result); return true; }
      } catch (error) {
        if (alive && generations.get(key) === generation) throw error;
      } finally { clearTimeout(timer); controllers.delete(controller); }
      return false;
    },
    async write(operation, apply) {
      if (!alive || writing || uncertain) return false;
      writing = true;
      const controller = new AbortController(); controllers.add(controller);
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const result = await bounded(operation, controller.signal);
        if (alive) { await apply(result); return true; }
        return false;
      } catch (error) {
        if (!alive) return false;
        if (alive && (error.status === 0 || error.status === 409 || error.status >= 500)) uncertain = true;
        throw error;
      } finally { clearTimeout(timer); writing = false; controllers.delete(controller); }
    },
  };
}
