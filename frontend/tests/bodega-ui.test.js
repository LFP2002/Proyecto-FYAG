import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {amount,movementAmount,preview} from '../src/bodega/domain.js';
let server,AuthProvider,AppProvider,App,MovementTable;
before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({AppProvider}=await server.ssrLoadModule('/src/context/AppContext.jsx'));
 ({default:App}=await server.ssrLoadModule('/src/app.jsx'));
 ({MovementTable}=await server.ssrLoadModule('/src/pages/Bodega.jsx'));
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

test('Movimientos: unidades compactas, precisión y celdas numéricas uniformes',async()=>{
 assert.equal(movementAmount('20.000','litro'),'20 L');
 assert.equal(movementAmount('0.125','unidad'),'0,125 un.');
 assert.equal(movementAmount('1234.567','kg'),'1.234,567 kg');
 assert.equal(movementAmount('2.000','caja'),'2 caja');
 assert.equal(movementAmount(null,'litro'),'—');
 const common={...material,unidad:'litro',creado_en:'2026-11-25T23:33:54Z',referencia:'Recepción',motivo:'Motivo de prueba',actor:'bodega_qa'};
 const rows=[{...common,id:1,tipo:'INGRESO',cantidad:'20.000',saldo_anterior:'0.000',saldo_posterior:'20.000'},{...common,id:2,tipo:'SALIDA',cantidad:'0.125',saldo_anterior:'20.000',saldo_posterior:'19.875'},{...common,id:3,tipo:'DEVOLUCION',cantidad:'0.125',saldo_anterior:'19.875',saldo_posterior:'20.000'},{...common,id:4,tipo:'MERMA',cantidad:'1.000',saldo_anterior:'20.000',saldo_posterior:'19.000'}];
 let renderer;
 try{
  await act(async()=>{renderer=Renderer.create(React.createElement(MovementTable,{rows}));});
  const root=renderer.root,headers=root.findAllByType('th');
  assert.deepEqual(headers.filter(h=>h.props.className==='bodega-number-cell').map(text),['Cantidad','Stock anterior','Stock final']);
  const bodyRows=root.findByType('tbody').findAllByType('tr');
  assert.deepEqual(bodyRows.map(row=>row.findAllByType('td').filter(td=>td.props.className==='bodega-number-cell').map(text)),[['+20 L','0 L','20 L'],['−0,125 L','20 L','19,875 L'],['+0,125 L','19,875 L','20 L'],['−1 L','20 L','19 L']]);
  for(const [i,row] of bodyRows.entries()){
   const cells=row.findAllByType('td');
   assert.equal(cells[2].props.className,'bodega-number-cell');
   assert.equal(cells[2].findByType('span').props.className,i===0||i===2?'bodega-movement-in':'bodega-movement-out');
   assert.equal(cells[4].findByType('strong').type,'strong');
   assert.match(text(cells[6]),/RecepciónMotivo de pruebabodega_qa/);
  }
 }finally{if(renderer)await act(async()=>renderer.unmount());}
});
