import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';

let server,AuthProvider,Presupuestos;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=node=>typeof node==='string'?node:(node?.children||[]).map(text).join('');
test.before(async()=>{
  server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
  ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({default:Presupuestos}=await server.ssrLoadModule('/src/pages/Presupuestos.jsx'));
});
test.after(async()=>{await server.close();});
const budget={id:66,codigo:'PRE-000066',cliente:1,descripcion:'Servicio',estado:'BORRADOR',monto_neto:'45300.00',creado_por:3,creado_en:'2026-11-22T12:00:00Z',items:[]};
async function mount(role){
  const calls=[];
  const request=async path=>{
    calls.push(path);
    if(path==='/api/clientes/')return [{id:1,nombre_legal:'Cliente de prueba',activo:true}];
    if(path==='/api/presupuestos/?page=1')return {count:2,previous:null,next:'/api/presupuestos/?page=2',results:[{...budget,id:65,codigo:'PRE-000065'}]};
    if(path==='/api/presupuestos/?page=2')return {count:2,previous:'/api/presupuestos/',next:null,results:[budget]};
    if(path==='/api/presupuestos/66/')return budget;
    if(path==='/api/presupuestos/66/historial/?page=1')return {count:0,previous:null,next:null,results:[]};
    throw Error('Ruta inesperada '+path);
  };
  const session={status:'authenticated',user:{id:9,username:'Cuenta de prueba',role}};
  const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};
  let renderer;
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Presupuestos)));await flush();});
  return {renderer,calls};
}
async function click(root,label){
  const button=root.findAllByType('button').find(b=>text(b)===label);
  assert.ok(button,label);assert.ok(!button.props.disabled,label);
  await act(async()=>{await button.props.onClick();await flush();});
}
test('Presupuestos: detalle sustituye listado y conserva página y filtro al volver',async()=>{
  const {renderer,calls}=await mount('GERENCIA');
  try{
    const root=renderer.root;
    await click(root,'Siguiente');
    await act(async()=>{root.findByProps({id:'budget-filter'}).props.onChange({target:{value:'BORRADOR'}});await flush();});
    await click(root,'Ver presupuesto');
    assert.equal(root.findAllByProps({'aria-label':'Listado de presupuestos'}).length,0);
    assert.equal(root.findByProps({id:'budget-items'}).props.hidden,false);
    assert.equal(root.findByProps({id:'budget-history'}).props.hidden,true);
    assert.equal(root.findAllByType('button').some(b=>text(b)==='Editar cabecera'),false);
    const before=calls.length;
    await click(root,'Historial comercial');
    assert.equal(root.findByProps({id:'budget-items'}).props.hidden,true);
    assert.equal(root.findByProps({id:'budget-history'}).props.hidden,false);
    assert.equal(calls.length,before);
    await click(root,'Volver al listado');
    assert.equal(root.findByProps({id:'budget-filter'}).props.value,'BORRADOR');
    assert.match(text(renderer.toJSON()),/PRE-000066/);
    assert.equal(calls.filter(p=>p==='/api/presupuestos/?page=2').length,1);
  }finally{await act(async()=>renderer.unmount());}
});
test('Presupuestos: Finanzas conserva edición y puede cancelar antes de volver',async()=>{
  const {renderer}=await mount('ADMINISTRATIVO_FINANZAS');
  try{
    const root=renderer.root;
    await click(root,'Siguiente');await click(root,'Ver presupuesto');
    await click(root,'Editar cabecera');
    assert.ok(root.findAllByType('form').length);
    assert.equal(root.findAllByType('button').find(b=>text(b)==='Volver al listado').props.disabled,true);
    await click(root,'Cancelar');await click(root,'Volver al listado');
    assert.equal(root.findAllByProps({'aria-label':'Listado de presupuestos'}).length,1);
  }finally{await act(async()=>renderer.unmount());}
});
