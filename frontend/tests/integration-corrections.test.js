import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {ApiError} from '../src/auth/client.js';
import {createScope} from '../src/comercial/scope.js';
import {financeBackend,document as doc,origin,payment,paginated} from './helpers/finance-contract.js';

let server,AuthProvider,Auditoria,FinanceAdmin,FinanceDocument,Adjuntos,EvidenceMetadata,Cobranzas,Dashboard,auditSources,validAuditRange;
const flush=()=>new Promise((resolve)=>setImmediate(resolve));
const text=(node)=>typeof node==='string'?node:(node?.children||[]).map(text).join('');
test.before(async()=>{
  server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
  ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({default:Auditoria}=await server.ssrLoadModule('/src/pages/Auditoria.jsx'));
  ({default:FinanceAdmin}=await server.ssrLoadModule('/src/integrations/FinanceAdmin.jsx'));
  ({default:FinanceDocument}=await server.ssrLoadModule('/src/integrations/FinanceDocument.jsx'));
  ({default:Adjuntos}=await server.ssrLoadModule('/src/integrations/Adjuntos.jsx'));
  ({default:EvidenceMetadata}=await server.ssrLoadModule('/src/integrations/EvidenceMetadata.jsx'));
  ({default:Cobranzas}=await server.ssrLoadModule('/src/pages/Cobranzas.jsx'));
  ({default:Dashboard}=await server.ssrLoadModule('/src/pages/Dashboard.jsx'));
  ({auditSources,validAuditRange}=await server.ssrLoadModule('/src/integrations/audit.js'));
  globalThis.window={confirm:()=>true};
});
test.after(async()=>{delete globalThis.window;await server.close();});
async function mount(Page,request,role='ADMINISTRATIVO_FINANZAS',props={}){
  const session={status:'authenticated',user:{id:9,username:'Cuenta sintética',email:'account@example.test',role}};
  const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};
  const tree=(next)=>React.createElement(AuthProvider,{client},React.createElement(Page,next));let renderer;
  await act(async()=>{renderer=Renderer.create(tree(props));await flush();});
  return {renderer,update:async(next)=>act(async()=>{renderer.update(tree(next));await flush();}),close:async()=>act(async()=>renderer.unmount())};
}
function button(root,label){const found=root.findAllByType('button').find((b)=>text(b)===label);assert.ok(found,`Falta botón ${label}`);return found;}
async function click(root,label){const found=button(root,label);assert.ok(!found.props.disabled,`${label} deshabilitado`);await act(async()=>{await found.props.onClick({preventDefault(){}});await flush();});}
function control(root,label){const field=root.findAllByType('label').find((node)=>node.children[0]===label);assert.ok(field,`Falta campo ${label}`);return field.findAll((node)=>['input','select','textarea'].includes(node.type))[0];}
async function change(root,label,value){await act(async()=>{control(root,label).props.onChange({target:{value}});await flush();});}
async function submit(root,label){const form=root.findAllByType('form').find((node)=>!label||node.props['aria-label']===label);assert.ok(form,`Falta form ${label}`);await act(async()=>{await form.props.onSubmit({preventDefault(){}});await flush();});}
const deferred=()=>{let resolve;const promise=new Promise((r)=>{resolve=r;});return {resolve,promise};};

