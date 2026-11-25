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
    const choose=async number=>{
      await act(async()=>control('Tamaño de letra').props.onClick());
      assert.equal(control('Tamaño de letra').props['aria-expanded'],true);
      assert.equal(view.root.findAllByType('button').filter(b=>b.props.className==='fyag-font-option').length,4);
      await act(async()=>control(['Tamaño normal','Tamaño mediano','Tamaño grande','Tamaño muy grande'][number-1]).props.onClick());
      assert.equal(control('Tamaño de letra').props['aria-expanded'],false);
      assert.equal(attrs.get('data-fyag-font-level'),String(number-1));
    };
    for(const number of [2,3,4,1,4])await choose(number);
    assert.equal(values.get('fyag.font-level'),'3');
    await act(async()=>view.unmount());view=null;
    assert.equal(attrs.has('data-fyag-font-level'),false);
    values.set('fyag.font-level','4'); // Preferencia anterior al retiro del quinto tamaño.
    view=await mount();
    await act(async()=>control('Tamaño de letra').props.onClick());
    assert.equal(control('Tamaño muy grande').props['aria-pressed'],true);
    assert.equal(control('Tamaño normal').props['aria-pressed'],false);
    await act(async()=>view.root.findByProps({className:'fyag-font-reset'}).props.onClick());
    assert.equal(attrs.get('data-fyag-font-level'),'0');
    assert.equal(values.get('fyag.font-level'),'0');
    await act(async()=>control('Tamaño de letra').props.onClick());
    const picker=view.root.findByProps({className:'fyag-font-picker'});
    await act(async()=>picker.props.onKeyDown({key:'Escape',preventDefault(){}}));
    assert.equal(control('Tamaño de letra').props['aria-expanded'],false);
  }finally{
    if(view)await act(async()=>view.unmount());
    if(oldStorage)Object.defineProperty(globalThis,'localStorage',oldStorage);else delete globalThis.localStorage;
    if(oldDocument)Object.defineProperty(globalThis,'document',oldDocument);else delete globalThis.document;
  }
});

test('selector de letra compacto con puntero y cuatro columnas', async()=>{
  const css=await readFile(new URL('../src/styles/layout.css',import.meta.url),'utf8');
  assert.match(css,/\.fyag-font-options::before\s*\{[^}]*rotate\(45deg\)/);
  assert.match(css,/\.fyag-font-grid\s*\{[^}]*repeat\(4,/);
});
