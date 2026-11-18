// Prueba opt-in contra Edge/Chromium y una sesión TI en un laboratorio QA.
// No instala dependencias, no crea cuentas ni envía escrituras al backend.
// FYAG_QA_CDP=http://127.0.0.1:<puerto> FYAG_QA_ORIGIN=<origen QA>
// FYAG_QA_EVIDENCE=<directorio externo> node qa/usuarios-responsive.mjs
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const endpoint = new URL(process.env.FYAG_QA_CDP);
assert(['127.0.0.1', 'localhost'].includes(endpoint.hostname), 'CDP solo loopback');
const origin = new URL(process.env.FYAG_QA_ORIGIN).origin;
const output = process.env.FYAG_QA_EVIDENCE;
assert(output, 'Indique directorio externo de evidencia');
const targets = await (await fetch(new URL('/json/list', endpoint))).json();
const target = targets.find((item) => item.type === 'page' && new URL(item.url).origin === origin);
assert(target, 'Abra Usuarios y roles con una cuenta TI exclusivamente QA');
const ws = new WebSocket(target.webSocketDebuggerUrl), pending = new Map();
let sequence = 0;
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
ws.onmessage = ({ data }) => {
  const message = JSON.parse(data), task = pending.get(message.id);
  if (!task) return;
  pending.delete(message.id);
  message.error ? task.reject(new Error(message.error.message)) : task.resolve(message.result);
};
const call = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) => {
  const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  assert(!result.exceptionDetails, result.exceptionDetails?.text);
  return result.result.value;
};
const measures = () => evaluate(`(() => {
  const root = document.documentElement;
  return { viewport: innerWidth, clientWidth: root.clientWidth, scrollWidth: root.scrollWidth,
    regions: [...document.querySelectorAll('.usuarios-table-region')].map(e => ({
      label: e.getAttribute('aria-label'), clientWidth: e.clientWidth, scrollWidth: e.scrollWidth,
      tabIndex: e.tabIndex, overflow: getComputedStyle(e).overflowX })),
    tables: [...document.querySelectorAll('.usuarios-page [role=table]')].map(e => ({
      label: e.getAttribute('aria-label'), minWidth: getComputedStyle(e).minWidth })),
    uncontained: [...document.querySelectorAll('.usuarios-page *')].filter(e =>
      !e.closest('.usuarios-table-region') && e.getBoundingClientRect().right > root.clientWidth + 1
    ).map(e => ({ tag: e.tagName, className: e.className })) };
})()`);
const evidence = [];
mkdirSync(output, { recursive: true });
try {
  assert(await evaluate(`!!document.querySelector('.usuarios-page [aria-label="Cuentas de usuario"]')`));
  for (const width of [375, 768, 1280]) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 950, deviceScaleFactor: 1, mobile: false });
    await evaluate(`new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`);
    const measured = await measures(); evidence.push({ case: 'listado', ...measured });
    assert.equal(measured.scrollWidth, measured.clientWidth, `Documento desbordado a ${width}`);
    assert.equal(measured.regions.length, 2);
    assert(measured.regions.every(r => r.tabIndex === 0 && r.overflow === 'auto'));
    assert.equal(measured.uncontained.length, 0);
    if (width < 900) assert(measured.regions.every(r => r.scrollWidth > r.clientWidth));
    await evaluate(`document.querySelector('.usuarios-table-region').focus()`);
    await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await evaluate(`new Promise(r => setTimeout(r, 150))`);
    const keyboard = await evaluate(`({focused: document.activeElement.classList.contains('usuarios-table-region'), scrollLeft: document.querySelector('.usuarios-table-region').scrollLeft})`);
    assert(keyboard.focused); if (width < 900) assert(keyboard.scrollLeft > 0, 'Scroll de teclado no funciona');
    evidence.push({ case: 'teclado', width, ...keyboard });
    const image = await call('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(output, `usuarios-${width}.png`), Buffer.from(image.data, 'base64'));
  }
  // Prueba local de estrés textual: no modifica datos persistidos.
  await evaluate(`(() => { const cells = document.querySelectorAll('.usuarios-page [role=cell]'); cells[0].textContent = 'Nombre'.repeat(30); cells[1].textContent = 'correo'.repeat(35) + '@example.test'; })()`);
  await call('Emulation.setDeviceMetricsOverride', { width: 375, height: 950, deviceScaleFactor: 1, mobile: false });
  const longText = await measures(); evidence.push({ case: 'texto largo DOM sintético', ...longText });
  assert.equal(longText.scrollWidth, longText.clientWidth);
  await evaluate(`document.querySelectorAll('.usuarios-table-region').forEach(e => e.scrollLeft = 0)`);
  await evaluate(`([...document.querySelectorAll('button')].find(e => e.textContent === 'Nueva cuenta')).click()`);
  await evaluate(`new Promise(r => requestAnimationFrame(r))`);
  assert(await evaluate('!!document.querySelector("#usuario-email")'));
  const form = await measures(); evidence.push({ case: 'formulario', ...form });
  assert.equal(form.scrollWidth, form.clientWidth);
  assert(await evaluate(`document.querySelector('#usuario-email').getBoundingClientRect().right <= document.documentElement.clientWidth`));
  await evaluate(`([...document.querySelectorAll('button')].find(e => e.textContent === 'Cancelar')).click()`);
  console.log('Usuarios: listado 375/768/1280, scroll de teclado, textos largos y formulario OK.');
} finally {
  writeFileSync(join(output, 'usuarios-responsive.json'), JSON.stringify(evidence, null, 2));
  ws.close();
}
