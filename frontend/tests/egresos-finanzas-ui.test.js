import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {ApiError} from '../src/auth/client.js';

let server,AuthProvider,Egresos;
test.before(async()=>{
  server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
  ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({default:Egresos}=await server.ssrLoadModule('/src/pages/Egresos.jsx'));
});
test.after(async()=>{await server.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const BASE='/api/finanzas/egresos/';
const row={id:6,naturaleza:'REGISTRO_ADMINISTRATIVO_DINERO_PAGADO',moneda:'CLP',monto:'154000.00',fecha_pago:'2026-11-24',categoria:'MATERIALES',concepto:'Compra de accesorios',beneficiario:'Distribuidora Frío',medio:'TRANSFERENCIA',referencia_respaldo:'COMP-8105',observacion:'',obra:null,registrado_por:2,registrado_en:'2026-11-25T20:33:59-03:00',activo:true,anulado_por:null,anulado_en:null,motivo_anulacion:null,referencia_correccion:null};
const page=results=>({count:results.length,next:null,previous:null,results});
async function mount({uncertain=false}={}){
 const calls=[],rows=[{...row}],events=[{id:1,egreso:6,tipo:'CREACION',actor:2,motivo:'',creado_en:row.registrado_en}];
 const session={status:'authenticated',user:{id:2,username:'finanzas',role:'ADMINISTRATIVO_FINANZAS'}};
 let lost=uncertain,created=null;
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
   const method=opts.method||'GET';calls.push({path,method,body:opts.body,headers:opts.headers});const url=new URL(path,'http://localhost');
   if(method==='POST'&&url.pathname===BASE){if(!created){created={...row,...opts.body,id:7,monto:'150000.00'};rows.push(created);}if(lost){lost=false;throw new ApiError(503,'Respuesta no confirmada');}return {...created};}
   if(method==='POST'&&url.pathname===BASE+'6/anular/'){Object.assign(rows[0],{activo:false,anulado_por:2,anulado_en:row.registrado_en,motivo_anulacion:opts.body.motivo,referencia_correccion:opts.body.referencia_correccion});events.push({id:2,egreso:6,tipo:'ANULACION',actor:2,motivo:opts.body.motivo,creado_en:row.registrado_en});return {...rows[0]};}
   if(url.pathname===BASE)return {...page(rows.map(r=>({...r}))),resumen:{moneda:'CLP',total:'3989000.00',pagos:rows.filter(r=>r.activo).length}};
   if(url.pathname===BASE+'6/')return {...rows[0]};
   if(url.pathname===BASE+'7/')return {...created};
   if(url.pathname===BASE+'6/historial/')return page(events);
   if(url.pathname===BASE+'7/historial/')return page([{...events[0],egreso:7}]);
   if(url.pathname==='/api/finanzas/obras-resumen/')return page([{id:9,codigo:'OB-000009',cliente_nombre:'Frigorífico Portal'}]);
   if(url.pathname==='/api/finanzas/flujo-dinero/resumen/')return {moneda:'CLP',naturaleza:'REGISTROS_ADMINISTRATIVOS_NO_CONCILIADOS',periodo:{desde:url.searchParams.get('desde'),hasta:url.searchParams.get('hasta')},ingresos_recibidos:'100.00',egresos_pagados:'150.00',flujo_neto_registrado:'-50.00'};
   throw Error('Ruta no prevista: '+path);
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Egresos)));await flush();});
 return {renderer,calls,rows,close:()=>act(async()=>renderer.unmount())};
}
const click=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
const change=async(r,label,value)=>{const l=r.root.findAllByType('label').find(l=>text(l).startsWith(label));assert.ok(l,label);const c=l.findAll(n=>['input','select','textarea'].includes(n.type))[0];await act(async()=>{c.props.onChange({target:{value}});await flush();});};
const submit=async(r,label)=>{const f=r.root.findByProps({'aria-label':label});await act(async()=>{await f.props.onSubmit({preventDefault(){}});await flush();});};
test('Finanzas: egresos legibles, filtros globales, detalle y anulación contextual',async()=>{
 const ui=await mount(),r=ui.renderer,old=globalThis.confirm;globalThis.confirm=()=>true;
 try{
   assert.match(text(r.toJSON()),/\$3\.989\.000/);assert.match(text(r.toJSON()),/24\/11\/2026/);assert.doesNotMatch(text(r.toJSON()),/ID de obra|REGISTRO_ADMINISTRATIVO_DINERO_PAGADO|Anular egreso/);
   await change(r,'Buscar egreso','Distribuidora');await submit(r,'Filtros de egresos');
   assert.ok(ui.calls.some(c=>c.path.includes('buscar=Distribuidora')&&c.path.includes('resumen=true')));
   await click(r,'Ver detalle');assert.match(text(r.toJSON()),/Egreso registrado/);
   await click(r,'Anular egreso');await change(r,'Motivo','Error de registro');await change(r,'Referencia de corrección','RECT-1');await submit(r,'Anular egreso');
   assert.equal(ui.calls.filter(c=>c.method==='POST').length,1);assert.equal(ui.rows[0].activo,false);assert.match(text(r.toJSON()),/Egreso anulado/);
   assert.match(r.root.findAllByType('button').find(b=>text(b).trim()==='Volver a egresos').props.className,/eg-back/);
   await click(r,'Volver a egresos');await click(r,'Flujo de dinero');
   assert.match(text(r.toJSON()),/Selecciona un período/);assert.equal(ui.calls.some(c=>c.path.includes('/flujo-dinero/resumen/')),false);
   const f=r.root.findAllByType('form')[0];await act(async()=>{f.props.onSubmit({preventDefault(){}});await flush();});assert.match(text(r.toJSON()),/-\$50/);assert.doesNotMatch(text(r.toJSON()),/Selecciona un período/);
 }finally{globalThis.confirm=old;await ui.close();}
});
test('Alta con selector de obra conserva UUID y payload ante respuesta incierta',async()=>{
 const ui=await mount({uncertain:true}),r=ui.renderer;
 try{
   await click(r,'+ Registrar egreso');await change(r,'Monto pagado','150000');await change(r,'Fecha de pago','2026-01-01');await change(r,'Concepto','Compra');await change(r,'Beneficiario','Proveedor');await change(r,'Referencia del respaldo','COMP-2');
   await click(r,'Seleccionar obra');await click(r,'Seleccionar');assert.match(text(r.toJSON()),/OB-000009 · Frigorífico Portal/);
   await submit(r,'Registro de egreso');assert.match(text(r.toJSON()),/El registro no pudo confirmarse/);
   await click(r,'Confirmar registro pendiente');
   const writes=ui.calls.filter(c=>c.method==='POST');assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body);assert.deepEqual(writes[0].headers,writes[1].headers);assert.equal(writes[0].body.obra,9);
   assert.equal(ui.rows.length,2);assert.ok(ui.calls.some(c=>c.path===BASE+'7/'));assert.match(text(r.toJSON()),/\$150\.000/);
 }finally{await ui.close();}
});
