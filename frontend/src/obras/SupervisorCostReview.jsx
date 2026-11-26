import React,{useEffect,useState} from 'react';
import {formatCompactCLP} from '../utils/format.js';
import {timestamp} from './domain.js';
import {Field} from './ui.jsx';
import TecIcon from './TecIcon.jsx';

const LABELS={PENDIENTE:'Pendiente de declaración',CON_REGISTROS:'Con registros',NO_APLICA:'No aplica'};
const RUBROS=[['materiales','Materiales','materiales_total'],['otros','Otros gastos','otros_total']];
const positive=value=>typeof value==='string'&&/^\d+(?:\.\d{1,2})?$/.test(value)&&/[1-9]/.test(value);
const cents=value=>BigInt(String(value).split('.')[0])*100n+BigInt((String(value).split('.')[1]||'').padEnd(2,'0'));
export function costReviewState(obra,summary,control){
 const editable=['EN_PROCESO','SUSPENDIDA'].includes(obra.estado);
 const consistent=!!summary&&!!control&&summary.version_actual===control.version_actual&&summary.version_validada===control.version_validada&&summary.costos_validados===control.costos_validados&&RUBROS.every(([k])=>summary[k+'_estado']===control[k+'_estado']);
 const validated=consistent&&control.costos_validados&&control.version_actual===control.version_validada;
 const missing=consistent?RUBROS.filter(([k])=>control[k+'_estado']==='PENDIENTE').map(([,label])=>label):[];
 const canValidate=editable&&consistent&&!validated&&!missing.length&&positive(summary.costo_total);
 return {editable,consistent,validated,missing,canValidate,canFinalize:obra.estado==='EN_PROCESO'&&validated};
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
export default function SupervisorCostReview({obra,summary,control,api,onAction,onFinalize,onTab,refreshEpoch,busyAction}){
 const [editor,setEditor]=useState(null);
 useEffect(()=>{setEditor(null);},[refreshEpoch]);
 const state=costReviewState(obra,summary,control);
 const blocked=api.busy||api.loading||api.locked||busyAction||!state.consistent;
 const open=(type,name)=>{api.setError(null);setEditor({type,name,choice:'',reason:'',justification:''});};
 const change=(name,value)=>setEditor(old=>({...old,[name]:value}));
 const validText=value=>typeof value==='string'&&value.trim().length>0&&value.trim().length<=2000;
 const valid=editor&&(editor.type==='rubric'?!!editor.choice&&validText(editor.reason)&&(editor.choice!=='NO_APLICA'||validText(editor.justification)):editor.type==='courtesy'?validText(editor.justification)&&(!summary?.cortesia_sin_cobro||(validText(editor.reason)&&editor.reason.trim()!==editor.justification.trim()&&editor.justification.trim()!==summary.cortesia_justificacion)):validText(editor.reason));
 async function submit(e){
  e.preventDefault();if(blocked||!valid||!editor)return;
  let ok=false;
  if(editor.type==='rubric'&&state.editable)ok=await onAction('costos/control/',{[editor.name+'_estado']:editor.choice,[editor.name+'_justificacion']:editor.choice==='NO_APLICA'?editor.justification.trim():'',motivo:editor.reason.trim()},'PATCH');
  if(editor.type==='courtesy'&&state.editable)ok=await onAction('cortesia-sin-cobro/',{justificacion:editor.justification.trim(),...(summary.cortesia_sin_cobro?{motivo:editor.reason.trim()}:{})});
  if(editor.type==='validate'&&state.canValidate)ok=await onAction('costos/validar/',{motivo:editor.reason.trim()});
  if(editor.type==='finalize'&&state.canFinalize)ok=await onFinalize(editor.reason.trim());
  if(ok)setEditor(null);
 }
 function editorForm(type,name){
  if(editor?.type!==type||(name&&editor.name!==name))return null;
  const title=type==='rubric'?'Declarar '+RUBROS.find(([k])=>k===name)[1].toLowerCase():type==='courtesy'?(summary.cortesia_sin_cobro?'Rectificar servicio sin cobro':'Registrar servicio sin cobro'):type==='validate'?'Confirmar validación':'Confirmar finalización';
  const allowed=type==='validate'?state.canValidate:type==='finalize'?state.canFinalize:state.editable;
  return <form className="so-editor" aria-label={title} onSubmit={submit}><h4>{title}</h4>
   {type==='rubric'&&<Field name={'rubric-'+name} label="Declaración" value={editor.choice} options={ [['','Selecciona una opción'],['CON_REGISTROS','Existen registros vigentes'],['NO_APLICA','No aplica a esta obra']] } disabled={blocked} onChange={v=>change('choice',v)}/>}
   {(type==='courtesy'||type==='rubric'&&editor.choice==='NO_APLICA')&&<Field name={type==='courtesy'?'cortesia-justificacion':'rubric-'+name+'-reason'} label="Justificación obligatoria" type="textarea" value={editor.justification} maxLength={2000} disabled={blocked} onChange={v=>change('justification',v)}/>}
   {(type!=='courtesy'||summary.cortesia_sin_cobro)&&<Field name={type==='finalize'?'finalizar-motivo':type==='validate'?'costos-motivo':type==='rubric'?'rubric-'+name+'-motivo':'cortesia-motivo'} label={type==='finalize'?'Motivo de finalización':type==='validate'?'Motivo para validar costos':type==='courtesy'?'Motivo de la rectificación':'Motivo de la declaración'} type="textarea" value={editor.reason} maxLength={2000} disabled={blocked} onChange={v=>change('reason',v)}/>}
   {type==='finalize'&&<p className="so-warning"><TecIcon name="warning"/> Esta acción es definitiva. El servidor verificará nuevamente los requisitos y conservará los costos de cierre.</p>}
   {type==='validate'&&<p className="commercial-help">El servidor comprobará los turnos, registros vigentes, responsable y demás requisitos de cierre.</p>}
   {!allowed&&<p className="so-warning">El estado actual ya no permite esta acción.</p>}
   <div className="so-actions"><button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.locked} onClick={()=>setEditor(null)}>Cancelar</button><button className={'btn '+(type==='finalize'?'btn-outline-danger':'btn-fyag-primary')} disabled={blocked||!valid||!allowed} type="submit">{type==='rubric'?'Guardar declaración':type==='courtesy'?'Guardar sin cobro':type==='validate'?'Confirmar validación':'Confirmar finalización'}</button></div>
  </form>;
 }
 if(!summary||!control)return !api.loading&&!api.error?<SupervisorEmpty title="Información de costos no disponible" description="Actualiza para consultar el resumen y el control."/>:null;
 return <>
 <section className="card-fyag so-panel so-cost-summary" aria-label="Resumen de costos">
  <div className="so-section-head"><h3>Resumen económico</h3><span className={state.validated&&!summary.provisional?'so-good':'so-warning-text'}>{state.validated&&!summary.provisional?'Costos validados':'Costo provisional'}</span></div>
  <div className="so-cost-total"><span>Costo real total · CLP neto</span><strong>{formatCompactCLP(summary.costo_total)}</strong><small>{summary.provisional?'Importe registrado hasta ahora; puede cambiar.':'Importe registrado en el sistema.'}</small></div>
  <Breakdown summary={summary}/>
 </section>
 {!state.consistent&&<p role="alert" className="so-warning"><TecIcon name="warning"/> Los datos de costos y control no coinciden. Actualiza antes de continuar.</p>}
 <section className="card-fyag so-panel">
  <div className="so-section-head"><h3>Revisión de costos</h3><small>Versión {control.version_actual}</small></div>
  {!state.editable&&<p className="commercial-help">{obra.estado==='PLANIFICADA'?'Inicia la obra para registrar y revisar sus costos.':'La obra está cerrada; los registros solo están disponibles para consulta.'}</p>}
  {RUBROS.map(([key,label,amount])=><div className="so-rubric" key={key}><div className="so-rubric-row"><TecIcon name={control[key+'_estado']==='PENDIENTE'?'clock':'check'}/><div className="so-grow"><strong>{label}</strong><span className={control[key+'_estado']==='PENDIENTE'?'so-warning-text':'commercial-help'}>{LABELS[control[key+'_estado']]}</span>{control[key+'_justificacion']&&<p>{control[key+'_justificacion']}</p>}</div><strong className="so-rubric-amount">{formatCompactCLP(summary[amount])}</strong>{state.editable&&!editor&&<button className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>open('rubric',key)}>Revisar {label.toLowerCase()}</button>}</div>{editorForm('rubric',key)}</div>)}
  <div className="so-rubric"><div className="so-rubric-row"><TecIcon name={state.validated?'check':'clock'}/><div className="so-grow"><strong>Mano de obra</strong><span className="commercial-help">{state.validated?'Validación vigente':'Revisa los turnos cerrados y su valoración.'}</span></div><strong className="so-rubric-amount">{formatCompactCLP(summary.mano_obra_total)}</strong>{onTab&&!editor&&<button className="btn btn-outline-secondary btn-sm" disabled={api.busy||api.locked} onClick={()=>onTab('turnos')}>Ver turnos</button>}</div></div>
  <div className="so-rubric"><div className="so-rubric-row"><TecIcon name="work"/><div className="so-grow"><strong>Servicio sin cobro</strong><span className="commercial-help">{summary.cortesia_sin_cobro?'Registrado · no modifica los costos reales.':'Excepción opcional; no reduce los costos reales.'}</span>{summary.cortesia_justificacion&&<p>{summary.cortesia_justificacion}</p>}</div>{state.editable&&!editor&&<button className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>open('courtesy')}>{summary.cortesia_sin_cobro?'Rectificar':'Registrar sin cobro'}</button>}</div>{editorForm('courtesy')}</div>
 </section>
 <section className="card-fyag so-panel">
  <div className="so-section-head"><h3>Validación y cierre operativo</h3></div>
  <div className="so-close-state"><TecIcon name={state.validated?'check':'clock'}/><div className="so-grow"><strong>{obra.estado==='FINALIZADA'?'Obra finalizada':state.validated?'Validación vigente':'Costos pendientes de validación'}</strong>
   {state.validated&&control.validado_en&&<p className="commercial-help">Validada el {timestamp(control.validado_en)} · versión {control.version_validada}</p>}
   {!state.validated&&<p className="commercial-help">{!state.editable?'La validación requiere una obra en ejecución o suspendida.':state.missing.length?'Falta declarar: '+state.missing.join(' y ')+'.':!positive(summary.costo_total)?'El costo real debe ser mayor que cero.':'Solicita la validación; el servidor comprobará todos los requisitos.'}</p>}
   {obra.estado==='SUSPENDIDA'&&<p className="commercial-help">Para finalizar, primero reanuda la obra.</p>}
   {state.validated&&obra.estado==='EN_PROCESO'&&<p className="commercial-help">La finalización definitiva requiere una nueva comprobación del servidor.</p>}
  </div>{!editor&&state.editable&&(state.validated?(state.canFinalize&&<button className="btn btn-outline-danger" disabled={blocked} onClick={()=>open('finalize')}>Finalizar obra</button>):<button className="btn btn-fyag-primary" disabled={blocked||!state.canValidate} onClick={()=>open('validate')}>Validar costos</button>)}</div>
  {editorForm('validate')}{editorForm('finalize')}
 </section>
 </>;
}