test('Auditoría: calendario real, rango inclusivo 366 días y defaults civiles del backend',()=>{
  for(const [desde,hasta,valid] of [['2024-01-01','2024-12-31',true],['2024-01-01','2025-01-01',false],['2026-02-30','2026-03-02',false],['2026-2-01','2026-03-01',false],['2026-03-02','2026-03-01',false],['0000-01-01','0000-01-02',false],['2026-09-06','2026-09-06',true]])assert.equal(validAuditRange({desde,hasta},'2026-11-17'),valid);
  assert.equal(validAuditRange({desde:'',hasta:''},'2026-11-17'),true);
  assert.equal(validAuditRange({desde:'',hasta:'0001-01-01'},'2026-11-17'),false);
});
test('Auditoría: matriz coincide con permissions.POR_ROL, Supervisor no hereda categorías',async()=>{
  const expected={GERENCIA:['PRESUPUESTO_EVENTO','OBRA_EVENTO','PARTICIPANTE_EVENTO','CATEGORIA_SERVICIO_EVENTO','TURNO_EVENTO','COSTO_OBRA_EVENTO','FINANZAS_EVENTO'],SUPERVISOR_OBRAS:['OBRA_EVENTO','PARTICIPANTE_EVENTO','TURNO_EVENTO','COSTO_OBRA_EVENTO'],ADMINISTRATIVO_FINANZAS:['FINANZAS_EVENTO'],ADMINISTRADOR_TI:['USUARIO_EVENTO'],TECNICO:[]};
  for(const [role,sources] of Object.entries(expected)){
    assert.deepEqual(auditSources(role),sources);const calls=[];
    const ui=await mount(Auditoria,async(path)=>{calls.push(path);return {results:[],next_cursor:null,has_more:false,fecha_corte:'2026-11-17T12:00:00Z',zona_horaria:'America/Santiago'};},role);
    try{if(role==='TECNICO')assert.equal(calls.length,0);else assert.deepEqual(control(ui.renderer.root,'Fuente').findAllByType('option').slice(1).map((node)=>text(node)),sources);}finally{await ui.close();}
  }
});
test('Auditoría: draft actualiza fuentes, filtros válidos consultan, inválidos no, cursor solo y reinicio',async()=>{
  const calls=[];const ui=await mount(Auditoria,async(path)=>{calls.push(path);return {results:[],next_cursor:path.includes('cursor=')?null:'opaco',has_more:!path.includes('cursor='),fecha_corte:'2026-11-17T12:00:00Z',zona_horaria:'America/Santiago'};},'GERENCIA');
  try{
    const root=ui.renderer.root;await change(root,'Módulo','OBRAS');assert.ok(control(root,'Fuente').findAllByType('option').some((node)=>text(node)==='OBRA_EVENTO'));
    await change(root,'Fuente','OBRA_EVENTO');await change(root,'Módulo','FINANZAS');assert.equal(control(root,'Fuente').props.value,'');assert.deepEqual(control(root,'Fuente').findAllByType('option').slice(1).map(text),['FINANZAS_EVENTO']);
    await change(root,'Desde','2026-11-01');await change(root,'Hasta','2026-11-17');await submit(root);
    assert.match(calls.at(-1),/modulo=FINANZAS&desde=2026-11-01&hasta=2026-11-17/);
    await click(root,'Siguiente');assert.equal(calls.at(-1),'/api/auditoria/eventos/?cursor=opaco');await click(root,'Anterior');assert.doesNotMatch(calls.at(-1),/cursor=/);
    await click(root,'Siguiente');await submit(root);assert.doesNotMatch(calls.at(-1),/cursor=/);
    const count=calls.length;await change(root,'Desde','2026-02-30');await submit(root);assert.equal(calls.length,count);assert.match(text(ui.renderer.toJSON()),/rango civil válido/);
  }finally{await ui.close();}
});

