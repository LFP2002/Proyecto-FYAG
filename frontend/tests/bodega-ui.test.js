import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {amount,preview} from '../src/bodega/domain.js';
let server,AuthProvider,AppProvider,App;
before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({AppProvider}=await server.ssrLoadModule('/src/context/AppContext.jsx'));
 ({default:App}=await server.ssrLoadModule('/src/app.jsx'));
});
after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n.children||[]).map(text).join('');
const material={id:1,articulo:1,codigo:'tub-001',nombre:'Tubería',unidad:'m',saldo:'12.000',activo:true,descripcion:'Material'};
const auth={...material,id:15,tipo:'AUTORIZACION_ENTREGA',obra:'OB-000006',cantidad:'2.000',ejecutada:'0.000',pendiente:'2.000',maximo:'2.000',bloqueo:null};
const page=results=>({count:results.length,results,next:null,previous:null});
test('Cantidades chilenas sin redondeo y vista previa exacta',()=>{
 assert.equal(amount('70.000','m'),'70 m');
 assert.equal(amount('0.125','kg'),'0,125 kg');
 assert.equal(preview({kind:'ENTREGA',row:auth,cantidad:'1,125'}).saldo,'10.875');
 assert.equal(preview({kind:'ENTREGA',row:auth,cantidad:'2.001'}),null);
 assert.equal(preview({kind:'INGRESO',row:{saldo:'999999999.999'},cantidad:'0.001'}),null);
 assert.equal(preview({kind:'ENTREGA',row:{...auth,bloqueo:'Sin stock'},cantidad:'1'}),null);
});
test('Bodega: menú propio, despacho desde autorización y una sola escritura',async()=>{
 const calls=[];let delivered=false;
 const session={status:'authenticated',user:{id:9,username:'bodega',email:'bodega@example.test',role:'BODEGUERO'}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET',body:opts.body});
  if(opts.method==='POST'){delivered=true;return {id:20};}
  const p=new URL(path,'http://localhost').searchParams,section=p.get('seccion');
  if(section==='resumen')return {materiales:1,sin_stock:0,entregas:delivered?0:1,devoluciones:0,faltantes:[],pendientes:delivered?[]:[auth],retornos:[]};
  if(section==='entregas')return page(delivered?[]:[auth]);
  if(section==='inventario')return page([material]);
  throw Error(path);
 }};
 let renderer;
 const click=async(label)=>{const b=renderer.root.findAllByType('button').find(b=>text(b).trim()===label||b.props['aria-label']===label);assert.ok(b,label);assert.equal(!!b.props.disabled,false);await act(async()=>{b.props.onClick();await flush();});};
 try{
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(AppProvider,null,React.createElement(App))));await flush();});
  assert.deepEqual(renderer.root.findByProps({id:'fyag-modules-nav'}).findAllByType('button').map(text),['Resumen de bodega','Inventario','Movimientos','Entregas','Devoluciones','Mermas','Chat interno']);
  await click('Entregas');await click('Despachar');
  const label=renderer.root.findAllByType('label').find(x=>text(x).startsWith('Cantidad'));
  await act(async()=>label.findByType('input').props.onChange({target:{value:'2'}}));
  assert.match(text(renderer.root),/10 m/);
  await act(async()=>{await renderer.root.findByProps({className:'bodega-form'}).props.onSubmit({preventDefault(){}});await flush();});
  const writes=calls.filter(c=>c.method==='POST');
  assert.equal(writes.length,1);assert.equal(writes[0].body.autorizacion,15);assert.equal(writes[0].body.cantidad,'2.000');
  assert.match(text(renderer.root),/No hay autorizaciones pendientes/);
  await click('Inventario');assert.match(text(renderer.root),/Tubería/);
 }finally{if(renderer)await act(async()=>renderer.unmount());}
});
