import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';

let server, AuthProvider, AppProvider, DesktopLayout;
before(async () => {
  server = await createServer({
    configFile: false, esbuild: { jsx: 'automatic' },
    server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ AppProvider } = await server.ssrLoadModule('/src/context/AppContext.jsx'));
  ({ default: DesktopLayout } = await server.ssrLoadModule('/src/components/layouts/DesktopLayout.jsx'));
});
after(async () => { await server?.close(); });

async function mount(role = 'GERENCIA') {
  const session = { status: 'authenticated', user: { id: 99, username: 'Prueba de navegación', email: 'navegacion@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, logout: async () => {} };
  let renderer;
  await act(async () => {
    renderer = Renderer.create(React.createElement(AuthProvider, { client },
      React.createElement(AppProvider, null, React.createElement(DesktopLayout, null, React.createElement('p', null, 'Contenido')))));
  });
  return renderer;
}
const textContent = (node) => typeof node === 'string' ? node : (node.children || []).map(textContent).join('');
const btn = (renderer, label) => renderer.root.findAllByType('button').find((button) => textContent(button) === label);

test('menú móvil plegable: abre, cambia módulo, cierra y marca el enlace seleccionado', async () => {
  const view = await mount();
  try {
    const menu = btn(view, 'Menú');
    assert.ok(menu);
    assert.equal(menu.props['aria-expanded'], false);
    let nav = view.root.findByProps({ id: 'fyag-modules-nav' });
    assert.doesNotMatch(nav.props.className, /is-open/);
    await act(async () => { menu.props.onClick(); });
    nav = view.root.findByProps({ id: 'fyag-modules-nav' });
    assert.match(nav.props.className, /is-open/);
    assert.equal(btn(view, 'Cerrar menú').props['aria-expanded'], true);
    assert.equal(btn(view, 'Dashboard').props['aria-current'], 'page');
    assert.equal(btn(view, 'Clientes'), undefined);
    await act(async () => { btn(view, 'Presupuestos').props.onClick(); });
    nav = view.root.findByProps({ id: 'fyag-modules-nav' });
    assert.doesNotMatch(nav.props.className, /is-open/);
    assert.equal(btn(view, 'Menú').props['aria-expanded'], false);
    assert.equal(btn(view, 'Presupuestos').props['aria-current'], 'page');
  } finally { await act(async () => view.unmount()); }
});

test('menú móvil se cierra con Escape sin cambiar el módulo', async () => {
  const view = await mount('SUPERVISOR_OBRAS');
  try {
    await act(async () => { btn(view, 'Menú').props.onClick(); });
    const nav = view.root.findByProps({ id: 'fyag-modules-nav' });
    let prevented = false;
    await act(async () => { nav.props.onKeyDown({ key: 'Escape', preventDefault() { prevented = true; } }); });
    assert.equal(prevented, true);
    assert.equal(btn(view, 'Menú').props['aria-expanded'], false);
    assert.equal(btn(view, 'Obras').props['aria-current'], 'page');
    assert.equal(btn(view, 'Clientes'), undefined);
  } finally { await act(async () => view.unmount()); }
});

test('diseño móvil no deja la navegación como barra horizontal desplazable', async () => {
  const css = await readFile(new URL('../src/styles/layout.css', import.meta.url), 'utf8');
  assert.match(css, /@media \(max-width: 880px\)/);
  assert.match(css, /\.fyag-side\.is-open\s*\{[^}]*display:\s*grid;/s);
  assert.match(css, /\.fyag-side\s*\{[^}]*display:\s*none;/s);
  assert.doesNotMatch(css, /overflow-x:\s*auto/);
});


test('tamaño global: cuatro tamaños, restablecimiento y persistencia local', async()=>{
  const oldStorage=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document');
  const values=new Map(), attrs=new Map();
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)}});
  Object.defineProperty(globalThis,'document',{configurable:true,value:{documentElement:{setAttribute:(k,v)=>attrs.set(k,v),removeAttribute:k=>attrs.delete(k)}}});
  let view;
  const control=(label)=>view.root.findByProps({'aria-label':label});
  try{
    view=await mount();
    assert.equal(control('Tamaño de letra').props['aria-expanded'],false);
    const minus=()=>control('Disminuir tamaño');
    const plus=()=>control('Aumentar tamaño');
    const level=()=>control('Nivel de tamaño de letra').props.children;
    const click=async(button)=>{await act(async()=>button().props.onClick());};
    await click(()=>control('Tamaño de letra'));
    assert.equal(level(),1);
    assert.equal(minus().props['aria-disabled'],true);
    await click(minus);
    assert.equal(level(),1);
    for(const expected of [2,3,4]){
      await click(plus);
      assert.equal(level(),expected);
      assert.equal(control('Tamaño de letra').props['aria-expanded'],true);
      assert.equal(attrs.get('data-fyag-font-level'),String(expected-1));
    }
    assert.equal(plus().props['aria-disabled'],true);
    await click(plus);
    assert.equal(level(),4);
    await click(minus);
    assert.equal(level(),3);
    assert.equal(values.get('fyag.font-level'),'2');
    await act(async()=>view.unmount());view=null;
    assert.equal(attrs.has('data-fyag-font-level'),false);
    view=await mount();
    await click(()=>control('Tamaño de letra'));
    assert.equal(level(),3);
    await act(async()=>view.unmount());view=null;
    values.set('fyag.font-level','4'); // Preferencia anterior al retiro del quinto tamaño.
    view=await mount();
    await click(()=>control('Tamaño de letra'));
    assert.equal(level(),4);
    await click(()=>view.root.findByProps({className:'fyag-font-reset'}));
    assert.equal(level(),1);
    assert.equal(attrs.get('data-fyag-font-level'),'0');
    assert.equal(values.get('fyag.font-level'),'0');
    assert.equal(control('Tamaño de letra').props['aria-expanded'],true);
    const picker=view.root.findByProps({className:'fyag-font-picker'});
    await act(async()=>picker.props.onKeyDown({key:'Escape',preventDefault(){}}));
    assert.equal(control('Tamaño de letra').props['aria-expanded'],false);
  }finally{
    if(view)await act(async()=>view.unmount());
    if(oldStorage)Object.defineProperty(globalThis,'localStorage',oldStorage);else delete globalThis.localStorage;
    if(oldDocument)Object.defineProperty(globalThis,'document',oldDocument);else delete globalThis.document;
  }
});

