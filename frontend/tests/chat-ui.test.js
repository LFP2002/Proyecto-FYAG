import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';

let server, AuthProvider, Chat;
const previous = {};
test.before(async () => {
  server = await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
  ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({default:Chat}=await server.ssrLoadModule('/src/pages/Chat.jsx'));
  for(const key of ['location','WebSocket'])previous[key]=Object.getOwnPropertyDescriptor(globalThis,key);
  Object.defineProperty(globalThis,'location',{configurable:true,value:{protocol:'http:',hostname:'localhost',port:'5173'}});
  Object.defineProperty(globalThis,'WebSocket',{configurable:true,value:class {close(){} send(){}}});
});
test.after(async()=>{
  for(const key of ['location','WebSocket']){if(previous[key])Object.defineProperty(globalThis,key,previous[key]);else delete globalThis[key];}
  await server.close();
});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=node=>typeof node==='string'?node:(node?.children||[]).map(text).join('');
const now=new Date().toISOString(), expires=new Date(Date.now()+86400000).toISOString();
const self={id:9,nombre:'Finanzas',rol:'ADMINISTRATIVO_FINANZAS'};
const ana={id:10,nombre:'Ana Pérez',rol:'SUPERVISOR_OBRAS'};
const jose={id:11,nombre:'José Soto',rol:'BODEGUERO'};
const conv=id=>({id,tipo:'DIRECTA',titulo:'',creador:9,creado_en:now,no_leidos:1});
const msg=(id,conversation,author,body)=>({id,conversacion:conversation,autor:author,texto:body,creado_en:now,vence_en:expires,archivo:null,clave_idempotencia:'qa'});
const page=results=>({count:results.length,next:null,previous:null,results});
async function mount(overrides={}){
  const calls=[], conversations=[conv(1),conv(2)];
  const request=async(path,options={})=>{
    calls.push({path,options});
    if(overrides[path])return overrides[path](options);
    if(path==='/api/chat/conexion/')return {ticket:'qa-ticket'};
    if(path==='/api/chat/conversaciones/?page=1')return page(conversations);
    if(path==='/api/chat/conversaciones/1/')return {...conv(1),participantes:[self,ana],ultimo_leido_mensaje_id:null};
    if(path==='/api/chat/conversaciones/2/')return {...conv(2),participantes:[self,jose],ultimo_leido_mensaje_id:null};
    if(path==='/api/chat/conversaciones/1/mensajes/')return {results:[msg(21,1,10,'Hola Ana')],siguiente_antes_id:null};
    if(path==='/api/chat/conversaciones/2/mensajes/')return {results:[msg(22,2,11,'Hola José')],siguiente_antes_id:null};
    if(path.endsWith('/leido/'))return {ultimo_leido_mensaje_id:options.body.ultimo_mensaje_id};
    throw Error('Unexpected '+path);
  };
  const session={status:'authenticated',user:{id:9,username:'qa',email:'qa@example.test',role:self.rol}};
  const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};
  let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Chat)));await flush();});
  return {renderer,calls};
}
async function select(renderer,name){
  const button=renderer.root.findAllByType('button').find(b=>b.props.className?.startsWith('chat-conv')&&text(b).includes(name));
  assert.ok(button,'Conversación no encontrada: '+name);
  await act(async()=>{button.props.onClick();await flush();});
}

test('Chat muestra nombres reales y marca lectura con el contrato actual',async()=>{
  const {renderer,calls}=await mount();
  try{
    await select(renderer,'Ana Pérez');
    assert.match(text(renderer.toJSON()),/Hola Ana/);
    assert.ok(calls.some(c=>c.path==='/api/chat/conversaciones/1/leido/'&&c.options.body.ultimo_mensaje_id===21));
    assert.ok(calls.filter(c=>c.path.endsWith('/leido/')).every(c=>!Object.hasOwn(c.options.body,'ultimo_leido_mensaje_id')));
  }finally{await act(async()=>renderer.unmount());}
});
test('Chat descarta respuestas tardías al cambiar de conversación',async()=>{
  let resolveOld;
  const delayed=new Promise(resolve=>{resolveOld=resolve;});
  const {renderer,calls}=await mount({'/api/chat/conversaciones/1/mensajes/':()=>delayed});
  try{
    await select(renderer,'Ana Pérez');
    await select(renderer,'José Soto');
    await act(async()=>{resolveOld({results:[msg(21,1,10,'Mensaje atrasado')],siguiente_antes_id:null});await flush();});
    assert.match(text(renderer.toJSON()),/Hola José/);
    assert.doesNotMatch(text(renderer.toJSON()),/Mensaje atrasado/);
    assert.ok(!calls.some(c=>c.path==='/api/chat/conversaciones/1/leido/'));
  }finally{await act(async()=>renderer.unmount());}
});
