export const AF = 'ADMINISTRATIVO_FINANZAS';
export const G = 'GERENCIA';
export const canRead = (role) => [AF, G].includes(role);
export const actionsFor = (role, state) => {
  if (role === G) return state === 'PENDIENTE_GERENCIA' ? ['aprobar-gerencia', 'rechazar-gerencia'] : [];
  if (role !== AF) return [];
  const actions = ({ BORRADOR: ['enviar-gerencia'], APROBADO_GERENCIA: ['enviar-cliente'], ENVIADO_CLIENTE: ['registrar-aprobacion-cliente', 'registrar-rechazo-cliente'] })[state] || [];
  return [...actions, ...(['RECHAZADO_GERENCIA', 'RECHAZADO_CLIENTE', 'ANULADO'].includes(state) ? ['crear-revision'] : []), ...(['BORRADOR', 'PENDIENTE_GERENCIA', 'APROBADO_GERENCIA', 'ENVIADO_CLIENTE', 'APROBADO_CLIENTE'].includes(state) ? ['anular'] : [])];
};
export const needsReason = (action) => ['rechazar-gerencia', 'registrar-rechazo-cliente', 'anular'].includes(action);
export const labels = { 'enviar-gerencia': 'Enviar a Gerencia', 'aprobar-gerencia': 'Aprobar por Gerencia', 'rechazar-gerencia': 'Rechazar por Gerencia', 'enviar-cliente': 'Enviar al cliente', 'registrar-aprobacion-cliente': 'Registrar aprobación del cliente', 'registrar-rechazo-cliente': 'Registrar rechazo del cliente', anular: 'Anular', 'crear-revision': 'Crear revisión' };
export const emptyClient = { tipo_cliente: 'PERSONA', tipo_identificacion: 'RUT', numero_identificacion: '', pais_identificacion: '', tipo_documento_extranjero: '', nombre_legal: '', nombre_contacto: '', correo: '', telefono: '' };
export const emptyItem = { descripcion: '', cantidad: '', unidad: '', precio_unitario: '', orden: '' };
export function validRut(value) {
  const text = String(value || '').trim().toUpperCase();
  if (text.length > 100 || (text.includes('.') && !text.includes('-'))) return false;
  const parts = text.split('-');
  if (parts.length > 2 || (parts.length === 2 && !/^[0-9K]$/.test(parts[1]))) return false;
  const body = parts.length === 2 ? parts[0] : text.slice(0, -1);
  if (body.includes('.') && !/^[0-9]{1,3}(?:\.[0-9]{3})+$/.test(body)) return false;
  const rut = text.replaceAll('.', '').replaceAll('-', '');
  if (!/^[0-9]+[0-9K]$/.test(rut)) return false;
  const digits = rut.slice(0, -1);
  if (/^0+$/.test(digits)) return false;
  let sum = 0, factor = 2;
  for (const digit of [...digits].reverse()) { sum += Number(digit) * factor; factor = factor === 7 ? 2 : factor + 1; }
  return String(({ 11: '0', 10: 'K' })[11 - sum % 11] ?? 11 - sum % 11) === rut.at(-1);
}
export function clientPayload(form, original) {
  const data = Object.fromEntries(Object.keys(emptyClient).map((key) => [key, (form[key] || '').trim()]));
  if (data.tipo_identificacion === 'SIN_IDENTIFICACION') {
    data.numero_identificacion = data.pais_identificacion = data.tipo_documento_extranjero = null;
  } else if (data.tipo_identificacion === 'RUT') {
    data.pais_identificacion = data.tipo_documento_extranjero = null;
  }
  return original ? Object.fromEntries(Object.entries(data).filter(([k, v]) => v !== original[k] || (data.tipo_identificacion !== original.tipo_identificacion && ['numero_identificacion', 'pais_identificacion', 'tipo_documento_extranjero'].includes(k)))) : data;
}
export function validateClient(form) {
  const errors = {};
  if (!form.nombre_legal.trim()) errors.nombre_legal = ['Ingresa el nombre legal.'];
  if (!form.correo.trim() && !form.telefono.trim()) errors.correo = ['Ingresa correo o teléfono.'];
  if (form.correo && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.correo)) errors.correo = ['Revisa el correo.'];
  if (form.tipo_identificacion === 'RUT' && !validRut(form.numero_identificacion)) errors.numero_identificacion = ['RUT inválido (módulo 11).'];
  if (form.tipo_identificacion === 'DOCUMENTO_EXTRANJERO') {
    for (const k of ['numero_identificacion', 'pais_identificacion', 'tipo_documento_extranjero']) if (!form[k]?.trim()) errors[k] = ['Campo obligatorio para documento extranjero.'];
    if (!/^[A-Za-z]{2}$/.test(form.pais_identificacion)) errors.pais_identificacion = ['Usa el código de país de dos letras.'];
  }
  return errors;
}
export function validDecimal(value, integers, scale, positive = false) {
  return typeof value === 'string' && new RegExp(`^[0-9]{1,${integers}}(?:\\.[0-9]{1,${scale}})?$`).test(value) && (!positive || /[1-9]/.test(value));
}
export function itemPayload(form, original) {
  const data = { descripcion: form.descripcion.trim(), cantidad: form.cantidad.trim(), unidad: form.unidad.trim(), precio_unitario: form.precio_unitario.trim(), orden: Number(form.orden) };
  return original ? Object.fromEntries(Object.entries(data).filter(([k, v]) => v !== original[k])) : data;
}
export function validateItem(form) {
  const errors = {};
  for (const k of ['descripcion', 'unidad']) if (!form[k].trim()) errors[k] = ['Campo obligatorio.'];
  if (!validDecimal(form.cantidad, 9, 3, true)) errors.cantidad = ['Usa hasta 9 enteros y 3 decimales; mínimo 0.001.'];
  if (!validDecimal(form.precio_unitario, 13, 2)) errors.precio_unitario = ['Usa hasta 13 enteros y 2 decimales, sin comas.'];
  if (!/^[1-9][0-9]*$/.test(String(form.orden)) || Number(form.orden) > 2147483647) errors.orden = ['Orden entero positivo hasta 2147483647.'];
  return errors;
}
export function money(value) {
  if (typeof value !== 'string' || !/^\d+(\.\d+)?$/.test(value)) return '—';
  const [integer, fraction = '00'] = value.split('.');
  return `$${integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')} CLP`;
}
export const dateLabel = (iso) => new Date(iso).toLocaleString('es-CL');