test('modo oscuro persistente y acento visual asociado al rol autenticado',async()=>{
  const oldStorage=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document');
  const values=new Map(),attrs=new Map();
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)}});
  Object.defineProperty(globalThis,'document',{configurable:true,value:{documentElement:{setAttribute:(k,v)=>attrs.set(k,v),removeAttribute:k=>attrs.delete(k)}}});
  let view;
  try{
    view=await mount('SUPERVISOR_OBRAS');
    const toggle=()=>view.root.findByProps({'aria-label':'Activar modo oscuro'});
    assert.ok(toggle());
    await act(async()=>toggle().props.onClick());
    assert.equal(attrs.get('data-fyag-theme'),'dark');
    assert.equal(attrs.get('data-fyag-role'),'SUPERVISOR_OBRAS');
    assert.equal(values.get('fyag.theme'),'dark');
    assert.equal(view.root.findByProps({'aria-label':'Activar modo claro'}).props['aria-pressed'],true);
    await act(async()=>view.root.findByProps({'aria-label':'Activar modo claro'}).props.onClick());
    assert.equal(attrs.get('data-fyag-theme'),'light');
    assert.equal(values.get('fyag.theme'),'light');
  }finally{
    if(view)await act(async()=>view.unmount());
    if(oldStorage)Object.defineProperty(globalThis,'localStorage',oldStorage);else delete globalThis.localStorage;
    if(oldDocument)Object.defineProperty(globalThis,'document',oldDocument);else delete globalThis.document;
  }
});

