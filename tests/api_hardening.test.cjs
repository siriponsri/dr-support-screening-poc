const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync(path.resolve('web','app.js'), 'utf8')
  .split('load().catch')[0];

async function runScenario(label, responses, assert_fn) {
  const calls = [];
  const ctx = {
    console,
    window: {addEventListener: () => {}},
    document: {querySelector: () => null, querySelectorAll: () => []},
    sessionStorage: {getItem: () => '', setItem: () => {}},
    location: {hash: ''},
    fetch: async (url, init) => {
      calls.push({url, init});
      const next = responses.shift();
      if (!next) throw new Error('No response queued for ' + url);
      return next;
    },
    setTimeout,
  };
  vm.createContext(ctx);
  vm.runInContext(source, ctx);

  try {
    await assert_fn(ctx);
    console.log(`PASS: ${label}`);
  } catch (err) {
    console.error(`FAIL: ${label}:`, err && err.stack ? err.stack : err);
    process.exitCode = 1;
  }
}

(async () => {
  // 1. text/plain HTTP 500 → must surface a useful error, not JSON.parse.
  await runScenario(
    'api() surfaces text/plain HTTP 500 without JSON.parse crash',
    [{
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: {get: (k) => (k.toLowerCase() === 'content-type' ? 'text/plain' : '')},
      text: async () => 'Internal Server Error',
    }],
    async (ctx) => {
      let caught;
      try { await ctx.api('/v1/models'); }
      catch (e) { caught = e; }
      assert.ok(caught, 'api() must throw on a 5xx response');
      assert.ok(/HTTP 500/.test(caught.message),
                `error must mention HTTP 500, got: ${caught.message}`);
      assert.ok(/Internal Server Error/.test(caught.message),
                `error must surface plain-text body, got: ${caught.message}`);
      assert.ok(/v1\/models/.test(caught.message),
                `error must include the request path, got: ${caught.message}`);
    }
  );

  // 2. Valid JSON 200 → returns parsed payload.
  await runScenario(
    'api() returns parsed JSON on 200',
    [{
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: {get: () => 'application/json'},
      text: async () => '[{"model_id":"x"}]',
    }],
    async (ctx) => {
      const body = await ctx.api('/v1/models');
      // vm realms do not share Array prototypes; compare via JSON.
      assert.equal(JSON.stringify(body), JSON.stringify([{model_id: 'x'}]));
    }
  );

  // 3. Valid JSON 4xx → surfaces FastAPI `detail` if present.
  await runScenario(
    'api() surfaces FastAPI detail on JSON 4xx',
    [{
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      headers: {get: () => 'application/json'},
      text: async () => '{"detail":"Modality does not match admitted image"}',
    }],
    async (ctx) => {
      let caught;
      try { await ctx.api('/v1/infer/global', {x: 1}); }
      catch (e) { caught = e; }
      assert.ok(caught, 'api() must throw on a 4xx response');
      assert.equal(caught.message, 'Modality does not match admitted image');
    }
  );

  // 4. Empty 200 → returns empty object, never undefined.
  await runScenario(
    'api() returns {} on empty 200 body',
    [{
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: {get: () => 'application/json'},
      text: async () => '',
    }],
    async (ctx) => {
      const body = await ctx.api('/v1/cases');
      assert.equal(typeof body, 'object');
      assert.equal(JSON.stringify(body), '{}');
    }
  );

  // 5. HTML body 500 → useful error, no JSON.parse crash.
  await runScenario(
    'api() surfaces HTML HTTP 500 as a useful error',
    [{
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      headers: {get: () => 'text/html'},
      text: async () => '<html><body>502 Bad Gateway</body></html>',
    }],
    async (ctx) => {
      let caught;
      try { await ctx.api('/v1/models'); }
      catch (e) { caught = e; }
      assert.ok(caught, 'api() must throw on a 5xx response');
      assert.ok(/HTTP 502/.test(caught.message),
                `error must mention HTTP 502, got: ${caught.message}`);
    }
  );

  if (process.exitCode) process.exit(process.exitCode);
})();
