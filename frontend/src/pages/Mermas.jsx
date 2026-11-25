import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui/index.js';
import { useCommercial, Pager, Errors } from '../comercial/ui.jsx';
import { fm } from '../utils/format.js';

const ROOT = '/api/inventario/';
const uuid = () => crypto.randomUUID();
const MB = ['DANO', 'VENCIMIENTO', 'EXTRAVIO', 'DIFERENCIA_CONTEO', 'OTRA'];
const MO = ['CORTE_NO_REUTILIZABLE', 'DANO_EN_OBRA', 'EXTRAVIO_EN_OBRA', 'OTRA'];
// Solo presentación: los valores enviados al backend siguen siendo los códigos originales.
const TIPO_LABEL = {
  DANO: 'Daño', VENCIMIENTO: 'Vencimiento', EXTRAVIO: 'Extravío',
  DIFERENCIA_CONTEO: 'Diferencia de conteo', OTRA: 'Otra',
  CORTE_NO_REUTILIZABLE: 'Corte no reutilizable', DANO_EN_OBRA: 'Daño en obra',
  EXTRAVIO_EN_OBRA: 'Extravío en obra',
};
const tipoTxt = (type) => TIPO_LABEL[type] || type;
const ESTADO_CHIP = { PENDIENTE: 'amber', APROBADA: 'green', RECHAZADA: 'red' };
const EstadoChip = ({ estado }) => <span className={`chip ${ESTADO_CHIP[estado] || 'gray'}`}>{estado}</span>;
const money = (value) => value == null || value === '' || Number.isNaN(Number(value)) ? '—' : fm(Number(value));
const FILTER_LABEL = { articulo: 'Artículo', obra: 'Obra', entrega: 'Entrega', estado: 'Estado', tipo: 'Tipo' };
const FACT_LABEL = {
  ambito: 'Ámbito', obra: 'Obra', entrega: 'Entrega', articulo: 'Artículo', unidad: 'Unidad',
  cantidad: 'Cantidad', tipo: 'Tipo', motivo: 'Motivo', actividad: 'Actividad / detalle',
  referencia: 'Referencia', informado_por: 'Informado por', motivo_decision: 'Motivo de la decisión',
  costo_unitario_neto: 'Costo unitario neto', importe_perdida: 'Importe de la pérdida',
  importe_informativo_no_aditivo: 'Importe informativo (no aditivo)',
};
const MONEY_KEYS = ['costo_unitario_neto', 'importe_perdida', 'importe_informativo_no_aditivo'];
const LONG_KEYS = ['motivo', 'actividad', 'motivo_decision'];
const valid = (value) => {
  if (!value || !Number.isSafeInteger(value.count) || !Array.isArray(value.results) || value.results.length > 25) {
    throw new Error('Respuesta de mermas inesperada.');
  }
  return value;
};

