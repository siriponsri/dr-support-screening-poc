// Root smoke test: boot the review API and walk the synthetic case through AI, grade correction and
// read-back over real HTTP. (Replaces the legacy /ui page smoke tests, removed with the web/ folder.)
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const os = require('node:os');
const path = require('node:path');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dr-api-'));
const windowsVenvPython = path.resolve('.venv', 'Scripts', 'python.exe');
const posixVenvPython = path.resolve('.venv', 'bin', 'python');
const venvPython = process.env.DR_SUPPORT_TEST_PYTHON ||
  (fs.existsSync(windowsVenvPython) ? windowsVenvPython :
    (fs.existsSync(posixVenvPython) ? posixVenvPython : 'python3'));
// The legacy `dr_support.api:app` entry point honours MODEL_RUNTIME without the strict profile checks,
// so the synthetic fixture and mock models run on a CPU-only machine.
const server = spawn(venvPython, ['-m', 'uvicorn', 'dr_support.api:app', '--port', '8011'], {
  env: {...process.env,
    DR_SUPPORT_CASE_STORE: 'sqlite',
    DR_SUPPORT_STATE: path.join(tmp, 'review.sqlite'),
    DR_SUPPORT_WORKSPACE_CATALOG: path.join(tmp, 'workspaces.sqlite')}, stdio: 'ignore'});
const base = 'http://127.0.0.1:8011';

async function until(fn) {
  for (let i = 0; i < 240; i++) {
    try { if (await fn()) return; } catch {}
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw Error('Timed out waiting for the review API');
}

async function json(url, body) {
  const init = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)};
  const response = await fetch(base + url, init);
  const data = await response.json();
  assert.ok(response.ok, `${url}: HTTP ${response.status} ${JSON.stringify(data)}`);
  return data;
}

(async () => {
  await until(async () => (await fetch(base + '/health')).ok);
  const cases = await json('/v1/cases');
  assert.ok(cases.length >= 1, 'the synthetic workflow fixture must be admitted');
  const synthetic = cases.find((item) => item.image_id === 'SYNTH_001');
  assert.ok(synthetic, 'SYNTH_001 is admitted');

  await json('/v1/infer/global', {image_id: 'SYNTH_001', model_id: 'mock-global', modality: synthetic.modality});
  await json('/v1/infer/lesion-roi', {image_id: 'SYNTH_001', model_id: 'mock-lesion', modality: synthetic.modality});
  const analysed = await json('/v1/cases/SYNTH_001');
  assert.equal(analysed.global.grade, 2);

  await json('/v1/cases/SYNTH_001/review', {revision: analysed.revision, action: 'CORRECT_GRADE',
    reviewer: 'API synthetic reviewer', comment: '', grade: 3});
  const record = await json('/v1/cases/SYNTH_001');
  assert.equal(record.reviewed_grade, 3);
  assert.equal(record.cvat, null);
  assert.equal(record.lesion.lesions.length, 1);

  const models = await json('/v1/models');
  assert.ok(models.some((model) => model.model_id === 'prism-dr-5fold'));
  const home = await fetch(base + '/', {redirect: 'manual'});
  assert.ok([302, 307].includes(home.status) && home.headers.get('location') === '/app/');

  console.log(`PASS: real API: ${cases.length} admitted cases, AI suggestion, grade correction persistence, ` +
    'lesion result, model list, home redirect to /app/.');
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => server.kill());
