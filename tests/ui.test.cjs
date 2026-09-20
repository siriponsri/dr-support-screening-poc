const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const os = require('node:os');
const path = require('node:path');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(),'dr-ui-'));
const venvPython = path.resolve('.venv','Scripts','python.exe');
// Spawn the legacy review-API entrypoint directly. This path honours
// MODEL_RUNTIME without the new strict profile invariants so the historical
// UI smoke (synthetic-only Analyze + correction flow) continues to pass.
const server = spawn(venvPython,['-m','uvicorn','dr_support.api:app','--port','8011'],{
  env:{...process.env,
    DR_SUPPORT_STATE:path.join(tmp,'review.sqlite'),
    DR_SUPPORT_WORKSPACE_CATALOG:path.join(tmp,'workspaces.sqlite')},stdio:'ignore'});
const base='http://127.0.0.1:8011';

async function until(fn){for(let i=0;i<120;i++){try{if(await fn())return;}catch{}await new Promise(r=>setTimeout(r,50));}throw Error('Timed out waiting for UI state');}

(async()=>{
  await until(async()=> (await fetch(base+'/health')).ok);
  const dom=new JSDOM(fs.readFileSync('web/index.html','utf8'),{url:base+'/ui/index.html',runScripts:'outside-only'});
  const w=dom.window;
  w.fetch=(url,opts)=>fetch(new URL(url,base),opts);
  w.eval(fs.readFileSync('web/app.js','utf8'));
  const q=s=>w.document.querySelector(s);

  await until(()=>q('#rows')?.children.length===11);
  assert.equal(w.document.querySelectorAll('[data-nav]').length,3);

  q('[data-open="SYNTH_001"]').click();
  await until(()=>q('#run-analyze'));
  q('#run-analyze').click();
  await until(()=>q('.grade-number')?.textContent==='2');
  await until(()=>q('.canvas svg rect'));

  q('#reviewer').value='UI synthetic reviewer'; q('#reviewer').dispatchEvent(new w.Event('input'));
  q('[data-review="CORRECT_GRADE"]').click();
  await until(()=>q('#grade-adjust')?.style.display !== 'none');
  q('#grade').value='3'; q('[data-review="CORRECT_GRADE"]').click();
  await until(()=>q('#content').textContent.includes('Recorded grade 3'));

  w.location.hash='models';
  await until(()=>q('#content').textContent.includes('prism-dr-5fold'));

  const record=await (await fetch(base+'/v1/cases/SYNTH_001')).json();
  assert.equal(record.reviewed_grade,3);
  assert.equal(record.cvat,null);
  assert.equal(record.lesion.lesions.length,1);

  dom.window.close();
  console.log('PASS: DOM + real API: 11 samples, navigation, unified Analyze, grade correction persistence, lesion overlay, Models & Audit.');
  console.log('LIMITATION: jsdom validates DOM behavior, not browser pixel layout.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.kill());
