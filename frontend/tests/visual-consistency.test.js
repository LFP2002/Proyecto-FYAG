import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const read=path=>readFile(new URL('../src/'+path,import.meta.url),'utf8');

test('La escala institucional cubre los seis roles y se carga después de los estilos locales',async()=>{
 const [css,main,base,variables]=await Promise.all([read('styles/pages/role-typography.css'),read('main.jsx'),read('styles/base.css'),read('styles/variables.css')]);
 assert.match(css,/:root\[data-fyag-role\]\s*\{/);
 assert.doesNotMatch(css,/data-fyag-role=/);
 for(const [key,value] of [['module','1.75rem'],['detail','1.5rem'],['section','1.0625rem']]){
  assert.ok(css.includes('--fyag-'+key+'-title-size: '+value));
  assert.ok(css.includes('font-size:var(--fyag-'+key+'-title-size)'));
 }
 for(const selector of ['.page-head h1','.tec-heading h1','.bodega-heading h1','.ti-page-heading h1','.so-heading h1','.clientes-heading h1','.manager-work-heading h1','.audit-detail h1','.supervisor-requests .ss-heading h1','.supervisor-inventory .si-detail .si-heading h2'])assert.ok(css.includes(selector),selector);
 assert.match(css,/font-family:var\(--bs-body-font-family\)/);
 assert.match(variables,/'IBM Plex Sans'/);
 assert.match(base,/data-fyag-font-level='3'/);
 assert.ok(main.indexOf('role-typography.css')>main.indexOf('dark-mode.css'));
});

test('Las tarjetas de filtro comparten tinte y foco; las informativas no se seleccionan',async()=>{
 const [css,main,obra,alert,inv,sol]=await Promise.all(['styles/pages/interactive-cards.css','main.jsx','styles/pages/obras.css','styles/pages/alertas-gerencia.css','styles/pages/inventario-supervisor.css','styles/pages/solicitudes.css'].map(read));
 assert.match(main,/import '\.\/styles\/pages\/interactive-cards\.css';/);
 assert.match(css,/button:is\(\.portfolio-kpi,\.si-kpi,\.ss-kpi\)\[aria-pressed=true\]\s*\{\s*box-shadow:none;\s*background-color:color-mix/);
 assert.match(css,/button:is\(\.portfolio-kpi,\.si-kpi,\.ss-kpi\):focus-visible\s*\{\s*outline:2px solid var\(--fyag-blue\)/);
 assert.match(css,/--fyag-selection-strength:7%/);
 assert.match(css,/--fyag-selection-strength:16%/);
 assert.match(css,/data-fyag-theme='dark'[^\n]+\[aria-pressed=true\]\s*\{[^}]*background-color:color-mix[^}]*!important/s);
 for(const local of [obra,alert,inv,sol])assert.doesNotMatch(local,/(?:portfolio-kpi|manager-alert-kpi|si-kpi|ss-kpi)\[aria-pressed=true\][^{]*\{[^}]*?(?:outline\s*:|box-shadow\s*:)/s);
 assert.match(css,/\.manager-work-tabs,\.budget-tabs,\.cobranzas-tabs,\.so-tabs,\.si-tabs,\.tec-tabs,\.bodega-tabs,\.ti-tabs/);
});