test('Obras elegibles: AF pagina todo el selector y conserva la obra elegida de otra página',async()=>{
  const backend=financeBackend(),ui=await mount(FinanceAdmin,backend.request);
  try{
    const root=ui.renderer.root;await click(root,'Registrar documento externo');assert.ok(backend.calls.some((c)=>c.path==='/api/finanzas/obras-elegibles/?page=1'));
    await change(root,'Obra elegible para facturación','7');const nav=root.findByProps({'aria-label':'Paginación de obras elegibles'});await click(nav,'Siguiente');
    assert.equal(control(root,'Obra elegible para facturación').props.value,'7');assert.ok(control(root,'Obra elegible para facturación').findAllByType('option').some((o)=>o.props.value==='7'));
    assert.ok(backend.calls.some((c)=>c.path==='/api/finanzas/obras-elegibles/?page=2'));await change(root,'Obra elegible para facturación','32');await click(root.findByProps({'aria-label':'Paginación de obras elegibles'}),'Anterior');assert.equal(control(root,'Obra elegible para facturación').props.value,'32');
    for(const [field,value] of Object.entries({'Folio externo exacto':'00088','Fecha de emisión':'2026-11-10','Fecha de vencimiento':'2026-11-20','Neto decimal':'100.00','Impuesto decimal':'0.00','Total decimal':'100.00','Referencia externa':'Respaldo sintético'}))await change(root,field,value);
    await submit(root,'Registro de documento externo');const created=backend.calls.find((c)=>c.method==='POST');assert.equal(created.body.obra,32);assert.equal(created.body.monto_total,'100.00');assert.equal(created.body.folio_externo,'00088');assert.match(text(ui.renderer.toJSON()),/relecturas confirmadas/);
  }finally{await ui.close();}
});
test('Finanzas: Gerencia consulta estado real, no elegibles ni escritura; otros roles no solicitan API',async()=>{
  for(const role of ['GERENCIA','SUPERVISOR_OBRAS','TECNICO','ADMINISTRADOR_TI']){
    const backend=financeBackend(),ui=await mount(FinanceAdmin,backend.request,role);
    try{if(role==='GERENCIA'){await change(ui.renderer.root,'ID de Obra para consulta financiera','80');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');assert.match(text(ui.renderer.toJSON()),/PENDIENTE_REGISTRO_SIN_COBRO/);assert.equal(ui.renderer.root.findAllByType('button').some((b)=>text(b)==='Confirmar cierre sin cobro'),false);assert.ok(backend.calls.every((c)=>!c.path.includes('obras-elegibles')&&c.method==='GET'));}else assert.equal(backend.calls.length,0);}finally{await ui.close();}
  }
});
test('Cierre sin cobro: consulta previa, motivo, confirmación, un POST y relecturas obligatorias',async()=>{
  const backend=financeBackend();let updated=0;const ui=await mount(FinanceAdmin,backend.request,'ADMINISTRATIVO_FINANZAS',{onChanged:async()=>{updated+=1;return true;}});
  try{
    const root=ui.renderer.root;assert.equal(root.findAllByProps({'aria-label':'Registro administrativo sin cobro'}).length,0);
    await change(root,'ID de Obra para consulta financiera','80');await submit(root,'Consulta del estado financiero de una obra');await change(root,'Motivo de registro sin cobro',' Cierre autorizado ');
    const form=root.findByProps({'aria-label':'Registro administrativo sin cobro'});globalThis.window.confirm=()=>false;await submit(root,'Registro administrativo sin cobro');assert.equal(backend.calls.some((c)=>c.method==='POST'),false);
    globalThis.window.confirm=()=>true;await act(async()=>{await Promise.all([form.props.onSubmit({preventDefault(){}}),form.props.onSubmit({preventDefault(){}})]);await flush();});
    const calls=backend.calls.filter((c)=>c.method==='POST');assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/finanzas/obras/80/registrar-sin-cobro/');assert.deepEqual(calls[0].body,{motivo_registro:'Cierre autorizado'});assert.equal(updated,1);assert.match(text(ui.renderer.toJSON()),/SIN_COBRO/);assert.match(text(ui.renderer.toJSON()),/estado reconsultado/);
  }finally{globalThis.window.confirm=()=>true;await ui.close();}
});
for(const status of [400,403,404,409,503])test(`Cierre sin cobro: error ${status} no se reintenta ni confirma éxito`,async()=>{
  const backend=financeBackend();backend.fail=(path,options)=>options.method==='POST'?new ApiError(status,`Error ${status}`):null;const ui=await mount(FinanceAdmin,backend.request);
  try{await change(ui.renderer.root,'ID de Obra para consulta financiera','80');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');await change(ui.renderer.root,'Motivo de registro sin cobro','Motivo');await submit(ui.renderer.root,'Registro administrativo sin cobro');assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);assert.doesNotMatch(text(ui.renderer.toJSON()),/registrado y estado reconsultado/);}finally{await ui.close();}
});
test('Cierre sin cobro no se ofrece sin finalización, sin cortesía o con documento vigente',async()=>{
  for(const scenario of ['no-finalizada','sin-cortesia','documentado']){
    const backend=financeBackend();if(scenario==='no-finalizada')backend.financial.origen.finalizado_en=null;if(scenario==='sin-cortesia'){backend.financial.origen.cortesia=null;backend.financial.estado_financiero='PENDIENTE_FACTURACION';}if(scenario==='documentado'){backend.financial={origen:origin(80),estado_financiero:'DOCUMENTADO',documento_vigente:doc(11,80),cierre_sin_cobro:null};}
    const ui=await mount(FinanceAdmin,backend.request);try{await change(ui.renderer.root,'ID de Obra para consulta financiera','80');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');assert.equal(ui.renderer.root.findAllByProps({'aria-label':'Registro administrativo sin cobro'}).length,0);}finally{await ui.close();}
  }
});

test('Sin cobro confirmado con relectura fallida conserva motivo y no habilita otro POST', async()=>{
  const backend=financeBackend();
  backend.fail=(path)=>path.endsWith('/estado-financiero/')&&backend.financial.estado_financiero==='SIN_COBRO'?new ApiError(503,'Lectura no disponible'):null;
  const ui=await mount(FinanceAdmin,backend.request);
  try {
    await change(ui.renderer.root,'ID de Obra para consulta financiera','80');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');
    await change(ui.renderer.root,'Motivo de registro sin cobro','Motivo conservado');await submit(ui.renderer.root,'Registro administrativo sin cobro');
    assert.match(text(ui.renderer.toJSON()),/Escritura bloqueada/);assert.doesNotMatch(text(ui.renderer.toJSON()),/registrado y estado reconsultado/);
    backend.fail=null;await click(ui.renderer.root,'Actualizar documentos y estado');
    assert.match(text(ui.renderer.toJSON()),/SIN_COBRO/);assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);
  } finally {await ui.close();}
});

test('Documento: tres paginaciones independientes y reset completo al cambiar de documento',async()=>{
  const backend=financeBackend();backend.payments=Array.from({length:26},(_,i)=>payment(i+1));const ui=await mount(FinanceDocument,backend.request,'GERENCIA',{document:doc(),onClose(){}});
  try{
    const root=ui.renderer.root;for(const label of ['Paginación de pagos','Paginación: Historial del documento','Paginación: Historial de pagos'])await click(root.findByProps({'aria-label':label}),'Siguiente');
    for(const suffix of ['pagos/','historial/','pagos/historial/'])assert.ok(backend.calls.some((c)=>c.path===`/api/finanzas/documentos/11/${suffix}?page=2`));
    await click(root.findByProps({'aria-label':'Paginación de pagos'}),'Anterior');assert.match(text(root.findByProps({'aria-label':'Paginación: Historial del documento'})),/Página 2/);
    await ui.update({document:doc(12),onClose(){}});assert.ok(backend.calls.some((c)=>c.path==='/api/finanzas/documentos/12/pagos/?page=1'));assert.match(text(root.findByProps({'aria-label':'Paginación: Historial del documento'})),/Página 1/);
  }finally{await ui.close();}
});
async function paymentForm(root){for(const [label,value] of Object.entries({'Monto decimal':'25.00','Fecha de pago':'2026-11-11','Referencia externa del pago':'Comprobante sintético','Observación del pago':'Observación sintética'}))await change(root,label,value);}
test('Pago incierto conserva clave y payload inmutables; reintento explícito no duplica y notifica al padre',async()=>{
  const backend=financeBackend();backend.lostPayment=true;let updated=0;const ui=await mount(FinanceDocument,backend.request,'ADMINISTRATIVO_FINANZAS',{document:doc(),onClose(){},onChanged:async()=>{updated+=1;return true;}});
  try{
    await paymentForm(ui.renderer.root);await submit(ui.renderer.root,'Registro de pago informado');assert.equal(backend.payments.length,1);assert.match(text(ui.renderer.toJSON()),/Intención de pago conservada/);
    assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);await click(ui.renderer.root,'Reintentar misma intención de pago');
    const writes=backend.calls.filter((c)=>c.method==='POST');assert.equal(writes.length,2);assert.equal(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);assert.deepEqual(writes[0].body,writes[1].body);assert.equal(typeof writes[1].body.monto,'string');assert.equal(backend.payments.length,1);assert.ok(updated>=1);assert.match(text(ui.renderer.toJSON()),/relecturas confirmadas/);
  }finally{await ui.close();}
});
test('Pago rechazado cambia de clave solamente después de descartar explícitamente la intención',async()=>{
  const backend=financeBackend();backend.fail=(path,opts)=>opts.method==='POST'?new ApiError(400,'Rechazo contractual'):null;const ui=await mount(FinanceDocument,backend.request,'ADMINISTRATIVO_FINANZAS',{document:doc(),onClose(){}});
  try{await paymentForm(ui.renderer.root);await submit(ui.renderer.root,'Registro de pago informado');await click(ui.renderer.root,'Actualizar detalle financiero');assert.equal(control(ui.renderer.root,'Monto decimal').props.disabled,true);await click(ui.renderer.root,'Nueva intención tras rechazo');await change(ui.renderer.root,'Fecha de pago','2026-11-12');backend.fail=null;await submit(ui.renderer.root,'Registro de pago informado');const writes=backend.calls.filter((c)=>c.method==='POST');assert.notEqual(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);assert.equal(writes[1].body.fecha_pago,'2026-11-12');}finally{await ui.close();}
});
test('Documento: anulación y reversión reconsultan recursos y un callback fallido impide éxito/reenvío',async()=>{
  const backend=financeBackend();backend.payments=[payment(1)];let callbacks=0;const ui=await mount(FinanceDocument,backend.request,'ADMINISTRATIVO_FINANZAS',{document:doc(),onClose(){},onChanged:async()=>{callbacks+=1;return callbacks===1;}});
  try{
    const root=ui.renderer.root;await change(root,'Motivo de reversión o anulación','Corrección');await change(root,'Referencia externa de rectificación o reversión','Comprobante');await click(root,'Anular pago #1');assert.equal(callbacks,1);assert.equal(backend.payments[0].activo,false);
    await change(root,'Motivo de reversión o anulación','Rectificación');await change(root,'Referencia externa de rectificación o reversión','Nota externa');await click(root,'Revertir documento externo');assert.equal(callbacks,2);assert.doesNotMatch(text(ui.renderer.toJSON()),/Operación confirmada con relecturas/);assert.match(text(ui.renderer.toJSON()),/Falta confirmar el resultado/);assert.equal(backend.calls.filter((c)=>c.method==='POST').length,2);
  }finally{await ui.close();}
});
test('Cobranzas recibe callbacks de pago y actualiza lista administrativa, cartera y resumen',async()=>{
  const backend=financeBackend(),ui=await mount(Cobranzas,backend.request);
  try{const root=ui.renderer.root;await click(root,'Documentos y pagos');await click(root,'Consultar / administrar');await paymentForm(root);const before=backend.calls.length;await submit(root,'Registro de pago informado');const reads=backend.calls.slice(before).filter((c)=>c.method==='GET');for(const prefix of ['/api/finanzas/documentos/?','/api/finanzas/cobranzas/','/api/finanzas/cobranzas/resumen/'])assert.ok(reads.some((c)=>c.path.startsWith(prefix)),prefix);assert.match(text(root.findByProps({id:'cobranzas-cartera'})),/\$75/);}finally{await ui.close();}
});

test('Factura revertida: Gerencia y Finanzas consultan respaldos históricos sin permitir cargas ni PATCH',async()=>{
  for(const role of ['GERENCIA','ADMINISTRATIVO_FINANZAS']){
    const backend=financeBackend(),historical={...doc(),estado:'REVERTIDO',cobranza:null};
    backend.documents=[historical];
    const file={id:44,tipo:'RESPALDO_FACTURA',destino:{documento_cobro:11},nombre_visible:'factura-historica.pdf',
      mime:'application/pdf',tamano_bytes:25,estado:'DISPONIBLE',registrado_por:9,registrado_en:'2026-11-17T12:00:00Z'};
    const calls=[];
    const request=(path,options={})=>{
      if(!path.startsWith('/api/adjuntos/'))return backend.request(path,options);
      calls.push({path,...options});
      if(path==='/api/adjuntos/documentos-cobro/11/?page=1')return Promise.resolve({count:1,next:null,previous:null,results:[file]});
      if(path==='/api/adjuntos/44/anotaciones/')return Promise.resolve({adjunto_id:44,tipo:'RESPALDO_FACTURA',destino_id:11,
        mime:file.mime,tamano_bytes:file.tamano_bytes,registrado_en:file.registrado_en,sincronizado_en:file.registrado_en,
        descripcion:'Respaldo histórico',etiquetas:[],atributos:{},revision:1});
      throw new Error(`Ruta documental no esperada: ${path}`);
    };
    const ui=await mount(FinanceDocument,request,role,{document:historical,onClose(){}});
    try{
      const root=ui.renderer.root;
      assert.equal(calls.length,0,'la sección debe cargar solo al abrirse');
      await click(root,'Consultar respaldos documentales');
      assert.ok(calls.some((c)=>c.path==='/api/adjuntos/documentos-cobro/11/?page=1'));
      assert.match(text(ui.renderer.toJSON()),/factura-historica\.pdf/);
      assert.equal(root.findAllByType('button').some((b)=>text(b)==='Subir archivo'),false);
      assert.equal(root.findAllByProps({type:'file'}).length,0);
      await click(root,'Anotaciones');
      assert.match(text(ui.renderer.toJSON()),/Consulta de solo lectura/);
      assert.equal(root.findAllByType('button').some((b)=>text(b)==='Guardar anotaciones'),false);
      assert.equal(calls.filter((c)=>['POST','PATCH'].includes(c.method)).length,0);
      await click(root,'Ocultar respaldos documentales');
      assert.equal(root.findAllByProps({'aria-label':'Adjuntos de factura externa'}).length,0);
    }finally{await ui.close();}
  }
});
test('Factura vigente: Finanzas puede subir respaldos y Gerencia solo consultarlos',async()=>{
  for(const role of ['GERENCIA','ADMINISTRATIVO_FINANZAS']){
    const backend=financeBackend(),calls=[];
    const request=(path,options={})=>{
      if(path==='/api/adjuntos/documentos-cobro/11/?page=1'){
        calls.push({path,...options});return Promise.resolve({count:0,next:null,previous:null,results:[]});
      }
      return backend.request(path,options);
    };
    const ui=await mount(FinanceDocument,request,role,{document:doc(),onClose(){}});
    try{
      await click(ui.renderer.root,'Consultar respaldos documentales');
      assert.equal(calls.length,1);
      assert.equal(ui.renderer.root.findAllByType('button').some((b)=>text(b)==='Subir archivo'),role==='ADMINISTRATIVO_FINANZAS');
      assert.equal(ui.renderer.root.findAllByProps({type:'file'}).length,role==='ADMINISTRATIVO_FINANZAS'?1:0);
    }finally{await ui.close();}
  }
});

const attachment=(id=4,obra=7)=>({id,tipo:'INFORME_TECNICO',destino:{obra},nombre_visible:`informe-${obra}.pdf`,mime:'application/pdf',tamano_bytes:20,estado:'DISPONIBLE',registrado_por:9,registrado_en:'2026-11-17T12:00:00Z'});
const annotation=(id=4,obra=7,revision=0)=>({adjunto_id:id,tipo:'INFORME_TECNICO',destino_id:obra,mime:'application/pdf',tamano_bytes:20,registrado_en:'2026-11-17T12:00:00Z',sincronizado_en:'2026-11-17T12:00:00Z',descripcion:'Vista frontal',etiquetas:['historico'],atributos:{zona_tecnica:'Sala'},revision});
function attachmentsBackend(){const state={calls:[],revision:0,conflict:false,lost:false};state.request=async(path,opts={})=>{state.calls.push({path,...opts});if(path.startsWith('/api/adjuntos/obras/')){const obra=Number(path.split('/')[4]);if(opts.method==='POST'){if(state.lost){state.lost=false;throw new ApiError(0,'Carga incierta');}return attachment(4,obra);}return {count:1,next:null,previous:null,results:[attachment(4,obra)]};}if(path.endsWith('/anotaciones/')){if(opts.method==='PATCH'){if(state.conflict)throw new ApiError(409,'Revisión obsoleta');state.revision+=1;}return annotation(4,7,state.revision);}if(path.endsWith('/descargar/'))return new Blob(['archivo sintético'],{type:'application/pdf'});return attachment();};return state;}
test('Adjuntos: PATCH usa scope, conserva revisión CAS y bloquea doble envío y reenvío obsoleto',async()=>{
  const backend=attachmentsBackend();backend.conflict=true;const ui=await mount(Adjuntos,backend.request,'SUPERVISOR_OBRAS',{type:'INFORME_TECNICO',destinationId:7,canUpload:true});
  try{const root=ui.renderer.root;await click(root,'Anotaciones');const form=root.findByProps({'aria-label':'Anotaciones de adjunto'});await act(async()=>{await Promise.all([form.props.onSubmit({preventDefault(){}}),form.props.onSubmit({preventDefault(){}})]);await flush();});assert.equal(backend.calls.filter((c)=>c.method==='PATCH').length,1);assert.equal(button(root,'Guardar anotaciones').props.disabled,true);await submit(root,'Anotaciones de adjunto');assert.equal(backend.calls.filter((c)=>c.method==='PATCH').length,1);backend.revision=3;backend.conflict=false;await click(root,'Reconsultar anotaciones seleccionadas');await submit(root,'Anotaciones de adjunto');assert.equal(backend.calls.filter((c)=>c.method==='PATCH').at(-1).body.revision,3);assert.deepEqual(backend.calls.filter((c)=>c.method==='PATCH').at(-1).body.etiquetas,['historico']);assert.deepEqual(backend.calls.filter((c)=>c.method==='PATCH').at(-1).body.atributos,{zona_tecnica:'Sala'});assert.equal(root.findAllByType('textarea').length,1);assert.doesNotMatch(text(ui.renderer.toJSON()),/Atributos técnicos JSON|Etiquetas separadas por coma/);assert.match(text(ui.renderer.toJSON()),/revisión 4/);}finally{await ui.close();}
});
test('Adjuntos: carga FormData conserva clave/archivo tras incertidumbre, sin reintento automático',async()=>{
  const backend=attachmentsBackend();backend.lost=true;const ui=await mount(Adjuntos,backend.request,'SUPERVISOR_OBRAS',{type:'INFORME_TECNICO',destinationId:7,canUpload:true});
  try{const root=ui.renderer.root;const file=Object.assign(new Blob(['PDF sintético'],{type:'application/pdf'}),{name:'prueba.pdf'});await act(async()=>root.findByType('input').props.onChange({target:{files:[file]}}));const uploadForm=root.findAllByType('form')[0];await act(async()=>{await uploadForm.props.onSubmit({preventDefault(){}});await flush();});assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);await click(root,'Reconsultar y reintentar misma carga');const writes=backend.calls.filter((c)=>c.method==='POST');assert.equal(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);assert.ok(writes[0].body instanceof FormData);assert.equal(await writes[0].body.get('archivo').text(),await writes[1].body.get('archivo').text());}finally{await ui.close();}
});
test('Adjuntos: cambio de destino borra selección, página e intención y descarta detalle tardío',async()=>{
  const backend=attachmentsBackend(),late=deferred();const ui=await mount(Adjuntos,(path,opts)=>path==='/api/adjuntos/4/'?late.promise:backend.request(path,opts),'SUPERVISOR_OBRAS',{type:'INFORME_TECNICO',destinationId:7,canUpload:true});
  try{await act(async()=>{button(ui.renderer.root,'Detalle').props.onClick();await flush();});await ui.update({type:'INFORME_TECNICO',destinationId:8,canUpload:true});await act(async()=>{late.resolve(attachment(4,7));await flush();});assert.doesNotMatch(text(ui.renderer.toJSON()),/Detalle del adjunto|informe-7/);assert.match(text(ui.renderer.toJSON()),/informe-8/);assert.ok(backend.calls.some((c)=>c.path==='/api/adjuntos/obras/8/?page=1'));}finally{await ui.close();}
});
test('Adjuntos: Gerencia solo lee anotaciones; AF y TI no acceden a informes aunque canUpload=true',async()=>{
  for(const role of ['GERENCIA','ADMINISTRATIVO_FINANZAS','ADMINISTRADOR_TI']){const backend=attachmentsBackend(),ui=await mount(Adjuntos,backend.request,role,{type:'INFORME_TECNICO',destinationId:7,canUpload:true});try{if(role==='GERENCIA'){await click(ui.renderer.root,'Anotaciones');assert.match(text(ui.renderer.toJSON()),/Vista frontal/);assert.equal(ui.renderer.root.findAllByType('textarea').length,0);assert.equal(ui.renderer.root.findAllByType('input').length,0);}else assert.equal(backend.calls.length,0);}finally{await ui.close();}}
});

for(const status of [403,404,413,422,503])test(`Adjuntos: carga rechazada/incierta ${status} conserva intención sin éxito ni reintento automático`,async()=>{
  const backend=attachmentsBackend(),request=async(path,opts={})=>{if(opts.method==='POST'){backend.calls.push({path,...opts});throw new ApiError(status,'Carga no confirmada');}return backend.request(path,opts);};
  const ui=await mount(Adjuntos,request,'SUPERVISOR_OBRAS',{type:'INFORME_TECNICO',destinationId:7,canUpload:true});
  try {
    const file=Object.assign(new Blob(['PDF sintético'],{type:'application/pdf'}),{name:'sintetico.pdf'});
    await act(async()=>ui.renderer.root.findByType('input').props.onChange({target:{files:[file]}}));
    await submit(ui.renderer.root);assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);
    assert.match(text(ui.renderer.toJSON()),/conserva la intención/);assert.doesNotMatch(text(ui.renderer.toJSON()),/Archivo aceptado/);
  }finally{await ui.close();}
});
const evidence=(id=1,obra=7,revision=0)=>({evidencia_id:id,obra_id:obra,turno_id:2,tipo_mime:'image/png',tamano_bytes:20,creado_en:'2026-11-17T12:00:00Z',sincronizado_en:'2026-11-17T12:00:00Z',descripcion:'Estado inicial',etiquetas:['historico'],atributos:{zona_tecnica:'Sala'},revision});
test('012A: roles G/S editan con CAS, conflicto bloquea y cambio de Obra invalida selección',async()=>{
  let revision=0,conflict=true;const calls=[];const request=async(path,opts={})=>{calls.push({path,...opts});if(path.startsWith('/api/documentos-metadata/?')){const obra=Number(new URL(path,'http://localhost').searchParams.get('obra'));return {count:1,next:null,previous:null,results:[evidence(1,obra,revision)],proyeccion:'EVENTUAL',fuente_autoritativa:'POSTGRESQL'};}if(opts.method==='PATCH'){if(conflict)throw new ApiError(409,'CAS obsoleto');revision+=1;}return evidence(1,7,revision);};
  const ui=await mount(EvidenceMetadata,request,'GERENCIA',{obraId:7});
  try{await click(ui.renderer.root,'Editar descripción');await submit(ui.renderer.root,'Anotaciones de evidencia');assert.equal(button(ui.renderer.root,'Guardar anotaciones').props.disabled,true);conflict=false;revision=2;await click(ui.renderer.root,'Reconsultar revisión');await submit(ui.renderer.root,'Anotaciones de evidencia');assert.equal(calls.filter((c)=>c.method==='PATCH').at(-1).body.revision,2);assert.deepEqual(calls.filter((c)=>c.method==='PATCH').at(-1).body.etiquetas,['historico']);assert.deepEqual(calls.filter((c)=>c.method==='PATCH').at(-1).body.atributos,{zona_tecnica:'Sala'});assert.equal(ui.renderer.root.findAllByType('textarea').length,1);assert.doesNotMatch(text(ui.renderer.toJSON()),/Atributos técnicos JSON|Etiquetas separadas por coma|image\/png/);await ui.update({obraId:8});assert.equal(ui.renderer.root.findAllByType('textarea').length,0);assert.ok(calls.some((c)=>c.path==='/api/documentos-metadata/?obra=8&page=1'));}finally{await ui.close();}
});
test('012A: Técnico, AF y TI no consultan metadatos aunque se monte el componente',async()=>{
  for(const role of ['TECNICO','ADMINISTRATIVO_FINANZAS','ADMINISTRADOR_TI']){const calls=[];const ui=await mount(EvidenceMetadata,async(path)=>{calls.push(path);},role,{obraId:7});try{assert.equal(calls.length,0);}finally{await ui.close();}}
});
test('Scope: error sin status y relectura fallida tras escritura confirmada mantienen bloqueo',async()=>{
  for(const failure of [new Error('Infraestructura'),new ApiError(400,'Lectura inválida')]){const scope=createScope();await assert.rejects(scope.write(async()=>({id:1}),async()=>{throw failure;}));assert.equal(scope.locked,true);assert.equal(await scope.write(async()=>{},async()=>{}),false);scope.dispose();}
  const scope=createScope(),late=deferred();let applied=false;const pending=scope.read('summary',()=>late.promise,()=>{applied=true;});scope.cancelRead('summary');late.resolve({});await pending;assert.equal(applied,false);scope.dispose();
});