test('tema oscuro global sobrescribe superficies blancas de todas las páginas y conserva texto legible',async()=>{
  const css=await readFile(new URL('../src/styles/dark-mode.css',import.meta.url),'utf8');
  const entry=await readFile(new URL('../src/main.jsx',import.meta.url),'utf8');
  assert.match(entry,/styles\/pages\/solicitudes\.css';\s*import '\.\/styles\/dark-mode\.css';/);
  assert.match(css,/\.dash-filterbar \.form-label[^}]*color:#e2ecf7 !important/s);
  assert.match(css,/\.dash-filterbar input\[type='date'\][^{]*\{[^}]*background-color:#111c28 !important/s);
  assert.match(css,/\.table > tbody > tr > td[^}]*background-color:#1b2633 !important/s);
  assert.match(css,/\.table > thead > tr > th[^}]*background-color:#29394a !important/s);
  assert.match(css,/\.app-root :where\(\.portfolio-kpi\)[^}]*background-color:#1b2633 !important/s);
  assert.match(css,/\.portfolio-kpi\.portfolio-amber[^}]*background-color:#342b1e !important/s);
  assert.match(css,/\.portfolio-kpi\.portfolio-blue[^}]*background-color:#202f43 !important/s);
  assert.match(css,/\.portfolio-kpi\.portfolio-green[^}]*background-color:#1e342d !important/s);
  assert.match(css,/\.portfolio-kpi\.portfolio-red[^}]*background-color:#3b272b !important/s);
  assert.match(css,/\.app-root :where\(\.commercial-empty,.finance-empty,.fyag-empty[^}]*background-color:#202b38 !important/s);
  assert.match(css,/\.app-root :where\(\.manager-eg-chart \.commercial-empty\)[^}]*display:grid/s);
  assert.match(css,/\.dash-filterbar,.card-fyag,.dash-kpi,.kpi,[^}]*background-color:#1b2633 !important/s);
  assert.match(css,/\.app-root :where\(\.alert-info,.bg-info-subtle\)[^}]*color:#c8e0ff !important/s);
  assert.match(css,/\.inventory-attention button:not\(:disabled\):hover[^}]*background-color:#263748 !important/s);
  assert.match(css,/\.inventory-losses > div[^}]*background-color:#243243 !important/s);
  assert.match(css,/\.inventory-losses > div span,.inventory-losses > div small[^}]*color:#d0dbe8 !important/s);
  assert.match(css,/\.trow\.thead,.thead[^}]*background-color:#29394a !important/s);
  assert.match(css,/\.usuarios-matriz \.trow:not\(\.thead\):nth-child\(odd\)[^}]*background-color:#243243 !important/s);
  assert.match(css,/\.usuarios-pill\[data-tone='ti'\][^}]*color:#c8e0ff !important/s);
  assert.match(css,/\.auditoria-empty[^}]*background-color:#1b2633 !important/s);
  assert.match(css,/\.commercial-toolbar,.commercial-period,.mermas-filters[^}]*background-color:#1b2633 !important/s);
  assert.match(css,/\.mermas-filters label[^}]*color:#e2ecf7 !important/s);
  assert.match(css,/\.mermas-filters \.form-control,.mermas-filters \.form-select[^}]*background-color:#111c28 !important/s);
});

test('selector de letra compacto con puntero y tres controles', async()=>{
  const css=await readFile(new URL('../src/styles/layout.css',import.meta.url),'utf8');
  assert.match(css,/\.fyag-font-options::before\s*\{[^}]*rotate\(45deg\)/);
  assert.match(css,/\.fyag-font-options\s*\{[^}]*width:184px/);
  assert.match(css,/\.fyag-font-controls\s*\{[^}]*grid-template-columns:44px minmax\(0,1fr\) 44px/);
});

test('Gerencia: nueve accesos principales, auditoría secundaria y sin módulos operativos de materiales',async()=>{
  const view=await mount();
  try{
    const nav=view.root.findByProps({id:'fyag-modules-nav'});
    assert.deepEqual(nav.findAllByType('button').map(textContent),['Dashboard','Presupuestos','Obras','Cobranzas','Egresos','Inventario','Alertas','Reportes','Chat interno']);
    assert.equal(btn(view,'Auditoría'),undefined);
    await act(async()=>view.root.findByProps({'aria-label':'Menú de usuario'}).props.onClick());
    assert.ok(btn(view,'Auditoría'));
    await act(async()=>btn(view,'Auditoría').props.onClick());
    assert.equal(view.root.findByProps({'aria-label':'Menú de usuario'}).props['aria-expanded'],false);
    await act(async()=>view.root.findByProps({'aria-label':'Menú de usuario'}).props.onClick());
    assert.equal(btn(view,'Auditoría').props['aria-current'],'page');
  }finally{await act(async()=>view.unmount());}
});
test('Supervisor conserva solicitudes, mermas y auditoría en navegación principal',async()=>{
  const view=await mount('SUPERVISOR_OBRAS');
  try{
    assert.ok(btn(view,'Solicitudes de materiales'));
    assert.ok(btn(view,'Mermas'));
    assert.ok(btn(view,'Auditoría'));
    assert.equal(view.root.findAllByProps({'aria-label':'Menú de usuario'}).length,0);
  }finally{await act(async()=>view.unmount());}
});
