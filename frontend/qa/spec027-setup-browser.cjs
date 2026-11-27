// Firefox real; API simulada para controlar latencia y fallos sin tocar una instalación.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { firefox } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const { createServer } = await import(pathToFileURL(require.resolve('vite', { paths: [root] })).href);
  const server = await createServer({ root, server: { host: '127.0.0.1', port: 25174, strictPort: true } });
  await server.listen();
  const origin = 'http://127.0.0.1:25174';
  let browser;
  try {
    browser = await firefox.launch();
    console.log(`Firefox ${browser.version()}`);
    const context = await browser.newContext({ colorScheme: 'dark' });
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    const requests = [];
    let respond, ready, status, restore = false, pending = true, failSetup = true;
    const delayStatus = () => { ready = new Promise(resolve => { respond = resolve; }); };
    delayStatus();
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url()).pathname;
      requests.push(url);
      const json = (value, status = 200) => route.fulfill({ status, json: value });
      switch (url) {
        case '/api/auth/setup/estado/':
          if (ready) await ready;
          if (status === 'offline') return route.abort('failed');
          if (status === 'invalid') return json({ pendiente: 'true' });
          if (status === 'unavailable') return json({ pendiente: true }, 503);
          return json({ pendiente: pending });
        case '/api/auth/csrf/': return json({ csrfToken: 'csrf-sintetico' });
        case '/api/auth/refresh/': return restore ? json({ access: 'acceso-sintetico' }) : json({}, 401);
        case '/api/auth/login/': return json({ access: 'acceso-sintetico', csrfToken: 'csrf-rotado' });
        case '/api/auth/me/': return json({ id: 1, username: 'ti_qa', email: 'primera-ti@qa.test', role: 'ADMINISTRADOR_TI' });
        case '/api/auth/setup/':
          assert.equal(route.request().method(), 'POST');
          assert.equal(route.request().headers()['x-csrftoken'], 'csrf-sintetico');
          if (failSetup) return json({}, 409);
          pending = false;
          return json({ detail: 'Cuenta TI creada. Ya puedes iniciar sesión.' }, 201);
        default: return json({ results: [] });
      }
    });
    const statePath = '/api/auth/setup/estado/';
    const login = page.getByRole('button', { name: 'Ingresar', exact: true });
    const submit = page.getByRole('button', { name: 'Crear cuenta TI', exact: true });
    const retry = page.getByRole('button', { name: 'Reintentar', exact: true });
    const urlIs = pathname => page.waitForURL(origin + pathname);

    await page.goto(origin);
    await page.getByText('Comprobando el estado de la instalación…').waitFor();
    assert.equal(await login.count(), 0);
    assert.equal(await submit.count(), 0);
    status = 'offline';
    respond();
    await retry.waitFor();
    assert.deepEqual(requests, [statePath]);
    for (const outcome of ['invalid', 'unavailable']) {
      status = outcome;
      await retry.click();
      await retry.waitFor();
      assert.equal(page.url(), origin + '/');
      assert.equal(await login.count() + await submit.count(), 0);
    }
    status = null;
    await retry.click();
    await urlIs('/configuracion-inicial');
    await submit.waitFor();
    assert.deepEqual(requests, Array(4).fill(statePath));
    assert.equal(await page.evaluate(() => history.length), 1);
    assert.equal(await page.locator('html').getAttribute('data-fyag-theme'), 'dark');

    const theme = page.getByRole('button', { name: 'Tema oscuro' });
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      for (const mode of ['dark', 'light']) {
        if (await theme.getAttribute('aria-pressed') !== String(mode === 'dark')) await theme.click();
        for (const [level, font] of [16, 18, 20, 22].entries()) {
          await page.getByLabel('Tamaño de letra').selectOption(String(level));
          await page.waitForFunction(({ mode, font }) => {
            const root = document.documentElement;
            return root.dataset.fyagTheme === mode && getComputedStyle(root).fontSize === `${font}px`;
          }, { mode, font });
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
            `Desborde ${width}/${mode}/${level}`);
          assert.ok(await submit.isVisible());
        }
      }
    }
    const password = 'Sintetica-QA-Setup-95+!';
    const secrets = { password, password_confirm: password, clave_instalacion: 'A'.repeat(43) };
    const fill = async values => {
      for (const [key, value] of Object.entries(values)) await page.locator(`#setup-${key}`).fill(value);
    };
    await fill({ first_name: 'Nombre', last_name: 'QA', username: 'ti_qa', email: 'primera-ti@qa.test', ...secrets });
    await submit.click();
    await page.getByRole('alert').getByText('No se autorizó el aprovisionamiento.', { exact: false }).waitFor();
    for (const key of Object.keys(secrets)) assert.equal(await page.locator(`#setup-${key}`).inputValue(), '');
    failSetup = false;
    await fill(secrets);
    await submit.click();
    await urlIs('/');
    await login.waitFor();
    await page.getByRole('status').getByText('Cuenta TI creada.', { exact: false }).waitFor();
    assert.deepEqual(requests.slice(4), Array(2).fill(['/api/auth/csrf/', '/api/auth/setup/']).flat());
    assert.equal(await page.evaluate(() => history.length), 1);

    requests.length = 0;
    await page.locator('#f-email').fill('primera-ti@qa.test');
    await page.locator('#f-pass').fill(password);
    await login.click();
    await page.waitForFunction(() => document.documentElement.dataset.fyagRole === 'ADMINISTRADOR_TI');
    assert.deepEqual(requests.slice(0, 3), ['/api/auth/csrf/', '/api/auth/login/', '/api/auth/me/']);

    requests.length = 0;
    await page.goto(origin + '/configuracion-inicial');
    await urlIs('/');
    await login.waitFor();
    assert.deepEqual(requests, [statePath]);
    assert.equal(await submit.count(), 0);

    requests.length = 0;
    await page.goto(origin);
    await login.waitFor();
    assert.deepEqual(requests, [statePath, '/api/auth/csrf/', '/api/auth/refresh/']);

    requests.length = 0;
    restore = true;
    await page.goto(origin);
    await page.waitForFunction(() => document.documentElement.dataset.fyagRole === 'ADMINISTRADOR_TI');
    assert.deepEqual(requests.slice(0, 4), [statePath, '/api/auth/csrf/', '/api/auth/refresh/', '/api/auth/me/']);
    assert.equal(await login.count(), 0);

    for (const [route, heading] of [['/restablecer-clave', /contraseña/i], ['/verificar-correo', /correo/i]]) {
      requests.length = 0;
      await page.goto(origin + route);
      await page.getByRole('heading', { name: heading }).waitFor();
      assert.equal(requests.includes(statePath), false);
    }
    console.log('OK: carga, fallos y reintentos, rutas, alta sin sesión, restauración y 32 combinaciones visuales.');
  } finally {
    await browser?.close();
    await server.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
