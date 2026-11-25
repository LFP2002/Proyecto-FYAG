import React,{useState} from 'react';
import {useCommercial,Errors} from '../comercial/ui.jsx';
import InventoryPicker from './InventoryPicker.jsx';
const ROOT='/api/inventario/';
const uid=()=>crypto.randomUUID();
const id=v=>/^[1-9][0-9]*$/.test(String(v))&&Number.isSafeInteger(Number(v));
const refs=['obra','articulo','entrega','autorizacion','ingreso'];
const policies={
 SUPERVISOR_OBRAS:[['AUTORIZACION_ENTREGA','Autorizar entrega'],['AUTORIZACION_DEVOLUCION','Autorizar devolución']],
 BODEGUERO:[['ENTREGA','Despachar material'],['DEVOLUCION','Recibir devolución']],
 ADMINISTRATIVO_FINANZAS:[['VALORIZACION','Valorizar ingreso'],['REGULARIZACION','Regularizar saldo histórico']]
};
const contracts={
 AUTORIZACION_ENTREGA:{path:'autorizaciones-entrega/',required:['obra','articulo','cantidad'],optional:['referencia','motivo']},
 VALORIZACION:{path:'valorizaciones/',required:['ingreso','costo_unitario_neto','referencia'],optional:['motivo']},
 REGULARIZACION:{path:'regularizaciones-iniciales/',required:['articulo','costo_unitario_neto','referencia','motivo'],optional:[]},
 AUTORIZACION_DEVOLUCION:{path:'autorizaciones-devolucion/',required:['entrega','cantidad'],optional:['referencia','motivo']},
 ENTREGA:{path:'entregas/',required:['autorizacion','cantidad'],optional:['referencia','motivo']},
 DEVOLUCION:{path:'devoluciones/',required:['autorizacion','cantidad'],optional:['referencia','motivo']}
};
const labels={obra:'Obra',articulo:'Material',entrega:'Entrega',autorizacion:'Autorización',ingreso:'Ingreso de materiales',cantidad:'Cantidad',costo_unitario_neto:'Costo de adquisición unitario (neto CLP)',referencia:'Referencia de respaldo',motivo:'Motivo'};
export default function InventoryActions({role,onSuccess}){
 const api=useCommercial();const allowed=policies[role]||[];const [form,setForm]=useState(null),[message,setMessage]=useState('');
 function begin(type){setMessage('');setForm({type,key:uid(),values:Object.fromEntries([...contracts[type].required,...contracts[type].optional].map(k=>[k,'']))});}
 async function submit(e){e.preventDefault();if(!form||api.busy||api.locked)return;const spec=contracts[form.type],body={clave_idempotencia:form.key};for(const key of [...spec.required,...spec.optional]){const value=form.values[key]?.trim()??'';if(spec.required.includes(key)&&!value){api.setError({message:`Completa ${labels[key]}.`});return;}if(['obra','articulo','entrega','autorizacion','ingreso'].includes(key)&&value){if(!id(value)){api.setError({message:`${labels[key]} debe ser un identificador positivo.`});return;}body[key]=Number(value);continue;}if(key==='cantidad'&&value&&!/^[0-9]{1,9}(?:\.[0-9]{1,3})?$/.test(value)){api.setError({message:'Cantidad decimal inválida; máximo 9 enteros y 3 decimales.'});return;}if(key==='costo_unitario_neto'&&value&&!/^[0-9]{1,13}(?:\.[0-9]{1,2})?$/.test(value)){api.setError({message:'Costo neto inválido; ingresa hasta 13 enteros y 2 decimales.'});return;}if(value||spec.required.includes(key))body[key]=value;}
 await api.write(`${ROOT}${spec.path}`,'POST',body,async()=>{setForm(null);setMessage('Operación confirmada por la API.');await onSuccess?.();});}
 if(!allowed.length)return null;
 return <section className="card-fyag p-3 mt-3" aria-labelledby="inventory-operations-title"><h2 id="inventory-operations-title">Operaciones de materiales</h2><Errors error={api.error}/>{message&&<p className="alert alert-info" role="status">{message}</p>}<div className="d-flex flex-wrap gap-2">{allowed.map(([type,label])=><button key={type} className="btn btn-outline-secondary" type="button" disabled={api.busy||api.locked} onClick={()=>begin(type)}>{label}</button>)}</div>{form&&<form className="commercial-form mt-3" onSubmit={submit}><h3>{allowed.find(([key])=>key===form.type)?.[1]}</h3>{[...contracts[form.type].required,...contracts[form.type].optional].map(key=>refs.includes(key)?<InventoryPicker key={form.type+':'+key} kind={key==='autorizacion'?(form.type==='DEVOLUCION'?'autorizacionDevolucion':'autorizacionEntrega'):key} label={labels[key]} value={form.values[key]} onChange={value=>setForm(previous=>({...previous,values:{...previous.values,[key]:value}}))} activeOnly={key==='articulo'&&form.type==='AUTORIZACION_ENTREGA'} required disabled={api.busy||api.locked}/>:<label key={key} className="form-label">{labels[key]}{key==='motivo'?<textarea className="form-control" required={contracts[form.type].required.includes(key)} maxLength="2000" value={form.values[key]} disabled={api.busy||api.locked} onChange={e=>setForm({...form,values:{...form.values,[key]:e.target.value}})}/>:<input className="form-control" required={contracts[form.type].required.includes(key)} inputMode={['obra','articulo','entrega','autorizacion','ingreso','cantidad','costo_unitario_neto'].includes(key)?'decimal':'text'} maxLength={key==='referencia'?150:undefined} value={form.values[key]} disabled={api.busy||api.locked} onChange={e=>setForm({...form,values:{...form.values,[key]:e.target.value}})}/>}</label>)}{api.locked&&<p role="alert">Resultado incierto: conserva esta clave y los mismos datos. No abras una operación nueva hasta reconciliar.</p>}<div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.busy||api.locked}>Confirmar</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.locked} onClick={()=>setForm(null)}>Cancelar</button></div></form>}</section>;
}
