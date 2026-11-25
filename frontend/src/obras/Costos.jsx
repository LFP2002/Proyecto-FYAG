import { formatCLP } from '../utils/format.js';
import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PageHead } from '../components/ui';
import { AF, G, S, timestamp } from './domain.js';
import { obraPath, readPage } from './api.js';
import { Feedback, Field, Pager, useOperational } from './ui.jsx';

const TYPES = [['MATERIAL', 'Material'], ['TRANSPORTE', 'Transporte'], ['ARRIENDO_EQUIPO', 'Arriendo de equipo'], ['SERVICIO_EXTERNO', 'Servicio externo'], ['OTRO', 'Otro']];
const emptyExpense = { tipo: 'MATERIAL', descripcion: '', unidad: '', cantidad: '', costo_unitario_neto: '', fecha_gasto: '', referencia_respaldo: '', observacion: '' };
const decimal = (value, scale) => new RegExp(`^[0-9]{1,${scale === 2 ? 13 : 9}}(?:\\.[0-9]{1,${scale}})?$`).test(value);
const validId = (value) => /^[1-9][0-9]*$/.test(String(value)) && Number.isSafeInteger(Number(value));
const compareDecimal = (left, right, scale = 3) => { const unit = 10n ** BigInt(scale); const toInt = (value) => { const [whole, fraction = ''] = String(value).split('.'); return BigInt(whole || '0') * unit + BigInt((fraction + '0'.repeat(scale)).slice(0, scale)); }; return toInt(left) - toInt(right); };
const object = (data) => data && typeof data === 'object' && !Array.isArray(data);
function money(value) { return formatCLP(value); }
function strictKeys(value, keys) { return object(value) && Object.keys(value).every((key) => keys.includes(key)); }
function projectExpense(row) {
  const keys = ['id', 'obra', 'tipo', 'descripcion', 'unidad', 'cantidad', 'cantidad_devuelta', 'costo_unitario_neto', 'subtotal', 'fecha_gasto', 'referencia_respaldo', 'observacion', 'vigente', 'anulado_por', 'anulado_en', 'motivo_anulacion', 'registrado_por', 'creado_en', 'actualizado_en'];
  if (!strictKeys(row, keys) || !validId(String(row.id)) || !validId(String(row.obra)) || !TYPES.some(([type]) => type === row.tipo) || !['descripcion', 'unidad', 'cantidad', 'cantidad_devuelta', 'costo_unitario_neto', 'subtotal', 'fecha_gasto', 'referencia_respaldo', 'observacion', 'motivo_anulacion'].every((key) => typeof row[key] === 'string') || !['cantidad', 'cantidad_devuelta'].every((key) => decimal(row[key], 3)) || !['costo_unitario_neto', 'subtotal'].every((key) => decimal(row[key], 2)) || typeof row.vigente !== 'boolean') throw new Error('Gasto con formato inesperado.');
  return Object.fromEntries(keys.map((key) => [key, row[key]]));
}
function validDate(value) { if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false; const date = new Date(`${value}T00:00:00Z`); return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value; }

