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
async function mount(role,firstPage=[{...budget,id:65,codigo:'PRE-000065'}]){
  const calls=[];
  const request=async path=>{
    calls.push(path);
    if(path.startsWith('/api/presupuestos/seguimiento-comercial/')){
      const url=new URL(path,'http://localhost'),all=[...firstPage,budget],group={PENDIENTE_GERENCIA:'PENDIENTE_FINANZAS',APROBADO_GERENCIA:'APROBADO_FINANZAS',RECHAZADO_GERENCIA:'RECHAZADO_FINANZAS'};
      const states=['BORRADOR','PENDIENTE_FINANZAS','APROBADO_FINANZAS','RECHAZADO_FINANZAS','ENVIADO_CLIENTE','APROBADO_CLIENTE','RECHAZADO_CLIENTE','ANULADO'];
      const rows=all.map(b=>({...b,cliente_nombre:'Cliente de prueba',estado_original:b.estado,estado:group[b.estado]||b.estado,sin_actualizar:b.sin_actualizar===true}));
      const estados=Object.fromEntries(states.map(k=>{
        const matching=rows.filter(r=>r.estado===k),sin_precio=matching.filter(r=>r.monto_neto===null).length;
        return [k,{cantidad:matching.length,sin_precio,monto_neto:sin_precio?null:(matching.length*45300).toFixed(2)}];
      }));
      const filtered=rows.filter(r=>(!url.searchParams.has('estado')||r.estado===url.searchParams.get('estado'))&&(!url.searchParams.has('sin_actualizar')||r.sin_actualizar));
      const accepted=estados.APROBADO_CLIENTE.cantidad,answered=accepted+estados.RECHAZADO_CLIENTE.cantidad;
      const page=Number(url.searchParams.get('page')),size=firstPage.length>1?25:1;
      const link=n=>'/api/presupuestos/seguimiento-comercial/?page='+n+(url.searchParams.has('estado')?'&estado='+url.searchParams.get('estado'):'');
      return {count:filtered.length,results:filtered.slice((page-1)*size,page*size),next:page*size<filtered.length?link(page+1):null,previous:page>1?link(page-1):null,resumen:{total:rows.length,estados,sin_actualizar:rows.filter(r=>r.sin_actualizar).length,dias_sin_actualizar:7,respuestas_cliente:answered,tasa_aceptacion:answered?(accepted/answered*100).toFixed(1):null}};
    }
    if(path==='/api/clientes/')return [{id:1,nombre_legal:'Cliente de prueba',activo:true}];
    if(path==='/api/presupuestos/?page=1')return {count:2,previous:null,next:'/api/presupuestos/?page=2',results:firstPage};
    if(path==='/api/presupuestos/?page=2')return {count:2,previous:'/api/presupuestos/',next:null,results:[budget]};
    if(path==='/api/presupuestos/66/')return budget;
    if(path==='/api/presupuestos/65/')return firstPage.find(b=>b.id===65);
    if(path==='/api/presupuestos/66/historial/?page=1')return {count:0,previous:null,next:null,results:[]};
    throw Error('Ruta inesperada '+path);
  };
  const session={status:'authenticated',user:{id:9,username:'Cuenta de prueba',role}};
  const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};
  let renderer;
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Presupuestos)));await flush();});
  return {renderer,calls};
}
test('Gerencia distingue precios pendientes del cero en cartera y detalle',async()=>{
  const {renderer}=await mount('GERENCIA',[{...budget,id:65,codigo:'PRE-000065',estado:'PENDIENTE_FINANZAS',monto_neto:null,items:[{id:1,descripcion:'Material',cantidad:'1.000',unidad:'kg',precio_unitario:null,subtotal:null}]}]);
  try {
    assert.match(text(renderer.root),/1 con precios pendientes/);
    assert.match(text(renderer.root),/PRE-000065.*Precios pendientes/);
    await click(renderer.root,'Ver presupuesto');
    assert.match(text(renderer.root),/Total neto · CLPPrecios pendientes/);
    assert.match(text(renderer.root),/Material1.000kgPendiente—/);
  } finally {await act(async()=>renderer.unmount());}
});
async function click(root,label){
  const button=root.findAllByType('button').find(b=>text(b)===label);
  assert.ok(button,label);assert.ok(!button.props.disabled,label);
  await act(async()=>{await button.props.onClick();await flush();});
}
test('Presupuestos: detalle sustituye listado y conserva página y filtro al volver',async()=>{
  const {renderer,calls}=await mount('GERENCIA');
  try{
    const root=renderer.root;
    await act(async()=>{root.findByProps({id:'budget-filter'}).props.onChange({target:{value:'BORRADOR'}});await flush();});
    await click(root,'Siguiente');
    await click(root,'Ver presupuesto');
    assert.equal(root.findAllByProps({'aria-label':'Listado de presupuestos'}).length,0);
    const back=root.findByProps({className:'manager-budget-back'});
    assert.equal(text(back),'Volver al listado');
    assert.equal(back.findByType('svg').props['aria-hidden'],'true');
    assert.ok(root.findByProps({className:'commercial-page budgets-page'}));
    assert.equal(root.findByProps({id:'budget-items'}).props.hidden,false);
    assert.equal(root.findByProps({id:'budget-history'}).props.hidden,true);
    assert.equal(root.findAllByType('button').some(b=>text(b)==='Editar datos generales'),false);
    const before=calls.length;
    await click(root,'Historial comercial');
    assert.equal(root.findByProps({id:'budget-items'}).props.hidden,true);
    assert.equal(root.findByProps({id:'budget-history'}).props.hidden,false);
    assert.equal(calls.length,before+1);
    await click(root,'Volver al listado');
    assert.equal(root.findByProps({id:'budget-filter'}).props.value,'BORRADOR');
    assert.match(text(renderer.toJSON()),/PRE-000066/);
    assert.equal(calls.filter(p=>p.includes('seguimiento-comercial/')&&p.includes('page=2')).length,1);
  }finally{await act(async()=>renderer.unmount());}
});
test('Presupuestos: Finanzas conserva edición y puede cancelar antes de volver',async()=>{
  const {renderer}=await mount('ADMINISTRATIVO_FINANZAS');
  try{
    const root=renderer.root;
    await click(root,'Siguiente');await click(root,'Ver presupuesto');
    await click(root,'Editar datos generales');
    assert.ok(root.findByProps({className:'card-fyag commercial-form budget-header-form'}));
    assert.equal(root.findAllByType('button').some(b=>text(b)==='Volver al listado'),false);
    assert.equal(root.findAllByProps({'aria-label':'Listado de presupuestos'}).length,0);
    const description=root.findByProps({id:'com-descripcion'});
    assert.equal(description.props.value,'Servicio');
    await act(async()=>description.props.onChange({target:{value:'Borrador que se cancela'}}));
    assert.equal(root.findByProps({id:'com-descripcion'}).props.value,'Borrador que se cancela');
    await click(root,'Cancelar');
    assert.equal(root.findAllByType('form').length,0);
    assert.match(text(renderer.toJSON()),/Servicio/);
    assert.doesNotMatch(text(renderer.toJSON()),/Borrador que se cancela/);
    await click(root,'Volver al listado');
    assert.equal(root.findAllByProps({'aria-label':'Listado de presupuestos'}).length,1);
  }finally{await act(async()=>renderer.unmount());}
});

