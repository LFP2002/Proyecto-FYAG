import React,{useEffect,useState} from 'react';
import {formatCompactCLP} from '../utils/format.js';
import {timestamp} from './domain.js';
import {Field} from './ui.jsx';
import TecIcon from './TecIcon.jsx';
import {movementAmount} from '../bodega/domain.js';

const LABELS={PENDIENTE:'Por validar',CON_REGISTROS:'Con registros',NO_APLICA:'No aplica'};
const RUBROS=[['materiales','Materiales','materiales_total'],['otros','Otros gastos','otros_total']];
const cents=value=>BigInt(String(value).split('.')[0])*100n+BigInt((String(value).split('.')[1]||'').padEnd(2,'0'));
export function costReviewState(obra,summary,requirements){
 const editable=['EN_PROCESO','SUSPENDIDA'].includes(obra.estado);
 const validated=summary?.costos_validados===true;
 const canValidate=editable&&!!requirements&&!validated&&requirements.validacion.length===0;
 const canFinalize=obra.estado==='EN_PROCESO'&&validated&&!!requirements&&!requirements.finalizacion.length&&!requirements.devoluciones.length;
 return {editable,validated,canValidate,canFinalize};
}
export function SupervisorEmpty({title,description}){
 return <div className="so-empty" role="status"><TecIcon name="inbox"/><strong>{title}</strong>{description&&<p>{description}</p>}</div>;
}
function Breakdown({summary}){
 const items=[['Materiales','materiales_total','materials'],['Mano de obra','mano_obra_total','labor'],['Otros gastos','otros_total','other']];
 const total=items.reduce((n,[,key])=>n+cents(summary[key]),0n);
 return <div className="so-breakdown"><div className="so-cost-values">{items.map(([label,key,tone])=><div key={key}><span><i className={'so-dot '+tone}/>{label}</span><strong>{formatCompactCLP(summary[key])}</strong></div>)}</div>
 {total>0n&&<div className="so-cost-chart" role="img" aria-label={'Composición del costo registrado: '+items.map(([label,key])=>label+' '+formatCompactCLP(summary[key])).join(', ')}>{items.filter(([,key])=>cents(summary[key])>0n).map(([label,key,tone])=><span key={key} className={tone} title={label+': '+formatCompactCLP(summary[key])} style={{flexGrow:Number(cents(summary[key])*1000000n/total),flexBasis:0}}/>)}</div>}
 {total===0n&&<p className="commercial-help">No hay importes registrados para representar la composición.</p>}</div>;
}
export default function SupervisorCostReview({obra,summary,requirements,api,onAction,onFinalize,onTab,refreshEpoch,busyAction}){
 const [editor,setEditor]=useState(null);
 useEffect(()=>{setEditor(null);},[refreshEpoch]);
 const state=costReviewState(obra,summary,requirements);
 const blocked=api.busy||api.loading||api.locked||busyAction;
 const open=type=>{api.setError(null);setEditor({type,reason:'',justification:'',accepted:false,token:requirements?.confirmacion_remanente??null});};
 const change=(name,value)=>setEditor(old=>({...old,[name]:value}));
 const validText=value=>typeof value==='string'&&value.trim().length>0&&value.trim().length<=2000;
 const valid=editor&&(editor.type==='courtesy'?validText(editor.justification)&&(!summary?.cortesia_sin_cobro||(validText(editor.reason)&&editor.reason.trim()!==editor.justification.trim()&&editor.justification.trim()!==summary.cortesia_justificacion)):validText(editor.reason)&&(editor.type!=='finalize'||editor.accepted&&editor.token===requirements?.confirmacion_remanente));
 async function submit(e){
  e.preventDefault();if(blocked||!valid||!editor)return;
  let ok=false;
  if(editor.type==='courtesy'&&state.editable&&!window.confirm(summary.cortesia_sin_cobro?'¿Rectificar la justificación del servicio sin cobro? Se registrará el cambio y deberá validarse nuevamente el costo.':'¿Autorizar el servicio sin cobro? Esta autorización no puede retirarse desde el sistema; solo podrás rectificar su justificación. No reduce los costos reales y deja sin efecto la validación anterior.'))return;
  if(editor.type==='courtesy'&&state.editable)ok=await onAction('cortesia-sin-cobro/',{justificacion:editor.justification.trim(),...(summary.cortesia_sin_cobro?{motivo:editor.reason.trim()}:{})});
  if(editor.type==='validate'&&state.canValidate)ok=await onAction('costos/validar/',{motivo:editor.reason.trim()});
  if(editor.type==='finalize'&&state.canFinalize)ok=await onFinalize(editor.reason.trim(),editor.token);
  if(ok)setEditor(null);
 }
 function editorForm(type){
  if(editor?.type!==type)return null;
  const title=type==='courtesy'?(summary.cortesia_sin_cobro?'Rectificar servicio sin cobro':'Registrar servicio sin cobro'):type==='validate'?'Confirmar validación':'Confirmar finalización';
  const allowed=type==='validate'?state.canValidate:type==='finalize'?state.canFinalize:state.editable;
  return <form className="so-editor" aria-label={title} onSubmit={submit}><h4>{title}</h4>
   {type==='courtesy'&&<Field name="cortesia-justificacion" label="Justificación obligatoria" type="textarea" value={editor.justification} maxLength={2000} disabled={blocked} onChange={v=>change('justification',v)}/>}
   {(type!=='courtesy'||summary.cortesia_sin_cobro)&&<Field name={type==='finalize'?'finalizar-motivo':type==='validate'?'costos-motivo':'cortesia-motivo'} label={type==='finalize'?'Motivo de finalización':type==='validate'?'Motivo para validar costos':'Motivo de la rectificación'} type="textarea" value={editor.reason} maxLength={2000} disabled={blocked} onChange={v=>change('reason',v)}/>}
   {type==='courtesy'&&<p className="so-warning"><TecIcon name="warning"/> La autorización sin cobro no se puede retirar; solo rectificar su justificación. No reduce el costo real.</p>}
   {type==='finalize'&&<p className="so-warning"><TecIcon name="warning"/> Esta acción es definitiva. El servidor verificará nuevamente los requisitos y conservará los costos de cierre.</p>}
   {type==='finalize'&&<label><input type="checkbox" checked={editor.accepted} disabled={blocked||!allowed} onChange={e=>change('accepted',e.target.checked)}/> {editor.token?'Confirmo que los despachos pendientes mostrados quedarán inhabilitados.':'Confirmo la finalización definitiva.'}</label>}
   {type==='validate'&&<p className="commercial-help">El servidor comprobará los turnos, registros vigentes, responsable y demás requisitos de cierre.</p>}
   {!allowed&&<p className="so-warning">El estado actual ya no permite esta acción.</p>}
    <div className="so-actions"><button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.locked} onClick={()=>setEditor(null)}>Cancelar</button><button className={'btn '+(['finalize','courtesy'].includes(type)?'btn-outline-danger so-danger-action':'btn-outline-success so-positive-action')} disabled={blocked||!valid||!allowed} type="submit">{type==='courtesy'?'Guardar sin cobro':type==='validate'?'Confirmar validación':'Confirmar finalización'}</button></div>
  </form>;
 }
 if(!summary)return !api.loading&&!api.error?<SupervisorEmpty title="Información de costos no disponible" description="Actualiza para consultar el resumen."/>:null;
 return <>
 <section className="card-fyag so-panel so-cost-summary" aria-label="Resumen de costos">
  <div className="so-section-head"><h3>Resumen económico</h3><span className={state.validated&&!summary.provisional?'so-good':'so-warning-text'}>{state.validated&&!summary.provisional?'Costos validados':'Costo provisional'}</span></div>
  <div className="so-cost-total"><span>Costo real total · CLP neto</span><strong>{formatCompactCLP(summary.costo_total)}</strong><small>{summary.provisional?'Importe registrado hasta ahora; puede cambiar.':'Importe registrado en el sistema.'}</small></div>
  <Breakdown summary={summary}/>
 </section>
 <section className="card-fyag so-panel">
   <div className="so-section-head"><h3>Revisión de costos</h3></div>
  {!state.editable&&<p className="commercial-help">{obra.estado==='PLANIFICADA'?'Inicia la obra para registrar y revisar sus costos.':'La obra está cerrada; los registros solo están disponibles para consulta.'}</p>}
   {RUBROS.map(([key,label])=><div className="so-rubric" key={key}><strong>{label} · {LABELS[summary[key+'_estado']]}</strong>{summary[key+'_justificacion']&&<p>{summary[key+'_justificacion']}</p>}</div>)}
  <div className="so-rubric"><div className="so-rubric-row"><TecIcon name={state.validated?'check':'clock'}/><div className="so-grow"><strong>Mano de obra</strong><span className="commercial-help">{state.validated?'Validación vigente':'Revisa los turnos cerrados y su valoración.'}</span></div><div className="so-rubric-value"><span>Costo neto registrado · CLP</span><strong>{formatCompactCLP(summary.mano_obra_total)}</strong></div><div className="so-rubric-action">{onTab&&!editor&&<button className="btn btn-outline-secondary btn-sm" disabled={api.busy||api.locked} onClick={()=>onTab('turnos')}>Ver turnos</button>}</div></div></div>
  <div className="so-rubric so-rubric-courtesy"><div className="so-rubric-row"><TecIcon name="work"/><div className="so-grow"><strong className="so-sensitive-label">Servicio sin cobro</strong><span className="commercial-help">{summary.cortesia_sin_cobro?'Registrado · no modifica los costos reales.':'Excepción opcional; no reduce los costos reales.'}</span>{summary.cortesia_justificacion&&<p>{summary.cortesia_justificacion}</p>}</div><div className="so-rubric-action">{state.editable&&!editor&&<button className="btn btn-outline-danger so-danger-action btn-sm" disabled={blocked} onClick={()=>open('courtesy')}>{summary.cortesia_sin_cobro?'Rectificar':'Registrar sin cobro'}</button>}</div></div>{editorForm('courtesy')}</div>
 </section>
 <section className="card-fyag so-panel">
  <div className="so-section-head"><h3>Validación y cierre operativo</h3></div>
  <div className="so-close-state"><TecIcon name={state.validated?'check':'clock'}/><div className="so-grow"><strong>{obra.estado==='FINALIZADA'?'Obra finalizada':state.validated?'Validación vigente':'Costos pendientes de validación'}</strong>
    {state.validated&&summary.validado_en&&<p className="commercial-help">Validada el {timestamp(summary.validado_en)}</p>}
    {state.editable&&!requirements&&<p className="commercial-help">{api.loading?'Comprobando requisitos…':'Requisitos no comprobados. Actualiza antes de continuar.'}</p>}
   {obra.estado==='SUSPENDIDA'&&<p className="commercial-help">Para finalizar, primero reanuda la obra.</p>}
   {state.validated&&obra.estado==='EN_PROCESO'&&<p className="commercial-help">La finalización definitiva requiere una nueva comprobación del servidor.</p>}
   </div>{!editor&&state.editable&&(state.validated?(state.canFinalize&&<button className="btn btn-outline-danger so-danger-action" disabled={blocked} onClick={()=>open('finalize')}>Finalizar obra</button>):<button className="btn btn-outline-success so-positive-action" disabled={blocked||!state.canValidate} onClick={()=>open('validate')}>Validar costos</button>)}</div>
   {requirements&&<>
    <h4>Requisitos para {state.validated?'finalizar':'validar costos'}</h4>
    <ul>{(state.validated?requirements.finalizacion:requirements.validacion).map(({codigo,destino,mensaje})=><li key={codigo}>{mensaje} {onTab&&destino!=='costos'&&<button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>onTab(destino)}>{{turnos:'Ver turnos',tecnicos:'Ver equipo',gastos:'Ver materiales y gastos',resumen:'Ver estado'}[destino]}</button>}</li>)}</ul>
    {!!requirements.devoluciones.length&&<div className="so-warning"><strong>Bodega debe recibir estas devoluciones antes del cierre</strong><ul>{requirements.devoluciones.map((r,i)=><li key={i}>{r.obra} · {r.codigo} · {r.nombre}: {movementAmount(r.cantidad,r.unidad)}</li>)}</ul></div>}
    {!!requirements.despachos.length&&<div className="so-warning"><strong>Despachos que quedarán inhabilitados al finalizar</strong><ul>{requirements.despachos.map(r=><li key={r.codigo+r.unidad}>{r.codigo} · {r.nombre}: {r.cantidad.replace('.',',')} {r.unidad}</li>)}</ul></div>}
   </>}
  {editorForm('validate')}{editorForm('finalize')}
 </section>
 </>;
}
