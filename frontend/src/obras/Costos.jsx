import WarehouseAuthorization from './WarehouseAuthorization.jsx';
import MaterialPlan from './MaterialPlan.jsx';
import {quantityInput,unitCostInput,quantityHint,moneyHint} from '../utils/decimalInput.js';
import SupervisorCostHistory from './SupervisorCostHistory.jsx';
import SupervisorCostReview, {SupervisorEmpty} from './SupervisorCostReview.jsx';
import TecIcon from './TecIcon.jsx';
import { formatCLP, formatCompactCLP, formatCivilDate } from '../utils/format.js';
import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PageHead } from '../components/ui';
import { AF, G, S, timestamp } from './domain.js';
import { obraPath, readPage } from './api.js';
import { Feedback, Field, Pager, useOperational } from './ui.jsx';

const TYPES = [['MATERIAL', 'Material comprado fuera de Bodega'], ['TRANSPORTE', 'Transporte'], ['ARRIENDO_EQUIPO', 'Arriendo de equipo'], ['SERVICIO_EXTERNO', 'Servicio externo'], ['OTRO', 'Otro']];
const emptyExpense = { tipo: 'MATERIAL', descripcion: '', unidad: '', cantidad: '', costo_unitario_neto: '', fecha_gasto: '', referencia_respaldo: '', observacion: '' };
const decimal = (value, scale) => new RegExp(`^[0-9]{1,${scale === 2 ? 13 : 9}}(?:\\.[0-9]{1,${scale}})?$`).test(value);
const validId = (value) => /^[1-9][0-9]*$/.test(String(value)) && Number.isSafeInteger(Number(value));
const compareDecimal = (left, right, scale = 3) => { const unit = 10n ** BigInt(scale); const toInt = (value) => { const [whole, fraction = ''] = String(value).split('.'); return BigInt(whole || '0') * unit + BigInt((fraction + '0'.repeat(scale)).slice(0, scale)); }; return toInt(left) - toInt(right); };
const object = (data) => data && typeof data === 'object' && !Array.isArray(data);
function money(value) { return formatCLP(value); }
function strictKeys(value, keys) { return object(value) && Object.keys(value).every((key) => keys.includes(key)); }
function projectExpense(row) {
  const keys = ['id', 'obra', 'tipo', 'origen', 'entrega_bodega', 'descripcion', 'unidad', 'cantidad', 'cantidad_devuelta', 'costo_unitario_neto', 'subtotal', 'fecha_gasto', 'referencia_respaldo', 'observacion', 'vigente', 'anulado_por', 'anulado_en', 'motivo_anulacion', 'registrado_por', 'creado_en', 'actualizado_en'];
  if (!strictKeys(row, keys) || !['MANUAL','BODEGA_019B'].includes(row.origen) || (row.origen==='MANUAL'?row.entrega_bodega!==null:row.tipo!=='MATERIAL'||!validId(row.entrega_bodega)) || !validId(String(row.id)) || !validId(String(row.obra)) || !TYPES.some(([type]) => type === row.tipo) || !['descripcion', 'unidad', 'cantidad', 'cantidad_devuelta', 'costo_unitario_neto', 'subtotal', 'fecha_gasto', 'referencia_respaldo', 'observacion', 'motivo_anulacion'].every((key) => typeof row[key] === 'string') || !['cantidad', 'cantidad_devuelta'].every((key) => decimal(row[key], 3)) || !['costo_unitario_neto', 'subtotal'].every((key) => decimal(row[key], 2)) || typeof row.vigente !== 'boolean') throw new Error('Gasto con formato inesperado.');
  return Object.fromEntries(keys.map((key) => [key, row[key]]));
}
function validDate(value) { if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false; const date = new Date(`${value}T00:00:00Z`); return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value; }

