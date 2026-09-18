'use strict';
const $ = s => document.querySelector(s);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const grades = ['No DR predicted','Mild','Moderate','Severe','Proliferative'];
// Lesion colors intentionally stay separate from the KKU product chrome and match the owner-created CVAT labels.
const colors = {MICROANEURYSM:'#00d9ff',HEMORRHAGE:'#8bff3d',HARD_EXUDATE:'#ff3cac',SOFT_EXUDATE:'#8b5cf6'};
let cases = [], models = [], selected = '01_dr', current = null, busy = false;
let reviewer = sessionStorage.getItem('reviewer') || '';

async function api(path, data) {
  if (window.DR_PREVIEW) {
    if (data !== undefined) throw new Error('Read-only preview. Start the API runtime to run inference or record reviews.');
    if (path === '/v1/cases') return window.DR_PREVIEW.cases;
    if (path === '/v1/models') return window.DR_PREVIEW.models;
    throw new Error('This action requires the API runtime.');
  }
  const response = await fetch(path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Request rejected. Check the input and reload.');
  return payload;
}
function status(message, error=false) {
  $('#status').textContent = message;
  $('#status').className = error ? 'error' : '';
}
async function action(fn, message) {
  if (busy) return;
  busy = true;
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  status('Working… Please keep this page open.');
  try { await fn(); await load(); status(message); }
  catch (e) { status(e.message, true); }
  finally { busy = false; render(); }
}
function heading(title, subtitle, extra='') {
  return `<div class="heading"><div><div class="kicker">CLINICIAN REVIEW</div><h1>${escapeHTML(title)}</h1><p class="sub">${escapeHTML(subtitle)}</p></div>${extra}</div>`;
}
function nav() {
  const p = location.hash.slice(1) || 'queue';
  return ['queue','case','annotation','models'].includes(p) ? p : 'queue';
}
function caseSelector() {
  return `<div class="top-actions"><label for="case-select" class="help">Case</label><select id="case-select">${cases.map(c=>`<option value="${escapeHTML(c.image_id)}" ${c.image_id===selected?'selected':''}>${escapeHTML(c.image_id)}</option>`).join('')}</select></div>`;
}
function badge(s) {
  const value = (s || 'PENDING').replaceAll('_',' ');
  return `<span class="badge badge-${escapeHTML((s || 'PENDING').toLowerCase())}">${escapeHTML(value)}</span>`;
}
function legend() {
  return `<div class="legend">${Object.entries(colors).map(([label,color])=>`<span><b style="background:${color}"></b>${escapeHTML(label.replaceAll('_',' '))}</span>`).join('')}</div>`;
}
function reviewLesions(c) {
  return c.lesion_review?.lesions || c.lesion?.lesions || [];
}
function svgN(value) { return Math.round(Number(value)*1000)/1000; }
function pointPairs(points=[]) {
  const pairs=[]; for(let i=0;i+1<points.length;i+=2) pairs.push([svgN(points[i]),svgN(points[i+1])]); return pairs;
}
function renderImportedShape(a) {
  const g=a?.geometry || {}; const pts=pointPairs(g.points); const stroke=colors[a.canonical_label] || '#FFFFFF';
  const common=`fill="none" stroke="${stroke}" stroke-width="3.5" vector-effect="non-scaling-stroke" class="overlay-imported"`;
  if(g.type==='rectangle' && pts.length===2){const [[x1,y1],[x2,y2]]=pts;return `<rect x="${svgN(Math.min(x1,x2))}" y="${svgN(Math.min(y1,y2))}" width="${svgN(Math.abs(x2-x1))}" height="${svgN(Math.abs(y2-y1))}" ${common}/>`;}
  if(g.type==='ellipse' && pts.length===2){const [[cx,cy],[right,top]]=pts;return `<ellipse cx="${cx}" cy="${cy}" rx="${svgN(Math.abs(right-cx))}" ry="${svgN(Math.abs(top-cy))}" ${common}/>`;}
  if(g.type==='polygon' && pts.length>=3)return `<polygon points="${pts.map(p=>p.join(',')).join(' ')}" ${common}/>`;
  if(g.type==='polyline' && pts.length>=2)return `<polyline points="${pts.map(p=>p.join(',')).join(' ')}" ${common}/>`;
  if(g.type==='points' && pts.length>=1)return pts.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="5" fill="${stroke}" stroke="#FFFFFF" stroke-width="1.5" vector-effect="non-scaling-stroke" class="overlay-imported"/>`).join('');
  return '';
}
function overlaySVG(c) {
  const ai=reviewLesions(c); const imported=Array.isArray(c.annotations)?c.annotations:[]; const hasImported=imported.length>0;
  const aiMarkup=ai.map(s=>`<rect x="${s.rectangle[0]}" y="${s.rectangle[1]}" width="${s.rectangle[2]-s.rectangle[0]}" height="${s.rectangle[3]-s.rectangle[1]}" fill="none" stroke="${colors[s.canonical_label]}" stroke-width="2" vector-effect="non-scaling-stroke" class="overlay-ai ${hasImported?'overlay-ai-superseded':''}"/>`).join('');
  const importedMarkup=imported.map(renderImportedShape).join('');
  return `<svg viewBox="0 0 ${c.width} ${c.height}" aria-label="AI suggestions and imported CVAT corrections">${aiMarkup}${importedMarkup}</svg>`;
}
function overlaySourceLegend(c) {
  if(!Array.isArray(c.annotations) || !c.annotations.length) return '';
  return `<div class="overlay-source-legend"><span><i class="source-ai"></i>AI pre-label</span><span><i class="source-imported"></i>CVAT imported correction</span></div>`;
}
function imagePanel(c, overlay=false) {
  return `<section class="panel image-panel"><div class="image-top"><strong>${escapeHTML(c.image_id)}</strong><span>${c.width} × ${c.height} · ${escapeHTML(c.modality)}</span></div><div class="canvas"><img src="${c.image_url}" alt="${escapeHTML(c.source_type)} review sample ${escapeHTML(c.image_id)}">${overlay?overlaySVG(c):''}</div>${overlay?legend()+overlaySourceLegend(c):''}<div class="image-foot">${escapeHTML(c.source_type)} sample · ${c.source_type==='PUBLIC'?'HRF / MedOtter · viewer JPEG derivative · CC BY 4.0':'Generated synthetic workflow fixture'}<br>No lesion or ordinal grading ground truth is supplied for this smoke workflow.</div></section>`;
}
function queue() {
  $('#content').innerHTML = heading('Review Queue','Select a case, inspect AI suggestions, and record a clinician decision.',`<span class="tag">${cases.filter(c=>c.source_type==='PUBLIC').length} public samples</span>`)+
    `<div class="queue-controls"><input id="search" type="search" placeholder="Search case ID" aria-label="Search case ID"><select id="filter" aria-label="Review state"><option value="ALL">All cases</option><option value="PENDING">Pending</option><option value="REVIEWED">Reviewed</option><option value="NEEDS_CORRECTION">Needs correction</option><option value="ESCALATED">Escalated</option></select></div><section class="panel table-panel"><table><thead><tr><th>Image</th><th>Source</th><th>AI grade suggestion</th><th>Review state</th><th></th></tr></thead><tbody id="rows"></tbody></table></section>`;
  const rows = () => {
    const q = $('#search').value.toLowerCase();
    const filter = $('#filter').value;
    $('#rows').innerHTML = cases.filter(c => c.image_id.toLowerCase().includes(q) && (filter==='ALL' || c.state===filter)).map(c=>`<tr><td><div class="sample"><img class="thumb" src="${c.image_url}" alt=""><div><div class="id">${escapeHTML(c.image_id)}</div><div class="subcell">CFP · ${c.width} × ${c.height}</div></div></div></td><td>${escapeHTML(c.source_type)}</td><td>${c.global?.grade != null?`${c.global.grade} · ${grades[c.global.grade]}`:'Not run'}</td><td>${badge(c.state)}</td><td><button class="text-button" data-open="${escapeHTML(c.image_id)}">Review</button></td></tr>`).join('');
    document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{selected=b.dataset.open;location.hash='case';});
  };
  rows(); $('#search').oninput=rows; $('#filter').onchange=rows;
}
function caseReview(c) {
  const g = c.global;
  const manual = g?.grade == null;
  const reviewSource = c.grade_review_source ? c.grade_review_source.replaceAll('_',' ') : '';
  $('#content').innerHTML = heading('Case Review','Inspect the retinal image before accepting, correcting, or recording a manual grade.',caseSelector())+
    `<div class="review-layout"><div class="stack">${imagePanel(c)}<section class="panel"><div class="section-head"><h2>Review history</h2>${badge(c.state)}</div>${c.events.length?`<ol class="history">${c.events.slice(-6).map(e=>`<li>${escapeHTML(e.action.replaceAll('_',' '))}${e.reviewer?' · '+escapeHTML(e.reviewer):''}${e.comment?' — '+escapeHTML(e.comment):''}</li>`).join('')}</ol>`:'<p class="sub">No review decisions yet.</p>'}</section></div><section class="panel decision-panel"><div class="section-head"><h2>Grade suggestion</h2><span class="eyebrow">AI ASSIST</span></div>${g?.grade != null?`<div class="grade"><div class="grade-number">${g.grade}</div><div><strong>${grades[g.grade]}</strong><span>AI suggestion · ${Math.round(g.confidence*100)}% model score</span></div></div>${g.probabilities.map((p,i)=>`<div class="prob"><span>Grade ${i}</span><span class="bar"><i style="width:${p*100}%"></i></span><span>${Math.round(p*100)}%</span></div>`).join('')}`:'<div class="empty-compact">No grade suggestion yet. Manual clinician grading remains available.</div>'}<p class="help">Model scores are uncalibrated and are not the probability that a diagnosis is correct.</p><button id="run-global">${g?'Run grading again':'Run grading'}</button><details><summary>Model & limitations</summary><p>${escapeHTML(g?.model_id || (c.source_type==='SYNTHETIC'?'Synthetic fixture':'RETFound APTOS'))}</p><ul class="warnings">${(g?.warnings||['Research use only']).map(w=>`<li>${escapeHTML(w)}</li>`).join('')}</ul></details><hr class="rule"><h2>Your review</h2>${c.reviewed_grade!=null?`<div class="review-result"><strong>Recorded grade ${c.reviewed_grade}</strong><span>${grades[c.reviewed_grade]}${reviewSource?' · '+escapeHTML(reviewSource):''}</span></div>`:''}<label class="field" for="reviewer">Reviewer name</label><input id="reviewer" autocomplete="name" value="${escapeHTML(reviewer)}" placeholder="Name for the review record"><label class="field" for="comment">Review note <span>(optional)</span></label><textarea id="comment" placeholder="Add context for this decision"></textarea><div class="actions top-gap"><button class="primary" data-review="ACCEPT" ${manual?'disabled':''}>Accept AI grade</button><button data-review="MARK_INCORRECT" ${manual?'disabled':''}>Mark AI incorrect</button></div><label class="field" for="grade">${manual?'Manual grade':'Corrected grade'}</label><select id="grade">${grades.map((s,i)=>`<option value="${i}">${i} · ${s}</option>`).join('')}</select><div class="actions top-gap-small"><button data-review="CORRECT_GRADE">${manual?'Record manual grade':'Correct grade'}</button><button class="escalate" data-review="ESCALATE">Escalate</button></div><hr class="rule"><a class="inline-link" href="#annotation">Inspect lesion suggestions →</a></section></div>`;
  $('#run-global').onclick=()=>action(()=>api('/v1/infer/global',{image_id:c.image_id,model_id:c.source_type==='SYNTHETIC'?'mock-global':'retfound-aptos5',modality:c.modality}),'Grade suggestion ready for review.');
  bindReview(c);
}
function bindReview(c) {
  if ($('#reviewer')) $('#reviewer').oninput=e=>{reviewer=e.target.value;sessionStorage.setItem('reviewer',reviewer);};
  document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>action(()=>api(`/v1/cases/${c.image_id}/review`,{
    revision:c.revision, action:b.dataset.review, reviewer:reviewer.trim(), comment:$('#comment')?.value||'',
    grade:b.dataset.review==='CORRECT_GRADE'?Number($('#grade').value):null
  }),'Review recorded.'));
}
function annotation(c) {
  const link = c.cvat?.job_url || c.cvat?.task_url;
  const view = c.lesion_review;
  const rawCount = view?.raw_count ?? c.lesion?.lesions?.length ?? 0;
  const shownCount = view?.suggestion_count ?? rawCount;
  $('#content').innerHTML = heading('Annotation','Review a bounded pre-label set and refine geometry in CVAT Online.',caseSelector())+
    `<div class="review-layout"><div class="stack">${imagePanel(c,true)}<section class="panel"><div class="section-head"><h2>Imported annotation review</h2>${c.lesion_review_state?badge(c.lesion_review_state):''}</div><p class="sub">${c.annotations?`${c.annotations.length} shapes imported`:'No annotations synced yet.'}</p>${c.annotations?`<details><summary>Inspect imported coordinates</summary><div class="table-panel"><table><thead><tr><th>Label</th><th>Type</th><th>Points</th></tr></thead><tbody>${c.annotations.map(a=>`<tr><td>${escapeHTML(a.canonical_label)}</td><td>${escapeHTML(a.geometry.type)}</td><td>${escapeHTML(JSON.stringify(a.geometry.points))}</td></tr>`).join('')}</tbody></table></div></details>`:''}<p class="help">Before sync, the overlay shows the bounded AI pre-label subset. After sync, imported CVAT corrections are drawn as solid thicker geometry while the original AI boxes remain dashed and faded for provenance. Imported corrections remain unconfirmed until a clinician reviews them.</p></section></div><section class="panel decision-panel"><div class="section-head"><h2>Lesion suggestions</h2><span class="eyebrow">PRE-LABEL</span></div>${c.lesion?`<div class="metric-row"><div><strong>${shownCount}</strong><span>shown / pushed</span></div><div><strong>${rawCount}</strong><span>raw model output</span></div></div>`:'<div class="empty-compact">Pre-label has not been run.</div>'}<p class="help">Raw model output is retained for provenance. Display/CVAT suggestions are bounded by configurable thresholds and safety caps; counts are not performance metrics.</p><button id="run-lesion" class="primary">${c.lesion?'Run pre-label again':'Run pre-label'}</button>${view?`<details><summary>Review filter policy</summary><dl class="meta"><dt>Max per class</dt><dd>${view.policy.max_per_class}</dd><dt>Max total</dt><dd>${view.policy.max_total}</dd><dt>Threshold overrides</dt><dd>${escapeHTML(JSON.stringify(view.policy.thresholds))}</dd></dl></details>`:''}<details><summary>Model limitations</summary><ul class="warnings">${(c.lesion?.warnings||['PRISM-DR research-only pipeline']).map(w=>`<li>${escapeHTML(w)}</li>`).join('')}</ul></details><hr class="rule"><h2>CVAT workspace</h2><p class="sub">Project 445923 · rectangle / polygon / ellipse / points / polyline sync supported</p><div class="actions top-gap"><button id="send-cvat">Prepare CVAT task</button>${link?`<a class="button" href="${link}" target="_blank" rel="noopener">Open in CVAT ↗</a>`:''}<button id="sync-cvat">Sync corrections</button></div><p class="help"><strong>Mask sync is not supported in v0.1.2.</strong> Do not use CVAT Mask for this acceptance pass. Unsupported geometry is rejected rather than silently dropped.</p><hr class="rule"><label class="field" for="reviewer">Reviewer name</label><input id="reviewer" value="${escapeHTML(reviewer)}"><div class="actions top-gap-small"><button data-review="CONFIRM_ANNOTATIONS" ${!c.annotation_hash?'disabled':''}>Confirm imported annotations</button></div><hr class="rule"><h3>Manual sync fallback</h3><a class="inline-link" href="/v1/cases/${c.image_id}/export" target="_blank" rel="noopener">Export case & suggestion JSON</a><label class="field" for="manual">Import reviewed JSON envelope</label><input id="manual" type="file" accept="application/json"><p class="help">Imports remain unverified until reviewed. See the runbook for the exact envelope.</p></section></div>`;
  $('#run-lesion').onclick=()=>action(()=>api('/v1/infer/lesion-roi',{image_id:c.image_id,model_id:c.source_type==='SYNTHETIC'?'mock-lesion':'prism-dr-5fold',modality:c.modality}),'Lesion suggestions ready.');
  $('#send-cvat').onclick=()=>action(()=>api(`/v1/cases/${c.image_id}/cvat/send`,{}),'CVAT task ready.');
  $('#sync-cvat').onclick=()=>action(()=>api(`/v1/cases/${c.image_id}/cvat/sync`,{}),'Corrections synced. Please review before confirming.');
  $('#manual').onchange=e=>{const file=e.target.files[0];if(file)action(async()=>{const data=JSON.parse(await file.text());await api(`/v1/cases/${c.image_id}/manual-sync`,{...data,revision:c.revision});},'Manual annotations imported; review required.');};
  bindReview(c);
}
function modelPage() {
  $('#content').innerHTML = heading('Models','Provider readiness, supported modality, provenance, and limitations.')+
    `<div class="models">${models.map(m=>`<section class="panel model-card"><div class="section-head"><h2>${escapeHTML(m.model_id)}</h2>${badge(m.status)}</div><dl class="meta"><dt>Task</dt><dd>${escapeHTML(m.task)}</dd><dt>Modality</dt><dd>${escapeHTML(m.modalities.join(', '))}</dd>${m.revision?`<dt>Source revision</dt><dd class="mono">${escapeHTML(m.revision)}</dd>`:''}</dl>${m.preprocessing?`<details><summary>Preprocessing</summary><p>${escapeHTML(m.preprocessing)}</p></details>`:''}<ul class="warnings">${m.warnings.map(w=>`<li>${escapeHTML(w)}</li>`).join('')}</ul></section>`).join('')}</div><p class="help page-help">Configured assets are verified when loaded. Each response carries checkpoint hashes and image provenance. UWF is unsupported. No scientific champion or performance claim is made here.</p>`;
}
function render() {
  const page = nav();
  document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===page));
  current = cases.find(c=>c.image_id===selected) || cases[0];
  if (current) selected = current.image_id;
  if (page==='queue') queue(); else if (page==='models') modelPage(); else if (current) (page==='case'?caseReview:annotation)(current); else $('#content').innerHTML='<p>No samples available.</p>';
  if ($('#case-select')) $('#case-select').onchange=e=>{selected=e.target.value;render();};
  if (window.DR_PREVIEW) {
    document.querySelectorAll('[data-review],#run-global,#run-lesion,#send-cvat,#sync-cvat,#manual').forEach(e=>e.disabled=true);
    document.querySelectorAll('a[href^="/v1/"]').forEach(e=>e.remove());
  }
}
async function load() { [cases,models] = await Promise.all([api('/v1/cases'),api('/v1/models')]); render(); }
window.addEventListener('hashchange',()=>{status('');render();});
load().catch(e=>status(e.message,true));
