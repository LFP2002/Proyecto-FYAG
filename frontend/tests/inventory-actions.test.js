import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const root=new URL('../src/',import.meta.url);
const read=(name)=>fs.readFileSync(new URL(name,root),'utf8');

test('inventario ofrece todas las listas paginadas y filtros del contrato 019A/019B',()=>{
 const source=read('pages/Inventario.jsx');
 for(const endpoint of ['articulos/','existencias/','movimientos/','autorizaciones-entrega/','entregas/','autorizaciones-devolucion/','valorizaciones/','regularizaciones-iniciales/','estados-valorizacion/'])assert.ok(source.includes(endpoint),`falta ruta ${endpoint}`);
 for(const filter of ['articulo','obra','autorizacion','entrega','tipo','desde','hasta'])assert.ok(source.includes(`'${filter}'`),`falta filtro ${filter}`);
 assert.match(source,/Pager data=\{data\}/);
 assert.match(source,/dateRangeValid\(\)/);
});

test('acciones de materiales usan claves de idempotencia, cadenas decimales y rutas por operación',()=>{
 const source=read('integrations/InventoryActions.jsx');
 for(const endpoint of ['autorizaciones-entrega/','autorizaciones-devolucion/','entregas/','devoluciones/','valorizaciones/','regularizaciones-iniciales/'])assert.ok(source.includes(endpoint));
 assert.match(source,/clave_idempotencia:form\.key/);
 assert.match(source,/quantityInput\(value\)/);
 assert.match(source,/unitCostInput\(value\)/);
 assert.match(source,/body\[key\]=normalized/);
});

test('inventario no muestra proyecciones económicas de entregas a Bodeguero',()=>{
 const source=read('pages/Inventario.jsx');
 assert.match(source,/user\.role==='BODEGUERO'\?\['id','obra','articulo','cantidad','unidad','referencia','creado_en'\]/);
 assert.match(source,/\['BODEGUERO','SUPERVISOR_OBRAS','GERENCIA','ADMINISTRATIVO_FINANZAS'\]/);
});

test('Egresos usa filtros REST acordados, detalle, historial paginado y no pone claves en URL',()=>{
 const router=read('pages/Egresos.jsx'),source=read('integrations/FinanzasEgresos.jsx'),manager=read('integrations/GerenciaEgresos.jsx');
 assert.match(router,/user\.role==='GERENCIA'.*<GerenciaEgresos/);
 assert.match(router,/user\.role==='ADMINISTRATIVO_FINANZAS'.*<FinanzasEgresos/);
 for(const key of ['buscar','categoria','medio','activo','desde','hasta'])assert.match(source,new RegExp('const FILTERS=\\{[^}]*\\b'+key+':'));
 assert.match(source,/Concepto, beneficiario o código de obra/);
 assert.match(source,/const BASE='\/api\/finanzas\/egresos\/'/);
 assert.match(source,/Idempotency-Key/);
 assert.match(source,/api\.load\('detail',BASE\+id\+'\/'/);
 assert.match(source,/api\.load\('history',BASE\+id\+'\/historial\/\?page='\+p/);
 assert.match(source,/setPage=\{setHistoryPage\}/);
 assert.doesNotMatch(source,/clave_idempotencia=.*URLSearchParams/);
 assert.match(manager,/PATH=BASE\+'supervision-gerencial\/'/);
 assert.match(manager,/hp\+'\?page='\+page/);
 assert.doesNotMatch(manager,/Idempotency-Key/);
});

test('Chat usa ticket REST y WS sin transportar ticket por URL; avisos recuperan por REST',()=>{
 const source=read('pages/Chat.jsx');
 assert.match(source,/conexion\/.*method:'POST',body:\{\}/);
 assert.match(source,/new WebSocket\(`\$\{origin\}\/ws\/chat\/`\)/);
 assert.match(source,/JSON\.stringify\(\{tipo:'autenticar',ticket:issued\.ticket\}\)/);
 assert.match(source,/siguiente_antes_id/);
 assert.match(source,/conversaciones\/\$\{active\.id\}\/leido/);
 assert.match(source,/ultimo_mensaje_id:newest\.id/);
 assert.doesNotMatch(source,/body:\s*\{\s*ultimo_leido_mensaje_id:/);
 assert.match(source,/retryCount\.current>=5/);
});

test('Solicitudes y mermas usan scope/paginación de API y Técnico no recibe importes',()=>{
 const requests=read('pages/Solicitudes.jsx'),mermas=read('pages/Mermas.jsx');
 assert.match(requests,/solicitudes-materiales\/\?page=\$\{page\}/);
 assert.match(requests,/articulos-solicitables\/\?page=1/);
 assert.match(mermas,/const base=`\$\{ROOT\}mermas-\$\{scope\.toLowerCase\(\)\}\/`/);
 assert.match(mermas,/new URLSearchParams\(\{page:String\(page\)\}\)/);
 assert.match(mermas,/role!=='TECNICO'/);
});


test('Bodega permite elegir materiales e ingresos de la API sin escribir identificadores',()=>{
 const page=read('pages/Inventario.jsx'), actions=read('integrations/InventoryActions.jsx'), picker=read('integrations/InventoryPicker.jsx');
 assert.match(page,/InventoryPicker label="Material recibido"/);
 assert.doesNotMatch(page,/ID del artículo<input/);
 assert.match(actions,/refs.includes\(key\)\?<InventoryPicker/);
 assert.match(picker,/tipo:'INGRESO'/);
 assert.match(picker,/query.set\('buscar',search.trim\(\)\)/);
 assert.match(picker,/validatePage\(v,source.path\)/);
 assert.match(picker,/api.cancelRead\('choices'\)/);
 assert.match(page,/formatCLP\(value\)/);
});
