import { useApp } from '../context/AppContext';
import { PRE_E } from '../data/constants';
import { fm } from '../utils/format';
import { Callout, Chip, Feed, Icon, PageHead, Pills, Table } from '../components/ui';

const FILTROS = [
  ['all', 'Todos', () => true],
  ['pend', 'Por aprobar (Gerencia)', (p) => p.estado === 'PENDIENTE_GERENCIA'],
  ['cli', 'Con el cliente', (p) => p.estado === 'ENVIADO_CLIENTE'],
  ['ok', 'Aceptados', (p) => p.estado === 'APROBADO_CLIENTE']
];

export default function Presupuestos() {
  const { role, pres, presPend, filtroPre, showPreForm, clientes, fPreCliente, fPreDesc, fPreMonto, logs, UMBRAL, setField, presAction, savePre } = useApp();

  const actionsFor = (p) => {
    const out = [];
    const mk = (label, kind, estado, title) => out.push({ label, kind, run: () => presAction(p, estado, title) });
    if (role === 'finanzas') {
      if (p.estado === 'BORRADOR') {
        if (p.monto >= UMBRAL) mk('Enviar a Gerencia', 'primary', 'PENDIENTE_GERENCIA', `Presupuesto ${p.id} enviado a Gerencia`);
        else mk('Enviar al cliente', 'primary', 'ENVIADO_CLIENTE', `Presupuesto ${p.id} enviado al cliente`);
        mk('Anular', 'danger', 'ANULADO', `Presupuesto ${p.id} anulado`);
      }
      if (p.estado === 'APROBADO_GERENCIA') mk('Enviar al cliente', 'primary', 'ENVIADO_CLIENTE', `Presupuesto ${p.id} enviado al cliente`);
      if (p.estado === 'ENVIADO_CLIENTE') {
        mk('Cliente acepta', 'primary', 'APROBADO_CLIENTE', `Presupuesto ${p.id} aceptado por el cliente`);
        mk('Cliente rechaza', 'danger', 'RECHAZADO_CLIENTE', `Presupuesto ${p.id} rechazado por el cliente`);
      }
    }
    if (role === 'gerencia' && p.estado === 'PENDIENTE_GERENCIA') {
      mk('Aprobar', 'primary', 'APROBADO_GERENCIA', `Presupuesto ${p.id} aprobado por Gerencia`);
      mk('Rechazar', 'danger', 'RECHAZADO_GERENCIA', `Presupuesto ${p.id} rechazado por Gerencia`);
    }
    return out;
  };

  const f = FILTROS.find((x) => x[0] === filtroPre);
  const monto = Number(fPreMonto) || 0;

  return (
    <section>
      <PageHead title="Presupuestos" sub={role === 'gerencia' ? 'Revisión y aprobación de presupuestos.' : 'Creación y seguimiento de presupuestos.'}>
        {role === 'finanzas' && (
          <button className="btn btn-fyag-primary" onClick={() => setField('showPreForm', !showPreForm)}>
            <Icon d="M12 5v14M5 12h14" />Nuevo presupuesto
          </button>
        )}
      </PageHead>

      {role === 'gerencia' && presPend.length > 0 && (
        <Callout warn>Tienes {presPend.length} {presPend.length === 1 ? 'presupuesto esperando' : 'presupuestos esperando'} tu decisión.</Callout>
      )}
      <Callout>Los presupuestos desde {fm(UMBRAL)} requieren aprobación de Gerencia.</Callout>

      {showPreForm && (
        <div className="card-fyag">
          <h2>Nuevo presupuesto</h2>
          <fieldset className="fs">
            <legend>Cliente</legend>
            <Pills items={clientes.map((c) => ({ key: c.nombre, label: c.nombre, on: fPreCliente === c.nombre, pick: () => setField('fPreCliente', c.nombre) }))} />
          </fieldset>
          <div className="fgrid">
            <div><label htmlFor="f-pd">Descripción</label><input id="f-pd" className="form-control" type="text" value={fPreDesc} onChange={(e) => setField('fPreDesc', e.target.value)} /></div>
            <div><label htmlFor="f-pm">Monto neto ($)</label><input id="f-pm" className="form-control" type="number" value={fPreMonto} onChange={(e) => setField('fPreMonto', e.target.value)} /></div>
          </div>
          <div className="actions mt-3">
            <button className="btn btn-fyag-primary" onClick={savePre}>Guardar borrador</button>
            <button className="btn btn-outline-secondary" onClick={() => setField('showPreForm', false)}>Cancelar</button>
          </div>
        </div>
      )}

      <div className="mb-3">
        <Pills items={FILTROS.map(([k, label, fn]) => ({ key: k, label: `${label} (${pres.filter(fn).length})`, on: filtroPre === k, pick: () => setField('filtroPre', k) }))} />
      </div>

      <div className="card-fyag flush">
        <Table label="Presupuestos" min="1020px" columns="80px 1.2fr 1.8fr 110px 190px 80px 1.5fr" head={['N°', 'Cliente', 'Descripción', 'Monto', 'Estado', 'Obra', 'Acciones']}>
          {pres.filter(f[2]).map((p) => {
            const acts = actionsFor(p);
            return (
              <div key={p.id} className="trow" role="row">
                <div role="cell"><strong>{p.id}</strong></div>
                <div role="cell">{p.cliente}</div>
                <div role="cell">{p.desc}</div>
                <div role="cell" className="fyag-money">{fm(p.monto)}</div>
                <div role="cell"><Chip cls={PRE_E[p.estado][1]}>{PRE_E[p.estado][0]}</Chip></div>
                <div role="cell">{p.obra || '—'}</div>
                <div role="cell" className="acts">
                  {acts.map((x) => <button key={x.label} className={`btn btn-sm ${x.kind === 'primary' ? 'btn-fyag-primary' : 'btn-fyag-danger'}`} onClick={x.run}>{x.label}</button>)}
                  {acts.length === 0 && <span className="fyag-muted">—</span>}
                </div>
              </div>
            );
          })}
        </Table>
      </div>

      <div className="card-fyag">
        <h2>Historial de decisiones</h2>
        {logs.filter((g) => g.kind === 'pre').slice(0, 6).map((g, i) => <Feed key={i} g={g} />)}
      </div>
    </section>
  );
}