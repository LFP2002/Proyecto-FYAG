import React, { useState } from 'react';
import { categoryPath, collectionPath, obraPath, readPage } from './api.js';
import { emptyObra, obraErrors, obraPayload } from './domain.js';
import { Feedback, Field, focusError, PagedSelect, RefreshButton, useOperational } from './ui.jsx';

export function ObraFields({ form, setForm, original, errors, disabled, refreshKey = 0 }) {
  const change = (name) => (value) => setForm({ ...form, [name]: value });
  return <div className="obras-form-grid">
    {!original && <PagedSelect name="presupuesto" label="Presupuesto disponible" path={`${obraPath()}presupuestos-disponibles/`} value={form.presupuesto} onChange={change('presupuesto')} disabled={disabled} error={errors.presupuesto} required refreshKey={refreshKey} />}
    <PagedSelect name="categoria_servicio" label="Categoría de servicio" path={categoryPath()} activeOnly value={form.categoria_servicio} selectedLabel={original?.categoria_nombre} onChange={change('categoria_servicio')} disabled={disabled} error={errors.categoria_servicio} required refreshKey={refreshKey} />
    {!original && <PagedSelect name="tecnico_responsable" label="Técnico responsable (opcional)" path={`${obraPath()}tecnicos-disponibles/`} value={form.tecnico_responsable} onChange={change('tecnico_responsable')} disabled={disabled} error={errors.tecnico_responsable} refreshKey={refreshKey} />}
    <Field name="fecha_programada" label="Fecha programada" type="date" value={form.fecha_programada} onChange={change('fecha_programada')} disabled={disabled} error={errors.fecha_programada} />
    <Field name="descripcion" label="Descripción operativa" type="textarea" value={form.descripcion} onChange={change('descripcion')} disabled={disabled} error={errors.descripcion} required maxLength={2000} />
    <Field name="motivo" label="Motivo" type="textarea" value={form.motivo} onChange={change('motivo')} disabled={disabled} error={errors.motivo} maxLength={2000} />
  </div>;
}
export default function NewObra({ onClose, onCreated }) {
  const api = useOperational();
  const [form, setForm] = useState({ ...emptyObra }), [errors, setErrors] = useState({}), [revision, setRevision] = useState(0);
  async function reconcile() {
    const paths = [obraPath(), `${obraPath()}presupuestos-disponibles/`, `${obraPath()}tecnicos-disponibles/`, categoryPath()];
    const results = await Promise.all(paths.map((path) => api.load(`verify:${path}`, collectionPath(path), (data) => readPage(data, path))));
    if (results.every(Boolean)) { setRevision((value) => value + 1); return true; }
    return false;
  }
  async function submit(event) {
    event.preventDefault();
    const invalid = obraErrors(form); setErrors(invalid); focusError(event, invalid);
    if (Object.keys(invalid).length || api.busy || api.locked) return;
    await api.write(obraPath(), 'POST', obraPayload(form), async (result) => {
      await api.requiredLoad('created', obraPath(result.id), (actual) => onCreated(actual.id));
    });
  }
  return <form className="card-fyag commercial-form" noValidate onSubmit={submit}>
    <div className="commercial-section-head"><h2>Nueva obra</h2><RefreshButton label="Reconsultar opciones" busy={api.busy || api.loading} onClick={() => void api.reconcile(reconcile)} /></div>
    <Feedback api={api} />
    <ObraFields form={form} setForm={setForm} errors={errors} disabled={api.busy} refreshKey={revision} />
    <div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy || api.locked} type="submit">{api.busy ? 'Guardando…' : 'Crear obra'}</button><button className="btn btn-outline-secondary" disabled={api.busy} type="button" onClick={onClose}>Cancelar</button></div>
  </form>;
}
