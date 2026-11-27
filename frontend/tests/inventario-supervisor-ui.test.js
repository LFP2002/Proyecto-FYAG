import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
let server,AuthProvider,Inventario;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Inventario}=await server.ssrLoadModule('/src/pages/Inventario.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const ROOT='/api/inventario/', article={id:4,codigo:'lub-001',nombre:'Aceite para compresor',unidad:'litro',descripcion:'Lubricante',activo:true};
const stock={articulo:4,codigo:article.codigo,unidad:article.unidad,saldo:'10.500'};
const move={id:2,articulo:4,tipo:'SALIDA',cantidad:'2.500',saldo_anterior:'13.000',saldo_posterior:'10.500',referencia:'OT-5',motivo:'Despacho',actor:8,creado_en:'2026-11-25T20:33:59-03:00'};
const auth={id:9,articulo:4,obra:3,cantidad:'5.000',unidad:'litro',referencia:'OT-5',motivo:'Material de obra',actor:2,creado_en:move.creado_en};
const paged=results=>({count:results.length,results,next:null,previous:null});
async function mount(){
 const calls=[],session={status:'authenticated',user:{id:2,username:'supervisor',role:'SUPERVISOR_OBRAS'}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET'});const u=new URL(path,'http://localhost');
  switch(u.pathname){
   case ROOT+'articulos/':return paged(!u.searchParams.get('buscar')||article.nombre.includes(u.searchParams.get('buscar'))?[article]:[]);
   case ROOT+'articulos/4/':return article;
   case ROOT+'existencias/':return paged([stock]);
   case ROOT+'movimientos/':return paged([move]);
   case ROOT+'autorizaciones-entrega/':return paged([auth]);
   case ROOT+'entregas/':return paged([{...auth,costo_unitario_neto:'500.00'}]);
   case ROOT+'autorizaciones-devolucion/':return paged([{...auth,cantidad_recibible_efectiva:'1.500',entrega:2}]);
   default:throw Error('Ruta inesperada '+path);
  }
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Inventario)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
async function click(r,label){const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);assert.ok(!b.props.disabled,label);await act(async()=>{b.props.onClick();await flush();});}
test('Supervisor consulta materiales, stock, movimientos y autorizaciones sin funciones de Bodega o Finanzas',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/Inventario y bodega/);assert.match(body(),/Aceite para compresor/);
  assert.doesNotMatch(body(),/Registrar ingreso|Valorizar ingreso|Despachar material|Nuevo artículo/);
  assert.doesNotMatch(body(),/Autorizar entrega|Autorizar devolución|Operaciones de materiales/);
  assert.equal(r.root.findAllByProps({'aria-labelledby':'inventory-operations-title'}).length,0);
  assert.equal(r.root.findAllByProps({'aria-label':'Paginación de inventario'}).length,0);
  await click(r,'Ver detalle');assert.match(body(),/Existencias actuales/);assert.match(body(),/10,5 litro/);
  assert.ok(ui.calls.some(c=>c.path===ROOT+'existencias/?articulo=4'));
  await click(r,'Ver movimientos');assert.ok(ui.calls.some(c=>c.path.includes('movimientos/?page=1&articulo=4')));
  assert.match(body(),/Aceite para compresor/);assert.match(body(),/−2,5 litro/);
  await click(r,'Ver detalle');assert.match(body(),/Stock anterior/);assert.match(body(),/13 litro/);
  await click(r,'Volver al listado');await click(r,'Autorizaciones de devolución');assert.match(body(),/1,5 litro/);
  await click(r,'Entregas');await click(r,'Ver detalle');assert.match(body(),/Costo unitario neto registrado/);
  assert.doesNotMatch(body(),/Autorizar entrega|Autorizar devolución|Operaciones de materiales/);
  assert.ok(ui.calls.every(c=>c.method==='GET'&&!/finanzas\/|supervision-gerencial\/|bodega-operativa\//.test(c.path)));
 }finally{await ui.close();}
});
test('Supervisor usa búsqueda de catálogo real, estado vacío y limpiar filtros',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  await act(async()=>r.root.findByProps({'aria-label':'Buscar artículo'}).props.onChange({target:{value:'Inexistente'}}));
  const form=r.root.findAllByType('form').find(f=>f.props.className==='si-toolbar');
  await act(async()=>{form.props.onSubmit({preventDefault(){}});await flush();});
  assert.ok(ui.calls.some(c=>c.path.includes('buscar=Inexistente')));
  assert.match(text(r.toJSON()),/No hay resultados/);
  await click(r,'Quitar filtros');assert.match(text(r.toJSON()),/Aceite para compresor/);
 }finally{await ui.close();}
});
