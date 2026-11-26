import React from 'react';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';
import {timestamp} from './domain.js';
import TecIcon from './TecIcon.jsx';

const states={PENDIENTE:'Pendiente de declaración',CON_REGISTROS:'Con registros',NO_APLICA:'No aplica'};
const types={MATERIAL:'Material',TRANSPORTE:'Transporte',ARRIENDO_EQUIPO:'Arriendo de equipo',SERVICIO_EXTERNO:'Servicio externo',OTRO:'Otro gasto'};
const isObject=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const scalar=value=>value==null||['string','number','boolean'].includes(typeof value);
const plain=value=>value==null||value===''?'No registrado':String(value);
const amount=value=>value==null||value===''?'No registrado':formatCompactCLP(value)+' CLP';
const quantity=value=>typeof value==='string'&&/^\d+(?:\.\d{1,3})?$/.test(value)?value.replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,'').replace('.',','):plain(value);
const status=value=>states[value]||plain(value);
const yesNo=value=>value===true?'Sí':value===false?'No':plain(value);
const version=value=>value==null?'Sin validación vigente':String(value);
const fields=[
 ['descripcion','Descripción',plain],['tipo','Tipo de gasto',value=>types[value]||plain(value)],
 ['cantidad','Cantidad',quantity],['unidad','Unidad',plain],['cantidad_devuelta','Cantidad devuelta',quantity],
 ['costo_unitario_neto','Costo unitario neto',amount],['subtotal','Subtotal neto',amount],
 ['fecha_gasto','Fecha del gasto',value=>value?formatCivilDate(value):'No registrado'],
 ['referencia_respaldo','Referencia de respaldo',plain],['observacion','Observación',plain],
 ['vigente','Vigencia',value=>value===true?'Vigente':value===false?'Anulado':plain(value)],
 ['materiales_estado','Declaración de materiales',status],['materiales_justificacion','Justificación de materiales',plain],
 ['otros_estado','Declaración de otros gastos',status],['otros_justificacion','Justificación de otros gastos',plain],
 ['costos_validados','Validación de costos',yesNo],['version_actual','Versión del control',plain],
 ['version_validada','Versión validada',version],['version_costos','Versión de costos',plain],
 ['justificacion','Justificación del servicio sin cobro',plain]
];
export function describeCostEvent(event){
 const before=isObject(event.datos_anteriores)?event.datos_anteriores:{};
 const after=isObject(event.datos_nuevos)?event.datos_nuevos:{};
 const courtesy=event.tipo==='CORTESIA';
 const changed=fields.filter(([key])=>!(courtesy&&key==='tipo')&&(Object.hasOwn(before,key)||Object.hasOwn(after,key))&&scalar(before[key])&&scalar(after[key])&&before[key]!==after[key]).map(([key,label,format])=>({key,label,before:format(before[key]),after:format(after[key])}));
 const hasPrevious=Object.keys(before).length>0;
 const rubricChanges=['materiales','otros'].filter(k=>Object.hasOwn(after,k+'_estado')&&before[k+'_estado']!==after[k+'_estado']);
 const reset=event.tipo==='DECLARACION'&&rubricChanges.some(k=>before[k+'_estado']&&before[k+'_estado']!=='PENDIENTE'&&after[k+'_estado']==='PENDIENTE');
 const names={DECLARACION:reset?'Declaración pendiente de revisión':'Declaración de rubros actualizada',VALIDACION:'Costos validados',CORTESIA:hasPrevious?'Servicio sin cobro rectificado':'Servicio sin cobro autorizado',ALTA:'Gasto registrado',CORRECCION:'Gasto corregido',DEVOLUCION:'Devolución registrada',ANULACION:'Gasto anulado'};
 const tone=event.tipo==='VALIDACION'?'positive':['ANULACION','CORTESIA'].includes(event.tipo)?'sensitive':reset?'warning':'normal';
 const highlights=[];
 if(event.tipo==='DECLARACION'){
  for(const key of rubricChanges)highlights.push({label:key==='materiales'?'Materiales':'Otros gastos',value:status(after[key+'_estado'])});
 }
 if(event.tipo==='VALIDACION'&&after.version_validada!=null)highlights.push({label:'Versión validada',value:String(after.version_validada)});
 if(courtesy&&typeof after.justificacion==='string'&&after.justificacion.trim())highlights.push({label:'Justificación',value:after.justificacion});
 if(event.tipo==='DEVOLUCION'&&isObject(after.devolucion)){
  if(typeof after.devolucion.cantidad==='string')highlights.push({label:'Cantidad devuelta en esta operación',value:quantity(after.devolucion.cantidad)+(typeof after.unidad==='string'?' '+after.unidad:'')});
  if(typeof after.devolucion.fecha==='string')highlights.push({label:'Fecha de devolución',value:formatCivilDate(after.devolucion.fecha)});
 }
 if(['ALTA','CORRECCION','DEVOLUCION','ANULACION'].includes(event.tipo)&&typeof after.subtotal==='string')highlights.push({label:event.tipo==='ANULACION'?'Subtotal registrado al anular':'Subtotal neto registrado',value:amount(after.subtotal)});
 return {title:names[event.tipo]||'Movimiento de costos registrado',tone,changed,highlights,subject:event.gasto&&typeof after.descripcion==='string'?after.descripcion:null,hasPrevious};
}

export default function SupervisorCostHistory({events}){
 return <ol className="so-cost-history" aria-label="Actividad de costos">{events.map(event=>{
  const {title,tone,changed,highlights,subject,hasPrevious}=describeCostEvent(event);
  return <li className="so-cost-event" key={event.id} data-tone={tone}>
   <span className="so-event-marker"><TecIcon name={tone==='positive'?'check':tone==='sensitive'||tone==='warning'?'warning':'document'}/></span>
   <div className="so-event-content">
    <header className="so-event-heading"><div><h4>{title}</h4>{subject&&<p className="so-event-subject">{subject}</p>}</div><span className="commercial-help">{timestamp(event.creado_en)}</span></header>
    <p className="so-event-meta commercial-help">{event.registrado_por!=null?'Registrado por usuario #'+event.registrado_por:'Autor no disponible'}{event.gasto?' · Gasto #'+event.gasto:''}</p>
    {highlights.length>0&&<dl className="so-event-highlights">{highlights.map(({label,value})=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
    {event.motivo&&<div className="so-event-reason"><strong>Motivo</strong><p>{event.motivo}</p></div>}
    {changed.length>0&&<details className="so-event-details"><summary>{hasPrevious?'Ver cambios registrados':'Ver datos registrados'}</summary><div className="table-responsive"><table className="table commercial-table so-event-table"><thead><tr><th scope="col">Campo</th>{hasPrevious&&<th scope="col">Anterior</th>}<th scope="col">{hasPrevious?'Nuevo':'Valor registrado'}</th></tr></thead><tbody>{changed.map(row=><tr key={row.key}><th scope="row">{row.label}</th>{hasPrevious&&<td>{row.before}</td>}<td>{row.after}</td></tr>)}</tbody></table></div></details>}
   </div>
  </li>;
 })}</ol>;
}