export default function Costos({ obra, onFinalized, section = 'costs', onTab, onOperationalLock }) {
  const { user } = useAuth(), api = useOperational();
  const base = obraPath(obra.id);
  const [page, setPage] = useState(1), [historyPage, setHistoryPage] = useState(1), [expenses, setExpenses] = useState(null), [control, setControl] = useState(null), [summary, setSummary] = useState(null), [history, setHistory] = useState(null);
  const [refreshEpoch,setRefreshEpoch]=useState(0),[expenseOpen,setExpenseOpen]=useState(false),[warehouseForm,setWarehouseForm]=useState(null),[notice,setNotice]=useState('');
  useEffect(()=>{onOperationalLock?.(api.busy||api.locked||!!warehouseForm);return()=>onOperationalLock?.(false);},[api.busy,api.locked,warehouseForm,onOperationalLock]);
  const [form, setForm] = useState(null), [issue, setIssue] = useState(''), [busyAction, setBusyAction] = useState(false);
  const [motive, setMotive] = useState('');
  const [requirements, setRequirements] = useState(null);
  const canManage = user.role === S, canRead = [G, S, AF].includes(user.role), canSeeDetail = [G, S].includes(user.role);
  const expensesView = section === 'expenses', costsView = section === 'costs';
  const expensesPath = `${base}gastos/?page=${page}`, historyPath = `${base}costos/historial/?page=${historyPage}`;

  function loadExpenses() { return api.load('expenses', expensesPath, (data) => { const result = readPage(data, `${base}gastos/`); setExpenses({ ...result, results: result.results.map(projectExpense) }); }); }
  function loadControl() { return api.load('control', `${base}costos/control/`, (data) => { const keys = ['id', 'obra', 'materiales_estado', 'materiales_justificacion', 'otros_estado', 'otros_justificacion', 'version_actual', 'version_validada', 'validado_por', 'validado_en', 'costos_validados', 'creado_en', 'actualizado_en']; if (!strictKeys(data, keys) || !Number.isSafeInteger(data.version_actual) || typeof data.costos_validados !== 'boolean' || !['PENDIENTE', 'CON_REGISTROS', 'NO_APLICA'].includes(data.materiales_estado) || !['PENDIENTE', 'CON_REGISTROS', 'NO_APLICA'].includes(data.otros_estado)) throw new Error('Control de costos inesperado.'); setControl(Object.fromEntries(keys.map((key) => [key, data[key]]))); }); }
  function loadSummary() { return api.load('summary', `${base}costos/resumen/`, (data) => { const keys = user.role === AF ? ['obra', 'materiales_total', 'otros_total', 'mano_obra_total', 'costo_total', 'costos_validados', 'cortesia_sin_cobro'] : ['obra', 'materiales_total', 'otros_total', 'mano_obra_total', 'costo_total', 'costos_validados', 'cortesia_sin_cobro', 'materiales_estado', 'otros_estado', 'materiales_justificacion', 'otros_justificacion', 'version_actual', 'version_validada', 'validado_por', 'validado_en', 'cortesia_justificacion', 'provisional']; if (!strictKeys(data, keys) || !['materiales_total', 'otros_total', 'mano_obra_total', 'costo_total'].every((key) => typeof data[key] === 'string' && decimal(data[key], 2)) || typeof data.costos_validados !== 'boolean' || typeof data.cortesia_sin_cobro !== 'boolean') throw new Error('Resumen de costos inesperado.'); setSummary(Object.fromEntries(keys.map((key) => [key, data[key]]))); }); }
  function loadHistory() { return api.load('history', historyPath, (data) => { const result = readPage(data, `${base}costos/historial/`); const keys = ['id', 'obra', 'gasto', 'control', 'cortesia', 'tipo', 'registrado_por', 'motivo', 'datos_anteriores', 'datos_nuevos', 'creado_en']; if (result.results.some((event) => !strictKeys(event, keys) || typeof event.tipo !== 'string' || typeof event.motivo !== 'string' || !object(event.datos_nuevos))) throw new Error('Historial de costos inesperado.'); setHistory(result); }); }
  function loadRequirements() {
    setRequirements(null);
    return api.load('requirements', `${base}requisitos-cierre/`, data => {
      const valid = data && ['validacion','finalizacion','devoluciones','despachos'].every(key=>Array.isArray(data[key])) &&
        (data.confirmacion_remanente===null || /^[0-9a-f]{64}$/.test(data.confirmacion_remanente)) &&
        !!data.confirmacion_remanente===!!data.despachos.length;
      if(!valid) throw new Error('No se pudieron comprobar los requisitos de cierre.');
      setRequirements(data);
    });
  }
  useEffect(() => { setExpenses(null); if (canSeeDetail && expensesView) void loadExpenses(); }, [obra.id, page, user.id, user.role, expensesView]);
  useEffect(() => { setHistory(null); if (canSeeDetail && costsView) void loadHistory(); }, [obra.id, historyPage, user.id, user.role, costsView]);
  useEffect(() => { setControl(null); setSummary(null); setRequirements(null); if (costsView && canRead) void loadSummary(); if (costsView && canSeeDetail && !canManage) void loadControl(); if(costsView&&canManage&&['EN_PROCESO','SUSPENDIDA'].includes(obra.estado)) void loadRequirements(); }, [obra.id, obra.estado, user.id, user.role, costsView]);

  async function afterWrite() {
    if (canSeeDetail) {
      if(costsView) await api.requiredLoad('summary', `${base}costos/resumen/`, (data) => { if (!object(data) || !['materiales_total', 'otros_total', 'mano_obra_total', 'costo_total'].every((key) => typeof data[key] === 'string' && decimal(data[key], 2)) || typeof data.costos_validados !== 'boolean') throw new Error('Resumen de costos inesperado.'); setSummary(data); });
      if (expensesView) await api.requiredLoad('expenses', expensesPath, (data) => { const result = readPage(data, `${base}gastos/`); setExpenses({ ...result, results: result.results.map(projectExpense) }); });
      if (costsView) await api.requiredLoad('history', historyPath, (data) => setHistory(readPage(data, `${base}costos/historial/`)));
    }
    setForm(null); setIssue(''); setMotive(''); setExpenseOpen(false);
  }

  async function saveExpense(event) {
    event.preventDefault(); if (!canManage || !['EN_PROCESO','SUSPENDIDA'].includes(obra.estado) || api.busy || api.loading || api.locked) return;
    const item = form?.item, values = form?.values || emptyExpense;
    if(item&&item.origen!=='MANUAL')return;
    const errors = {};
    if (!values.descripcion.trim()) errors.descripcion = 'Campo obligatorio';
    if (!values.unidad.trim()) errors.unidad = 'Campo obligatorio';
    const quantity=quantityInput(values.cantidad),unitCost=unitCostInput(values.costo_unitario_neto);
    if (quantity===null) errors.cantidad = 'Ingresa una cantidad mayor que cero, con hasta tres cifras después de la coma.';
    if (unitCost===null) errors.costo_unitario_neto = 'Ingresa un costo por unidad válido, sin separadores de miles.';
    if (!validDate(values.fecha_gasto)) errors.fecha_gasto = 'Fecha inválida.';
    if (item && !motive.trim()) errors.motivo = 'Indica el motivo de corrección.';
    if (Object.keys(errors).length) { setIssue(Object.values(errors).join(' ')); return; }
    const payload = { ...values, descripcion: values.descripcion.trim(), unidad: values.unidad.trim(), cantidad: quantity, costo_unitario_neto: unitCost, referencia_respaldo: values.referencia_respaldo.trim(), observacion: values.observacion.trim(), ...(item ? { motivo: motive.trim() } : {}) };
    if(values.tipo==='MATERIAL'&&(!item||item.tipo!=='MATERIAL')&&!globalThis.confirm?.('¿Confirmas que el material fue comprado fuera de Bodega y no está imputado por una entrega de inventario? Registrar el mismo consumo dos veces duplicaría el costo.'))return;
    await api.write(item ? `${base}gastos/${item.id}/` : `${base}gastos/`, item ? 'PATCH' : 'POST', payload, afterWrite);
  }

  async function action(path, body, method = 'POST') {
    if (!canManage || !['EN_PROCESO','SUSPENDIDA'].includes(obra.estado) || busyAction || api.busy || api.loading || api.locked) return false;
    setIssue(''); setBusyAction(true);
    try { const ok=await api.write(path, method, body, afterWrite); if(costsView) void loadRequirements(); return ok; }
    finally { setBusyAction(false); }
  }
  async function finalize(reason, confirmation) {
    if (!canManage || obra.estado !== 'EN_PROCESO' || !reason.trim() || !summary?.costos_validados || !requirements || requirements.finalizacion.length || requirements.devoluciones.length || api.busy || api.loading || api.locked || busyAction) return false;
    setBusyAction(true); setIssue('');
    try { const ok=await api.write(`${base}finalizar/`, 'POST', { motivo: reason.trim(), ...(confirmation?{confirmacion_remanente:confirmation}:{}) }, async () => { await onFinalized(); }); if(!ok){setRefreshEpoch(v=>v+1);void loadRequirements();} return ok; }
    finally { setBusyAction(false); }
  }

  async function reconsult() {
    if(api.busy||api.loading||warehouseForm)return;
    await api.reconcile(async()=>{
      const reads=costsView?[loadSummary(),loadHistory(),...(canManage?(['EN_PROCESO','SUSPENDIDA'].includes(obra.estado)?[loadRequirements()]:[]):[loadControl()])]:[loadExpenses()];
      const ok=(await Promise.all(reads)).every(Boolean);
      if(!ok)return false;
      if(onFinalized){try{await onFinalized();}catch{api.setError(new Error('No se pudo actualizar el estado de la obra. Reconsulta antes de continuar.'));return false;}}
      setForm(null);setExpenseOpen(false);setIssue('');setMotive('');setRefreshEpoch(v=>v+1);
      return true;
    });
  }
  if (!canRead) return <p role="alert">No tienes acceso a los costos de esta obra.</p>;
  return <section className={canManage?'so-costs':undefined} aria-label="Costos y finalización">
    {canManage?<div className="so-section-head"><div><h2>{expensesView?'Materiales y gastos':'Costos y cierre operativo'}</h2><p className="commercial-help">{expensesView?'Consulta los costos reales de la obra, autoriza entregas y registra gastos externos.':'Revisa los rubros, valida los costos y completa el cierre.'}</p></div><div className="so-actions so-expense-toolbar"><button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.loading||!!warehouseForm} onClick={()=>void reconsult()}><TecIcon name="refresh"/> {api.locked?'Reconsultar resultado':'Actualizar'}</button>{expensesView&&canManage&&!expenseOpen&&!form&&!warehouseForm&&['EN_PROCESO','SUSPENDIDA'].includes(obra.estado)&&<><button type="button" className="btn btn-fyag-primary" disabled={api.busy||api.loading||api.locked} onClick={()=>{setNotice('');setWarehouseForm({});}}><TecIcon name="plus"/> Autorizar material</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.loading||api.locked} onClick={()=>{setExpenseOpen(true);setNotice('');setIssue('');}}><TecIcon name="plus"/> Registrar gasto externo</button></>}</div></div>:<PageHead title={expensesView ? 'Materiales y gastos' : 'Costos y cierre operativo'} sub={expensesView ? 'Movimientos de gastos registrados en esta Obra.' : 'Consulta los costos de esta obra.'} />}
    <Feedback api={api} />
    {notice&&<p className="alert alert-success" role="status">{notice}</p>}
    {expensesView&&canManage&&warehouseForm&&<WarehouseAuthorization obra={obra} delivery={warehouseForm.delivery} onClose={()=>setWarehouseForm(null)} onConfirmed={message=>{setWarehouseForm(null);setNotice(message);void loadExpenses();}}/>}
    {issue && <p className="alert alert-warning" role="alert">{issue}</p>}
    {expensesView&&canSeeDetail&&!warehouseForm&&!expenseOpen&&!form&&<MaterialPlan obra={obra} revision={refreshEpoch} disabled={api.busy||api.locked}/>}
    {costsView&&canManage&&<SupervisorCostReview obra={obra} summary={summary} requirements={requirements} api={api} busyAction={busyAction} refreshEpoch={refreshEpoch} onAction={(suffix,body)=>action(base+suffix,body)} onFinalize={finalize} onTab={onTab}/>}
    {costsView && !canManage && summary && <section className="card-fyag p-3 mb-3" aria-label="Resumen de costos">
      <h3>Resumen económico</h3>
      <dl className="commercial-facts">
        <div><dt>Materiales netos</dt><dd>{money(summary.materiales_total)}</dd></div><div><dt>Otros gastos netos</dt><dd>{money(summary.otros_total)}</dd></div>
        <div><dt>Mano de obra neta</dt><dd>{money(summary.mano_obra_total)}</dd></div><div><dt>Costo real total</dt><dd>{money(summary.costo_total)}</dd></div>
        <div><dt>Validación</dt><dd>{summary.costos_validados ? 'Validado' : summary.provisional ? 'Pendiente o provisional' : 'No validado'}</dd></div>
        <div><dt>Sin cobro</dt><dd>{summary.cortesia_sin_cobro ? 'Registrado; el costo real no cambia' : 'No registrado'}</dd></div>
      </dl>
      {summary.cortesia_justificacion && <p>Justificación de cortesía: {summary.cortesia_justificacion}</p>}
    </section>}

    {costsView && !canManage && canSeeDetail && control && <section className="card-fyag p-3 mb-3"><h3>Control de rubros</h3>
        <p>Versión {control.version_actual} · {control.costos_validados ? `Validada (versión ${control.version_validada})` : 'Sin validación vigente'}{control.validado_en ? ` · ${timestamp(control.validado_en)}` : ''}</p>
        <dl className="commercial-facts" aria-label="Estado de los rubros">{['materiales','otros'].map(name=><div key={name}><dt>{name==='materiales'?'Materiales':'Otros gastos'}</dt><dd>{({PENDIENTE:'Pendiente',CON_REGISTROS:'Con registros',NO_APLICA:'No aplica'})[control[`${name}_estado`]]}</dd>{control[`${name}_justificacion`]&&<dd>{control[`${name}_justificacion`]}</dd>}</div>)}</dl>
      </section>}

      
      {expensesView && canManage && (expenseOpen||form?.item) && !form?.mode && ['EN_PROCESO', 'SUSPENDIDA'].includes(obra.estado) && <form className="card-fyag commercial-form mb-3" noValidate onSubmit={saveExpense}>
        <h3>{form?.item ? `Corregir gasto #${form.item.id}` : 'Registrar gasto externo'}</h3>
        <p className="commercial-help">Usa este formulario para compras o servicios pagados fuera del inventario. Los materiales entregados por Bodega se registran automáticamente; no vuelvas a ingresarlos aquí.</p>
        <div className="obras-form-grid">
          <Field name="gasto-tipo" label="Tipo" value={form?.values.tipo ?? emptyExpense.tipo} options={TYPES} disabled={api.busy || api.locked} onChange={(v) => setForm({ ...(form || {}), values: { ...emptyExpense, ...(form?.values || {}), tipo: v } })} />
          {['descripcion', 'unidad', 'cantidad', 'costo_unitario_neto', 'fecha_gasto', 'referencia_respaldo', 'observacion'].map((key) => <Field key={key} name={`gasto-${key}`} label={({ descripcion: 'Descripción del gasto', unidad: 'Unidad de medida', cantidad: 'Cantidad', costo_unitario_neto: 'Costo por unidad (CLP, sin IVA)', fecha_gasto: 'Fecha del gasto', referencia_respaldo: 'N.º de documento de respaldo (opcional)', observacion: 'Observaciones (opcional)' })[key]} type={key === 'fecha_gasto' ? 'date' : ['observacion'].includes(key) ? 'textarea' : 'text'} inputMode={['cantidad','costo_unitario_neto'].includes(key)?'decimal':undefined} placeholder={key==='cantidad'?'Ej.: 2,5':key==='costo_unitario_neto'?'Ej.: 18500 o 18500,50':key==='descripcion'?'Ej.: transporte de materiales':key==='unidad'?'Ej.: unidad, metro, viaje':key==='referencia_respaldo'?'Ej.: factura 125, boleta 36':key==='observacion'?'Detalles adicionales del gasto':undefined} value={form?.values[key] ?? emptyExpense[key]} maxLength={key === 'descripcion' ? 500 : key === 'unidad' ? 30 : key === 'observacion' ? 2000 : key==='referencia_respaldo'?500:undefined} disabled={api.busy || api.locked} onChange={(v) => setForm({ ...(form || {}), values: { ...emptyExpense, ...(form?.values || {}), [key]: v } })} />)}
          {form?.item && <Field name="gasto-motivo" label="Motivo de corrección" value={motive} onChange={setMotive} maxLength={2000} disabled={api.busy || api.locked} />}
        </div>
        <div className="commercial-form-actions"><button type="submit" className="btn btn-fyag-primary" disabled={api.busy || api.locked}>{api.busy ? 'Guardando…' : form?.item ? 'Guardar corrección' : 'Registrar gasto externo'}</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.locked} onClick={() => { setForm(null); setExpenseOpen(false); setMotive(''); setIssue(''); }}>Cancelar</button></div>
      </form>}

      {expensesView && canSeeDetail && <section className={canManage?'card-fyag so-panel':'card-fyag p-3 mb-3'}><h3>{canManage?'Costos de materiales y gastos externos':'Materiales y gastos'}</h3>{canManage&&<p className="commercial-help">Bodega: costo de despachos confirmados, con devolución por Inventario. Externos: registros manuales de compras y servicios. El listado reúne ambos orígenes.</p>}
        {expenses?.results.length === 0 && (canManage?<SupervisorEmpty title="No hay gastos registrados" description="Los materiales y gastos de esta obra aparecerán aquí."/>:<p className="commercial-empty">No hay gastos registrados.</p>)}
        {(!canManage||!!expenses?.results.length)&&<div className="table-responsive" role="region" aria-label="Gastos de la obra" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Origen / tipo', 'Descripción', 'Unidad', 'Cantidad / devuelta', 'Costo unitario neto', 'Subtotal neto', 'Fecha', 'Vigencia', ...(canManage ? ['Acciones'] : [])].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{expenses?.results.map((item) => <tr key={item.id}><td><strong>{item.origen==='BODEGA_019B'?'Bodega':'Externo'}</strong><span className="commercial-help d-block">{item.origen==='BODEGA_019B'?'Entrega de material':TYPES.find(([key]) => key === item.tipo)?.[1] || item.tipo}</span></td><td>{item.descripcion}</td><td>{item.unidad}</td><td>{item.cantidad} / {item.cantidad_devuelta}</td><td className={canManage?'commercial-money':undefined}>{canManage?formatCompactCLP(item.costo_unitario_neto):money(item.costo_unitario_neto)}</td><td className={canManage?'commercial-money fw-bold':undefined}>{canManage?formatCompactCLP(item.subtotal):money(item.subtotal)}</td><td>{canManage?formatCivilDate(item.fecha_gasto):item.fecha_gasto}</td><td>{item.vigente ? 'Vigente' : `Anulado${item.motivo_anulacion ? `: ${item.motivo_anulacion}` : ''}`}</td>{canManage && <td>{item.vigente && ['EN_PROCESO', 'SUSPENDIDA'].includes(obra.estado) && (item.origen==='BODEGA_019B'?<div className="commercial-row-actions">{compareDecimal(item.cantidad_devuelta,item.cantidad)<0?<button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy||api.locked||!!form||expenseOpen||!!warehouseForm} onClick={()=>{setNotice('');setWarehouseForm({delivery:item});}}>Autorizar devolución</button>:<span className="commercial-help">Devuelto</span>}</div>:<div className="commercial-row-actions"><button className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.locked || !!form || expenseOpen || !!warehouseForm} onClick={() => { setForm({ item, values: Object.fromEntries(Object.keys(emptyExpense).map((key) => [key, item[key] ?? ''])) }); setMotive(''); }}>Corregir</button>{item.tipo === 'MATERIAL' && compareDecimal(item.cantidad_devuelta, item.cantidad) < 0 && <button className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.locked || !!form || expenseOpen || !!warehouseForm} onClick={() => setForm({ mode: 'devolver', item, values: { cantidad: '', fecha_devolucion: '', motivo: '' } })}>Devolver cantidad</button>}<button className="btn btn-outline-danger btn-sm" disabled={api.busy || api.locked || !!form || expenseOpen || !!warehouseForm} onClick={() => setForm({ mode: 'anular', item, values: { motivo: '' } })} >Anular</button></div>)}</td>}</tr>)}</tbody></table></div>}
        {(!canManage||expenses?.next||expenses?.previous)&&<Pager label="Paginación de gastos" data={expenses} page={page} setPage={setPage} disabled={api.loading || api.busy || api.locked || !!form || expenseOpen || !!warehouseForm} />}
      </section>}

      {expensesView && form?.mode && <TransactionForm mode={form.mode} item={form.item} api={api} onCancel={() => setForm(null)} onSave={(body, endpoint) => action(endpoint, body)} obraPath={base} />}

      {costsView && canSeeDetail && history && <section className={canManage?'card-fyag so-panel':'card-fyag p-3'}><h3>Historial de costos</h3>{history.results.length === 0 && (canManage?<SupervisorEmpty title="Sin movimientos de costos" description="Las declaraciones, validaciones y cambios de gastos aparecerán aquí."/>:<p>No hay eventos económicos.</p>)}{history.results.length>0&&(canManage?<SupervisorCostHistory events={history.results}/>:<ol>{history.results.map(event=><li key={event.id}><strong>{String(event.tipo).replaceAll('_',' ')}</strong> · {timestamp(event.creado_en)} · Usuario #{event.registrado_por}<p>{event.motivo || 'Sin motivo'}</p><SafeChanges data={event.datos_nuevos}/></li>)}</ol>)}{(!canManage||history.next||history.previous)&&<Pager label="Paginación del historial de costos" data={history} page={historyPage} setPage={setHistoryPage} disabled={api.loading || api.busy || api.locked} />}</section>}

  </section>;
}

function TransactionForm({ mode, item, api, onCancel, onSave, obraPath: base }) {
  const [values, setValues] = useState({ cantidad: '', fecha_devolucion: '', motivo: '' });
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (!values.motivo.trim()) { setError('El motivo es obligatorio.'); return; }
    const quantity=quantityInput(values.cantidad);
    if (mode === 'devolver' && (quantity===null || !validDate(values.fecha_devolucion))) { setError('Ingresa una cantidad mayor que cero y una fecha válida.'); return; }
    const endpoint = mode === 'devolver' ? `${base}gastos/${item.id}/devolver/` : `${base}gastos/${item.id}/anular/`;
    await onSave(mode === 'devolver' ? { ...values, cantidad: quantity, motivo: values.motivo.trim() } : { motivo: values.motivo.trim() }, endpoint);
  }
  return <form className="card-fyag commercial-form" onSubmit={submit}><h3>{mode === 'devolver' ? `Devolver cantidad del material #${item.id}` : `Anular gasto #${item.id}`}</h3>{mode === 'devolver' && <><Field name="devolucion-cantidad" label="Cantidad a devolver" inputMode="decimal" placeholder={quantityHint} value={values.cantidad} onChange={(v) => setValues({ ...values, cantidad: v })} /><Field name="devolucion-fecha" label="Fecha de devolución" type="date" value={values.fecha_devolucion} onChange={(v) => setValues({ ...values, fecha_devolucion: v })} /></>}<Field name="transaccion-motivo" label="Motivo" type="textarea" value={values.motivo} maxLength={2000} onChange={(v) => setValues({ ...values, motivo: v })} />{error && <p role="alert">{error}</p>}<div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy || api.locked} type="submit">Confirmar</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy||api.locked} onClick={onCancel}>Cancelar</button></div></form>;
}

const SAFE_CHANGE_KEYS = new Set(['tipo', 'descripcion', 'unidad', 'cantidad', 'cantidad_devuelta', 'costo_unitario_neto', 'fecha_gasto', 'vigente', 'subtotal', 'version_costos', 'materiales_estado', 'otros_estado', 'materiales_justificacion', 'otros_justificacion', 'cortesia', 'version_actual', 'version_validada']);
function SafeChanges({ data, before }) {
  if (!object(data)) return null;
  const entries = Object.entries(data).filter(([key, value]) => SAFE_CHANGE_KEYS.has(key) && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'));
  if (!entries.length) return null;
  return <dl className="obras-event-changes">{entries.map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{before&&Object.hasOwn(before,key)?<><span className="commercial-help">{String(before[key]??'—')}</span> → </>:null}{String(value)}</dd></div>)}</dl>;
}
