import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {ApiError} from '../src/auth/client.js';
import {createScope} from '../src/comercial/scope.js';
import {financeBackend,document as doc,origin,payment,paginated,event} from './helpers/finance-contract.js';

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
    try{if(role==='TECNICO')assert.equal(calls.length,0);else assert.deepEqual(control(ui.renderer.root,'Fuente').findAllByType('option').slice(1).map((node)=>node.props.value),sources);}finally{await ui.close();}
  }
});
test('Auditoría: draft actualiza fuentes, filtros válidos consultan, inválidos no, cursor solo y reinicio',async()=>{
  const calls=[];const ui=await mount(Auditoria,async(path)=>{calls.push(path);return {results:[],next_cursor:path.includes('cursor=')?null:'opaco',has_more:!path.includes('cursor='),fecha_corte:'2026-11-17T12:00:00Z',zona_horaria:'America/Santiago'};},'GERENCIA');
  try{
    const root=ui.renderer.root;assert.equal(root.findByProps({id:'audit-filters'}).props.hidden,true);await click(root,'Filtros');const before=calls.length;await change(root,'Módulo','OBRAS');assert.equal(calls.length,before);assert.ok(control(root,'Fuente').findAllByType('option').some((node)=>node.props.value==='OBRA_EVENTO'));
    await change(root,'Fuente','OBRA_EVENTO');await change(root,'Módulo','FINANZAS');assert.equal(control(root,'Fuente').props.value,'');assert.deepEqual(control(root,'Fuente').findAllByType('option').slice(1).map(node=>node.props.value),['FINANZAS_EVENTO']);
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
    const root=ui.renderer.root;await click(root,'Registrar factura');assert.ok(backend.calls.some((c)=>c.path==='/api/finanzas/obras-elegibles/?page=1'));
    await change(root,'Obra elegible para facturación','7');const nav=root.findByProps({'aria-label':'Paginación de obras elegibles'});await click(nav,'Siguiente');
    assert.equal(control(root,'Obra elegible para facturación').props.value,'7');assert.ok(control(root,'Obra elegible para facturación').findAllByType('option').some((o)=>o.props.value==='7'));
    assert.ok(backend.calls.some((c)=>c.path==='/api/finanzas/obras-elegibles/?page=2'));await change(root,'Obra elegible para facturación','32');await click(root.findByProps({'aria-label':'Paginación de obras elegibles'}),'Anterior');assert.equal(control(root,'Obra elegible para facturación').props.value,'32');
    for(const [field,value] of Object.entries({'Folio de factura':'00088','Fecha de emisión':'2026-11-10','Fecha de vencimiento':'2026-11-20','Monto neto (CLP)':'100.00','Impuesto (CLP)':'0.00','Monto total (CLP)':'100.00','Referencia del respaldo':'Respaldo sintético'}))await change(root,field,value);
    await submit(root,'Registro de documento externo');const created=backend.calls.find((c)=>c.method==='POST');assert.equal(created.body.obra,32);assert.equal(created.body.monto_total,'100.00');assert.equal(created.body.folio_externo,'00088');assert.match(text(ui.renderer.toJSON()),/relecturas confirmadas/);
  }finally{await ui.close();}
});
test('Finanzas: Gerencia consulta estado real, no elegibles ni escritura; otros roles no solicitan API',async()=>{
  for(const role of ['GERENCIA','SUPERVISOR_OBRAS','TECNICO','ADMINISTRADOR_TI']){
    const backend=financeBackend(),ui=await mount(FinanceAdmin,backend.request,role);
    try{if(role==='GERENCIA'){await change(ui.renderer.root,'Código de obra','OB-000080');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');assert.match(text(ui.renderer.toJSON()),/Pendiente de cierre sin cobro/);assert.equal(ui.renderer.root.findAllByType('button').some((b)=>text(b)==='Confirmar cierre sin cobro'),false);assert.ok(backend.calls.every((c)=>!c.path.includes('obras-elegibles')&&c.method==='GET'));}else assert.equal(backend.calls.length,0);}finally{await ui.close();}
  }
});
test('Cierre sin cobro: consulta previa, motivo, confirmación, un POST y relecturas obligatorias',async()=>{
  const backend=financeBackend();let updated=0;const ui=await mount(FinanceAdmin,backend.request,'ADMINISTRATIVO_FINANZAS',{onChanged:async()=>{updated+=1;return true;}});
  try{
    const root=ui.renderer.root;assert.equal(root.findAllByProps({'aria-label':'Registro administrativo sin cobro'}).length,0);
    await change(root,'Código de obra','OB-000080');await submit(root,'Consulta del estado financiero de una obra');await change(root,'Motivo de registro sin cobro',' Cierre autorizado ');
    const form=root.findByProps({'aria-label':'Registro administrativo sin cobro'});globalThis.window.confirm=()=>false;await submit(root,'Registro administrativo sin cobro');assert.equal(backend.calls.some((c)=>c.method==='POST'),false);
    globalThis.window.confirm=()=>true;await act(async()=>{await Promise.all([form.props.onSubmit({preventDefault(){}}),form.props.onSubmit({preventDefault(){}})]);await flush();});
    const calls=backend.calls.filter((c)=>c.method==='POST');assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/finanzas/obras/80/registrar-sin-cobro/');assert.deepEqual(calls[0].body,{motivo_registro:'Cierre autorizado'});assert.equal(updated,1);assert.match(text(ui.renderer.toJSON()),/Sin cobro/);assert.match(text(ui.renderer.toJSON()),/estado reconsultado/);
  }finally{globalThis.window.confirm=()=>true;await ui.close();}
});
for(const status of [400,403,404,409,503])test(`Cierre sin cobro: error ${status} no se reintenta ni confirma éxito`,async()=>{
  const backend=financeBackend();backend.fail=(path,options)=>options.method==='POST'?new ApiError(status,`Error ${status}`):null;const ui=await mount(FinanceAdmin,backend.request);
  try{await change(ui.renderer.root,'Código de obra','OB-000080');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');await change(ui.renderer.root,'Motivo de registro sin cobro','Motivo');await submit(ui.renderer.root,'Registro administrativo sin cobro');assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);assert.doesNotMatch(text(ui.renderer.toJSON()),/registrado y estado reconsultado/);}finally{await ui.close();}
});
test('Cierre sin cobro no se ofrece sin finalización, sin cortesía o con documento vigente',async()=>{
  for(const scenario of ['no-finalizada','sin-cortesia','documentado']){
    const backend=financeBackend();if(scenario==='no-finalizada')backend.financial.origen.finalizado_en=null;if(scenario==='sin-cortesia'){backend.financial.origen.cortesia=null;backend.financial.estado_financiero='PENDIENTE_FACTURACION';}if(scenario==='documentado'){backend.financial={origen:origin(80),estado_financiero:'DOCUMENTADO',documento_vigente:doc(11,80),cierre_sin_cobro:null};}
    const ui=await mount(FinanceAdmin,backend.request);try{await change(ui.renderer.root,'Código de obra','OB-000080');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');assert.equal(ui.renderer.root.findAllByProps({'aria-label':'Registro administrativo sin cobro'}).length,0);}finally{await ui.close();}
  }
});

test('Sin cobro confirmado con relectura fallida conserva motivo y no habilita otro POST', async()=>{
  const backend=financeBackend();
  backend.fail=(path)=>path.endsWith('/estado-financiero/')&&backend.financial.estado_financiero==='SIN_COBRO'?new ApiError(503,'Lectura no disponible'):null;
  const ui=await mount(FinanceAdmin,backend.request);
  try {
    await change(ui.renderer.root,'Código de obra','OB-000080');await submit(ui.renderer.root,'Consulta del estado financiero de una obra');
    await change(ui.renderer.root,'Motivo de registro sin cobro','Motivo conservado');await submit(ui.renderer.root,'Registro administrativo sin cobro');
    assert.match(text(ui.renderer.toJSON()),/Escritura bloqueada/);assert.doesNotMatch(text(ui.renderer.toJSON()),/registrado y estado reconsultado/);
    backend.fail=null;await click(ui.renderer.root,'Actualizar');
    assert.match(text(ui.renderer.toJSON()),/Sin cobro/);assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);
  } finally {await ui.close();}
});

test('Documento: tres paginaciones independientes y reset completo al cambiar de documento',async()=>{
  const backend=financeBackend();backend.payments=Array.from({length:26},(_,i)=>payment(i+1));const ui=await mount(FinanceDocument,backend.request,'GERENCIA',{document:doc(),onClose(){}});
  try{
    const root=ui.renderer.root;for(const [tab,label] of [['Pagos','Paginación de pagos'],['Historial del documento','Paginación: Historial del documento'],['Historial de pagos','Paginación: Historial de pagos']]){await click(root,tab);await click(root.findByProps({'aria-label':label}),'Siguiente');}
    for(const suffix of ['pagos/','historial/','pagos/historial/'])assert.ok(backend.calls.some((c)=>c.path===`/api/finanzas/documentos/11/${suffix}?page=2`));
    await click(root,'Pagos');await click(root.findByProps({'aria-label':'Paginación de pagos'}),'Anterior');assert.match(text(root.findByProps({'aria-label':'Paginación: Historial del documento'})),/Página 2/);
    await ui.update({document:doc(12),onClose(){}});assert.ok(backend.calls.some((c)=>c.path==='/api/finanzas/documentos/12/pagos/?page=1'));assert.match(text(root.findByProps({'aria-label':'Paginación: Historial del documento'})),/Página 1/);
  }finally{await ui.close();}
});
async function paymentForm(root){if(!root.findAllByProps({'aria-label':'Registro de pago informado'}).length)await click(root,'Registrar pago');for(const [label,value] of Object.entries({'Monto recibido (CLP)':'25.00','Fecha de pago':'2026-11-11','Referencia del pago':'Comprobante sintético','Observaciones':'Observación sintética'}))await change(root,label,value);}
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
  try{await paymentForm(ui.renderer.root);await submit(ui.renderer.root,'Registro de pago informado');await click(ui.renderer.root,'Actualizar');assert.equal(control(ui.renderer.root,'Monto recibido (CLP)').props.disabled,true);await click(ui.renderer.root,'Nueva intención tras rechazo');await change(ui.renderer.root,'Fecha de pago','2026-11-12');backend.fail=null;await submit(ui.renderer.root,'Registro de pago informado');const writes=backend.calls.filter((c)=>c.method==='POST');assert.notEqual(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);assert.equal(writes[1].body.fecha_pago,'2026-11-12');}finally{await ui.close();}
});
test('Documento: anulación y reversión reconsultan recursos y un callback fallido impide éxito/reenvío',async()=>{
  const backend=financeBackend();backend.payments=[payment(1)];let callbacks=0;const ui=await mount(FinanceDocument,backend.request,'ADMINISTRATIVO_FINANZAS',{document:doc(),onClose(){},onChanged:async()=>{callbacks+=1;return callbacks===1;}});
  try{
    const root=ui.renderer.root;await click(root,'Anular pago');await change(root,'Motivo de reversión o anulación','Corrección');await change(root,'Referencia externa de rectificación o reversión','Comprobante');await click(root,'Confirmar anulación');assert.equal(callbacks,1);assert.equal(backend.payments[0].activo,false);
    await click(root,'Revertir factura');await change(root,'Motivo de reversión o anulación','Rectificación');await change(root,'Referencia externa de rectificación o reversión','Nota externa');await click(root,'Confirmar reversión');assert.equal(callbacks,2);assert.doesNotMatch(text(ui.renderer.toJSON()),/Operación confirmada con relecturas/);assert.match(text(ui.renderer.toJSON()),/Falta confirmar el resultado/);assert.equal(backend.calls.filter((c)=>c.method==='POST').length,2);
  }finally{await ui.close();}
});
test('Cobranzas recibe callbacks de pago y actualiza lista administrativa, cartera y resumen',async()=>{
  const backend=financeBackend(),ui=await mount(Cobranzas,backend.request);
  try{const root=ui.renderer.root;await click(root.findByProps({id:'cobranzas-cartera'}),'Registrar pago');await paymentForm(root);const before=backend.calls.length;await submit(root,'Registro de pago informado');const reads=backend.calls.slice(before).filter((c)=>c.method==='GET');for(const prefix of ['/api/finanzas/documentos/?','/api/finanzas/cobranzas/','/api/finanzas/cobranzas/resumen/'])assert.ok(reads.some((c)=>c.path.startsWith(prefix)),prefix);assert.match(text(root.findByProps({id:'cobranzas-cartera'})),/\$75/);}finally{await ui.close();}
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
      await click(root,'Respaldos');
      assert.ok(calls.some((c)=>c.path==='/api/adjuntos/documentos-cobro/11/?page=1'));
      assert.match(text(ui.renderer.toJSON()),/factura-historica\.pdf/);
      assert.equal(root.findAllByType('button').some((b)=>text(b)==='Subir archivo'),false);
      assert.equal(root.findAllByProps({type:'file'}).length,0);
      await click(root,'Anotaciones');
      assert.match(text(ui.renderer.toJSON()),/Consulta de solo lectura/);
      assert.equal(root.findAllByType('button').some((b)=>text(b)==='Guardar anotaciones'),false);
      assert.equal(calls.filter((c)=>['POST','PATCH'].includes(c.method)).length,0);
      await click(root,'Historial del documento');
      assert.equal(root.findByProps({id:'finance-11-files'}).props.hidden,true);
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
      await click(ui.renderer.root,'Respaldos');
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
  try{const root=ui.renderer.root;await click(root,'Anotaciones');const form=root.findByProps({'aria-label':'Anotaciones de adjunto'});await act(async()=>{await Promise.all([form.props.onSubmit({preventDefault(){}}),form.props.onSubmit({preventDefault(){}})]);await flush();});assert.equal(backend.calls.filter((c)=>c.method==='PATCH').length,1);assert.equal(button(root,'Guardar anotaciones').props.disabled,true);await submit(root,'Anotaciones de adjunto');assert.equal(backend.calls.filter((c)=>c.method==='PATCH').length,1);backend.revision=3;backend.conflict=false;await click(root,'Actualizar anotaciones');await submit(root,'Anotaciones de adjunto');assert.equal(backend.calls.filter((c)=>c.method==='PATCH').at(-1).body.revision,3);assert.deepEqual(backend.calls.filter((c)=>c.method==='PATCH').at(-1).body.etiquetas,['historico']);assert.deepEqual(backend.calls.filter((c)=>c.method==='PATCH').at(-1).body.atributos,{zona_tecnica:'Sala'});assert.equal(root.findAllByType('textarea').length,1);assert.doesNotMatch(text(ui.renderer.toJSON()),/Atributos técnicos JSON|Etiquetas separadas por coma/);assert.match(text(ui.renderer.toJSON()),/Revisión 4/i);}finally{await ui.close();}
});
test('Adjuntos: carga FormData conserva clave/archivo tras incertidumbre, sin reintento automático',async()=>{
  const backend=attachmentsBackend();backend.lost=true;const ui=await mount(Adjuntos,backend.request,'SUPERVISOR_OBRAS',{type:'INFORME_TECNICO',destinationId:7,canUpload:true});
  try{const root=ui.renderer.root;const file=Object.assign(new Blob(['PDF sintético'],{type:'application/pdf'}),{name:'prueba.pdf'});await act(async()=>root.findByType('input').props.onChange({target:{files:[file]}}));const uploadForm=root.findAllByType('form')[0];await act(async()=>{await uploadForm.props.onSubmit({preventDefault(){}});await flush();});assert.equal(backend.calls.filter((c)=>c.method==='POST').length,1);await click(root,'Reconsultar y reintentar misma carga');const writes=backend.calls.filter((c)=>c.method==='POST');assert.equal(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);assert.ok(writes[0].body instanceof FormData);assert.equal(await writes[0].body.get('archivo').text(),await writes[1].body.get('archivo').text());}finally{await ui.close();}
});
test('Adjuntos: cambio de destino borra selección, página e intención y descarta detalle tardío',async()=>{
  const backend=attachmentsBackend(),late=deferred();const ui=await mount(Adjuntos,(path,opts)=>path==='/api/adjuntos/4/'?late.promise:backend.request(path,opts),'SUPERVISOR_OBRAS',{type:'INFORME_TECNICO',destinationId:7,canUpload:true});
  try{await act(async()=>{button(ui.renderer.root,'Información').props.onClick();await flush();});await ui.update({type:'INFORME_TECNICO',destinationId:8,canUpload:true});await act(async()=>{late.resolve(attachment(4,7));await flush();});assert.doesNotMatch(text(ui.renderer.toJSON()),/Información del archivo|informe-7/);assert.match(text(ui.renderer.toJSON()),/informe-8/);assert.ok(backend.calls.some((c)=>c.path==='/api/adjuntos/obras/8/?page=1'));}finally{await ui.close();}
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
test('012A: Supervisor edita con CAS, conflicto bloquea y cambio de Obra invalida selección',async()=>{
  let revision=0,conflict=true;const calls=[];const request=async(path,opts={})=>{calls.push({path,...opts});if(path.startsWith('/api/documentos-metadata/?')){const obra=Number(new URL(path,'http://localhost').searchParams.get('obra'));return {count:1,next:null,previous:null,results:[evidence(1,obra,revision)],proyeccion:'EVENTUAL',fuente_autoritativa:'POSTGRESQL'};}if(opts.method==='PATCH'){if(conflict)throw new ApiError(409,'CAS obsoleto');revision+=1;}return evidence(1,7,revision);};
  const ui=await mount(EvidenceMetadata,request,'SUPERVISOR_OBRAS',{obraId:7});
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
    await change(root,'Código de obra','OB-000080');
    await click(root,'Cobranzas vigentes');await click(root,'Documentos y pagos');
    assert.equal(control(root,'Código de obra').props.value,'OB-000080');
    await click(root,'Cobranzas vigentes');await click(root,'Filtros');
    const before=backend.calls.length;
    await change(root,'Buscar factura','Cliente sintético');
    assert.equal(backend.calls.length,before);
    await submit(root,'Filtros de cobranzas');
    for(const prefix of ['/api/finanzas/cobranzas/?','/api/finanzas/cobranzas/resumen/?'])assert.ok(backend.calls.slice(before).some(c=>c.path.startsWith(prefix)&&new URL(c.path,'http://localhost').searchParams.get('buscar')==='Cliente sintético'));
    assert.equal(root.findByProps({id:'cobranzas-filtros-avanzados'}).props.hidden,true);
    await click(root,'Limpiar filtros');
    assert.equal(control(root,'Buscar factura').props.value,'');
    assert.equal(root.findByProps({id:'cobranzas-filtros-avanzados'}).props.hidden,true);
  }finally{await ui.close();}
});

test('Cobranzas gerenciales: cartera exclusiva, prioridad, filtros y detalle bajo demanda',async()=>{
  const backend=financeBackend();backend.events=[event()];backend.payEvents=[];
  backend.documents=[{...doc(),cobranza:{moneda:'CLP',abonado:'25.00',saldo:'75.00',estado:'VENCIDA'}},{...doc(12),estado:'REVERTIDO',cobranza:null}];
  const calls=[];
  let fail=false;
  const request=async(path,options={})=>{
    calls.push({path,method:options.method||'GET'});
    const url=new URL(path,'http://localhost');
    if(url.pathname==='/api/finanzas/cobranzas/supervision-gerencial/'){
      if(fail)throw new ApiError(500,'Fallo de lectura');
      const rows=backend.documents.map(d=>({id:d.id,folio:d.folio_externo,cliente:d.origen.cliente.nombre_legal,obra:d.origen.codigo_obra,emision:d.fecha_emision,vencimiento:d.fecha_vencimiento,total:d.monto_total,cobrado:d.cobranza?.abonado??null,saldo:d.cobranza?.saldo??null,estado:d.cobranza?.estado??'REVERTIDO',dias_atraso:d.cobranza?.estado==='VENCIDA'?5:0}));
      const visible=rows.filter(r=>(url.searchParams.get('vista')==='documentos'||r.estado!=='REVERTIDO')&&(!url.searchParams.has('buscar')||r.cliente.toLowerCase().includes(url.searchParams.get('buscar').toLowerCase())));
      return {...paginated(visible,url),resumen:{moneda:'CLP',documentos:1,clientes_vencidos:1,total:'100.00',cobrado:'25.00',saldo:'75.00',vencido:'75.00',no_vencido:'0.00',fecha_corte:'2026-12-15'}};
    }
    if(path.startsWith('/api/adjuntos/documentos-cobro/'))return {count:0,next:null,previous:null,results:[]};
    return backend.request(path,options);
  };
  const ui=await mount(Cobranzas,request,'GERENCIA');
  try{
    const root=ui.renderer.root;
    assert.equal(calls.length,1);
    assert.match(text(ui.renderer.toJSON()),/25%/);
    assert.match(text(ui.renderer.toJSON()),/5 días de atraso/);
    assert.doesNotMatch(text(ui.renderer.toJSON()),/ID de Obra|Consultar \/ administrar|Registrar documento externo/);
    await click(root,'Documentos');
    assert.equal(root.findAllByProps({'data-state':'REVERTIDO'}).length,1);
    assert.equal(root.findByProps({id:'manager-cob-filters'}).props.hidden,true);
    await click(root,'Filtros');
    assert.equal(root.findByProps({id:'manager-cob-filters'}).props.hidden,false);
    await act(async()=>{root.findByProps({id:'cob-buscar'}).props.onChange({target:{value:'Cliente'}});});
    await act(async()=>{root.findByType('form').props.onSubmit({preventDefault(){}});await flush();});
    assert.match(calls.at(-1).path,/buscar=Cliente/);
    const before=calls.length;
    await act(async()=>{root.findByProps({'data-cobranza':11}).props.onClick();await flush();});
    assert.equal(root.findAllByProps({'data-cobranza':11}).length,0);
    assert.equal(calls.length,before+2);
    assert.ok(calls.slice(before).some(c=>c.path.endsWith('/11/pagos/?page=1')));
    assert.ok(calls.slice(before).every(c=>!c.path.includes('historial')));
    assert.match(text(ui.renderer.toJSON()),/Folio 0011/);
    assert.equal(root.findByProps({role:'progressbar'}).props['aria-valuenow'],25);
    assert.match(text(ui.renderer.toJSON()),/Saldo vencido/);
    assert.equal(root.findAllByProps({className:'portfolio-kpi portfolio-red'}).length,2);
    assert.doesNotMatch(text(ui.renderer.toJSON()),/Registrar pago|Anular pago|Revertir documento/);
    await click(root,'Historial del documento');
    assert.match(calls.at(-1).path,/\/11\/historial\//);
    assert.equal(root.findAllByProps({'aria-label':'Paginación de historial'}).length,0);
    assert.match(text(ui.renderer.toJSON()),/Usuario #9/);
    await click(root,'Respaldos');
    assert.doesNotMatch(text(ui.renderer.toJSON()),/Documento revertido/);
    assert.equal(root.findAllByProps({type:'file'}).length,0);
    await click(root,'Volver al listado');
    assert.equal(root.findByProps({id:'cob-buscar'}).props.value,'Cliente');
    assert.equal(root.findAllByProps({'data-cobranza':11}).length,1);
    await act(async()=>{root.findByProps({'data-cobranza':12}).props.onClick();await flush();});
    assert.equal(root.findAllByProps({role:'progressbar'}).length,0);
    await click(root,'Respaldos');
    assert.match(text(ui.renderer.toJSON()),/Documento revertido/);
    assert.equal(root.findAllByProps({type:'file'}).length,0);
    await click(root,'Volver al listado');
    await click(root,'Ver vencidos');
    assert.equal(root.findByProps({id:'cob-buscar'}).props.value,'');
    assert.equal(root.findAllByProps({'data-state':'REVERTIDO'}).length,0);
    assert.ok(calls.every(c=>c.method==='GET'));
    fail=true;
    await act(async()=>{root.findByProps({'aria-label':'Actualizar datos'}).props.onClick();await flush();});
    assert.doesNotMatch(text(ui.renderer.toJSON()),/\$100|\$75|25%/);
    assert.match(text(ui.renderer.toJSON()),/Fallo de lectura/);
  }finally{await ui.close();}
});

test('Adjuntos: información y anotaciones son mutuamente excluyentes y sin paginación de una página',async()=>{
  const backend=attachmentsBackend(),ui=await mount(Adjuntos,backend.request,'GERENCIA',{type:'INFORME_TECNICO',destinationId:7,canUpload:false});
  try{
    const root=ui.renderer.root;
    assert.equal(root.findAllByProps({'aria-label':'Paginación de adjuntos'}).length,0);
    await click(root,'Información');
    assert.equal(button(root,'Información').props['aria-expanded'],true);
    assert.equal(button(root,'Anotaciones').props['aria-expanded'],false);
    assert.match(text(ui.renderer.toJSON()),/Información del archivo/);
    assert.equal(root.findAllByType('button').some(b=>text(b)==='Actualizar anotaciones'),false);
    await click(root,'Anotaciones');
    assert.equal(button(root,'Información').props['aria-expanded'],false);
    assert.equal(button(root,'Anotaciones').props['aria-expanded'],true);
    assert.match(text(ui.renderer.toJSON()),/Vista frontal/);
    await click(root,'Anotaciones');
    assert.equal(button(root,'Anotaciones').props['aria-expanded'],false);
    assert.equal(root.findAllByProps({'aria-label':'Anotaciones de adjunto'}).length,0);
  }finally{await ui.close();}
});

test('Gerencia consulta evidencias sin acciones de edición',async()=>{
  const calls=[];const ui=await mount(EvidenceMetadata,async(path,opts={})=>{
    calls.push({path,method:opts.method||'GET'});
    return {count:1,next:null,previous:null,results:[evidence()],proyeccion:'EVENTUAL',fuente_autoritativa:'POSTGRESQL'};
  },'GERENCIA',{obraId:7});
  try{
    assert.match(text(ui.renderer.toJSON()),/Estado inicial/);
    assert.equal(ui.renderer.root.findAllByType('button').some(b=>text(b)==='Editar descripción'),false);
    assert.equal(ui.renderer.root.findAllByType('textarea').length,0);
    assert.ok(calls.length>0&&calls.every(c=>c.method==='GET'));
  }finally{await ui.close();}
});

test('Auditoría: detalle independiente, valores comparados y retorno sin nueva consulta',async()=>{
 const calls=[],event={id:'FINANZAS_EVENTO:12',evento_id:12,fuente:'FINANZAS_EVENTO',modulo:'FINANZAS',recurso_tipo:'DOCUMENTO',recurso_id:5,tipo:'DOCUMENTO_REVERTIDO',actor:2,actor_etiqueta:'Camila Hernández',actor_username:'finanzas',actor_identidad_origen:'ACTUAL',motivo:'Rectificación',creado_en:'2026-11-25T20:33:59-03:00',datos_anteriores:{estado:'VIGENTE',monto_total:'1000.25'},datos_nuevos:{estado:'REVERTIDO',motivo_reversion:'Rectificación',monto_total:'1000.25',referencia_rectificacion_externa:null}};
 const ui=await mount(Auditoria,async(path)=>{calls.push(path);return {results:[event],next_cursor:null,has_more:false,fecha_corte:'2026-11-25T21:00:00-03:00',zona_horaria:'America/Santiago'};},'GERENCIA');
 try{
  const root=ui.renderer.root,body=()=>text(ui.renderer.toJSON());
  assert.match(body(),/Documento revertido/);assert.match(body(),/Camila Hernández/);assert.match(body(),/finanzas/);assert.match(body(),/Identidad actual/);assert.doesNotMatch(body(),/Usuario #2/);assert.doesNotMatch(body(),/DOCUMENTO_REVERTIDO|Rectificación/);
  assert.equal(root.findAllByProps({'aria-label':'Paginación de auditoría'}).length,0);
  await click(root,'Ver detalle');
  assert.equal(root.findAllByProps({'aria-label':'Eventos de auditoría'}).length,0);
  assert.match(body(),/Usuario #2/);assert.match(body(),/Camila Hernández/);assert.match(body(),/Vigente/);assert.match(body(),/Revertido/);assert.match(body(),/\$1\.000,25/);assert.match(body(),/No registrado/);assert.match(body(),/Sin valor/);
  assert.equal(root.findAllByProps({className:'audit-changed'}).length,1);
  await click(root,'Volver al historial');
  assert.equal(calls.length,1);assert.equal(root.findAllByProps({'aria-label':'Eventos de auditoría'}).length,1);
 }finally{await ui.close();}
});

test('Auditoría: valida los campos de identidad 1.1.0 y rechaza campos inesperados',async()=>{
 const event={id:'FINANZAS_EVENTO:12',evento_id:12,fuente:'FINANZAS_EVENTO',modulo:'FINANZAS',recurso_tipo:'DOCUMENTO',recurso_id:5,tipo:'DOCUMENTO_REVERTIDO',actor:2,actor_etiqueta:'Camila Hernández',actor_username:'finanzas',actor_identidad_origen:'HISTORICA',motivo:'Rectificación',creado_en:'2026-11-25T20:33:59-03:00',datos_anteriores:{},datos_nuevos:{}};
 const {actor_username:omitted,...incomplete}=event;
 for(const [row,valid] of [[event,true],[{...event,actor_etiqueta:null,actor_username:null},true],[incomplete,false],[{...event,actor_username:12},false],[{...event,actor_identidad_origen:'DESCONOCIDA'},false],[{...event,email:'privado@example.test'},false]]){
  const ui=await mount(Auditoria,async()=>({results:[row],next_cursor:null,has_more:false,fecha_corte:'2026-11-25T21:00:00-03:00',zona_horaria:'America/Santiago'}),'GERENCIA');
  try{
   const root=ui.renderer.root,body=()=>text(ui.renderer.toJSON());
   assert.equal(root.findAllByProps({'aria-label':'Eventos de auditoría'}).length,valid?1:0);
   assert.equal(body().includes('Evento de auditoría inválido.'),!valid);
   assert.doesNotMatch(body(),/privado@example\.test/);
   if(valid&&row.actor_etiqueta){assert.match(body(),/Camila Hernández/);assert.doesNotMatch(body(),/Identidad actual/);await click(root,'Ver detalle');assert.match(body(),/Identidad registrada en el evento/);}
  }finally{await ui.close();}
 }
});
