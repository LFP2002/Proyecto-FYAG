import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';

let server,AuthProvider,Auditoria;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Auditoria}=await server.ssrLoadModule('/src/pages/Auditoria.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const date='2026-11-25T20:33:59-03:00';
const base={id:'FINANZAS_EVENTO:8',evento_id:8,fuente:'FINANZAS_EVENTO',modulo:'FINANZAS',recurso_tipo:'DOCUMENTO',recurso_id:5,tipo:'DOCUMENTO_REVERTIDO',actor:2,actor_etiqueta:'Finanzas QA',actor_username:'finanzas',actor_identidad_origen:'ACTUAL',motivo:'Rectificación de datos comerciales',creado_en:date,datos_anteriores:{estado:'VIGENTE'},datos_nuevos:{estado:'REVERTIDO',motivo_reversion:'Rectificación de datos comerciales',referencia_rectificacion_externa:'Acta 5'}};
const payment={...base,id:'FINANZAS_EVENTO:7',evento_id:7,tipo:'PAGO_REGISTRADO',recurso_tipo:'PAGO',recurso_id:2,actor_identidad_origen:'HISTORICA',motivo:'',datos_anteriores:{},datos_nuevos:{monto:'447440.00',estado:'ACTIVO'}};
async function mount({role='ADMINISTRATIVO_FINANZAS',rows=[base,payment],paged=false}={}){
 const calls=[],session={status:'authenticated',user:{id:2,username:'finanzas',role}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET'});const u=new URL(path,'http://localhost');
  assert.equal(u.pathname,'/api/auditoria/eventos/');
  const cursor=u.searchParams.get('cursor');
  const items=rows.filter(r=>(!u.searchParams.get('tipo')||r.tipo===u.searchParams.get('tipo'))&&(!u.searchParams.get('recurso_tipo')||r.recurso_tipo===u.searchParams.get('recurso_tipo')));
  return {results:paged?(cursor?[payment]:[base]):items,next_cursor:paged&&!cursor?'cursor-opaco':null,has_more:paged&&!cursor,fecha_corte:date,zona_horaria:'America/Santiago'};
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Auditoria)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
const click=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
const change=async(r,label,value)=>{const l=r.root.findAllByType('label').find(l=>text(l).startsWith(label));assert.ok(l,label);const c=l.findAll(n=>['input','select'].includes(n.type))[0];await act(async()=>{c.props.onChange({target:{value}});await flush();});};
const submit=async(r,label)=>{const f=r.root.findByProps({'aria-label':label});await act(async()=>{f.props.onSubmit({preventDefault(){}});await flush();});};
const openDetail=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>b.props['aria-label']===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
test('Auditoría TI: recuperación excepcional muestra autoridad, operador y autorización',async()=>{
 const event={...base,id:'RECUPERACION_TI_EVENTO:8',fuente:'RECUPERACION_TI_EVENTO',modulo:'USUARIOS',recurso_tipo:'USUARIO',recurso_id:27,tipo:'RECUPERACION_TI_INFRA',actor:null,actor_etiqueta:'Operador de infraestructura',actor_username:null,actor_identidad_origen:'INFRAESTRUCTURA',motivo:'Incidente autorizado',datos_anteriores:{acceso_estado:'REQUIERE_TI'},datos_nuevos:{operador:'operador.qa',referencia:'AUT-027'}};
 const ui=await mount({role:'ADMINISTRADOR_TI',rows:[event]}),r=ui.renderer;
 try{
  await click(r,'Filtros');
  await change(r,'Fuente',event.fuente);
  await change(r,'Tipo',event.tipo);
  await act(async()=>{r.root.findByProps({id:'audit-filters'}).props.onSubmit({preventDefault(){}});await flush();});
  const query=new URL(ui.calls.at(-1).path,'http://localhost').searchParams;
  assert.equal(query.get('fuente'),event.fuente);
  assert.equal(query.get('tipo'),event.tipo);
  await openDetail(r,'Ver detalle de Recuperación TI por infraestructura Usuario #27');
  assert.match(text(r.toJSON()),/AutoridadOperador de infraestructura.*Operadoroperador\.qa.*Referencia de autorizaciónAUT-027.*Incidente autorizado.*Estado de acceso anteriorRequiere TI/);
 }finally{await ui.close();}
});
test('Auditoría TI: filtro y detalle de recuperación por titularidad del correo',async()=>{
 const recovery={...base,id:'RECUPERACION_CORREO_EVENTO:8',fuente:'RECUPERACION_CORREO_EVENTO',modulo:'USUARIOS',recurso_tipo:'USUARIO',recurso_id:27,tipo:'RECUPERACION_CORREO',actor:null,actor_etiqueta:'Titularidad del correo',actor_username:null,actor_identidad_origen:'TITULARIDAD_CORREO',motivo:'',datos_anteriores:{acceso_estado:'REQUIERE_TI'},datos_nuevos:{}};
 const ui=await mount({role:'ADMINISTRADOR_TI',rows:[recovery]}),r=ui.renderer;
 try{
  await click(r,'Filtros');
  await change(r,'Fuente',recovery.fuente);
  await change(r,'Tipo',recovery.tipo);
  await change(r,'Tipo de recurso','USUARIO');
  await change(r,'Recurso ID','27');
  await act(async()=>{r.root.findByProps({id:'audit-filters'}).props.onSubmit({preventDefault(){}});await flush();});
  const query=new URL(ui.calls.at(-1).path,'http://localhost').searchParams;
  assert.equal(query.get('fuente'),recovery.fuente);
  assert.equal(query.get('tipo'),recovery.tipo);
  assert.equal(query.get('recurso_tipo'),'USUARIO');
  assert.equal(query.get('recurso_id'),'27');
  assert.match(text(r.toJSON()),/Titularidad del correo/);
  assert.equal(r.root.findByType('time').props.dateTime,date);
  await openDetail(r,'Ver detalle de Recuperación por correo Usuario #27');
  assert.match(text(r.toJSON()),/Cuenta objetivoUsuario #27.*AutoridadTitularidad del correo.*Estado de acceso anteriorRequiere TI/);
  await click(r,'Volver al historial');
  assert.match(text(r.toJSON()),/Fuente: Recuperaciones por correo/);
 }finally{await ui.close();}
});
test('Auditoría TI: vencimiento del sistema y desbloqueo administrativo',async()=>{
 const common={...base,modulo:'USUARIOS',recurso_tipo:'USUARIO',recurso_id:27,datos_anteriores:{acceso_estado:'BLOQUEO_TEMPORAL'},datos_nuevos:{acceso_estado:'NORMAL'}};
 const expiration={...common,id:'EVENTO_ACCESO:8',fuente:'EVENTO_ACCESO',tipo:'EXPIRACION',actor:null,actor_etiqueta:'Sistema',actor_username:null,actor_identidad_origen:'SISTEMA',motivo:''};
 const reset={...common,id:'USUARIO_EVENTO:9',evento_id:9,fuente:'USUARIO_EVENTO',tipo:'REEMISION',actor_etiqueta:'TI QA',actor_username:'ti'};
 const ui=await mount({role:'ADMINISTRADOR_TI',rows:[expiration,reset]}),r=ui.renderer;
 try{
  await openDetail(r,'Ver detalle de Vencimiento del bloqueo Usuario #27');
  assert.match(text(r.toJSON()),/AutoridadSistema.*Estado de acceso anteriorBloqueo temporal.*Estado de acceso nuevoNormal/);
  await click(r,'Volver al historial');
  await openDetail(r,'Ver detalle de Reemisión de credencial Usuario #27');
  assert.match(text(r.toJSON()),/Estado de accesoBloqueo temporalNormal/);
 }finally{await ui.close();}
});
test('Auditoría AF: filtros reales, detalle de reversión y retorno a consulta',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/Auditoría financiera/);
  assert.equal(r.root.findAllByType('label').some(l=>text(l).startsWith('Módulo')),false);
  await change(r,'Tipo de evento','DOCUMENTO_REVERTIDO');
  await change(r,'Recurso','DOCUMENTO');await submit(r,'Filtrar eventos financieros');
  assert.ok(ui.calls.some(c=>c.path.includes('tipo=DOCUMENTO_REVERTIDO')&&c.path.includes('recurso_tipo=DOCUMENTO')));
  await openDetail(r,'Ver detalle de Documento revertido Documento #5');
  assert.match(body(),/Estado registrado/);assert.match(body(),/Vigente→Revertido/);
  assert.match(body(),/Modificado/);assert.match(body(),/Registrado/);assert.match(body(),/Identidad actual/);
  assert.match(body(),/Acta 5/);assert.doesNotMatch(body(),/Monto total registrado/);
  await click(r,'Volver al historial');assert.match(body(),/Filtros aplicados/);
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('Auditoría AF: importe histórico, cursor opaco y estados vacíos',async()=>{
 const ui=await mount({paged:true}),r=ui.renderer;
 try{
  await click(r,'Siguiente');assert.ok(ui.calls.some(c=>c.path.endsWith('?cursor=cursor-opaco')));
  await openDetail(r,'Ver detalle de Pago registrado Pago #2');
  const body=text(r.toJSON());assert.match(body,/Monto registrado/);assert.match(body,/447\.440/);assert.match(body,/Identidad registrada en el evento/);assert.match(body,/No se registró un motivo/);
  await click(r,'Volver al historial');await click(r,'Anterior');assert.match(text(r.toJSON()),/Documento revertido/);
 }finally{await ui.close();}
 const empty=await mount({rows:[]});try{assert.match(text(empty.renderer.toJSON()),/No hay eventos para mostrar/);}finally{await empty.close();}
});
test('Gerencia mantiene filtros y presentación original',async()=>{
 const ui=await mount({role:'GERENCIA'});try{
  const r=ui.renderer;assert.match(text(r.toJSON()),/Auditoría global/);
  assert.ok(r.root.findAllByType('label').some(l=>text(l).startsWith('Módulo')));
  assert.equal(r.root.findAllByProps({'aria-label':'Filtrar eventos financieros'}).length,0);
 }finally{await ui.close();}
});

const validationEvent={...base,id:'COSTO_OBRA_EVENTO:31',evento_id:31,fuente:'COSTO_OBRA_EVENTO',modulo:'OBRAS',recurso_tipo:'CONTROL_COSTOS',recurso_id:6,tipo:'VALIDACION',actor:3,actor_etiqueta:'supervisor',actor_username:'supervisor',actor_identidad_origen:'HISTORICA',motivo:'Revisión completa',datos_anteriores:{materiales_estado:'CON_REGISTROS',otros_estado:'CON_REGISTROS',costos_validados:false,validado_por:null,validado_en:null},datos_nuevos:{materiales_estado:'CON_REGISTROS',otros_estado:'CON_REGISTROS',costos_validados:true,validado_por:3,validado_en:date}};
test('Auditoría Supervisor: alcance de Obras, filtros y cambios efectivos con detalle completo opcional',async()=>{
 const ui=await mount({role:'SUPERVISOR_OBRAS',rows:[validationEvent]}),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/Auditoría de obras/);
  assert.match(body(),/Validación de costos/);
  assert.equal(r.root.findAllByType('label').some(l=>text(l).startsWith('Módulo')),false);
  const resource=r.root.findAllByType('label').find(l=>text(l).startsWith('Recurso')).findByType('select');
  assert.deepEqual(resource.findAllByType('option').map(o=>o.props.value),['','OBRA','PARTICIPANTE','TURNO','GASTO','CONTROL_COSTOS','CORTESIA']);
  await change(r,'Recurso','CONTROL_COSTOS');
  await change(r,'Tipo de evento','VALIDACION');
  await submit(r,'Filtrar eventos de obras');
  assert.ok(ui.calls.some(c=>c.path.includes('tipo=VALIDACION')&&c.path.includes('recurso_tipo=CONTROL_COSTOS')));
  await openDetail(r,'Ver detalle de Validación Control de costos #6');
  assert.match(body(),/Costos validadosNo→Sí/);
  assert.match(body(),/3 campos con cambios/);
  assert.doesNotMatch(body(),/Estado de materiales/);
  assert.match(body(),/Revisión completa/);
  assert.match(body(),/Identidad registrada en el evento/);
  await click(r,'Mostrar todos los valores');
  assert.match(body(),/Estado de materiales/);
  assert.match(body(),/Estado de otros gastos/);
  await click(r,'Solo cambios');
  assert.doesNotMatch(body(),/Estado de materiales/);
  await click(r,'Volver al historial');
  assert.match(body(),/Filtros aplicados/);
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('Auditoría Supervisor: sin resultados y sin diferencias entre valores',async()=>{
 const empty=await mount({role:'SUPERVISOR_OBRAS',rows:[]});
 try{assert.match(text(empty.renderer.toJSON()),/No hay eventos para mostrar/);}finally{await empty.close();}
 const ui=await mount({role:'SUPERVISOR_OBRAS',rows:[{...validationEvent,datos_nuevos:validationEvent.datos_anteriores}]});
 try{
  await openDetail(ui.renderer,'Ver detalle de Validación Control de costos #6');
  assert.match(text(ui.renderer.toJSON()),/Sin cambios entre valores/);
  await click(ui.renderer,'Mostrar todos los valores');
  assert.match(text(ui.renderer.toJSON()),/Estado de materiales/);
 }finally{await ui.close();}
});
