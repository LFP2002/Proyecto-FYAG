import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
let server,AuthProvider,Solicitudes;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Solicitudes}=await server.ssrLoadModule('/src/pages/Solicitudes.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const ROOT='/api/inventario/solicitudes-supervisor/',WRITE='/api/inventario/solicitudes-materiales/',date='2026-11-25T20:33:59-03:00';
const make=id=>({id,obra:'OB-000006',obra_estado:'EN_PROCESO',material:'Filtro deshidratador',codigo:'FIL-003',unidad:'unidad',solicitante:'Técnico QA',estado:'PENDIENTE',cantidad_solicitada:'2.000',cantidad_aprobada:null,saldo:'3.000',justificacion:'Reponer filtro',motivo_decision:'',decidido_por:null,decidido_en:null,creado_en:date,autorizacion:null,historial:[{id,tipo:'CREACION',actor:'Técnico QA',motivo:'Reponer filtro',creado_en:date}]});
async function mount(){
 const calls=[],rows=[make(2),make(3)],session={status:'authenticated',user:{id:2,username:'supervisor',role:'SUPERVISOR_OBRAS'}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET',body:opts.body});
  const u=new URL(path,'http://localhost');
  if(u.pathname===ROOT){const estado=u.searchParams.get('estado');const results=rows.filter(r=>!estado||r.estado===estado).map(({historial,...r})=>r);return {count:results.length,results,next:null,previous:null,resumen:{pendientes:rows.filter(r=>r.estado==='PENDIENTE').length,aprobadas:rows.filter(r=>r.estado==='APROBADA').length,rechazadas:rows.filter(r=>r.estado==='RECHAZADA').length}};}
  if(u.pathname.startsWith(ROOT)){const id=Number(u.pathname.slice(ROOT.length).split('/')[0]);return structuredClone(rows.find(r=>r.id===id));}
  assert.equal(opts.method,'POST');const id=Number(u.pathname.slice(WRITE.length).split('/')[0]),r=rows.find(r=>r.id===id),body=opts.body;
  assert.equal(r.estado,'PENDIENTE');Object.assign(r,{estado:body.decision==='APROBAR'?'APROBADA':'RECHAZADA',cantidad_aprobada:body.cantidad_aprobada??null,motivo_decision:body.motivo,decidido_por:'supervisor',decidido_en:date,autorizacion:body.decision==='APROBAR'?12:null});
  r.historial.push({id:10,tipo:body.decision==='APROBAR'?'APROBACION':'RECHAZO',actor:'supervisor',motivo:body.motivo,creado_en:date});
  return {id:r.id,estado:r.estado};
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Solicitudes)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
async function click(r,label){const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);assert.ok(!b.props.disabled,label);await act(async()=>{b.props.onClick();await flush();});}
async function field(r,id,value){await act(async()=>{r.root.findByProps({id}).props.onChange({target:{value}});await flush();});}
async function submit(r){await act(async()=>{await r.root.findByProps({'aria-label':'Confirmar decisión'}).props.onSubmit({preventDefault(){}});await flush();});}
test('Supervisor: acciones visibles y volver desde una decisión sin pantalla en blanco ni POST',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  assert.match(text(r.toJSON()),/Filtro deshidratador/);assert.match(text(r.toJSON()),/Técnico QA/);
  assert.ok(ui.calls[0].path.includes('estado=PENDIENTE'));
  await click(r,'Aprobar');assert.match(text(r.toJSON()),/Aprobar solicitud/);
  assert.equal(r.root.findAllByType('table').length,0);
  await click(r,'Volver al listado');assert.equal(r.root.findAllByType('table').length,1);
  assert.equal(r.root.findAllByProps({'aria-label':'Confirmar decisión'}).length,0);
  await click(r,'Rechazar');assert.match(text(r.toJSON()),/Rechazar solicitud/);
  assert.equal(r.root.findAllByProps({id:'ss-quantity'}).length,0);
  await click(r,'Cancelar');assert.match(text(r.toJSON()),/Justificación/);
  await click(r,'Volver al listado');assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('Supervisor: validar cantidad y confirmar una sola aprobación conservando historial',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  await click(r,'Aprobar');await field(r,'ss-quantity','3');await field(r,'ss-reason','Necesario');
  await submit(r);assert.match(text(r.toJSON()),/no superar lo solicitado/);
  assert.equal(ui.calls.filter(c=>c.method==='POST').length,0);
  await field(r,'ss-quantity','1,5');await submit(r);
  const posts=ui.calls.filter(c=>c.method==='POST');assert.equal(posts.length,1);assert.equal(posts[0].body.cantidad_aprobada,'1.500');
  assert.match(text(r.toJSON()),/Solicitud aprobada/);assert.match(text(r.toJSON()),/Aprobación/);
  await click(r,'Volver al listado');assert.equal(r.root.findAllByType('tbody')[0].findAllByType('tr').length,1);
 }finally{await ui.close();}
});
test('Supervisor: rechazo sin cantidad y con motivo explícito',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  await click(r,'Rechazar');await field(r,'ss-reason','No corresponde');await submit(r);
  const posts=ui.calls.filter(c=>c.method==='POST');assert.equal(posts.length,1);assert.equal(posts[0].body.decision,'RECHAZAR');assert.ok(!('cantidad_aprobada' in posts[0].body));
  assert.match(text(r.toJSON()),/Solicitud rechazada/);
 }finally{await ui.close();}
});
