import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';

let server,AuthProvider,Inventario;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=node=>typeof node==='string'?node:(node?.children||[]).map(text).join('');
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Inventario}=await server.ssrLoadModule('/src/pages/Inventario.jsx'));
});
test.after(async()=>{await server.close();});
test('Inventario gerencial: indicadores globales, filtros y mermas sin duplicar pérdidas',async()=>{
 const calls=[],summary={valor_stock_valorado:'1250.50',sin_stock:1,pendientes_valoracion:1,mermas_bodega_neto:'100.00',mermas_obra_informativo:'75.00',mermas_bodega:1,mermas_obra:1,mermas_sin_valor:0,mermas_pendientes:2,desde:'2026-11-01',hasta:'2026-11-25'};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts)=>{
  calls.push({path,opts});
  const url=new URL(path,'http://localhost');
  assert.equal(url.pathname,'/api/inventario/supervision-gerencial/');
  const results=url.searchParams.get('seccion')==='mermas'?[{id:1,nombre:'Manguera',codigo:'m-01',ambito:'BODEGA',obra:null,cantidad:'1.000',unidad:'m',tipo:'DANO',fecha:'2026-11-25T12:00:00Z',valor_neto:'100.00'}]:[{id:1,nombre:'Manguera',codigo:'m-01',unidad:'m',activo:true,saldo:'0.000',valor_neto:'0.00',pendiente_valoracion:false}];
  return {count:results.length,results,next:null,previous:null,resumen:summary};
 }};
 const session={status:'authenticated',user:{id:1,username:'G',role:'GERENCIA'}};
 let renderer;
 try{
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Inventario)));await flush();});
  const root=renderer.root;
  assert.equal(calls.length,1);
  assert.match(text(renderer.toJSON()),/\$1\.250,50/);
  assert.match(text(renderer.toJSON()),/\$100/);
  assert.match(text(renderer.toJSON()),/\$75/);
  assert.doesNotMatch(text(renderer.toJSON()),/Autorizaciones de entrega|Nuevo artículo|Registrar ingreso/);
  const click=async(label)=>{const button=root.findAllByType('button').find(b=>text(b).startsWith(label));assert.ok(button,label);await act(async()=>{button.props.onClick();await flush();});};
  await click('Materiales sin stock');assert.match(calls.at(-1).path,/filtro=sin_stock/);
  await click('Mermas de bodega del mes');assert.match(calls.at(-1).path,/seccion=mermas&filtro=bodega/);
  assert.ok(root.findByProps({'aria-label':'Mermas aprobadas'}));
  assert.equal(root.findAllByProps({'aria-label':'Paginación de inventario'}).length,0);
  assert.ok(calls.every(c=>!c.opts.method||c.opts.method==='GET'));
 }finally{if(renderer)await act(async()=>renderer.unmount());}
});
