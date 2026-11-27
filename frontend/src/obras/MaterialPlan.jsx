import React, {useEffect, useState} from 'react';
import {movementAmount} from '../bodega/domain.js';
import {obraPath, readPage} from './api.js';
import {Feedback, Pager, useOperational} from './ui.jsx';

const STATES = {SIN_AUTORIZACION:'Sin autorización', PENDIENTE:'Pendiente', PARCIAL:'Parcial', COMPLETADO:'Completado', INHABILITADO:'Inhabilitado por cierre'};

export default function MaterialPlan({obra, revision = 0, disabled = false}) {
  const api = useOperational();
  const [origin, setOrigin] = useState('PRESUPUESTO'), [page, setPage] = useState(1), [data, setData] = useState(null);
  const path = `${obraPath(obra.id)}conciliacion-materiales/`;
  useEffect(() => {
    setData(null);
    void api.load('materials', `${path}?origen=${origin}&page=${page}`, result => setData(readPage(result, path)));
  }, [path, origin, page, revision]);
  const planned = origin === 'PRESUPUESTO';
  const fields = [...(planned ? [['Presupuestado','presupuestado']] : []), ['Autorizado','autorizado'], ['Despachado','despachado'], ['Devuelto','devuelto'], ['Neto imputado','neto_imputado'], ['Pendiente de despacho','pendiente_despacho']];
  return <section className="card-fyag so-panel" aria-label="Conciliación de materiales">
    <h3>Conciliación de materiales</h3>
    <p className="commercial-help">El neto imputado es lo despachado menos lo recibido de vuelta; no acredita consumo físico.</p>
    {obra.estado==='PLANIFICADA'&&<p className="commercial-help">Los materiales previstos se autorizan al iniciar. No se reserva stock.</p>}
    <div className="so-actions" aria-label="Origen de los materiales">
      {[['PRESUPUESTO','Previstos del presupuesto'],['ADICIONAL','Adicionales y sin vínculo histórico']].map(([value,label])=><button key={value} type="button" className="btn btn-outline-secondary" aria-pressed={origin===value} disabled={disabled} onClick={()=>{if(origin!==value){setData(null);setPage(1);setOrigin(value);}}}>{label}</button>)}
    </div>
    <Feedback api={api}/>
    {!api.loading&&!api.error&&data?.count===0&&<p className="commercial-help">{planned?'No hay materiales vinculados al presupuesto.':'No hay autorizaciones adicionales ni sin vínculo.'}</p>}
    {!api.loading&&!api.error&&data?.results.map(row=><article className="so-rubric" key={row.id}>
      <strong>{row.codigo} · {row.nombre}</strong> <span className="commercial-help">{STATES[row.estado]}{row.origen==='SOLICITUD'?' · Solicitud aprobada':''}</span>
      <dl className="commercial-facts">{fields.map(([label,key])=><div key={key}><dt>{label}</dt><dd>{movementAmount(row[key],row.unidad)}</dd></div>)}</dl>
    </article>)}
    {(data?.next||data?.previous)&&<Pager label="Paginación de materiales" data={data} page={page} setPage={setPage} disabled={disabled||api.loading}/>}
  </section>;
}
