import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';

let server,AuthProvider,Alertas;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Alertas}=await server.ssrLoadModule('/src/pages/Alertas.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const date='2026-11-25T20:33:59-03:00';
const page=results=>({count:results.length,results,next:null,previous:null});
const S='SUPERVISOR_OBRAS', G='GERENCIA', F='ADMINISTRATIVO_FINANZAS';
function alert(role,kind){
 const turn=kind==='TURNO', finance=role===F;
 return {id:turn?7:8,tipo:finance?'PRESUPUESTO_PENDIENTE_FINANZAS':turn?'TURNO_PENDIENTE_REVISION':'OBRA_SUSPENDIDA',estado:'PENDIENTE',severidad:turn||finance?'MEDIA':'ALTA',rol_destinatario:role,rol_responsable:finance?F:S,destinatarios:finance?[F]:turn?[S]:[S,G],es_legada:false,generacion:1,recurso_tipo:finance?'PRESUPUESTO':kind,recurso_id:turn?7:8,recurso_codigo:turn?null:finance?'PRE-000008':'OB-000008',obra:finance?null:8,titulo:finance?'Presupuesto pendiente de Finanzas':turn?'Turno pendiente de revisión':'Obra suspendida',descripcion:'Revisar antecedentes.',creado_en:date,atendida_por:null,atendida_en:null,motivo_atencion:'',resuelta_en:null,acciones_permitidas:role===G?[]:['ATENDER']};
}
async function mount(role=S){
 const calls=[],rows=role===S?[alert(role,'OBRA'),alert(role,'TURNO')]:[alert(role,'OBRA')],events=[];
 const session={status:'authenticated',user:{id:2,username:'qa',role}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET',body:opts.body});
  const u=new URL(path,'http://localhost');
  if(u.pathname==='/api/alertas/resumen/'){
   const por_estado={PENDIENTE:0,ATENDIDA:0,RESUELTA:0};
   for(const row of rows)por_estado[row.estado]++;
   return {generado_en:date,zona_horaria:'America/Santiago',por_estado,activas:por_estado.PENDIENTE+por_estado.ATENDIDA,por_tipo:{},sincronizacion:{ultima_correcta_en:date,desactualizada:false}};
  }
  if(u.pathname==='/api/alertas/'){
   const state=u.searchParams.get('estado')||'';
   return page(rows.filter(r=>(!state||state==='TODAS'||r.estado===state)&&['tipo','recurso_tipo','recurso_id'].every(k=>!u.searchParams.get(k)||String(r[k])===u.searchParams.get(k))));
  }
  const match=u.pathname.match(/^\/api\/alertas\/(\d+)\/(.*)$/);assert.ok(match,path);
  const row=rows.find(r=>r.id===Number(match[1]));assert.ok(row,path);
  if(match[2]==='historial/')return page(events.filter(e=>e.alerta===row.id));
  if(match[2]==='atender/'){
   assert.notEqual(role,G);assert.equal(opts.method,'POST');
   Object.assign(row,{estado:'ATENDIDA',atendida_por:2,atendida_en:date,motivo_atencion:opts.body.motivo,acciones_permitidas:[]});
   events.push({id:1,alerta:row.id,tipo:'ATENCION',estado_anterior:'PENDIENTE',estado_nuevo:'ATENDIDA',actor:2,motivo:opts.body.motivo,registrado_en:date});
  }else assert.equal(match[2],'');
  return structuredClone(row);
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Alertas)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
async function click(r,label){const b=r.root.findAllByType('button').find(b=>text(b).trim()===label||b.props['aria-label']===label);assert.ok(b,label);assert.ok(!b.props.disabled,label);await act(async()=>{b.props.onClick();await flush();});}
async function change(r,id,value){await act(async()=>{r.root.findByProps({id}).props.onChange({target:{value}});await flush();});}
async function submit(r,id){await act(async()=>{r.root.findByProps({id}).props.onSubmit({preventDefault(){}});await flush();});}
test('Supervisor: bandeja, filtros exactos, todas, detalle independiente y atención',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  assert.match(text(r.toJSON()),/Turno #7/);
  assert.doesNotMatch(text(r.toJSON()),/TURNO_PENDIENTE_REVISION/);
  assert.equal(r.root.findByProps({id:'alert-filters'}).props.hidden,true);
  assert.equal(r.root.findAllByProps({'aria-label':'Paginación de alertas'}).length,0);
  await click(r,'Filtros');
  await change(r,'alert-resource','TURNO');await change(r,'alert-resource-id','7');
  await submit(r,'alert-filters');
  assert.ok(ui.calls.some(c=>c.path.includes('recurso_tipo=TURNO')&&c.path.includes('recurso_id=7')));
  assert.doesNotMatch(text(r.toJSON()),/OB-000008/);
  await click(r,'Todas');assert.ok(ui.calls.some(c=>c.path.includes('estado=TODAS')));
  await click(r,'Turno pendiente de revisión · Turno #7');
  assert.match(text(r.toJSON()),/Historial de la alerta/);
  assert.equal(r.root.findAllByProps({id:'alert-filters'}).length,0);
  assert.equal(r.root.findAllByType('button').find(b=>text(b)==='Marcar como atendida').props.disabled,true);
  await change(r,'alert-reason','Revisado');
  const form=r.root.findAllByType('form').find(f=>f.props.className==='finance-alert-attention');
  await act(async()=>{await form.props.onSubmit({preventDefault(){}});await flush();});
  assert.equal(ui.calls.filter(c=>c.method==='POST').length,1);
  assert.match(text(r.toJSON()),/Alerta atendida/);
  await click(r,'Volver al listado');assert.match(text(r.toJSON()),/Turno #7/);
  await click(r,'Quitar filtros');assert.match(text(r.toJSON()),/OB-000008/);
 }finally{await ui.close();}
});
test('Gerencia conserva solo lectura y Finanzas conserva atención',async()=>{
 for(const role of [G,F]){
  const ui=await mount(role),r=ui.renderer;
  try{
   assert.equal(r.root.findAllByProps({id:'alert-resource'}).length,0);
   await click(r,role===G?'Obra suspendida · OB-000008':'Presupuesto pendiente de Finanzas · PRE-000008');
   assert.equal(r.root.findAllByProps({id:'alert-reason'}).length,role===G?0:1);
   assert.ok(ui.calls.every(c=>c.method==='GET'));
  }finally{await ui.close();}
 }
});
