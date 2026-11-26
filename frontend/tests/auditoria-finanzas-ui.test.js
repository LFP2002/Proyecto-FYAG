import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';

let server,AuthProvider,Auditoria;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Auditoria}=await server.ssrLoadModule('/src/pages/Auditoria.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const date='2026-11-25T20:33:59-03:00';
const base={id:'FINANZAS_EVENTO:8',evento_id:8,fuente:'FINANZAS_EVENTO',modulo:'FINANZAS',recurso_tipo:'DOCUMENTO',recurso_id:5,tipo:'DOCUMENTO_REVERTIDO',actor:2,actor_etiqueta:'Finanzas QA',actor_username:'finanzas',actor_identidad_origen:'ACTUAL',motivo:'Rectificación de datos comerciales',creado_en:date,datos_anteriores:{estado:'VIGENTE'},datos_nuevos:{estado:'REVERTIDO',motivo_reversion:'Rectificación de datos comerciales',referencia_rectificacion_externa:'Acta 5'}};
const payment={...base,id:'FINANZAS_EVENTO:7',evento_id:7,tipo:'PAGO_REGISTRADO',recurso_tipo:'PAGO',recurso_id:2,actor_identidad_origen:'HISTORICA',motivo:'',datos_anteriores:{},datos_nuevos:{monto:'447440.00',estado:'ACTIVO'}};
async function mount({role='ADMINISTRATIVO_FINANZAS',rows=[base,payment],paged=false}={}){
 const calls=[],session={status:'authenticated',user:{id:2,username:'finanzas',role}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET'});const u=new URL(path,'http://localhost');
  assert.equal(u.pathname,'/api/auditoria/eventos/');
  const cursor=u.searchParams.get('cursor');
  const items=rows.filter(r=>(!u.searchParams.get('tipo')||r.tipo===u.searchParams.get('tipo'))&&(!u.searchParams.get('recurso_tipo')||r.recurso_tipo===u.searchParams.get('recurso_tipo')));
  return {results:paged?(cursor?[payment]:[base]):items,next_cursor:paged&&!cursor?'cursor-opaco':null,has_more:paged&&!cursor,fecha_corte:date,zona_horaria:'America/Santiago'};
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Auditoria)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
const click=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
const change=async(r,label,value)=>{const l=r.root.findAllByType('label').find(l=>text(l).startsWith(label));assert.ok(l,label);const c=l.findAll(n=>['input','select'].includes(n.type))[0];await act(async()=>{c.props.onChange({target:{value}});await flush();});};
const submit=async(r,label)=>{const f=r.root.findByProps({'aria-label':label});await act(async()=>{f.props.onSubmit({preventDefault(){}});await flush();});};
const openDetail=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>b.props['aria-label']===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
test('Auditoría AF: filtros reales, detalle de reversión y retorno a consulta',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/Auditoría financiera/);
  assert.equal(r.root.findAllByType('label').some(l=>text(l).startsWith('Módulo')),false);
  await change(r,'Tipo de evento','DOCUMENTO_REVERTIDO');
  await change(r,'Recurso','DOCUMENTO');await submit(r,'Filtrar eventos financieros');
  assert.ok(ui.calls.some(c=>c.path.includes('tipo=DOCUMENTO_REVERTIDO')&&c.path.includes('recurso_tipo=DOCUMENTO')));
  await openDetail(r,'Ver detalle de Documento revertido Documento #5');
  assert.match(body(),/Estado registrado/);assert.match(body(),/Vigente→Revertido/);
  assert.match(body(),/Modificado/);assert.match(body(),/Registrado/);assert.match(body(),/Identidad actual/);
  assert.match(body(),/Acta 5/);assert.doesNotMatch(body(),/Monto total registrado/);
  await click(r,'Volver al historial');assert.match(body(),/Filtros aplicados/);
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('Auditoría AF: importe histórico, cursor opaco y estados vacíos',async()=>{
 const ui=await mount({paged:true}),r=ui.renderer;
 try{
  await click(r,'Siguiente');assert.ok(ui.calls.some(c=>c.path.endsWith('?cursor=cursor-opaco')));
  await openDetail(r,'Ver detalle de Pago registrado Pago #2');
  const body=text(r.toJSON());assert.match(body,/Monto registrado/);assert.match(body,/447\.440/);assert.match(body,/Identidad registrada en el evento/);assert.match(body,/No se registró un motivo/);
  await click(r,'Volver al historial');await click(r,'Anterior');assert.match(text(r.toJSON()),/Documento revertido/);
 }finally{await ui.close();}
 const empty=await mount({rows:[]});try{assert.match(text(empty.renderer.toJSON()),/No hay eventos para mostrar/);}finally{await empty.close();}
});
test('Gerencia mantiene filtros y presentación original',async()=>{
 const ui=await mount({role:'GERENCIA'});try{
  const r=ui.renderer;assert.match(text(r.toJSON()),/Auditoría global/);
  assert.ok(r.root.findAllByType('label').some(l=>text(l).startsWith('Módulo')));
  assert.equal(r.root.findAllByProps({'aria-label':'Filtrar eventos financieros'}).length,0);
 }finally{await ui.close();}
});
