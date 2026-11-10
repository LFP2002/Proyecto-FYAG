import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Chip } from '../components/ui';
import { collectionPath, memberPath, obraPath, readPage } from './api.js';
import { actionLabels, AF, canEditObra, canReadTeam, emptyObra, G, obraErrors, obraPayload, operationFor, projectObra, shortDate, S, T, timestamp, validId } from './domain.js';
import { ObraFields } from './ObraForm.jsx';
import { EventList, Feedback, Field, focusError, ObraStatus, PagedSelect, Pager, PendingSection, RefreshButton, useOperational } from './ui.jsx';

export default function ObraDetail({ id, onBack }) {
  const { user } = useAuth(), api = useOperational();
  const [obra, setObra] = useState(null), [tab, setTab] = useState('resumen'), [form, setForm] = useState(null), [errors, setErrors] = useState({});
  const [members, setMembers] = useState(null), [memberPage, setMemberPage] = useState(1), [active, setActive] = useState('');
  const [history, setHistory] = useState(null), [historyPage, setHistoryPage] = useState(1);
  const [memberHistory, setMemberHistory] = useState(null), [memberHistoryPage, setMemberHistoryPage] = useState(1);
  const base = obraPath(id), team = canReadTeam(user.role), editable = obra && canEditObra(user.role, obra.estado);
  const disabled = api.busy || api.loading || api.locked;
  const readDetail = () => { setObra(null); return api.load('detail', base, (result) => setObra(projectObra(result, user.role))); };
  const readMembers = () => api.load('members', collectionPath(`${base}participantes/`, memberPage, { activo: active }), (result) => setMembers(readPage(result, `${base}participantes/`)));
  const readHistory = () => api.load('history', collectionPath(`${base}historial/`, historyPage), (result) => setHistory(readPage(result, `${base}historial/`)));
  const readMemberHistory = () => api.load('memberHistory', collectionPath(`${base}participantes/historial/`, memberHistoryPage), (result) => setMemberHistory(readPage(result, `${base}participantes/historial/`)));
  const currentMember = form?.member ? members?.results.find((member) => member.id === form.member.id) : null;
  const formAllowed = editable && (!form || (
    (!['iniciar', 'suspender', 'reanudar'].includes(form.type) || operationFor(user.role, obra) === form.type)
    && (form.type !== 'desasignar' || (currentMember?.activo && !currentMember.es_responsable))
    && (form.type !== 'asignar' || !form.member || (currentMember && !currentMember.activo && !currentMember.es_responsable))
  ));
  useEffect(() => { void readDetail(); }, [id]);
  useEffect(() => { if (team && tab === 'tecnicos') { setMembers(null); void readMembers(); } }, [tab, memberPage, active]);
  useEffect(() => { if (team && tab === 'historial') { setHistory(null); void readHistory(); } }, [tab, historyPage]);
  useEffect(() => { if (team && tab === 'historial') { setMemberHistory(null); void readMemberHistory(); } }, [tab, memberHistoryPage]);
  async function reconcile() {
    const results = [await readDetail()];
    if (team) results.push(await readMembers(), await readHistory(), await readMemberHistory());
    return results.every(Boolean);
  }
  async function afterWrite() {
    await api.requiredLoad('detail', base, (result) => setObra(projectObra(result, user.role)));
    await api.requiredLoad('members', collectionPath(`${base}participantes/`, memberPage, { activo: active }), (result) => setMembers(readPage(result, `${base}participantes/`)));
    await api.requiredLoad('history', collectionPath(`${base}historial/`, historyPage), (result) => setHistory(readPage(result, `${base}historial/`)));
    await api.requiredLoad('memberHistory', collectionPath(`${base}participantes/historial/`, memberHistoryPage), (result) => { setMemberHistory(readPage(result, `${base}participantes/historial/`)); setForm(null); });
  }
  function open(type, member = null) {
    api.setError(null); setErrors({});
    setForm({ type, member, data: type === 'editar' ? { ...emptyObra, ...obra, fecha_programada: obra.fecha_programada || '', motivo: '' } : { tecnico_responsable: '', tecnico: member ? String(member.tecnico) : '', motivo: '' } });
  }
  async function submit(event) {
    event.preventDefault();
    if (!formAllowed || disabled || !form) return;
    const { type, data, member } = form;
    let invalid = {}, path = base, method = 'POST', payload;
    if (type === 'editar') { invalid = obraErrors(data, obra); method = 'PATCH'; payload = obraPayload(data, obra); }
    else {
      if (!data.motivo.trim()) invalid.motivo = 'Campo obligatorio';
      if (data.motivo.trim().length > 2000) invalid.motivo = 'Máximo 2000 caracteres';
      payload = { motivo: data.motivo.trim() };
      if (type === 'cambiar-tecnico') {
        if ((!data.tecnico_responsable && obra.estado !== 'PLANIFICADA') || (data.tecnico_responsable && !validId(data.tecnico_responsable))) invalid.tecnico_responsable = 'Selecciona un técnico elegible';
        payload.tecnico_responsable = data.tecnico_responsable ? Number(data.tecnico_responsable) : null;
      }
      if (type === 'asignar') { if (!validId(data.tecnico)) invalid.tecnico = 'Selecciona un técnico'; payload.tecnico = Number(data.tecnico); }
      if (type === 'desasignar' && (!member?.activo || member.es_responsable)) return;
      if (['iniciar', 'suspender', 'reanudar'].includes(type) && operationFor(user.role, obra) !== type) return;
      path = type === 'asignar' ? `${base}participantes/` : type === 'desasignar' ? memberPath(id, member.id) : `${base}${type}/`;
    }
    setErrors(invalid); focusError(event, invalid);
    if (Object.keys(invalid).length) return;
    const cambioResponsable = type === 'cambiar-tecnico' && payload.tecnico_responsable !== obra.tecnico_responsable;
    const avisoRelevo = cambioResponsable
      ? `¿Cambiar responsable en ${obra.codigo}?\n\n${obra.tecnico_responsable ? 'El responsable anterior dejará de ser participante activo de esta obra. ' : ''}${payload.tecnico_responsable ? 'El nuevo responsable quedará activo, incluso si fue desasignado anteriormente.' : 'La obra planificada quedará sin responsable.'}\n\n¿Deseas continuar?`
      : `¿${actionLabels[type]} en ${obra.codigo}?`;
    if (['desasignar', 'cambiar-tecnico', 'suspender'].includes(type) && !window.confirm(avisoRelevo)) return;
    await api.write(path, method, payload, afterWrite);
  }
  const tabs = [['resumen', 'Resumen / Estado'], ...(team ? [['tecnicos', 'Técnicos'], ['historial', 'Historial']] : []), ...([G, S, T].includes(user.role) ? [['turnos', 'Turnos']] : []), ...(team ? [['gastos', 'Materiales y gastos']] : []), ...([G, S, AF].includes(user.role) ? [['costos', 'Costos']] : [])];
  return <article className="card-fyag commercial-detail">
    <div className="commercial-section-head"><div><h2>{obra?.codigo || `Obra #${id}`}</h2>{obra && <ObraStatus state={obra.estado} />}</div><div className="commercial-row-actions"><RefreshButton busy={api.busy || api.loading} onClick={() => void api.reconcile(reconcile)} /><button className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={onBack}>Volver al listado</button></div></div>
    <Feedback api={api} />
    {obra && <>
      <nav className="obras-tabs" aria-label="Secciones de la obra">{tabs.map(([key, label]) => <button type="button" key={key} className={`btn btn-sm ${tab === key ? 'btn-fyag-primary' : 'btn-outline-secondary'}`} aria-current={tab === key ? 'page' : undefined} disabled={api.busy || !!form} onClick={() => setTab(key)}>{label}</button>)}</nav>
      {tab === 'resumen' && <>
        <dl className="commercial-facts">
          <div><dt>Cliente</dt><dd>{obra.cliente_nombre} · #{obra.cliente}</dd></div><div><dt>Presupuesto de origen</dt><dd>{obra.presupuesto_codigo} · #{obra.presupuesto}</dd></div>
          <div><dt>Categoría</dt><dd>{obra.categoria_nombre} · #{obra.categoria_servicio}</dd></div><div><dt>Responsable</dt><dd>{obra.tecnico_nombre || 'Sin asignar'}{obra.tecnico_responsable ? ` · #${obra.tecnico_responsable}` : ''}</dd></div>
          <div><dt>Programación</dt><dd>{shortDate(obra.fecha_programada)}</dd></div><div><dt>Inicio efectivo</dt><dd>{timestamp(obra.iniciado_en)}</dd></div>
          {obra.finalizado_en && <div><dt>Finalización</dt><dd>{timestamp(obra.finalizado_en)}</dd></div>}
          {user.role !== AF && obra.cancelado_en && <div><dt>Cancelación histórica</dt><dd>{timestamp(obra.cancelado_en)}</dd></div>}
          {team && <><div><dt>Creado por</dt><dd>Usuario #{obra.creado_por}</dd></div><div><dt>Creación</dt><dd>{timestamp(obra.creado_en)}</dd></div><div><dt>Última actualización</dt><dd>{timestamp(obra.actualizado_en)}</dd></div></>}
        </dl>
        {user.role !== AF && <p className="commercial-long-text">{obra.descripcion}</p>}
        {editable && <div className="commercial-actions"><button className="btn btn-outline-secondary" disabled={disabled || !!form} onClick={() => open('editar')}>Editar obra</button><button className="btn btn-outline-secondary" disabled={disabled || !!form} onClick={() => open('cambiar-tecnico')}>Cambiar responsable</button>{operationFor(user.role, obra) && <button className="btn btn-fyag-primary" disabled={disabled || !!form} onClick={() => open(operationFor(user.role, obra))}>{actionLabels[operationFor(user.role, obra)]}</button>}</div>}
        {user.role === S && <PendingSection>Finalización operativa: pendiente de integración frontend en 005C-3.</PendingSection>}
      </>}
      {tab === 'tecnicos' && team && <>
        <div className="budget-toolbar"><Field name="miembros_activo" label="Participantes" value={active} options={[[ '', 'Todos' ], ['true', 'Activos'], ['false', 'Históricos / inactivos']]} disabled={disabled || !!form} onChange={(value) => { setActive(value); setMemberPage(1); }} />{editable && <button className="btn btn-fyag-primary" disabled={disabled || !!form} onClick={() => open('asignar')}>Asignar participante</button>}</div>
        <div className="table-responsive" role="region" aria-label="Participantes de la obra" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Miembro / técnico', 'Vigencia', 'Origen', 'Asignación', 'Desasignación', 'Acción'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{members?.results.map((member) => <tr key={member.id}>
          <td>{member.tecnico_nombre} · Técnico #{member.tecnico}<span className="commercial-help d-block">Miembro #{member.id}{member.es_responsable ? ' · Responsable principal' : ''}</span></td><td><Chip cls={member.activo ? 'green' : 'gray'}>{member.activo ? 'Activo' : 'Histórico / inactivo'}</Chip></td><td>{member.origen_registro}</td>
          <td>{timestamp(member.asignado_en)} · Usuario {member.asignado_por ? `#${member.asignado_por}` : 'no registrado'}<p className="commercial-long-text">{member.motivo_asignacion}</p></td><td>{timestamp(member.desasignado_en)}{member.desasignado_por ? ` · Usuario #${member.desasignado_por}` : ''}<p className="commercial-long-text">{member.motivo_desasignacion}</p></td>
          <td>{editable && !member.es_responsable && <button className={`btn btn-sm ${member.activo ? 'btn-outline-danger' : 'btn-outline-secondary'}`} disabled={disabled || !!form} onClick={() => open(member.activo ? 'desasignar' : 'asignar', member)}>{member.activo ? 'Desasignar' : 'Reactivar'}</button>}</td>
        </tr>)}</tbody></table></div>
        {members && !members.count && <p className="commercial-empty">No hay participantes para este filtro.</p>}
        <Pager label="Paginación de participantes" data={members} page={memberPage} setPage={setMemberPage} disabled={disabled || !!form} />
      </>}
      {tab === 'historial' && team && <><EventList title="Historial operativo" data={history} /><Pager label="Paginación del historial operativo" data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled || !!form} /><EventList title="Historial de participantes" data={memberHistory} /><Pager label="Paginación del historial de participantes" data={memberHistory} page={memberHistoryPage} setPage={setMemberHistoryPage} disabled={disabled || !!form} /></>}
      {tab === 'turnos' && <PendingSection>Turnos y evidencia privada: pendiente de integración frontend en 005C-2.</PendingSection>}
      {tab === 'gastos' && team && <PendingSection>Materiales y gastos: pendiente de integración frontend en 005C-3.</PendingSection>}
      {tab === 'costos' && user.role !== T && <PendingSection>Costos y cierre operativo: pendiente de integración frontend en 005C-3.</PendingSection>}
      {form && <form className="commercial-form obras-action-form" noValidate onSubmit={submit}><h2>{actionLabels[form.type]}</h2>
        {form.type === 'editar' ? <ObraFields form={form.data} setForm={(data) => setForm({ ...form, data })} original={obra} errors={errors} disabled={api.busy || !editable} /> : <div className="obras-form-grid">
          {['cambiar-tecnico', 'asignar'].includes(form.type) && <PagedSelect name={form.type === 'asignar' ? 'tecnico' : 'tecnico_responsable'} label={form.type === 'asignar' ? 'Técnico participante' : 'Nuevo responsable'} path={`${obraPath()}tecnicos-disponibles/`} value={form.type === 'asignar' ? form.data.tecnico : form.data.tecnico_responsable} selectedLabel={form.member?.tecnico_nombre} onChange={(value) => setForm({ ...form, data: { ...form.data, [form.type === 'asignar' ? 'tecnico' : 'tecnico_responsable']: value } })} disabled={api.busy || !editable} error={errors[form.type === 'asignar' ? 'tecnico' : 'tecnico_responsable']} />}
          <Field name="motivo" label="Motivo" type="textarea" value={form.data.motivo} onChange={(value) => setForm({ ...form, data: { ...form.data, motivo: value } })} disabled={api.busy || !editable} error={errors.motivo} required maxLength={2000} />
        </div>}
        {!formAllowed && <p className="alert alert-warning">Los datos actuales ya no permiten esta acción. Cancela para continuar.</p>}
        <div className="commercial-form-actions"><button type="submit" className={`btn ${form.type === 'desasignar' ? 'btn-outline-danger' : 'btn-fyag-primary'}`} disabled={disabled || !formAllowed}>{api.busy ? 'Guardando…' : 'Guardar cambios'}</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={() => setForm(null)}>Cancelar</button></div>
      </form>}
    </>}
  </article>;
}
