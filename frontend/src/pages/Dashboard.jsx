import { useApp } from '../context/AppContext';
import { OBRA_CHIP } from '../data/constants';
import { fm, pctTxt } from '../utils/format';
import { Chip, Feed, Icon, PageHead, Table, Track } from '../components/ui';
import React from 'react';

const MESES = [['Abr', 2], ['May', 3], ['Jun', 4], ['Jul', 3], ['Ago', 5], ['Sep', 6]];
const ORDEN = ['En proceso', 'Finalizada', 'Suspendida', 'Cancelada'];
const LABEL = { 'En proceso': 'En proceso', Finalizada: 'Finalizadas', Suspendida: 'Suspendidas', Cancelada: 'Canceladas' };
const COLOR = { 'En proceso': '#2f9e66', Finalizada: '#e8923a', Suspendida: '#d9534f', Cancelada: '#8a97a6' };
const PERFILES = [
  ['Administrador General / Gerencia', 'Visión global, indicadores y aprobación de presupuestos.'],
  ['Administrativo / Finanzas', 'Gestión de clientes, presupuestos, estados de pago y reportes.'],
  ['Supervisor de Obras', 'Creación de obras, asignación de técnicos y seguimiento de estados.'],
  ['Técnico', 'Acceso restringido únicamente a obras asignadas. Sin acceso financiero.'],
];

