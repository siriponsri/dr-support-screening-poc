const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

let source = fs.readFileSync('web/app.js','utf8');
source = source.split('load().catch')[0];
const context = {
  console,
  window: {addEventListener:()=>{}},
  document: {querySelector:()=>null, querySelectorAll:()=>[]},
  sessionStorage: {getItem:()=>'', setItem:()=>{}},
  location: {hash:''},
  fetch: async()=>{throw new Error('not used')},
  setTimeout,
};
vm.createContext(context);
vm.runInContext(source, context);

const base = {canonical_label:'MICROANEURYSM'};
const rectangle = context.renderImportedShape({...base,geometry:{type:'rectangle',points:[10,20,40,60]}});
assert.match(rectangle, /<rect/);
assert.match(rectangle, /x="10"/);
assert.match(rectangle, /width="30"/);
assert.match(rectangle, /class="overlay-imported"/);

const polygon = context.renderImportedShape({...base,geometry:{type:'polygon',points:[1,2,3,4,5,6]}});
assert.match(polygon, /<polygon/);
const polyline = context.renderImportedShape({...base,geometry:{type:'polyline',points:[1,2,3,4]}});
assert.match(polyline, /<polyline/);
const points = context.renderImportedShape({...base,geometry:{type:'points',points:[1,2,3,4]}});
assert.equal((points.match(/<circle/g)||[]).length,2);
const ellipse = context.renderImportedShape({...base,geometry:{type:'ellipse',points:[20,30,35,10]}});
assert.match(ellipse, /<ellipse/);
assert.match(ellipse, /rx="15"/);
assert.match(ellipse, /ry="20"/);

const c = {
  width:640,height:480,
  lesion_review:{lesions:[{canonical_label:'MICROANEURYSM',rectangle:[250,160,264,176]}]},
  annotations:[{...base,geometry:{type:'rectangle',points:[244.5546875,145.220703125,277.2546875,179.120703125]}}]
};
const svg = context.overlaySVG(c);
assert.match(svg, /overlay-ai-superseded/);
assert.match(svg, /244\.555/);
assert.match(svg, /width="32\.7/);
assert.match(svg, /overlay-imported/);
console.log('PASS: imported CVAT geometry overrides visual emphasis while preserving dashed AI provenance; all supported shape renderers present.');
