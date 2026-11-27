import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {ApiError} from '../src/auth/client.js';

let server,AuthProvider,Mermas;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Mermas}=await server.ssrLoadModule('/src/pages/Mermas.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const BASE='/api/inventario/mermas-bodega/';
const date='2026-11-25T20:33:59-03:00';
const pending={id:3,ambito:'BODEGA',articulo:6,articulo_nombre:'Aceite para compresor',articulo_codigo:'lub-001',cantidad:'1.000',unidad:'litro',tipo:'DANO',estado:'PENDIENTE',motivo:'Daño durante recepción',referencia:'Acta QA',informado_nombre:'Bodega QA',creado_en:date,decidido_nombre:null,decidido_en:null,motivo_decision:'',costo_unitario_neto:null,importe_perdida:null};
const approved={...pending,id:1,articulo_nombre:'Aislación elastomérica',articulo_codigo:'ais-001',cantidad:'3.000',unidad:'m',estado:'APROBADA',decidido_nombre:'Finanzas QA',decidido_en:date,motivo_decision:'Verificado',costo_unitario_neto:'4200.00',importe_perdida:'12600.00'};
async function mount({uncertain=false}={}){
 const rows=[{...pending},{...approved}],calls=[],session={status:'authenticated',user:{id:2,username:'finanzas',role:'ADMINISTRATIVO_FINANZAS'}};
 let lost=uncertain,commits=0;
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  const method=opts.method||'GET';calls.push({path,method,body:opts.body});
  const url=new URL(path,'http://localhost');
  if(method==='POST'&&url.pathname===BASE+'3/decidir/'){
   const r=rows[0];
   if(r.estado==='PENDIENTE'){commits++;const yes=opts.body.decision==='APROBAR';Object.assign(r,{estado:yes?'APROBADA':'RECHAZADA',decidido_nombre:'Finanzas QA',decidido_en:date,motivo_decision:opts.body.motivo,costo_unitario_neto:yes?'18500.00':null,importe_perdida:yes?'18500.00':null});}
   if(lost){lost=false;throw new ApiError(503,'Sin respuesta');}
   return {...r};
  }
  if(url.pathname===BASE){
   const state=url.searchParams.get('estado'),search=url.searchParams.get('buscar');
   const results=rows.filter(r=>(!state||r.estado===state)&&(!search||r.articulo_codigo.includes(search)||r.articulo_nombre.toLowerCase().includes(search.toLowerCase())));
   return {count:results.length,next:null,previous:null,results:results.map(r=>({...r})),resumen:{pendientes:rows.filter(r=>r.estado==='PENDIENTE').length,aprobadas:rows.filter(r=>r.estado==='APROBADA').length,rechazadas:rows.filter(r=>r.estado==='RECHAZADA').length,perdida_neta:rows[0].estado==='APROBADA'?'31100.00':'12600.00'}};
  }
  const r=rows.find(r=>url.pathname===BASE+r.id+'/');
  if(r)return {...r,historial:[{id:1,tipo:'CREACION',actor:52,motivo:r.motivo,creado_en:date},...(r.estado==='PENDIENTE'?[]:[{id:2,tipo:r.estado==='APROBADA'?'APROBACION':'RECHAZO',actor:2,motivo:r.motivo_decision,creado_en:date}])]};
  throw Error('Ruta no prevista: '+path);
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Mermas)));await flush();});
 return {renderer,calls,commits:()=>commits,close:()=>act(async()=>renderer.unmount())};
}
const click=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
const change=async(r,label,value)=>{const l=r.root.findAllByType('label').find(l=>text(l).startsWith(label));assert.ok(l,label);const c=l.findAll(n=>['input','select','textarea'].includes(n.type))[0];await act(async()=>{c.props.onChange({target:{value}});await flush();});};
const submit=async(r,label)=>{const f=r.root.findByProps({'aria-label':label});await act(async()=>{await f.props.onSubmit({preventDefault(){}});await flush();});};
test('AF: totales globales, búsqueda, ficha y estados vacíos',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/12\.600/);assert.match(body(),/Aceite para compresor/);assert.doesNotMatch(body(),/ID de artículo|Ámbito/);
  await click(r,'Rechazadas');assert.match(body(),/No hay resultados/);assert.match(body(),/12\.600/);
  await click(r,'Todas');await change(r,'Buscar material','ais-001');await submit(r,'Buscar mermas');assert.doesNotMatch(body(),/Aceite para compresor/);
  await click(r,'Ver detalle');assert.match(body(),/4\.200/);assert.match(body(),/Merma aprobada/);assert.doesNotMatch(body(),/Aprobar merma|Rechazar merma/);
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('AF: decisión incierta repite exclusivamente la misma UUID y confirma estado',async()=>{
 const ui=await mount({uncertain:true}),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  await click(r,'Revisar');assert.match(body(),/Se determina al aprobar/);
  await click(r,'Aprobar merma');await change(r,'Motivo de la decisión','Pérdida verificada');await submit(r,'Confirmar decisión de merma');
  assert.match(body(),/La decisión no pudo confirmarse/);await click(r,'Confirmar decisión pendiente');
  const writes=ui.calls.filter(c=>c.method==='POST');assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body);assert.equal(ui.commits(),1);
  assert.match(body(),/18\.500/);assert.match(body(),/Decisión registrada y confirmada/);assert.doesNotMatch(body(),/Confirmar aprobación/);
 }finally{await ui.close();}
});
test('AF: rechazo explícito sin pérdida registrada',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  await click(r,'Revisar');await click(r,'Rechazar merma');await change(r,'Motivo de la decisión','Reporte no corresponde');await submit(r,'Confirmar decisión de merma');
  assert.equal(ui.calls.find(c=>c.method==='POST').body.decision,'RECHAZAR');assert.match(body(),/Sin pérdida registrada por esta merma/);assert.match(body(),/Merma rechazada/);
 }finally{await ui.close();}
});