export default function Dashboard() {
  const { obrasC, pagos, alertasPend, logs, go, flash } = useApp();
  const totalPres = obrasC.reduce((a, o) => a + o.presupuesto, 0);
  const totalCosto = obrasC.reduce((a, o) => a + o.costo, 0);
  const margen = totalPres - totalCosto;
  const activas = obrasC.filter((o) => o.estado === 'En proceso').length;
  const kpis = [
    { label: 'Obras activas', value: String(activas), sub: `de ${obrasC.length} obras registradas`, color: '#2b5f94' },
    { label: 'Presupuestos aprobados', value: fm(totalPres), sub: `${obrasC.length} obras registradas`, color: '#2f9e66' },
    { label: 'Costo real acumulado', value: fm(totalCosto), sub: `${pctTxt(totalPres ? (totalCosto / totalPres) * 100 : 0)} del presupuesto`, color: '#e8923a' },
    { label: 'Margen proyectado', value: fm(margen), sub: `${pctTxt(totalPres ? (margen / totalPres) * 100 : 0)} sobre presupuesto`, color: '#2f9e66', good: true },
  ];
  let acc = 0; const segs = [], legend = [];
  ORDEN.forEach((k) => {
    const n = obrasC.filter((o) => o.estado === k).length;
    if (!n) return;
    const a = (acc / obrasC.length) * 360; acc += n;
    segs.push(`${COLOR[k]} ${a}deg ${(acc / obrasC.length) * 360}deg`);
    legend.push({ k, n });
  });
  const sum = (est) => pagos.filter((p) => p.estado === est).reduce((a, p) => a + p.monto, 0);
  const pFact = sum('Facturado'), pPag = sum('Pagado'), pTot = pFact + pPag;

  return (
    <section>
      <PageHead title="Dashboard de Obras y Presupuestos" sub="Frío y Agroindustria SpA · Proyecto Beta · Actualizado hoy">
        <button className="btn btn-outline-secondary" onClick={() => flash('Exportación generada.')}>Exportar</button>
        <button className="btn btn-fyag-primary" onClick={() => go('reportes')}>Ver reportes</button>
      </PageHead>
      <div className="kpis">
        {kpis.map((k) => (
          <div key={k.label} className="kpi" style={{ borderTop: `3px solid ${k.color}` }}>
            <div className="kpi-l">{k.label}</div>
            <div className="kpi-v">{k.value}</div>
            <div className={`kpi-s${k.good ? ' good' : ''}`}>{k.sub}</div>
          </div>
        ))}
      </div>
      <div className="row g-3 mb-3">
        <div className="col-lg-8">
          <div className="card-fyag h-100">
            <h2>Obras ejecutadas por mes</h2>
            <p className="note">Últimos 6 meses</p>
            <div className="bars">
              {MESES.map(([l, v]) => (
                <div key={l} className="bar-col">
                  <span className="bar-v">{v}</span>
                  <div className="bar" style={{ height: Math.round((v / 6) * 140) }} />
                  <span className="bar-l">{l}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="col-lg-4">
          <div className="card-fyag h-100">
            <h2>Estado operativo de obras</h2>
            <p className="note">Por estado</p>
            <div className="donut-wrap">
              <div className="donut" style={{ background: `conic-gradient(${segs.join(',')})` }}>
                <div className="donut-hole"><strong>{obrasC.length}</strong><span>obras</span></div>
              </div>
              <div>{legend.map((l) => (<div key={l.k} className="lg"><span className="sw-dot" style={{ background: COLOR[l.k] }} />{LABEL[l.k]} ({l.n})</div>))}</div>
            </div>
          </div>
        </div>
      </div>
      <div className="row g-3 mb-3">
        <div className="col-lg-4">
          <div className="card-fyag h-100">
            <div className="card-h"><h2>Estado de pagos</h2><button className="btn btn-sm btn-outline-secondary" onClick={() => go('cobranzas')}>Ver pagos</button></div>
            <div className="pg"><div className="pg-l"><span>Facturado</span><strong>{fm(pFact)}</strong></div><Track value={pTot ? (pFact / pTot) * 100 : 0} cls="amber" /></div>
            <div className="pg"><div className="pg-l"><span>Pagado</span><strong>{fm(pPag)}</strong></div><Track value={pTot ? (pPag / pTot) * 100 : 0} cls="green" /></div>
            <div className="pg-total"><span>Total movimientos</span><strong>{fm(pTot)}</strong></div>
          </div>
        </div>
        <div className="col-lg-4">
          <div className="card-fyag h-100">
            <div className="card-h"><h2>Alertas</h2><button className="btn btn-sm btn-outline-secondary" onClick={() => go('alertas')}>Ver alertas</button></div>
            {alertasPend.length === 0 && <p className="fyag-empty">Sin alertas pendientes.</p>}
            {alertasPend.map((a) => (
              <div key={a.id} className="alert-item">
                <Icon d="M12 3l10 18H2zM12 10v5M12 18h.01" />
                <div><strong>{a.id} · {a.cliente}</strong><p>{a.msg}</p></div>
              </div>
            ))}
          </div>
        </div>
        <div className="col-lg-4">
          <div className="card-fyag h-100">
            <h2>Trazabilidad</h2>
            {logs.slice(0, 6).map((g, i) => <Feed key={i} g={g} />)}
          </div>
        </div>
      </div>
      <div className="card-fyag flush">
        <div className="card-h"><h2>Obras en curso</h2><button className="btn btn-sm btn-outline-secondary" onClick={() => go('obras')}>Ver todas</button></div>
        <Table label="Obras" min="1000px" style={{ marginTop: 14 }} columns="80px 1.5fr 1.3fr 1fr 110px 1.2fr 110px 110px 110px" head={['ID', 'Cliente', 'Servicio', 'Técnico', 'Estado', 'Avance', 'Presupuesto', 'Costo real', 'Margen']}>
          {obrasC.filter((o) => o.estado === 'En proceso').map((o) => (
            <div key={o.id} className="trow" role="row">
              <div role="cell"><strong>{o.id}</strong></div>
              <div role="cell">{o.cliente}</div>
              <div role="cell">{o.servicio}</div>
              <div role="cell">{o.tecnico || 'Sin asignar'}</div>
              <div role="cell"><Chip cls={OBRA_CHIP[o.estado]}>{o.estado}</Chip></div>
              <div role="cell" className="mini"><Track small value={o.avance} /><span>{o.avance}%</span></div>
              <div role="cell">{fm(o.presupuesto)}</div>
              <div role="cell">{fm(o.costo)}</div>
              <div role="cell" className={o.margen >= 0 ? 'fyag-pos' : 'fyag-neg'}>{fm(o.margen)}</div>
            </div>
          ))}
        </Table>
      </div>
      <div className="card-fyag">
        <h2>Perfiles definidos en el sistema</h2>
        <div className="profiles">
          {PERFILES.map(([t, d]) => (<div key={t} className="profile"><strong>{t}</strong><span>{d}</span></div>))}
        </div>
      </div>
    </section>
  );
}