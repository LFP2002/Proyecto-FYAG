import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {payload,path,readPage} from '../src/obras/materialesTecnico.js';
import {duration} from '../src/obras/tecnicoDomain.js';

let server,AuthProvider,AppProvider,App;
before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({AppProvider}=await server.ssrLoadModule('/src/context/AppContext.jsx'));
 ({default:App}=await server.ssrLoadModule('/src/app.jsx'));
});
after(async()=>{await server?.close();});
const work={id:3,codigo:'OB-000003',cliente:'Cliente técnico',categoria:'Mantención',estado:'EN_PROCESO'};
const mat={id:7,codigo:'tub-001',nombre:'Tubería de cobre',unidad:'m'};
const delivery={id:12,obra:work,material:mat,unidad:'m',cantidad:'12.000',devuelta:'2.000',mermas_aprobadas:'1.000',remanente:'9.000',creado_en:'2026-11-25T23:33:00Z'};
const baseRow={id:4,obra:work,material:mat,unidad:'m',cantidad:'0.750',estado:'PENDIENTE',creado_en:'2026-11-25T23:33:00Z',motivo_decision:'',decidido_por:null,decidido_en:null};
const history=[{id:1,tipo:'CREACION',actor:'Técnico',motivo:'Informe de prueba',creado_en:baseRow.creado_en}];
const lossRow={...baseRow,tipo:'CORTE_NO_REUTILIZABLE',entrega:12,motivo:'Corte sobrante',actividad:'Instalación',referencia:''};
const solRow={...baseRow,justificacion:'Material adicional',cantidad_aprobada:null,autorizacion:null};
const page=results=>({count:results.length,results,next:null,previous:null});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n.children||[]).map(text).join('');
const form={work,material:delivery,cantidad:'0,75',tipo:'CORTE_NO_REUTILIZABLE',motivo:'Corte sobrante',actividad:'Instalación',referencia:'',key:'test-key'};
test('Técnico: decimal exacto, límite original y entrega de la obra seleccionada',()=>{
 assert.deepEqual(payload(form,true),{entrega:12,cantidad:'0.750',tipo:'CORTE_NO_REUTILIZABLE',motivo:'Corte sobrante',actividad:'Instalación',referencia:'',clave_idempotencia:'test-key'});
 assert.equal(payload({...form,cantidad:'12.001'},true),null);
 assert.ok(payload({...form,cantidad:'10.000'},true)); // remanente informativo: decisión del supervisor
 assert.equal(payload({...form,work:{...work,id:99}},true),null);
 assert.throws(()=>readPage(page([delivery]),'entregas',99));
 assert.equal(duration({duracion_segundos:'18000.000000'}),'5 h');
 assert.equal(duration({duracion_segundos:'18060.000000'}),'5 h 1 min');
 assert.equal(duration({duracion_segundos:'60.000000'}),'1 min');
});
async function mount({uncertain=false}={}){
 const calls=[];let saved=false;let postCount=0;
 const session={status:'authenticated',user:{id:8,username:'tecnico',email:'tec@example.test',role:'TECNICO'}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(url,opts={})=>{
  calls.push({url,method:opts.method||'GET',body:opts.body});
  if(opts.method==='POST'){
   postCount++;saved=true;
   if(uncertain&&postCount===1)throw Object.assign(Error('Sin respuesta'),{status:503});
   return {id:4};
  }
  const p=new URL(url,'http://localhost').searchParams,section=p.get('seccion');
  if(url.startsWith('/api/obras/mis-obras/'))return page([]);
  if(section==='mermas')return page(saved?[lossRow]:[]);
  if(section==='solicitudes')return page(saved?[solRow]:[]);
  if(section==='obras')return page([work]);
  if(section==='catalogo')return page([mat]);
  if(section==='entregas'){assert.equal(p.get('obra'),'3');return page([delivery]);}
  if(section==='merma_detalle')return {...lossRow,historial:history};
  if(section==='solicitud_detalle')return {...solRow,historial:history};
  if(section==='confirmacion')return {id:saved?4:null};
  throw Error(url);
 }};
 let view;
 await act(async()=>{view=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(AppProvider,null,React.createElement(App))));await flush();});
 return {view,calls};
}
async function click(view,label){
 const b=view.root.findAllByType('button').find(x=>text(x).trim()===label||x.props['aria-label']===label);
 assert.ok(b,label);assert.ok(!b.props.disabled,label);
 await act(async()=>{b.props.onClick();await flush();});
}
async function choose(view,label){
 await click(view,label);
 const b=view.root.findAllByProps({className:'tec-picker-option'})[0];assert.ok(b,label);
 await act(async()=>{b.props.onClick();await flush();});
}
async function fill(view,label,value){
 const field=view.root.findAllByType('label').find(x=>text(x).startsWith(label));
 assert.ok(field,label);
 const control=field.findAllByType('input')[0]||field.findAllByType('textarea')[0];
 await act(async()=>control.props.onChange({target:{value}}));
}
async function submit(view){await act(async()=>{view.root.findByProps({className:'tec-material-form'}).props.onSubmit({preventDefault(){}});await flush();});}
test('Mermas: selección de obra y entrega, confirmación incierta sin duplicar POST',async()=>{
 const {view,calls}=await mount({uncertain:true});
 try{
  await click(view,'Mermas');assert.match(text(view.root),/Todavía no tienes mermas/);assert.equal(view.root.findAllByType('table').length,0);
  await click(view,'Informar merma');await choose(view,'Obra');await choose(view,'Material entregado');
  assert.match(text(view.root),/Remanente consultado9 m/);
  await fill(view,'Cantidad','0,75');await fill(view,'Motivo','Corte sobrante');await fill(view,'Actividad realizada','Instalación');
  await submit(view);assert.equal(calls.filter(c=>c.method==='POST').length,1);
  assert.match(text(view.root),/Verificar registro/);assert.ok(view.root.findAllByType('button').find(b=>text(b).trim()==='Mis obras').props.disabled);
  await click(view,'Verificar registro');
  assert.equal(calls.filter(c=>c.method==='POST').length,1);
  assert.equal(calls.find(c=>c.method==='POST').body.entrega,12);
  assert.equal(calls.find(c=>c.method==='POST').body.cantidad,'0.750');
  assert.match(text(view.root),/Registro confirmado por el servidor/);
  assert.match(text(view.root),/En espera de revisión por el supervisor/);
  assert.doesNotMatch(text(view.root),/Decidir|Importe informativo/);
 }finally{await act(async()=>view.unmount());}
});
test('Solicitudes: formulario independiente, catálogo por nombre, una escritura y detalle',async()=>{
 const {view,calls}=await mount();
 try{
  await click(view,'Solicitudes');assert.match(text(view.root),/Todavía no tienes solicitudes/);
  await click(view,'Nueva solicitud');await choose(view,'Obra');await choose(view,'Material');
  await fill(view,'Cantidad','0,75');await fill(view,'Justificación','Material adicional');
  await submit(view);
  const writes=calls.filter(c=>c.method==='POST');assert.equal(writes.length,1);
  assert.equal(writes[0].url,'/api/inventario/solicitudes-materiales/');
  assert.equal(writes[0].body.articulo,7);assert.equal(writes[0].body.obra,3);
  assert.match(text(view.root),/Solicitud enviada/);assert.match(text(view.root),/Tubería de cobre/);
  await click(view,'Volver a solicitudes');await click(view,'Ver detalle');
  assert.match(text(view.root),/Historial/);
 }finally{await act(async()=>view.unmount());}
});
