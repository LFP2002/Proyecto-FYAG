import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
let server,AuthProvider,Mermas;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Mermas}=await server.ssrLoadModule('/src/pages/Mermas.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const ROOT='/api/inventario/mermas-supervisor/',WRITE='/api/inventario/mermas-obra/',date='2026-11-25T20:33:59-03:00';
const make=id=>({id,obra:'OB-000006',obra_estado:'EN_PROCESO',material:'Tubería',codigo:'TUB-001',unidad:'m',informado_por:'Técnico QA',estado:'PENDIENTE',cantidad:'1.000',tipo:'CORTE_NO_REUTILIZABLE',motivo:'Recorte inutilizable',actividad:'Instalación',referencia:'OT-5',entrega:12,motivo_decision:'',decidido_por:null,decidido_en:null,creado_en:date});
async function mount(){
 const calls=[],rows=[make(2),make(3)],session={status:'authenticated',user:{id:2,username:'supervisor',role:'SUPERVISOR_OBRAS'}},events={};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET',body:opts.body});
  const u=new URL(path,'http://localhost');
  if(u.pathname===ROOT){const estado=u.searchParams.get('estado'),tipo=u.searchParams.get('tipo');const results=rows.filter(r=>(!estado||r.estado===estado)&&(!tipo||r.tipo===tipo));return {count:results.length,results,next:null,previous:null,resumen:{pendientes:rows.filter(r=>r.estado==='PENDIENTE').length,aprobadas:rows.filter(r=>r.estado==='APROBADA').length,rechazadas:rows.filter(r=>r.estado==='RECHAZADA').length}};}
  if(u.pathname.startsWith(ROOT)){const id=Number(u.pathname.slice(ROOT.length).split('/')[0]),r=rows.find(r=>r.id===id);return {...r,entregado:'6.000',devuelto:'1.000',mermas_aprobadas:r.estado==='APROBADA'?'1.000':'0.000',remanente:r.estado==='APROBADA'?'4.000':'5.000',importe_informativo_no_aditivo:'8900.00',historial:[{id,tipo:'CREACION',actor:'Técnico QA',motivo:r.motivo,creado_en:date},...(events[id]||[])]};}
  assert.equal(opts.method,'POST');assert.ok(u.pathname.startsWith(WRITE));const id=Number(u.pathname.slice(WRITE.length).split('/')[0]),r=rows.find(r=>r.id===id),body=opts.body;
  assert.equal(r.estado,'PENDIENTE');assert.deepEqual(Object.keys(body).sort(),['clave_idempotencia','decision','motivo']);Object.assign(r,{estado:body.decision==='APROBAR'?'APROBADA':'RECHAZADA',motivo_decision:body.motivo,decidido_por:'supervisor',decidido_en:date});
  events[id]=[{id:10,tipo:body.decision==='APROBAR'?'APROBACION':'RECHAZO',actor:'supervisor',motivo:body.motivo,creado_en:date}];return {id:r.id,estado:r.estado};
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Mermas)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
async function click(r,label){const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);assert.ok(!b.props.disabled,label);await act(async()=>{b.props.onClick();await flush();});}
async function reason(r,value){await act(async()=>{r.root.findByProps({id:'ss-reason'}).props.onChange({target:{value}});await flush();});}
async function submit(r){await act(async()=>{await r.root.findByProps({'aria-label':'Confirmar decisión'}).props.onSubmit({preventDefault(){}});await flush();});}
test('Mermas de obra: pendientes, filtro compacto, ficha y volver sin enviar',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  assert.match(text(r.toJSON()),/Mermas de obra/);assert.doesNotMatch(text(r.toJSON()),/Ámbito/);
  assert.ok(ui.calls[0].path.includes('estado=PENDIENTE'));
  await act(async()=>{r.root.findByProps({'aria-label':'Tipo de merma'}).props.onChange({target:{value:'CORTE_NO_REUTILIZABLE'}});await flush();});
  assert.ok(ui.calls.some(c=>c.path.includes('tipo=CORTE_NO_REUTILIZABLE')));
  await click(r,'Aprobar');assert.match(text(r.toJSON()),/Aprobar merma/);assert.match(text(r.toJSON()),/Importe informativo/);assert.match(text(r.toJSON()),/Remanente/);
  assert.equal(r.root.findAllByType('table').length,0);assert.equal(r.root.findAllByProps({id:'ss-quantity'}).length,0);
  await click(r,'Volver al listado');assert.equal(r.root.findAllByType('table').length,1);
  assert.equal(r.root.findAllByProps({'aria-label':'Confirmar decisión'}).length,0);
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('Mermas de obra: aprobar y rechazar requieren motivo y no envían cantidad',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  await click(r,'Aprobar');await submit(r);assert.equal(ui.calls.filter(c=>c.method==='POST').length,0);
  await reason(r,'Pérdida comprobada');await submit(r);assert.match(text(r.toJSON()),/Merma aprobada/);
  await click(r,'Volver al listado');await click(r,'Rechazar');await reason(r,'No corresponde');await submit(r);
  assert.match(text(r.toJSON()),/Merma rechazada/);assert.equal(ui.calls.filter(c=>c.method==='POST').length,2);
 }finally{await ui.close();}
});
