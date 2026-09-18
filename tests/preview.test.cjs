const {JSDOM}=require('jsdom');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const dom=new JSDOM(fs.readFileSync('PREVIEW.html','utf8'),{url:'http://preview.local/',runScripts:'outside-only'});
 const w=dom.window;
 for(const s of w.document.querySelectorAll('script:not([src])')) w.eval(s.textContent);
 w.fetch=()=>{throw Error('Preview must not call a server');};
 w.eval(fs.readFileSync('web/app.js','utf8'));
 await new Promise(r=>setTimeout(r,50));
 assert.equal(w.DR_PREVIEW.cases.length,11);
 for(const route of ['case','annotation','models','queue']){
  w.location.hash=route;await new Promise(r=>setTimeout(r,20));
  for(const b of w.document.querySelectorAll('[data-review],#run-global,#run-lesion,#send-cvat,#sync-cvat,#manual'))assert.ok(b.disabled);
  assert.equal(w.document.querySelectorAll('a[href^="/v1/"]').length,0);
 }
 dom.window.close();console.log('PASS: offline preview, 11 samples, no API calls, mutation controls disabled');
})().catch(e=>{console.error(e);process.exit(1);});