export default function Costos({ obra, onFinalized, section = 'costs' }) {
  const { user } = useAuth(), api = useOperational();
  const base = obraPath(obra.id);
  const [page, setPage] = useState(1), [historyPage, setHistoryPage] = useState(1), [expenses, setExpenses] = useState(null), [control, setControl] = useState(null), [summary, setSummary] = useState(null), [history, setHistory] = useState(null);
  const [form, setForm] = useState(null), [issue, setIssue] = useState(''), [busyAction, setBusyAction] = useState(false);
  const [finalReason, setFinalReason] = useState(''), [courtesyReason, setCourtesyReason] = useState(''), [motive, setMotive] = useState('');
  const canManage = user.role === S, canRead = [G, S, AF].includes(user.role), canSeeDetail = [G, S].includes(user.role);
  const expensesView = section === 'expenses', costsView = section === 'costs';
  const expensesPath = `${base}gastos/?page=${page}`, historyPath = `${base}costos/historial/?page=${historyPage}`;

  function loadExpenses() { return api.load('expenses', expensesPath, (data) => { const result = readPage(data, `${base}gastos/`); setExpenses({ ...result, results: result.results.map(projectExpense) }); }); }
  function loadControl() { return api.load('control', `${base}costos/control/`, (data) => { const keys = ['id', 'obra', 'materiales_estado', 'materiales_justificacion', 'otros_estado', 'otros_justificacion', 'version_actual', 'version_validada', 'validado_por', 'validado_en', 'costos_validados', 'creado_en', 'actualizado_en']; if (!strictKeys(data, keys) || !Number.isSafeInteger(data.version_actual) || typeof data.costos_validados !== 'boolean' || !['PENDIENTE', 'CON_REGISTROS', 'NO_APLICA'].includes(data.materiales_estado) || !['PENDIENTE', 'CON_REGISTROS', 'NO_APLICA'].includes(data.otros_estado)) throw new Error('Control de costos inesperado.'); setControl(Object.fromEntries(keys.map((key) => [key, data[key]]))); }); }
  function loadSummary() { return api.load('summary', `${base}costos/resumen/`, (data) => { const keys = user.role === AF ? ['obra', 'materiales_total', 'otros_total', 'mano_obra_total', 'costo_total', 'costos_validados', 'cortesia_sin_cobro'] : ['obra', 'materiales_total', 'otros_total', 'mano_obra_total', 'costo_total', 'costos_validados', 'cortesia_sin_cobro', 'materiales_estado', 'otros_estado', 'materiales_justificacion', 'otros_justificacion', 'version_actual', 'version_validada', 'validado_por', 'validado_en', 'cortesia_justificacion', 'provisional']; if (!strictKeys(data, keys) || !['materiales_total', 'otros_total', 'mano_obra_total', 'costo_total'].every((key) => typeof data[key] === 'string' && decimal(data[key], 2)) || typeof data.costos_validados !== 'boolean' || typeof data.cortesia_sin_cobro !== 'boolean') throw new Error('Resumen de costos inesperado.'); setSummary(Object.fromEntries(keys.map((key) => [key, data[key]]))); }); }
  function loadHistory() { return api.load('history', historyPath, (data) => { const result = readPage(data, `${base}costos/historial/`); const keys = ['id', 'obra', 'gasto', 'control', 'cortesia', 'tipo', 'registrado_por', 'motivo', 'datos_anteriores', 'datos_nuevos', 'creado_en']; if (result.results.some((event) => !strictKeys(event, keys) || typeof event.tipo !== 'string' || typeof event.motivo !== 'string' || !object(event.datos_nuevos))) throw new Error('Historial de costos inesperado.'); setHistory(result); }); }
  useEffect(() => { setExpenses(null); if (canSeeDetail && expensesView) void loadExpenses(); }, [obra.id, page, user.id, user.role, expensesView]);
  useEffect(() => { setHistory(null); if (canSeeDetail && costsView) void loadHistory(); }, [obra.id, historyPage, user.id, user.role, costsView]);
  useEffect(() => { setControl(null); setSummary(null); if (costsView && canRead) void loadSummary(); if (costsView && canSeeDetail) void loadControl(); }, [obra.id, user.id, user.role, costsView]);

  async function afterWrite() {
    const results = [await api.requiredLoad('summary', `${base}costos/resumen/`, (data) => { if (!object(data) || !['materiales_total', 'otros_total', 'mano_obra_total', 'costo_total'].every((key) => typeof data[key] === 'string' && decimal(data[key], 2)) || typeof data.costos_validados !== 'boolean') throw new Error('Resumen de costos inesperado.'); setSummary(data); })];
    if (canSeeDetail) {
      results.push(await api.requiredLoad('control', `${base}costos/control/`, (data) => setControl(data)));
      if (expensesView) results.push(await api.requiredLoad('expenses', expensesPath, (data) => { const result = readPage(data, `${base}gastos/`); setExpenses({ ...result, results: result.results.map(projectExpense) }); }));
      if (costsView) results.push(await api.requiredLoad('history', historyPath, (data) => setHistory(readPage(data, `${base}costos/historial/`))));
    }
    // requiredLoad resolves only after each refresh applies successfully; it throws on failure.
    if (results.length) { setForm(null); setIssue(''); setMotive(''); }
  }

  async function saveExpense(event) {
    event.preventDefault(); if (!canManage || api.busy || api.locked) return;
    const item = form?.item, values = form?.values || emptyExpense;
    const errors = {};
    if (!values.descripcion.trim()) errors.descripcion = 'Campo obligatorio';
    if (!values.unidad.trim()) errors.unidad = 'Campo obligatorio';
    if (!decimal(values.cantidad, 3) || Number(values.cantidad) <= 0) errors.cantidad = 'Usa una cantidad positiva con hasta 3 decimales.';
    if (!decimal(values.costo_unitario_neto, 2)) errors.costo_unitario_neto = 'Usa un decimal positivo con hasta 2 decimales.';
    if (!validDate(values.fecha_gasto)) errors.fecha_gasto = 'Fecha inválida.';
    if (item && !motive.trim()) errors.motivo = 'Indica el motivo de corrección.';
    if (Object.keys(errors).length) { setIssue(Object.values(errors).join(' ')); return; }
    const payload = { ...values, descripcion: values.descripcion.trim(), unidad: values.unidad.trim(), cantidad: values.cantidad.trim(), costo_unitario_neto: values.costo_unitario_neto.trim(), referencia_respaldo: values.referencia_respaldo.trim(), observacion: values.observacion.trim(), ...(item ? { motivo: motive.trim() } : {}) };
    await api.write(item ? `${base}gastos/${item.id}/` : `${base}gastos/`, item ? 'PATCH' : 'POST', payload, afterWrite);
  }

  async function action(path, body, method = 'POST') {
    if (!canManage || busyAction || api.busy || api.locked) return;
    setIssue(''); setBusyAction(true);
    try { await api.write(path, method, body, afterWrite); }
    finally { setBusyAction(false); }
  }
  async function declareRubric(name, state, justification) {
    const payload = { [`${name}_estado`]: state, [`${name}_justificacion`]: state === 'NO_APLICA' ? justification.trim() : '', motivo: motive.trim() };
    if (!payload.motivo) { setIssue('Indica el motivo del cambio de control.'); return; }
    await action(`${base}costos/control/`, payload, 'PATCH');
  }
  async function finalize() {
    if (!canManage || obra.estado !== 'EN_PROCESO' || !finalReason.trim()) { setIssue('La finalización requiere un motivo y una obra en proceso.'); return; }
    if (!globalThis.confirm?.('¿Finalizar esta obra? La finalización operativa es terminal.')) return;
    setBusyAction(true); setIssue('');
    try { await api.write(`${base}finalizar/`, 'POST', { motivo: finalReason.trim() }, async () => { await onFinalized(); await afterWrite(); }); }
    finally { setBusyAction(false); }
  }

  if (!canRead) return <p role="alert">No tienes acceso a los costos de esta obra.</p>;
  return <section aria-label="Costos y finalización">
    <PageHead title={expensesView ? 'Materiales y gastos' : 'Costos y cierre operativo'} sub={expensesView ? 'Movimientos de gastos registrados en esta Obra.' : 'Consulta los costos de esta obra.'} />
    <Feedback api={api} />
    {issue && <p className="alert alert-warning" role="alert">{issue}</p>}
    {costsView && summary && <section className="card-fyag p-3 mb-3" aria-label="Resumen de costos">
      <h3>Resumen económico</h3>
      <dl className="commercial-facts">
        <div><dt>Materiales netos</dt><dd>{money(summary.materiales_total)}</dd></div><div><dt>Otros gastos netos</dt><dd>{money(summary.otros_total)}</dd></div>
        <div><dt>Mano de obra neta</dt><dd>{money(summary.mano_obra_total)}</dd></div><div><dt>Costo real total</dt><dd>{money(summary.costo_total)}</dd></div>
        <div><dt>Validación</dt><dd>{summary.costos_validados ? 'Validado' : summary.provisional ? 'Pendiente o provisional' : 'No validado'}</dd></div>
        <div><dt>Sin cobro</dt><dd>{summary.cortesia_sin_cobro ? 'Registrado; el costo real no cambia' : 'No registrado'}</dd></div>
      </dl>
      {summary.cortesia_justificacion && <p>Justificación de cortesía: {summary.cortesia_justificacion}</p>}
    </section>}

    {costsView && canSeeDetail && control && <section className="card-fyag p-3 mb-3"><h3>Control de rubros</h3>
        <p>Versión {control.version_actual} · {control.costos_validados ? `Validada (versión ${control.version_validada})` : 'Sin validación vigente'}{control.validado_en ? ` · ${timestamp(control.validado_en)}` : ''}</p>
        {canManage ? ['materiales', 'otros'].map((name) => <Rubric key={`${control.version_actual}:${name}`} name={name} control={control} disabled={obra.estado === 'FINALIZADA' || api.busy || api.locked} onDeclare={declareRubric} />) : <dl className="commercial-facts" aria-label="Estado de los rubros">{['materiales','otros'].map(name=><div key={name}><dt>{name==='materiales'?'Materiales':'Otros gastos'}</dt><dd>{({PENDIENTE:'Pendiente',CON_REGISTROS:'Con registros',NO_APLICA:'No aplica'})[control[`${name}_estado`]]}</dd>{control[`${name}_justificacion`]&&<dd>{control[`${name}_justificacion`]}</dd>}</div>)}</dl>}
        {canManage && ['EN_PROCESO', 'SUSPENDIDA'].includes(obra.estado) && <div className="commercial-form-actions"><Field name="costos-motivo" label="Motivo para validar costos" value={motive} onChange={setMotive} maxLength={2000} /><button type="button" className="btn btn-fyag-primary" disabled={api.busy || api.locked || busyAction || control.costos_validados || !motive.trim()} onClick={() => action(`${base}costos/validar/`, { motivo: motive.trim() })}>Validar costos</button></div>}
        {canManage && ['EN_PROCESO', 'SUSPENDIDA'].includes(obra.estado) && <div className="commercial-form-actions"><Field name="cortesia-justificacion" label="Justificación de sin cobro (no reduce costos)" value={courtesyReason} onChange={setCourtesyReason} maxLength={2000} /><button type="button" className="btn btn-outline-secondary" disabled={api.busy || api.locked || !courtesyReason.trim() || (!!summary.cortesia_sin_cobro && !motive.trim())} onClick={() => action(`${base}cortesia-sin-cobro/`, { justificacion: courtesyReason.trim(), ...(summary.cortesia_sin_cobro ? { motivo: motive.trim() } : {}) })}>Registrar / rectificar sin cobro</button></div>}
      </section>}

      {expensesView && canManage && !form?.mode && ['EN_PROCESO', 'SUSPENDIDA'].includes(obra.estado) && <form className="card-fyag commercial-form mb-3" noValidate onSubmit={saveExpense}>
        <h3>{form?.item ? `Corregir gasto #${form.item.id}` : 'Registrar material u otro gasto'}</h3>
        <div className="obras-form-grid">
          <Field name="gasto-tipo" label="Tipo" value={form?.values.tipo ?? emptyExpense.tipo} options={TYPES} disabled={api.busy || api.locked} onChange={(v) => setForm({ ...(form || {}), values: { ...emptyExpense, ...(form?.values || {}), tipo: v } })} />
          {['descripcion', 'unidad', 'cantidad', 'costo_unitario_neto', 'fecha_gasto', 'referencia_respaldo', 'observacion'].map((key) => <Field key={key} name={`gasto-${key}`} label={({ descripcion: 'Descripción', unidad: 'Unidad', cantidad: 'Cantidad (decimal)', costo_unitario_neto: 'Costo unitario neto (decimal string)', fecha_gasto: 'Fecha del gasto', referencia_respaldo: 'Referencia de respaldo', observacion: 'Observación' })[key]} type={key === 'fecha_gasto' ? 'date' : ['observacion'].includes(key) ? 'textarea' : 'text'} value={form?.values[key] ?? emptyExpense[key]} maxLength={key === 'descripcion' ? 500 : key === 'unidad' ? 30 : key === 'observacion' ? 2000 : undefined} disabled={api.busy || api.locked} onChange={(v) => setForm({ ...(form || {}), values: { ...emptyExpense, ...(form?.values || {}), [key]: v } })} />)}
          {form?.item && <Field name="gasto-motivo" label="Motivo de corrección" value={motive} onChange={setMotive} maxLength={2000} disabled={api.busy || api.locked} />}
        </div>
        <div className="commercial-form-actions"><button type="submit" className="btn btn-fyag-primary" disabled={api.busy || api.locked}>{api.busy ? 'Guardando…' : form?.item ? 'Guardar corrección' : 'Registrar gasto'}</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={() => { setForm(null); setMotive(''); setIssue(''); }}>Cancelar</button></div>
      </form>}

      {expensesView && canSeeDetail && <section className="card-fyag p-3 mb-3"><h3>Materiales y gastos</h3>
        {expenses?.results.length === 0 && <p className="commercial-empty">No hay gastos registrados.</p>}
        <div className="table-responsive" role="region" aria-label="Gastos de la obra" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Tipo', 'Descripción', 'Unidad', 'Cantidad / devuelta', 'Costo unitario neto', 'Subtotal neto', 'Fecha', 'Vigencia', ...(canManage ? ['Acciones'] : [])].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{expenses?.results.map((item) => <tr key={item.id}><td>{TYPES.find(([key]) => key === item.tipo)?.[1] || item.tipo}</td><td>{item.descripcion}</td><td>{item.unidad}</td><td>{item.cantidad} / {item.cantidad_devuelta}</td><td>{money(item.costo_unitario_neto)}</td><td>{money(item.subtotal)}</td><td>{item.fecha_gasto}</td><td>{item.vigente ? 'Vigente' : `Anulado${item.motivo_anulacion ? `: ${item.motivo_anulacion}` : ''}`}</td>{canManage && <td>{item.vigente && ['EN_PROCESO', 'SUSPENDIDA'].includes(obra.estado) && <div className="commercial-row-actions"><button className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.locked} onClick={() => { setForm({ item, values: Object.fromEntries(Object.keys(emptyExpense).map((key) => [key, item[key] ?? ''])) }); setMotive(''); }}>Corregir</button>{item.tipo === 'MATERIAL' && compareDecimal(item.cantidad_devuelta, item.cantidad) < 0 && <button className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.locked} onClick={() => setForm({ mode: 'devolver', item, values: { cantidad: '', fecha_devolucion: '', motivo: '' } })}>Devolver cantidad</button>}<button className="btn btn-outline-danger btn-sm" disabled={api.busy || api.locked} onClick={() => setForm({ mode: 'anular', item, values: { motivo: '' } })}>Anular</button></div>}</td>}</tr>)}</tbody></table></div>
        <Pager label="Paginación de gastos" data={expenses} page={page} setPage={setPage} disabled={api.loading || api.busy || api.locked} />
      </section>}

      {expensesView && form?.mode && <TransactionForm mode={form.mode} item={form.item} api={api} onCancel={() => setForm(null)} onSave={(body, endpoint) => action(endpoint, body)} obraPath={base} />}

      {costsView && canSeeDetail && history && <section className="card-fyag p-3"><h3>Historial de costos</h3>{history.results.length === 0 && <p>No hay eventos económicos.</p>}<ol>{history.results.map((event) => <li key={event.id}><strong>{String(event.tipo).replaceAll('_', ' ')}</strong> · {timestamp(event.creado_en)} · Usuario #{event.registrado_por}<p>{event.motivo || 'Sin motivo'}</p><SafeChanges data={event.datos_nuevos} /></li>)}</ol><Pager label="Paginación del historial de costos" data={history} page={historyPage} setPage={setHistoryPage} disabled={api.loading || api.busy || api.locked} /></section>}

    {costsView && canManage && obra.estado === 'EN_PROCESO' && <section className="card-fyag p-3 mt-3"><h3>Finalización operativa</h3><p>Para finalizar la obra, primero valida sus costos.</p><Field name="finalizar-motivo" label="Motivo de finalización" type="textarea" value={finalReason} onChange={setFinalReason} maxLength={2000} disabled={api.busy || api.locked} /><button type="button" className="btn btn-outline-danger mt-2" disabled={api.busy || api.locked || busyAction || !finalReason.trim() || !summary?.costos_validados} onClick={finalize}>Finalizar obra</button></section>}
  </section>;
}

function Rubric({ name, control, disabled, onDeclare }) {
  const [state, setState] = useState(control[`${name}_estado`] === 'NO_APLICA' ? 'NO_APLICA' : 'CON_REGISTROS');
  const [reason, setReason] = useState(control[`${name}_justificacion`] || '');
  return <div className="obras-form-grid mb-3"><Field name={`rubric-${name}`} label={name === 'materiales' ? 'Materiales' : 'Otros gastos'} value={state} options={[[ 'CON_REGISTROS', 'Con registros' ], [ 'NO_APLICA', 'No aplica' ]]} disabled={disabled} onChange={setState} />{state === 'NO_APLICA' && <Field name={`rubric-${name}-reason`} label="Justificación obligatoria" value={reason} disabled={disabled} maxLength={2000} onChange={setReason} />}<button type="button" className="btn btn-outline-secondary align-self-end" disabled={disabled || (state === 'NO_APLICA' && !reason.trim())} onClick={() => onDeclare(name, state, reason)}>Guardar declaración de rubro</button></div>;
}

function TransactionForm({ mode, item, api, onCancel, onSave, obraPath: base }) {
  const [values, setValues] = useState({ cantidad: '', fecha_devolucion: '', motivo: '' });
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (!values.motivo.trim()) { setError('El motivo es obligatorio.'); return; }
    if (mode === 'devolver' && (!decimal(values.cantidad, 3) || compareDecimal(values.cantidad, '0') <= 0 || !validDate(values.fecha_devolucion))) { setError('Ingresa una cantidad decimal positiva y fecha.'); return; }
    const endpoint = mode === 'devolver' ? `${base}gastos/${item.id}/devolver/` : `${base}gastos/${item.id}/anular/`;
    await onSave(mode === 'devolver' ? { ...values, cantidad: values.cantidad.trim(), motivo: values.motivo.trim() } : { motivo: values.motivo.trim() }, endpoint);
  }
  return <form className="card-fyag commercial-form" onSubmit={submit}><h3>{mode === 'devolver' ? `Devolver cantidad del material #${item.id}` : `Anular gasto #${item.id}`}</h3>{mode === 'devolver' && <><Field name="devolucion-cantidad" label="Cantidad a devolver" value={values.cantidad} onChange={(v) => setValues({ ...values, cantidad: v })} /><Field name="devolucion-fecha" label="Fecha de devolución" type="date" value={values.fecha_devolucion} onChange={(v) => setValues({ ...values, fecha_devolucion: v })} /></>}<Field name="transaccion-motivo" label="Motivo" type="textarea" value={values.motivo} maxLength={2000} onChange={(v) => setValues({ ...values, motivo: v })} />{error && <p role="alert">{error}</p>}<div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy || api.locked} type="submit">Confirmar</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={onCancel}>Cancelar</button></div></form>;
}

const SAFE_CHANGE_KEYS = new Set(['tipo', 'descripcion', 'unidad', 'cantidad', 'cantidad_devuelta', 'costo_unitario_neto', 'fecha_gasto', 'vigente', 'subtotal', 'version_costos', 'materiales_estado', 'otros_estado', 'materiales_justificacion', 'otros_justificacion', 'cortesia', 'version_actual', 'version_validada']);
function SafeChanges({ data }) {
  if (!object(data)) return null;
  const entries = Object.entries(data).filter(([key, value]) => SAFE_CHANGE_KEYS.has(key) && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'));
  if (!entries.length) return null;
  return <dl className="obras-event-changes">{entries.map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}</dl>;
}
