import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import viteConfig from '../vite.config.js';
const read=path=>readFile(new URL('../src/'+path,import.meta.url),'utf8');
test('Pantallas diferidas; autenticación y clave compartida de Bodega conservadas',async()=>{
 const app=await read('app.jsx');
 assert.doesNotMatch(app,/^import .* from ['"]\.\/pages\//m);
 for(const name of ["Clientes","Presupuestos","Obras","MisTurnos","Usuarios","Alertas","Cobranzas","Dashboard","Reportes","Auditoria","Inventario","Solicitudes","Mermas","BodegaMermas","TecnicoMateriales","Egresos","Chat","Bodega"]){
  assert.ok(app.includes("const "+name+" = lazy(() => import('./pages/"+name+".jsx'));"),name);
 }
 assert.ok(app.indexOf("status !== 'authenticated'")<app.indexOf('const Page ='));
 assert.match(app,/warehouse\?'bodega':mod/);
 assert.match(app,/<ModuleBoundary key=\{pageKey\}><Suspense fallback=\{<ModuleLoading\/>\}><Page key=\{pageKey\}/);
 assert.match(app,/const TecnicoMermas=\(\)=> <TecnicoMateriales loss\/>/);
 assert.equal(viteConfig.build.cssCodeSplit,false);
 assert.equal(viteConfig.build.chunkSizeWarningLimit,undefined);
});
test('Estilos de módulo globales antes de reglas transversales',async()=>{
 const entry=await read('main.jsx');
 for(const path of ["pages/tecnico.css","pages/supervisor-obras.css","components/adjuntos.css","pages/obras-finanzas.css","pages/obras-gerencia.css","pages/alertas-gerencia.css","pages/reportes-gerencia.css","pages/inventario-gerencia.css","pages/inventario-finanzas.css","pages/inventario-supervisor.css","pages/mermas-finanzas.css","pages/egresos-gerencia.css","pages/egresos-finanzas.css","pages/bodega.css"]){
  const i=entry.indexOf("import './styles/"+path+"';");
  assert.ok(i>=0&&i<entry.indexOf("import './styles/dark-mode.css';"),path);
 }
});
test('Carga pendiente y fallo de módulo tienen recuperación accesible',async()=>{
 const server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 let renderer;
 const originalError=console.error;
 try {
  const {default:Boundary,ModuleLoading}=await server.ssrLoadModule('/src/components/ModuleBoundary.jsx');
  await act(async()=>{renderer=Renderer.create(React.createElement(ModuleLoading));});
  assert.equal(renderer.root.findByProps({role:'status'}).children[0],'Cargando módulo…');
  function Broken(){throw Error('fallo simulado');}
  console.error=()=>{};
  await act(async()=>{renderer.update(React.createElement(Boundary,{key:'a'},React.createElement(Broken)));});
  assert.equal(renderer.root.findByProps({role:'alert'}).findByType('h2').children[0],'No fue posible cargar este módulo');
  assert.equal(renderer.root.findByType('button').props.type,'button');
  await act(async()=>{renderer.update(React.createElement(Boundary,{key:'b'},React.createElement('p',null,'Otro módulo')));});
  assert.equal(renderer.root.findByType('p').children[0],'Otro módulo');
 }finally{
  console.error=originalError;
  if(renderer)await act(async()=>renderer.unmount());
  await server.close();
 }
});