test('Presupuestos: filtro agrupa estados históricos sin duplicar opciones ni alterar registros',async()=>{
  const states=['BORRADOR','PENDIENTE_FINANZAS','PENDIENTE_GERENCIA','APROBADO_FINANZAS','APROBADO_GERENCIA','RECHAZADO_FINANZAS','RECHAZADO_GERENCIA'];
  const rows=states.map((estado,i)=>({...budget,id:100+i,codigo:'PRE-'+(100+i),estado}));
  const {renderer}=await mount('GERENCIA',rows);
  try{
    const root=renderer.root,select=root.findByProps({id:'budget-filter'});
    const options=select.findAllByType('option');
    assert.equal(options.length,9);
    assert.ok(options.every(option=>!text(option).includes('legado')));
    for(const [state,index] of [['PENDIENTE_FINANZAS',1],['APROBADO_FINANZAS',3],['RECHAZADO_FINANZAS',5]]){
      await act(async()=>{select.props.onChange({target:{value:state}});});
      const visible=root.findAllByType('button').filter(b=>b.props['data-manager-budget']);
      assert.deepEqual(visible.map(b=>b.props['data-manager-budget']),[100+index,101+index]);
    }
    assert.equal(root.findByProps({'aria-label':'Actualizar datos'}).props.disabled,false);
  }finally{await act(async()=>renderer.unmount());}
});

test('Gerencia carga cartera sin consultar clientes ni detalles y filtra por período',async()=>{
  const {renderer,calls}=await mount('GERENCIA');
  try{
    assert.deepEqual(calls,['/api/presupuestos/seguimiento-comercial/?page=1']);
    assert.match(text(renderer.toJSON()),/Seguimiento comercial/);
    await act(async()=>{renderer.root.findByProps({id:'manager-budget-from'}).props.onChange({target:{value:'2026-11-01'}});});
    await act(async()=>{renderer.root.findByType('form').props.onSubmit({preventDefault(){}});await flush();});
    assert.match(calls.at(-1),/desde=2026-11-01/);
    assert.ok(calls.every(p=>p.startsWith('/api/presupuestos/seguimiento-comercial/')));
  }finally{await act(async()=>renderer.unmount());}
});

test('Gerencia: aceptación entera sin decimal y seguimiento vacío sin acción innecesaria',async()=>{
  const {renderer}=await mount('GERENCIA',[{...budget,id:65,estado:'APROBADO_CLIENTE'}]);
  try{
    const root=renderer.root;
    assert.equal(text(root.findByProps({className:'commercial-donut'}).findByType('strong')),'100%');
    const followup=root.findByProps({className:'commercial-followup-body followup-clear'});
    assert.match(text(followup),/Sin pendientes de seguimiento/);
    assert.equal(followup.findAllByType('button').length,0);
  }finally{await act(async()=>renderer.unmount());}
});
test('Gerencia: aceptación conserva decimal significativo y seguimiento pendiente permite filtrar',async()=>{
  const rows=['APROBADO_CLIENTE','APROBADO_CLIENTE','RECHAZADO_CLIENTE','ENVIADO_CLIENTE'].map((estado,i)=>({...budget,id:100+i,estado,sin_actualizar:i===3}));
  const {renderer,calls}=await mount('GERENCIA',rows);
  try{
    const root=renderer.root;
    assert.equal(text(root.findByProps({className:'commercial-donut'}).findByType('strong')),'66,7%');
    assert.equal(text(root.findByProps({className:'commercial-followup-count'})),'1');
    assert.ok(root.findByProps({className:'commercial-followup-body followup-pending'}));
    await click(root,'Ver pendientes sin actualizar');
    assert.match(calls.at(-1),/sin_actualizar=true/);
    assert.deepEqual(root.findAllByType('button').filter(b=>b.props['data-manager-budget']).map(b=>b.props['data-manager-budget']),[103]);
    await click(root,'Ver todos');
    assert.doesNotMatch(calls.at(-1),/sin_actualizar=/);
  }finally{await act(async()=>renderer.unmount());}
});
