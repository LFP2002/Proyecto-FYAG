import { useApp } from '../context/AppContext';
import { OBRA_CHIP } from '../data/constants';
import { devTxt, fm, pctTxt } from '../utils/format';
import { Chip, PageHead, Table, Track } from '../components/ui';

const TECNICOS = ['Pedro Díaz', 'Luis Torres'];

export default function Obras() {
  const a = useApp();
  const { role, obrasC, pres, sinObra, sel, crearPre, costos, estadoDraft, fObraTec, fObraCat, fCostoTipo, fCostoDesc, fCostoMonto, setField, set, openObra, crearObra, applyEstado, assignTec, addCosto } = a;
  const showMoney = role === 'gerencia';
  const showDev = role === 'supervisor';
  const canEdit = role === 'supervisor';
  const so = obrasC.find((o) => o.id === sel);
  const crearP = pres.find((p) => p.id === crearPre);
  const devChip = (o) => (o.dev > 10 ? 'red' : o.dev > 5 ? 'amber' : 'green');
  const cols = showMoney ? '80px 1.4fr 1.2fr 1fr 110px 1.2fr 110px 110px 110px' : '80px 1.4fr 1.2fr 1fr 110px 1.2fr 140px';
  const head = ['ID', 'Cliente', 'Servicio', 'Técnico', 'Estado', 'Avance', ...(showMoney ? ['Presupuesto', 'Costo real', 'Margen'] : ['Costo vs avance'])];
  const costoRows = so ? (costos[so.id] || []).slice().reverse() : [];

  return (
    <section>
      <PageHead title="Obras" sub={role === 'gerencia' ? 'Estado, avance y rentabilidad.' : 'Creación, técnicos, costos y estados.'} />
      {role === 'supervisor' && (
        <div className="card-fyag">
          <div className="card-h"><div><h2>Presupuestos aceptados sin obra</h2></div></div>
          {sinObra.length === 0 && <p className="fyag-empty">No hay pendientes.</p>}
          {sinObra.map((p) => (
            <div key={p.id} className="li">
              <div><strong>{p.id} · {p.cliente}</strong><div className="feed-d">{p.desc}</div></div>
              <button className="btn btn-sm btn-fyag-primary" onClick={() => set({ crearPre: p.id, fObraTec: '', fObraCat: 'Refrigeración Industrial' })}>Crear obra</button>
            </div>
          ))}
          {crearP && (
            <div className="subform">
              <h2>Nueva obra desde {crearP.id}</h2>
              <div className="fgrid">
                <div><label htmlFor="f-ot">Técnico</label><select id="f-ot" className="form-select" value={fObraTec} onChange={(e) => setField('fObraTec', e.target.value)}><option value="">Sin asignar</option>{TECNICOS.map((t) => <option key={t}>{t}</option>)}</select></div>
                <div><label htmlFor="f-oc">Categoría</label><select id="f-oc" className="form-select" value={fObraCat} onChange={(e) => setField('fObraCat', e.target.value)}><option>Refrigeración Industrial</option><option>Climatización</option><option>Mantención</option></select></div>
              </div>
              <div className="actions mt-3"><button className="btn btn-fyag-primary" onClick={crearObra}>Crear obra</button><button className="btn btn-outline-secondary" onClick={() => setField('crearPre', null)}>Cancelar</button></div>
            </div>
          )}
        </div>
      )}
      <div className="card-fyag flush">
        <Table label="Obras" min={showMoney ? '1000px' : '820px'} columns={cols} head={head} style={{ marginTop: 14 }}>
          {obrasC.map((o) => (
            <div key={o.id} className={`trow${sel === o.id ? ' sel' : ''}`} role="row">
              <div role="cell"><button className="linkbtn" onClick={() => openObra(o.id)}>{o.id}</button></div>
              <div role="cell">{o.cliente}</div>
              <div role="cell">{o.servicio}</div>
              <div role="cell">{o.tecnico || 'Sin asignar'}</div>
              <div role="cell"><Chip cls={OBRA_CHIP[o.estado]}>{o.estado}</Chip></div>
              <div role="cell" className="mini"><Track small value={o.avance} /><span>{o.avance}%</span></div>
              {showMoney && (<><div role="cell">{fm(o.presupuesto)}</div><div role="cell">{fm(o.costo)}</div><div role="cell" className={o.margen >= 0 ? 'fyag-pos' : 'fyag-neg'}>{fm(o.margen)}</div></>)}
              {showDev && <div role="cell"><Chip cls={devChip(o)}>{devTxt(o.dev)}</Chip></div>}
            </div>
          ))}
        </Table>
      </div>

      {so && (
        <div className="card-fyag">
          <div className="card-h">
            <div><h2>{so.id} · {so.cliente}</h2></div>
            <button className="btn btn-sm btn-outline-secondary" onClick={() => setField('sel', null)}>Cerrar</button>
          </div>
          <div className="dgrid">
            <div className="dcol">
              <div className="kv"><span>Estado</span><Chip cls={OBRA_CHIP[so.estado]}>{so.estado}</Chip></div>
              <div className="kv"><span>Técnico</span><strong>{so.tecnico || 'Sin asignar'}</strong></div>
              <div className="kv"><span>Avance</span><strong>{so.avance}%</strong></div>
              <Track value={so.avance} />
              {showMoney && (<><div className="kv"><span>Presupuesto</span><strong>{fm(so.presupuesto)}</strong></div><div className="kv"><span>Costo</span><strong>{fm(so.costo)}</strong></div><div className="kv"><span>Margen</span><strong className={so.margen >= 0 ? 'fyag-pos' : 'fyag-neg'}>{fm(so.margen)}</strong></div></>)}
              {showDev && (<><div className="kv"><span>Costo acumulado</span><strong>{fm(so.costo)}</strong></div><div className="kv"><span>Desviación</span><Chip cls={devChip(so)}>{devTxt(so.dev)}</Chip></div></>)}
              {canEdit && (
                <div className="subform">
                  <label htmlFor="f-est" style={{ marginTop: 0 }}>Cambiar estado</label>
                  <div className="inline">
                    <select id="f-est" className="form-select" value={estadoDraft} onChange={(e) => setField('estadoDraft', e.target.value)}><option>En proceso</option><option>Suspendida</option><option>Finalizada</option><option>Cancelada</option></select>
                    <button className="btn btn-fyag-primary" onClick={applyEstado}>Aplicar</button>
                  </div>
                  <label htmlFor="f-tec">Técnico</label>
                  <select id="f-tec" className="form-select" value={so.tecnico || ''} onChange={(e) => assignTec(e.target.value)}><option value="">Sin asignar</option>{TECNICOS.map((t) => <option key={t}>{t}</option>)}</select>
                </div>
              )}
            </div>
            <div className="dcol">
              <h2>Costos</h2>
              <Table label="Costos" min="0" columns="80px 1fr 56px 100px" head={['Tipo', 'Detalle', 'Fecha', 'Monto']} style={{ marginTop: 10 }}>
                {costoRows.map((c, i) => (
                  <div key={i} className="trow" role="row" style={{ padding: '10px 0' }}>
                    <div role="cell"><Chip cls={c.tipo === 'Material' ? 'blue' : 'gray'}>{c.tipo}</Chip></div>
                    <div role="cell">{c.desc}</div>
                    <div role="cell" className="fyag-muted">{c.fecha}</div>
                    <div role="cell" className="fyag-money">{fm(c.monto)}</div>
                  </div>
                ))}
              </Table>
              {canEdit && (
                <div className="subform">
                  <h2>Registrar costo</h2>
                  <div className="fgrid">
                    <div><label htmlFor="f-kt">Tipo</label><select id="f-kt" className="form-select" value={fCostoTipo} onChange={(e) => setField('fCostoTipo', e.target.value)}><option value="Material">Material</option><option value="Horas">Horas</option></select></div>
                    <div><label htmlFor="f-kd">Detalle</label><input id="f-kd" className="form-control" value={fCostoDesc} onChange={(e) => setField('fCostoDesc', e.target.value)} /></div>
                    <div><label htmlFor="f-km">Monto ($)</label><input id="f-km" className="form-control" type="number" value={fCostoMonto} onChange={(e) => setField('fCostoMonto', e.target.value)} /></div>
                  </div>
                  <div className="actions mt-3"><button className="btn btn-fyag-primary" onClick={addCosto}>Registrar</button></div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}