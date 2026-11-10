export const G = 'GERENCIA', S = 'SUPERVISOR_OBRAS', AF = 'ADMINISTRATIVO_FINANZAS', T = 'TECNICO';
export const canReadObras = (role) => [G, S, AF, T].includes(role);
export const canReadTeam = (role) => [G, S].includes(role);
export const OBRA_STATES = {
  PLANIFICADA: ['Planificada', 'blue'], EN_PROCESO: ['En proceso', 'green'],
  SUSPENDIDA: ['Suspendida', 'amber'], FINALIZADA: ['Finalizada', 'gray'], CANCELADA: ['Cancelada', 'red'],
};
export const canEditObra = (role, state) => role === S && ['PLANIFICADA', 'EN_PROCESO', 'SUSPENDIDA'].includes(state);
export const operationFor = (role, obra) => !canEditObra(role, obra.estado) ? null
  : ({ PLANIFICADA: obra.tecnico_responsable ? 'iniciar' : null, EN_PROCESO: 'suspender', SUSPENDIDA: obra.tecnico_responsable ? 'reanudar' : null })[obra.estado];
export const actionLabels = { iniciar: 'Iniciar obra', suspender: 'Suspender obra', reanudar: 'Reanudar obra', 'cambiar-tecnico': 'Cambiar responsable', asignar: 'Asignar participante', desasignar: 'Desasignar participante', editar: 'Editar obra' };
export const emptyObra = { presupuesto: '', categoria_servicio: '', descripcion: '', tecnico_responsable: '', fecha_programada: '', motivo: '' };
export const emptyFilters = { estado: '', cliente: '', tecnico_responsable: '', categoria_servicio: '', fecha_programada_desde: '', fecha_programada_hasta: '', ordering: '' };
export const orderingOptions = [['', 'Más recientes'], ['creado_en', 'Creación: más antiguas'], ['-creado_en', 'Creación: más recientes'], ['fecha_programada', 'Programación ascendente'], ['-fecha_programada', 'Programación descendente']];
export const validId = (value) => /^[1-9][0-9]*$/.test(String(value)) && Number.isSafeInteger(Number(value));
export function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
export function filterErrors(filters) {
  const errors = {};
  for (const key of ['cliente', 'tecnico_responsable', 'categoria_servicio']) if (filters[key] && !validId(filters[key])) errors[key] = 'Ingresa un ID positivo válido';
  for (const key of ['fecha_programada_desde', 'fecha_programada_hasta']) if (filters[key] && !validDate(filters[key])) errors[key] = 'Fecha inválida';
  if (filters.estado && !OBRA_STATES[filters.estado]) errors.estado = 'Estado inválido';
  if (!orderingOptions.some(([key]) => key === (filters.ordering || ''))) errors.ordering = 'Orden inválido';
  if (filters.fecha_programada_desde && filters.fecha_programada_hasta && filters.fecha_programada_desde > filters.fecha_programada_hasta) errors.fecha_programada_hasta = 'Debe ser igual o posterior a Desde';
  return errors;
}
export function obraPayload(form, original) {
  const data = { categoria_servicio: Number(form.categoria_servicio), descripcion: form.descripcion.trim(), fecha_programada: form.fecha_programada || null };
  if (original) return { ...Object.fromEntries(Object.entries(data).filter(([key, value]) => value !== original[key])), motivo: form.motivo.trim() };
  return { ...data, presupuesto: Number(form.presupuesto), tecnico_responsable: form.tecnico_responsable ? Number(form.tecnico_responsable) : null, motivo: form.motivo.trim() };
}
export function obraErrors(form, original) {
  const errors = {};
  if (!original && !validId(form.presupuesto)) errors.presupuesto = 'Selecciona un presupuesto disponible';
  if (!validId(form.categoria_servicio)) errors.categoria_servicio = 'Selecciona una categoría activa';
  if (!form.descripcion.trim()) errors.descripcion = 'Campo obligatorio';
  else if (form.descripcion.trim().length > 2000) errors.descripcion = 'Máximo 2000 caracteres';
  if (!original && form.tecnico_responsable && !validId(form.tecnico_responsable)) errors.tecnico_responsable = 'Selecciona un técnico';
  if (form.fecha_programada && !validDate(form.fecha_programada)) errors.fecha_programada = 'Fecha inválida';
  const changed = original && Object.keys(obraPayload(form, original)).some((key) => key !== 'motivo');
  if ((changed || (!original && form.tecnico_responsable)) && !form.motivo.trim()) errors.motivo = 'Campo obligatorio';
  if (form.motivo.trim().length > 2000) errors.motivo = 'Máximo 2000 caracteres';
  return errors;
}
export const shortDate = (value) => value ? new Date(`${value}T12:00:00`).toLocaleDateString('es-CL') : 'Sin programar';
export const timestamp = (value) => value ? new Date(value).toLocaleString('es-CL') : '—';
// No propagar objetos completos del backend a la presentación de la ficha.
export const minimalFields = ['id', 'codigo', 'presupuesto', 'presupuesto_codigo', 'cliente', 'cliente_nombre', 'categoria_servicio', 'categoria_nombre', 'tecnico_responsable', 'tecnico_nombre', 'fecha_programada', 'iniciado_en', 'estado', 'finalizado_en'];
export function projectObra(data, role) {
  const fields = role === AF ? minimalFields : [...minimalFields, 'descripcion', 'cancelado_en', 'creado_por', 'creado_en', 'actualizado_en'];
  return Object.fromEntries(fields.filter((key) => Object.hasOwn(data, key)).map((key) => [key, data[key]]));
}