export default function Mermas() {
  const { user } = useAuth();
  const api = useCommercial();
  const [scope, setScope] = useState(['TECNICO', 'SUPERVISOR_OBRAS', 'GERENCIA'].includes(user.role) ? 'OBRA' : 'BODEGA');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [selected, setSelected] = useState(null);
  const [decision, setDecision] = useState(null);
  const [msg, setMsg] = useState('');
  const [filters, setFilters] = useState({ articulo: '', obra: '', entrega: '', estado: '', tipo: '' });
  const role = user.role;
  const canCreate = scope === 'BODEGA' ? role === 'BODEGUERO' : role === 'TECNICO';
  const canDecide = scope === 'BODEGA' ? role === 'ADMINISTRATIVO_FINANZAS' : role === 'SUPERVISOR_OBRAS';
  const base=`${ROOT}mermas-${scope.toLowerCase()}/`;
  const url = () => {
    const query=new URLSearchParams({page:String(page)});
    for (const [key, value] of Object.entries(filters)) {
      if (value && !(role === 'TECNICO' && key === 'obra')) query.set(key, value);
    }
    return `${base}?${query}`;
  };
  async function load() {
    await api.load('mermas', url(), (value) => setData(valid(value)));
  }
  const setFilter = (key, value) => {
    setPage(1);
    setFilters((previous) => ({ ...previous, [key]: value }));
  };
  useEffect(() => {
    setData(null);
    void load();
  }, [base, page, filters]);

  async function inspect(row) {
    await api.load('merma-detail', `${base}${row.id}/`, setSelected);
  }
  async function create(event) {
    event.preventDefault();
    const body = scope === 'BODEGA'
      ? { articulo: Number(form.articulo), cantidad: form.cantidad, tipo: form.tipo, motivo: form.motivo.trim(), referencia_respaldo: form.referencia.trim(), clave_idempotencia: form.clave_idempotencia }
      : { entrega: Number(form.entrega), cantidad: form.cantidad, tipo: form.tipo, motivo: form.motivo.trim(), actividad: form.actividad.trim(), referencia: form.referencia.trim(), clave_idempotencia: form.clave_idempotencia };
    await api.write(base, 'POST', body, async () => {
      setForm(null);
      setMsg('Reporte de merma registrado.');
      await load();
    });
  }
  async function decide(event) {
    event.preventDefault();
    await api.write(`${base}${selected.id}/decidir/`, 'POST', {
      decision: decision.decision,
      motivo: decision.motivo.trim(),
      clave_idempotencia: decision.clave_idempotencia,
    }, async (value) => {
      setSelected(value);
      setDecision(null);
      await load();
    });
  }

  const types = scope === 'BODEGA' ? MB : MO;
  const scopes = role === 'BODEGUERO' || role === 'ADMINISTRATIVO_FINANZAS'
    ? ['BODEGA']
    : role === 'TECNICO' || role === 'SUPERVISOR_OBRAS' ? ['OBRA'] : ['OBRA', 'BODEGA'];
  const showMoney=role!=='TECNICO';
  const factKeys = ['ambito', 'obra', 'entrega', 'articulo', 'unidad', 'cantidad', 'tipo', 'motivo', 'actividad', 'referencia', 'informado_por', 'motivo_decision', ...(showMoney ? MONEY_KEYS : [])]
    .filter((key) => Object.hasOwn(selected || {}, key));
  const factValue = (key) => MONEY_KEYS.includes(key) ? money(selected[key]) : key === 'tipo' ? tipoTxt(selected[key]) : String(selected[key] ?? '—');

  return <section className="commercial-page">
    <PageHead title="Mermas" sub="Registro auditable y decisiones conforme al rol." />
    <Errors error={api.error} />
    {msg && <p className="alert alert-info" role="status">{msg}</p>}
    <div className="commercial-toolbar mermas-toolbar">
      <div className="commercial-filter mermas-scope"><label className="form-label" htmlFor="mermas-scope">Ámbito</label><select id="mermas-scope" className="form-select" value={scope} onChange={(event) => { setScope(event.target.value); setPage(1); setSelected(null); }}>
        {scopes.map((value) => <option key={value}>{value}</option>)}
      </select></div>
      {canCreate && <button className="btn btn-fyag-primary" disabled={api.busy} onClick={() => setForm({ tipo: types[0], articulo: '', entrega: '', cantidad: '', motivo: '', referencia: '', actividad: '', clave_idempotencia: uuid() })}>Informar merma</button>}
    </div>

    {form && <form className="card-fyag commercial-form mermas-form" onSubmit={create}>
      <h2>Informar merma de {scope === 'OBRA' ? 'obra' : 'bodega'}</h2>
      <p className="mermas-note">El reporte queda en estado PENDIENTE hasta que se decida conforme al rol.</p>
      <div className="d-grid commercial-fields">
        <div><label className="form-label" htmlFor="merma-ref-id">{scope === 'BODEGA' ? 'ID artículo' : 'ID entrega 019B'}</label><input id="merma-ref-id" className="form-control" required inputMode="numeric" value={scope === 'BODEGA' ? form.articulo : form.entrega} onChange={(event) => setForm({ ...form, [scope === 'BODEGA' ? 'articulo' : 'entrega']: event.target.value })} /></div>
        <div><label className="form-label" htmlFor="merma-cantidad">Cantidad</label><input id="merma-cantidad" className="form-control" required inputMode="decimal" value={form.cantidad} onChange={(event) => setForm({ ...form, cantidad: event.target.value })} /></div>
        <div><label className="form-label" htmlFor="merma-tipo">Tipo</label><select id="merma-tipo" className="form-select" value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value })}>{types.map((type) => <option key={type} value={type}>{tipoTxt(type)}</option>)}</select></div>
        <div><label className="form-label" htmlFor="merma-referencia">Referencia{scope === 'BODEGA' ? ' (obligatoria)' : ' (opcional)'}</label><input id="merma-referencia" className="form-control" required={scope === 'BODEGA'} maxLength="150" value={form.referencia} onChange={(event) => setForm({ ...form, referencia: event.target.value })} /></div>
      </div>
      <div className="mb-3"><label className="form-label" htmlFor="merma-motivo">Motivo</label><textarea id="merma-motivo" className="form-control" required maxLength="2000" rows="3" value={form.motivo} onChange={(event) => setForm({ ...form, motivo: event.target.value })} /></div>
      {scope === 'OBRA' && <div className="mb-3"><label className="form-label" htmlFor="merma-actividad">Actividad / detalle</label><textarea id="merma-actividad" className="form-control" required maxLength="2000" rows="3" value={form.actividad} onChange={(event) => setForm({ ...form, actividad: event.target.value })} /></div>}
      <div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy}>Registrar</button><button type="button" className="btn btn-outline-secondary" onClick={() => setForm(null)}>Cancelar</button></div>
    </form>}

    {selected && <article className="card-fyag commercial-detail mermas-detail">
      <div className="mermas-detail-head"><h2>Merma #{selected.id} <EstadoChip estado={selected.estado} /></h2><div className="commercial-actions">
        {canDecide && selected.estado === 'PENDIENTE' && <button className="btn btn-fyag-primary btn-sm" onClick={() => setDecision({ decision: 'APROBAR', motivo: '', clave_idempotencia: uuid() })}>Decidir</button>}
        <button className="btn btn-outline-secondary btn-sm" onClick={() => setSelected(null)}>Cerrar</button>
      </div></div>
      <dl className="commercial-facts">{factKeys.map((key) => <div key={key} className={LONG_KEYS.includes(key) ? 'mermas-fact-wide' : undefined}><dt>{FACT_LABEL[key] || key.replaceAll('_', ' ')}</dt><dd className={LONG_KEYS.includes(key) ? 'commercial-long-text' : undefined}>{factValue(key)}</dd></div>)}</dl>
      {selected.historial?.length > 0 && <div className="commercial-history"><h3>Historial</h3><ol className="commercial-timeline">{selected.historial.map((event) => <li key={event.id}><div className="commercial-history-states"><span className="chip blue">{event.tipo}</span></div><div className="commercial-help">{new Date(event.creado_en).toLocaleString('es-CL')} · {event.motivo}</div></li>)}</ol></div>}
    </article>}

    {decision && <form className="card-fyag commercial-form mermas-form" onSubmit={decide}>
      <h2>Decisión irreversible</h2>
      <div className="mb-3"><label className="form-label" htmlFor="merma-decision">Decisión</label><select id="merma-decision" className="form-select" value={decision.decision} onChange={(event) => setDecision({ ...decision, decision: event.target.value, clave_idempotencia: uuid() })}><option>APROBAR</option><option>RECHAZAR</option></select></div>
      <div className="mb-3"><label className="form-label" htmlFor="merma-decision-motivo">Motivo</label><textarea id="merma-decision-motivo" className="form-control" required maxLength="2000" rows="3" value={decision.motivo} onChange={(event) => setDecision({ ...decision, motivo: event.target.value })} /></div>
      <div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy}>Confirmar</button><button type="button" className="btn btn-outline-secondary" onClick={() => setDecision(null)}>Cancelar</button></div>
    </form>}

    <div className="card-fyag"><div className="mermas-filters">{['articulo', 'estado', 'tipo', ...(scope === 'OBRA' ? ['obra', 'entrega'] : [])].map((key) => <div key={key}>
      <label className="form-label" htmlFor={`merma-filtro-${key}`}>{FILTER_LABEL[key]}</label>
      {key === 'estado' ? <select id={`merma-filtro-${key}`} className="form-select" value={filters[key]} onChange={(event) => setFilter(key, event.target.value)}><option value="">Todos</option>{['PENDIENTE', 'APROBADA', 'RECHAZADA'].map((value) => <option key={value}>{value}</option>)}</select>
        : key === 'tipo' ? <select id={`merma-filtro-${key}`} className="form-select" value={filters[key]} onChange={(event) => setFilter(key, event.target.value)}><option value="">Todos</option>{types.map((type) => <option key={type} value={type}>{tipoTxt(type)}</option>)}</select>
          : <input id={`merma-filtro-${key}`} className="form-control" inputMode="numeric" placeholder={`ID de ${FILTER_LABEL[key].toLowerCase()}`} value={filters[key]} onChange={(event) => setFilter(key, event.target.value)} />}
    </div>)}</div></div>

    {data && <div className="card-fyag commercial-table-card">
      <div className="table-responsive" role="region" aria-label="Registro de mermas" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th>ID</th><th>Ámbito</th><th>Artículo / entrega</th><th className="text-end">Cantidad</th><th>Tipo</th><th>Estado</th>{showMoney && <th className="text-end">Importe informativo</th>}<th>Detalle</th></tr></thead><tbody>{data.results.map((row) => <tr key={row.id}>
        <td className="commercial-code">#{row.id}</td><td>{row.ambito}</td><td>{row.articulo} / {row.entrega ?? '—'}</td><td className="commercial-money">{row.cantidad} {row.unidad}</td><td>{tipoTxt(row.tipo)}</td><td><EstadoChip estado={row.estado} /></td>{showMoney && <td className="commercial-money">{money(row.importe_perdida ?? row.importe_informativo_no_aditivo)}</td>}<td><button className="btn btn-outline-secondary btn-sm" onClick={() => void inspect(row)}>Ver</button></td>
      </tr>)}</tbody></table></div>
      <Pager data={data} page={page} setPage={setPage} disabled={api.loading || api.busy} />
    </div>}
  </section>;
}
