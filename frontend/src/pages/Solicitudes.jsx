import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui/index.js';
import { useCommercial, Pager, Errors } from '../comercial/ui.jsx';

const BASE = '/api/inventario/';
const uuid = () => crypto.randomUUID();
// Solo presentación: etiquetas y colores; no cambian lo que se envía ni recibe de la API.
const ESTADO_CHIP = { PENDIENTE: 'amber', APROBADA: 'green', RECHAZADA: 'red' };
const EstadoChip = ({ estado }) => <span className={`chip ${ESTADO_CHIP[estado] || 'gray'}`}>{estado}</span>;
const FACTS = ['obra', 'solicitante', 'articulo', 'unidad', 'cantidad_solicitada', 'cantidad_aprobada', 'autorizacion', 'justificacion', 'motivo_decision'];
const FACT_LABEL = {
  obra: 'Obra', solicitante: 'Solicitante', articulo: 'Artículo', unidad: 'Unidad',
  cantidad_solicitada: 'Cantidad solicitada', cantidad_aprobada: 'Cantidad aprobada',
  autorizacion: 'Autorización', justificacion: 'Justificación', motivo_decision: 'Motivo de la decisión',
};
const LONG_FACTS = ['justificacion', 'motivo_decision'];

function validPage(value) {
  if (!value || !Number.isSafeInteger(value.count) || !Array.isArray(value.results) || value.results.length > 25) {
    throw new Error('Respuesta de solicitudes inesperada.');
  }
  return value;
}

