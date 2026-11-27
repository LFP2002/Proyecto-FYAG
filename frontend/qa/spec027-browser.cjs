// Playwright con Firefox real, instalación externa de QA, sin trazas ni credenciales impresas.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { firefox } = require('playwright');

const roles = ['ADMINISTRADOR_TI', 'GERENCIA', 'ADMINISTRATIVO_FINANZAS', 'SUPERVISOR_OBRAS', 'TECNICO', 'BODEGUERO'];
const api = new URL(process.env.FYAG_POSTMAN_URL);
assert.equal(api.hostname, '127.0.0.1');
const origin = 'http://127.0.0.1:25173';

async function validar(page, role) {
  const root = page.locator('html');
  const theme = name => page.waitForFunction(name => document.documentElement.dataset.fyagTheme === name, name);
  const geometry = () => page.evaluate(() => ({ width: document.documentElement.clientWidth, actual: document.documentElement.scrollWidth }));
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    const menu = page.getByRole('button', { name: 'Menú', exact: true });
    if (await menu.isVisible()) {
      await menu.click();
      assert.ok(await page.locator('#fyag-modules-nav').isVisible());
      await page.getByRole('button', { name: 'Cerrar menú', exact: true }).click();
    }
    for (const mode of ['light', 'dark']) {
      if (await root.getAttribute('data-fyag-theme') !== mode) {
        await page.getByRole('button', { name: `Activar modo ${mode === 'dark' ? 'oscuro' : 'claro'}` }).click();
      }
      await theme(mode);
      let previous = 0;
      const trigger = page.getByRole('button', { name: 'Tamaño de letra' });
      await trigger.click();
      for (let level = 0; level < 4; level++) {
        await page.waitForFunction(level => document.documentElement.dataset.fyagFontLevel === String(level), level);
        const font = await root.evaluate(node => parseFloat(getComputedStyle(node).fontSize));
        assert.ok(font > previous, `${role}: escala no creciente`);
        previous = font;
        const panel = await page.locator('#fyag-font-options').boundingBox();
        assert.ok(panel && panel.x >= -1 && panel.x + panel.width <= width + 1, `${role}: selector fuera de vista ${width}/${mode}/${level}`);
        const geo = await geometry();
        if (geo.actual > geo.width + 1) {
          const fuera = await page.evaluate(() => Array.from(document.querySelectorAll('main *'))
            .filter(el => el.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
            .slice(0, 12).map(el => `${el.tagName}.${el.getAttribute('class') || ''}`));
          console.error(`${role}: ${fuera.join(', ')}`);
        }
        assert.ok(geo.actual <= geo.width + 1, `${role}: desborde ${width}/${mode}/${level}: ${geo.actual}`);
        if (level < 3) await page.getByRole('button', { name: 'Aumentar tamaño' }).click();
      }
      await page.getByRole('button', { name: 'Restablecer', exact: true }).click();
      await trigger.click();
    }
  }
}

async function main() {
  const root = path.resolve(__dirname, '..');
  const { createServer } = await import(pathToFileURL(require.resolve('vite', { paths: [root] })).href);
  const server = await createServer({ root, server: { host: '127.0.0.1', port: 25173, strictPort: true,
    proxy: { '/api': { target: api.origin, changeOrigin: false }, '/ws': { target: api.origin, ws: true } } } });
  await server.listen();
  let browser;
  try {
    browser = await firefox.launch();
    for (const role of roles) {
      const context = await browser.newContext();
      try {
        const page = await context.newPage();
        await page.goto(origin);
        const email = role === 'ADMINISTRADOR_TI' ? 'primera-ti@qa.test' : `${role.toLowerCase()}@qa.test`;
        const password = process.env[role === 'ADMINISTRADOR_TI' ? 'FYAG_POSTMAN_NUEVA' : 'FYAG_POSTMAN_CLAVE'];
        assert.ok(password);
        await page.locator('#f-email').fill(email);
        await page.locator('#f-pass').fill(password);
        const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login/'));
        await page.getByRole('button', { name: 'Ingresar' }).click();
        assert.equal((await login).status(), 200, `${role}: login`);
        await page.waitForFunction(role => document.documentElement.dataset.fyagRole === role, role);
        const nav = page.locator('#fyag-modules-nav');
        assert.equal(await nav.getByText('Usuarios y roles', { exact: true }).count() > 0, role === 'ADMINISTRADOR_TI', `${role}: navegación TI`);
        await validar(page, role);
        console.log(`${role}: 4 anchos × 2 temas × 4 escalas`);
      } finally { await context.close(); }
    }
  } finally { await browser?.close(); await server.close(); }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
