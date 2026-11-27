// Newman 6, Node >=22. Solo loopback y datos sintéticos. No imprime cuerpos ni exporta variables.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const newman = require('newman');

const base = local('FYAG_POSTMAN_URL');
const mail = process.env.FYAG_POSTMAN_MAILPIT && local('FYAG_POSTMAN_MAILPIT');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function local(name) {
  const url = new URL(process.env[name]);
  assert.equal(url.hostname, '127.0.0.1');
  assert.match(url.protocol, /^https?:$/);
  return url.origin;
}

async function run(name, variables, items, iterations = 1) {
  const collection = JSON.parse(fs.readFileSync(path.join(__dirname, `../docs/postman/SPEC-027-${name}.postman_collection.json`)));
  if (items) collection.item = items.map(index => collection.item[index]);
  const result = await new Promise((resolve, reject) => {
    newman.run({ collection, reporters: [], iterationCount: iterations, timeoutRequest: 5000,
      envVar: Object.entries({ api: base, baseUrl: base, ...variables }).map(([key, value]) => ({ key, value })) },
    (error, summary) => error ? reject(new Error(`${name}: Newman no terminó`)) : resolve(summary));
  });
  const { requests, assertions } = result.run.stats;
  console.log(`${name}: ${requests.total} solicitudes, ${assertions.total - assertions.failed}/${assertions.total} aserciones`);
  if (result.run.failures.length) {
    for (const failure of result.run.failures) console.error(`${failure.source?.name}: ${failure.error?.test || failure.error?.name}`);
    throw new Error(`${name}: falló la colección`);
  }
  assert.ok(assertions.total > 0);
}

async function token(email, subject) {
  assert.match(email, /@qa\.test$/);
  for (let n = 0; n < 30; n++) {
    const list = await fetch(`${mail}/api/v1/messages`).then(r => r.json());
    const found = list.messages.find(m => m.Subject.startsWith(subject) && m.To.some(to => to.Address === email));
    if (found) {
      const message = await fetch(`${mail}/api/v1/message/${found.ID}`).then(r => r.json());
      const secret = message.Text.match(/#token=([A-Za-z0-9_-]{43})\b/);
      assert.ok(secret, 'fragmento esperado en Mailpit');
      return secret[1];
    }
    await delay(1000);
  }
  throw new Error('No llegó el mensaje sintético esperado');
}

async function auth(email, password) {
  const csrf = await fetch(`${base}/api/auth/csrf/`);
  assert.equal(csrf.status, 200);
  const cookie = csrf.headers.getSetCookie()[0].split(';')[0];
  const response = await fetch(`${base}/api/auth/login/`, { method: 'POST',
    headers: { Cookie: cookie, 'X-CSRFToken': (await csrf.json()).csrfToken, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }) });
  assert.equal(response.status, 200);
  return response.json();
}

async function main() {
  const env = process.env;
  const ti = 'primera-ti@qa.test';
  const objetivo = 'objetivo@qa.test';
  switch (process.argv[2]) {
    case 'setup':
      await run('setup', { email_qa: ti, password_qa: env.FYAG_POSTMAN_CLAVE, clave_qa: env.FYAG_POSTMAN_INSTALACION });
      break;
    case 'correo': {
      const variables = { email_qa: ti };
      await run('verificacion', variables, [0, 1]);
      await run('verificacion', { ...variables, token_mailpit: await token(ti, 'Verificación de correo') }, [0, 2, 3]);
      await run('recuperacion', variables, [0, 1]);
      await run('recuperacion', { ...variables, clave_qa: env.FYAG_POSTMAN_NUEVA, token_qa: await token(ti, 'Solicitud de recuperación') }, [0, 2, 3]);
      assert.ok((await auth(ti, env.FYAG_POSTMAN_NUEVA)).access);
      break;
    }
    case 'bloqueos': {
      const admin = await auth(ti, env.FYAG_POSTMAN_NUEVA);
      assert.ok(admin.access);
      await run('bloqueos', { correoSintetico: objetivo, claveSintetica: 'incorrecta-sintetica' }, [0, 1, 2], 5);
      const id = Number(env.FYAG_POSTMAN_OBJETIVO_ID);
      assert.ok(Number.isSafeInteger(id) && id > 0);
      const reset = await fetch(`${base}/api/usuarios/${id}/restablecer-clave/`, { method: 'POST',
        headers: { Authorization: `Bearer ${admin.access}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo: 'Validación sintética SPEC-027' }) });
      assert.ok(reset.ok, `restablecimiento HTTP ${reset.status}`);
      const temporal = (await reset.json()).credencial_temporal;
      assert.ok(temporal);
      const until = Number(reset.headers.get('Retry-After') || 61);
      await delay(until * 1000);
      const cambio = await auth(objetivo, temporal);
      assert.equal(cambio.estado, 'CAMBIO_OBLIGATORIO');
      await run('bloqueos', { desafioTemporal: cambio.desafio, nuevaClaveSintetica: env.FYAG_POSTMAN_CLAVE,
        tiAccessToken: admin.access, usuarioId: id }, [0, 3, 4, 5]);
      assert.ok((await auth(objetivo, env.FYAG_POSTMAN_CLAVE)).access);
      break;
    }
    default: throw new Error('Elegir setup, correo o bloqueos');
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