test('Cobranzas: pestañas conservan consultas y filtros solo se aplican al confirmar',async()=>{
  const backend=financeBackend(),ui=await mount(Cobranzas,backend.request);
  try{
    const root=ui.renderer.root;
    assert.equal(root.findByProps({id:'cobranzas-cartera'}).props.hidden,false);
    assert.equal(root.findByProps({id:'cobranzas-documentos'}).props.hidden,true);
    await click(root,'Documentos y pagos');
    await change(root,'ID de Obra para consulta financiera','80');
    await click(root,'Cobranzas vigentes');await click(root,'Documentos y pagos');
    assert.equal(control(root,'ID de Obra para consulta financiera').props.value,'80');
    await click(root,'Cobranzas vigentes');await click(root,'Filtros');
    const before=backend.calls.length;
    await change(root,'ID de cliente','0');
    assert.equal(button(root,'Aplicar filtros').props.disabled,true);
    await change(root,'ID de cliente','9');
    assert.equal(backend.calls.length,before);
    await submit(root,'Filtros de cobranzas');
    assert.ok(backend.calls.slice(before).some(c=>c.path.startsWith('/api/finanzas/cobranzas/')&&c.path.includes('cliente=9')));
    assert.equal(root.findByProps({id:'cobranzas-filtros'}).props.hidden,true);
    await click(root,'Filtros (1)');await click(root,'Limpiar');
    assert.equal(control(root,'ID de cliente').props.value,'');
    await submit(root,'Filtros de cobranzas');
    assert.equal(root.findByProps({id:'cobranzas-filtros'}).props.hidden,true);
  }finally{await ui.close();}
});
