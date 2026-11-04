import { useApp } from '../context/AppContext';
import { PAGO_CHIP } from '../data/constants';
import { fm } from '../utils/format';
import { Chip, Icon, PageHead, Pills, Table } from '../components/ui';

export default function Cobranzas() {
  const { role, pagos, obras, showPagoForm, fPagoObra, fPagoMonto, setField, savePago, pagoChange } = useApp();
  const sum = (est) => pagos.filter((p) => p.estado === est).reduce((a, p) => a + p.monto, 0);
  const pFact = sum('Facturado'), pPag = sum('Pagado');
  const kpis = [
    { label: 'Facturado', value: fm(pFact), color: '#e8923a' },
    { label: 'Pagado', value: fm(pPag), color: '#2f9e66' },
    { label: 'Total', value: fm(pFact + pPag), color: '#2b5f94' }
  ];
  const canPago = role === 'finanzas';

  return (
    <section>
      <PageHead title="Cobranzas" sub={canPago ? 'Registro y seguimiento.' : 'Consulta (solo lectura).'}>
        {canPago && <button className="btn btn-fyag-primary" onClick={() => setField('showPagoForm', !showPagoForm)}><Icon d="M12 5v14M5 12h14" />Nuevo pago</button>}
      </PageHead>

      <div className="kpis">
        {kpis.map((k) => <div key={k.label} className="kpi" style={{ borderTop: `3px solid ${k.color}` }}><div className="kpi-l">{k.label}</div><div className="kpi-v">{k.value}</div></div>)}
      </div>

      {showPagoForm && (
        <div className="card-fyag">
          <h2>Nuevo pago</h2>
          <fieldset className="fs">
            <legend>Obra</legend>
            <Pills items={obras.filter((o) => o.estado !== 'Cancelada').map((o) => ({ key: o.id, label: `${o.id} · ${o.cliente}`, on: fPagoObra === o.id, pick: () => setField('fPagoObra', o.id) }))} />
          </fieldset>
          <div className="fgrid"><div><label htmlFor="f-pg">Monto ($)</label><input id="f-pg" className="form-control" type="number" value={fPagoMonto} onChange={(e) => setField('fPagoMonto', e.target.value)} /></div></div>
          <div className="actions mt-3"><button className="btn btn-fyag-primary" onClick={savePago}>Guardar</button><button className="btn btn-outline-secondary" onClick={() => setField('showPagoForm', false)}>Cancelar</button></div>
        </div>
      )}

      <div className="card-fyag flush">
        <Table label="Pagos" min="900px" columns="90px 80px 1.4fr 120px 120px 80px 1.3fr" head={['N°', 'Obra', 'Cliente', 'Monto', 'Estado', 'Fecha', 'Acciones']}>
          {pagos.slice().reverse().map((p) => {
            const ob = obras.find((o) => o.id === p.obra);
            const canAct = canPago && p.estado === 'Facturado';
            return (
              <div key={p.id} className="trow" role="row">
                <div role="cell"><strong>{p.id}</strong></div>
                <div role="cell">{p.obra}</div>
                <div role="cell">{ob ? ob.cliente : '—'}</div>
                <div role="cell" className="fyag-money">{fm(p.monto)}</div>
                <div role="cell"><Chip cls={PAGO_CHIP[p.estado]}>{p.estado}</Chip></div>
                <div role="cell" className="fyag-muted">{p.fecha}</div>
                <div role="cell" className="acts">
                  {canAct ? (
                    <><button className="btn btn-sm btn-fyag-primary" onClick={() => pagoChange(p, 'Pagado', `Pago ${p.id} pagado`)}>Pagado</button><button className="btn btn-sm btn-fyag-danger" onClick={() => pagoChange(p, 'Anulado', `Pago ${p.id} anulado`)}>Anular</button></>
                  ) : <span className="fyag-muted">—</span>}
                </div>
              </div>
            );
          })}
        </Table>
      </div>
    </section>
  );
}