export default function Solicitudes() {
  const { user, request } = useAuth();
  const api = useCommercial();
  const [rows, setRows] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [works, setWorks] = useState([]);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const [decision, setDecision] = useState(null);
  const [msg, setMsg] = useState('');
  const tech = user.role === 'TECNICO';
  const supervisor = user.role === 'SUPERVISOR_OBRAS';

  async function load() {
    await api.load('sol-list', `${BASE}solicitudes-materiales/?page=${page}`, (value) => setRows(validPage(value)));
  }
  useEffect(() => { void load(); }, [page]);
  useEffect(() => {
    if (!tech) return;
    void Promise.all([
      request(`${BASE}articulos-solicitables/?page=1`).then((value) => setCatalog(value.results || [])).catch(() => {}),
      request('/api/obras/?page=1').then((value) => setWorks(value.results || [])).catch(() => {}),
    ]);
  }, [tech, request]);

  async function open(row) {
    setSelected(null);
    await api.load('sol-detail', `${BASE}solicitudes-materiales/${row.id}/`, setSelected);
  }
  async function submit(event) {
    event.preventDefault();
    const body = {
      obra: Number(form.obra), articulo: Number(form.articulo), cantidad: form.cantidad,
      justificacion: form.justificacion.trim(), clave_idempotencia: form.clave_idempotencia,
    };
    await api.write(`${BASE}solicitudes-materiales/`, 'POST', body, async () => {
      setForm(null);
      setMsg('Solicitud enviada.');
      await api.requiredLoad('sol-list', `${BASE}solicitudes-materiales/?page=${page}`, (value) => setRows(validPage(value)));
    });
  }
  async function decide(event) {
    event.preventDefault();
    const body = {
      decision: decision.decision,
      motivo: decision.motivo.trim(),
      clave_idempotencia: decision.clave_idempotencia,
      ...(decision.decision === 'APROBAR' ? { cantidad_aprobada: decision.cantidad_aprobada } : {}),
    };
    await api.write(`${BASE}solicitudes-materiales/${selected.id}/decidir/`, 'POST', body, async (saved) => {
      setDecision(null);
      setSelected(saved);
      setMsg('Decisión confirmada.');
      await load();
    });
  }

  return <section className="commercial-page">
    <PageHead title="Solicitudes de materiales" sub="Solicitudes de técnicos y decisiones de supervisión." />
    <Errors error={api.error} />
    {msg && <p role="status" className="alert alert-info">{msg}</p>}
    {tech && <div className="commercial-toolbar solicitudes-toolbar"><p>Pide materiales para tus obras en proceso. Un supervisor aprueba o rechaza cada solicitud.</p><button className="btn btn-fyag-primary" disabled={api.busy || api.loading} onClick={() => setForm({ obra: '', articulo: '', cantidad: '', justificacion: '', clave_idempotencia: uuid() })}>Nueva solicitud</button></div>}

    {form && <form className="card-fyag commercial-form solicitudes-form" onSubmit={submit}>
      <h2>Solicitar material</h2>
      <p className="solicitudes-note">Solo puedes solicitar para obras EN PROCESO o SUSPENDIDAS. La solicitud queda PENDIENTE hasta que el supervisor decida.</p>
      <div className="d-grid commercial-fields">
        <div><label className="form-label" htmlFor="sol-obra">Obra</label><select id="sol-obra" className="form-select" required value={form.obra} onChange={(event) => setForm({ ...form, obra: event.target.value })}><option value="">Selecciona</option>{works.filter((work) => ['EN_PROCESO', 'SUSPENDIDA'].includes(work.estado)).map((work) => <option key={work.id} value={work.id}>{work.codigo} · #{work.id}</option>)}</select></div>
        <div><label className="form-label" htmlFor="sol-articulo">Artículo</label><select id="sol-articulo" className="form-select" required value={form.articulo} onChange={(event) => setForm({ ...form, articulo: event.target.value })}><option value="">Selecciona</option>{catalog.map((item) => <option key={item.id} value={item.id}>{item.codigo} · {item.nombre} ({item.unidad})</option>)}</select></div>
        <div><label className="form-label" htmlFor="sol-cantidad">Cantidad</label><input id="sol-cantidad" className="form-control" required inputMode="decimal" value={form.cantidad} onChange={(event) => setForm({ ...form, cantidad: event.target.value })} /></div>
      </div>
      <div className="mb-3"><label className="form-label" htmlFor="sol-justificacion">Justificación</label><textarea id="sol-justificacion" className="form-control" required maxLength="2000" rows="3" value={form.justificacion} onChange={(event) => setForm({ ...form, justificacion: event.target.value })} /></div>
      <div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy}>Enviar</button><button type="button" className="btn btn-outline-secondary" onClick={() => setForm(null)}>Cancelar</button></div>
    </form>}

    {selected && <article className="card-fyag commercial-detail solicitudes-detail">
      <div className="solicitudes-detail-head"><h2>Solicitud #{selected.id} <EstadoChip estado={selected.estado} /></h2><div className="commercial-actions">{supervisor && selected.estado === 'PENDIENTE' && <button className="btn btn-fyag-primary btn-sm" onClick={() => setDecision({ decision: 'APROBAR', cantidad_aprobada: selected.cantidad_solicitada, motivo: '', clave_idempotencia: uuid() })}>Decidir</button>}<button className="btn btn-outline-secondary btn-sm" onClick={() => setSelected(null)}>Volver</button></div></div>
      <dl className="commercial-facts">{FACTS.map((key) => <div key={key} className={LONG_FACTS.includes(key) ? 'solicitudes-fact-wide' : undefined}><dt>{FACT_LABEL[key]}</dt><dd className={LONG_FACTS.includes(key) ? 'commercial-long-text' : undefined}>{String(selected[key] ?? '—')}</dd></div>)}</dl>
      {selected.historial?.length > 0 && <div className="commercial-history"><h3>Historial</h3><ol className="commercial-timeline">{selected.historial.map((history) => <li key={history.id}><div className="commercial-history-states"><span className="chip blue">{history.tipo}</span></div><div className="commercial-help">{new Date(history.creado_en).toLocaleString('es-CL')} · {history.motivo}</div></li>)}</ol></div>}
    </article>}

    {decision && <form className="card-fyag commercial-form solicitudes-form" onSubmit={decide}>
      <h2>Decidir solicitud #{selected.id}</h2>
      <div className="d-grid commercial-fields">
        <div><label className="form-label" htmlFor="sol-decision">Decisión</label><select id="sol-decision" className="form-select" value={decision.decision} onChange={(event) => setDecision({ ...decision, decision: event.target.value, clave_idempotencia: uuid() })}><option value="APROBAR">Aprobar</option><option value="RECHAZAR">Rechazar</option></select></div>
        {decision.decision === 'APROBAR' && <div><label className="form-label" htmlFor="sol-cant-aprobada">Cantidad aprobada</label><input id="sol-cant-aprobada" className="form-control" required inputMode="decimal" value={decision.cantidad_aprobada} onChange={(event) => setDecision({ ...decision, cantidad_aprobada: event.target.value })} /></div>}
      </div>
      <div className="mb-3"><label className="form-label" htmlFor="sol-decision-motivo">Motivo</label><textarea id="sol-decision-motivo" className="form-control" required maxLength="2000" rows="3" value={decision.motivo} onChange={(event) => setDecision({ ...decision, motivo: event.target.value })} /></div>
      <div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy}>Confirmar decisión</button><button type="button" className="btn btn-outline-secondary" onClick={() => setDecision(null)}>Cancelar</button></div>
    </form>}

    {rows && <div className="card-fyag commercial-table-card">
      <div className="table-responsive" role="region" aria-label="Solicitudes de materiales" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th>ID</th><th>Obra</th><th>Artículo</th><th className="text-end">Cantidad</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>{rows.results.map((row) => <tr key={row.id}><td className="commercial-code">#{row.id}</td><td>#{row.obra}</td><td>#{row.articulo}</td><td className="commercial-money">{row.cantidad_solicitada} {row.unidad}</td><td><EstadoChip estado={row.estado} /></td><td><button className="btn btn-outline-secondary btn-sm" onClick={() => void open(row)}>Ver</button></td></tr>)}</tbody></table></div>
      <Pager data={rows} page={page} setPage={setPage} disabled={api.loading || api.busy} />
    </div>}
  </section>;
}
