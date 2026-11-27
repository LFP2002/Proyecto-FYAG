import {quantityInput,unitCostInput} from '../utils/decimalInput.js';
export const AF = 'ADMINISTRATIVO_FINANZAS';
export const G = 'GERENCIA';
export const canRead = (role, module) => (role === AF || (role === G && module !== 'clientes')) || (role === 'SUPERVISOR_OBRAS' && module === 'presupuestos');
export const actionsFor = (role, state, pricesPending = false) => {
  if (role === G) return [];
  if (role === 'SUPERVISOR_OBRAS') return state === 'BORRADOR' ? ['enviar-finanzas'] : state === 'RECHAZADO_FINANZAS' ? ['crear-revision'] : [];
  if (role !== AF) return [];
  const actions = (({ BORRADOR: ['enviar-finanzas'], PENDIENTE_FINANZAS: ['aprobar-finanzas', 'rechazar-finanzas'], PENDIENTE_GERENCIA: ['aprobar-finanzas', 'rechazar-finanzas'], APROBADO_FINANZAS: ['enviar-cliente'], APROBADO_GERENCIA: ['enviar-cliente'], ENVIADO_CLIENTE: ['registrar-aprobacion-cliente', 'registrar-rechazo-cliente'] })[state] || [])
    .filter(action => !pricesPending || !['aprobar-finanzas','enviar-cliente','registrar-aprobacion-cliente'].includes(action));
  return [...actions, ...(['RECHAZADO_FINANZAS', 'RECHAZADO_GERENCIA', 'RECHAZADO_CLIENTE', 'ANULADO'].includes(state) ? ['crear-revision'] : []), ...(['BORRADOR', 'PENDIENTE_FINANZAS', 'PENDIENTE_GERENCIA', 'APROBADO_FINANZAS', 'APROBADO_GERENCIA', 'ENVIADO_CLIENTE', 'APROBADO_CLIENTE'].includes(state) ? ['anular'] : [])];
};
export const needsReason = (action) => ['rechazar-finanzas', 'rechazar-gerencia', 'registrar-rechazo-cliente', 'anular'].includes(action);
export const labels = { 'enviar-finanzas': 'Enviar a Finanzas', 'aprobar-finanzas': 'Aprobar por Finanzas', 'rechazar-finanzas': 'Rechazar por Finanzas', 'enviar-gerencia': 'Enviar a Gerencia (retirado)', 'aprobar-gerencia': 'Aprobar por Gerencia (legado)', 'rechazar-gerencia': 'Rechazar por Gerencia (legado)', 'enviar-cliente': 'Enviar al cliente', 'registrar-aprobacion-cliente': 'Registrar aprobación del cliente', 'registrar-rechazo-cliente': 'Registrar rechazo del cliente', anular: 'Anular', 'crear-revision': 'Crear revisión' };
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
export function itemPayload(form, original, role = AF) {
  const price = unitCostInput(form.precio_unitario);
  const linked = form.articulo != null;
  const data = { cantidad: quantityInput(form.cantidad), orden: Number(form.orden) };
  if (!linked) Object.assign(data, {descripcion: form.descripcion.trim(), unidad: form.unidad.trim()});
  if (!linked || (role === AF && price !== null)) data.precio_unitario = price;
  if (Object.hasOwn(form, 'articulo') && (form.articulo !== null || original?.articulo != null)) {
    data.articulo = form.articulo;
  }
  const identityChanged = (original?.articulo ?? null) !== (form.articulo ?? null);
  return original ? Object.fromEntries(Object.entries(data).filter(([k, v]) => v !== original[k] || (identityChanged && k === 'precio_unitario'))) : data;
}
export function nextItemOrder(items) {
  const used = new Set(items.map(item => item.orden));
  const max = Math.max(0, ...used);
  if (max < 2147483647) return String(max + 1);
  let next = 1;
  while (used.has(next)) next += 1;
  return String(next);
}
export function validateItem(form, role = AF) {
  const errors = {};
  const linked = form.articulo != null;
  if (!linked) {
    for (const k of ['descripcion', 'unidad']) if (!form[k].trim()) errors[k] = ['Campo obligatorio.'];
    if (form.descripcion.trim().length > 2000) errors.descripcion = ['La descripción debe tener como máximo 2000 caracteres.'];
    if (form.unidad.trim().length > 30) errors.unidad = ['La unidad debe tener como máximo 30 caracteres.'];
  }
  if (quantityInput(form.cantidad)===null) errors.cantidad = ['Ingresa una cantidad mayor que cero, con hasta tres cifras después de la coma.'];
  if ((!linked || (role === AF && String(form.precio_unitario ?? '').trim())) && unitCostInput(form.precio_unitario)===null) errors.precio_unitario = ['Ingresa un precio válido, sin separadores de miles.'];
  if (!/^[1-9][0-9]*$/.test(String(form.orden)) || Number(form.orden) > 2147483647) errors.orden = ['Orden entero positivo hasta 2147483647.'];
  return errors;
}
export function money(value) {
  if (typeof value !== 'string' || !/^\d+(\.\d+)?$/.test(value)) return '—';
  const [integer, fraction = '00'] = value.split('.');
  return `$${integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')} CLP`;
}
export const dateLabel = (iso) => new Date(iso).toLocaleString('es-CL');
