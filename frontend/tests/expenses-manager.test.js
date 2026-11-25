import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {paginated} from './helpers/finance-contract.js';

let server,AuthProvider,Egresos,safePage;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Egresos}=await server.ssrLoadModule('/src/pages/Egresos.jsx'));
 ({safePage}=await server.ssrLoadModule('/src/integrations/useApi.js'));
});
test.after(async()=>{await server.close();});
const PATH='/api/finanzas/egresos/supervision-gerencial/';
const row={id:6,naturaleza:'REGISTRO_ADMINISTRATIVO_DINERO_PAGADO',moneda:'CLP',monto:'100.25',fecha_pago:'2026-11-24',categoria:'MATERIALES',concepto:'Accesorios eléctricos',beneficiario:'Distribuidora del Sur',medio:'TRANSFERENCIA',referencia_respaldo:'Comprobante 8105',observacion:'',obra:null,registrado_por:2,registrado_en:'2026-11-25T12:00:00Z',activo:true,anulado_por:null,anulado_en:null,motivo_anulacion:null,referencia_correccion:null};
const cancelled={...row,id:7,activo:false,anulado_por:2,anulado_en:'2026-11-25T13:00:00Z',motivo_anulacion:'Duplicado',referencia_correccion:'Rectificación'};
test('Egresos gerenciales: resumen global, filtro confirmado, flujo y detalle de solo lectura',async()=>{
 const calls=[];let fail=false;
 const session={status:'authenticated',user:{id:1,username:'G',role:'GERENCIA'}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET'});const url=new URL(path,'http://localhost'),q=url.searchParams;
  if(url.pathname===PATH){
   if(fail)throw Error('Fallo de consulta');
   const rows=q.get('vista')==='anulados'?[cancelled]:q.get('vista')==='todos'?[row,cancelled]:[row];
   const results=q.get('buscar')==='inexistente'?[]:rows;
   return {...paginated(results,url),resumen:{moneda:'CLP',desde:q.get('desde'),hasta:q.get('hasta'),total:'100.25',pagos:1,beneficiarios:1,mayor:'100.25',categorias:['MATERIALES','TRANSPORTE','SERVICIOS','ARRIENDO','OTROS'].map(c=>({categoria:c,monto:c==='MATERIALES'?'100.25':'0.00'})),ranking:[{beneficiario:row.beneficiario,monto:'100.25',pagos:1}]}};
  }
  if(url.pathname==='/api/finanzas/flujo-dinero/resumen/')return {periodo:{desde:q.get('desde'),hasta:q.get('hasta')},moneda:'CLP',naturaleza:'REGISTROS_ADMINISTRATIVOS_NO_CONCILIADOS',ingresos_recibidos:'50.00',egresos_pagados:'100.25',flujo_neto_registrado:'-50.25'};
  if(url.pathname==='/api/finanzas/egresos/6/')return row;
  if(url.pathname==='/api/finanzas/egresos/7/')return cancelled;
  if(url.pathname==='/api/finanzas/egresos/6/historial/')return {count:1,next:null,previous:null,results:[{id:1,egreso:6,tipo:'CREACION',actor:2,motivo:'',creado_en:row.registrado_en}]};
  throw Error('Ruta inesperada '+path);
 }};
 let renderer;
 try{
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Egresos)));await flush();});
  const root=renderer.root,body=()=>text(renderer.toJSON());
  const click=async(label)=>{const b=root.findAllByType('button').find(x=>text(x)===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
  assert.equal(calls.length,1);
  assert.match(body(),/\$100,25/);assert.match(body(),/100%/);
  assert.doesNotMatch(body(),/Registrar egreso pagado|REGISTRO_ADMINISTRATIVO_DINERO_PAGADO/);
  assert.equal(root.findByProps({id:'eg-filters'}).props.hidden,true);
  assert.equal(root.findAllByProps({'aria-label':'Paginación de egresos'}).length,0);
  await click('Ver flujo');assert.match(body(),/-\$50,25/);assert.match(body(),/no al saldo bancario/);
  await click('Filtros');assert.equal(root.findByProps({id:'eg-filters'}).props.hidden,false);
  const before=calls.length;
  await act(async()=>{root.findByProps({id:'eg-search'}).props.onChange({target:{value:'inexistente'}});await flush();});
  assert.equal(calls.length,before);
  await act(async()=>{root.findByProps({id:'eg-filters'}).props.onSubmit({preventDefault(){}});await flush();});
  assert.match(body(),/No hay egresos para estos filtros/);assert.match(body(),/\$100,25/);
  await click('Limpiar filtros');
  const n=calls.length;
  await act(async()=>{root.findByProps({'data-egreso':6}).props.onClick();await flush();});
  assert.equal(calls.length,n+1);assert.match(body(),/Comprobante 8105/);assert.match(body(),/24\/11\/2026/);
  await click('Historial');assert.match(body(),/Egreso registrado/);assert.match(body(),/Usuario #2/);
  assert.equal(root.findAllByProps({'aria-label':'Paginación del historial'}).length,0);
  await click('Volver al listado');await click('Anulados');
  await act(async()=>{root.findByProps({'data-egreso':7}).props.onClick();await flush();});
  assert.match(body(),/Monto anulado/);assert.match(body(),/Duplicado/);
  await click('Volver al listado');fail=true;await click('Actualizar');
  assert.match(body(),/Fallo de consulta/);assert.equal(root.findAllByProps({'data-egreso':7}).length,0);
  assert.ok(calls.every(c=>c.method==='GET'));
 }finally{if(renderer)await act(async()=>renderer.unmount());}
});
test('Paginación de supervisión de egresos rechaza parámetros manipulados',()=>{
 const f={desde:'2026-11-01',hasta:'2026-11-25',vista:'activos',buscar:'obra'};
 const link=PATH+'?'+new URLSearchParams({...f,page:2});
 assert.equal(safePage(link,PATH,f),2);
 assert.throws(()=>safePage(link+'&activo=false',PATH,f));
 assert.throws(()=>safePage(link.replace('buscar=obra','buscar=otro'),PATH,f));
 assert.throws(()=>safePage(link.replace('2026-11-25','2026-02-30'),PATH));
});
