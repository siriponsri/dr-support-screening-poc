'use strict';

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const grades = ['No DR predicted','Mild','Moderate','Severe','Proliferative'];
const lesionLabels = ['MICROANEURYSM','HEMORRHAGE','HARD_EXUDATE','SOFT_EXUDATE'];
const colors = {MICROANEURYSM:'#00d9ff',HEMORRHAGE:'#8bff3d',HARD_EXUDATE:'#ff3cac',SOFT_EXUDATE:'#8b5cf6'};

let cases = [], models = [], selected = '01_dr', current = null, busy = false;
let reviewer = sessionStorage.getItem('reviewer') || '';
let filterState = {MICROANEURYSM:true,HEMORRHAGE:true,HARD_EXUDATE:true,SOFT_EXUDATE:true,imported:true,ai:true};
let viewer = {scale:1,panX:0,panY:0,dragging:false,lastX:0,lastY:0,minScale:0.2,maxScale:8};

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

function status(message, type='') {
  const el = $('#status');
  el.textContent = message;
  el.className = type;
}

async function action(fn, message) {
  if (busy) return;
  busy = true;
  $$('button').forEach(b => b.disabled = true);
  status('Working… Please keep this page open.');
  try {
    await fn();
    await load();
    status(message, 'success');
  } catch (e) {
    status(e.message, 'error');
  } finally {
    busy = false;
    render();
  }
}

function nav() {
  const p = location.hash.slice(1) || 'worklist';
  return ['worklist','case','models'].includes(p) ? p : 'worklist';
}

function heading(title, subtitle, extra='') {
  return `<div class="heading"><div><div class="kicker">CLINICIAN REVIEW</div><h1>${escapeHTML(title)}</h1><p class="sub">${escapeHTML(subtitle)}</p></div>${extra}</div>`;
}

function badge(s) {
  const value = (s || 'PENDING').replaceAll('_',' ');
  return `<span class="badge badge-${escapeHTML((s || 'PENDING').toLowerCase())}">${escapeHTML(value)}</span>`;
}

function updateCaseSelector() {
  const sel = $('#case-select');
  if (!sel) return;
  const opts = cases.map(c => `<option value="${escapeHTML(c.image_id)}" ${c.image_id===selected?'selected':''}>${escapeHTML(c.image_id)}</option>`).join('');
  if (sel.innerHTML !== opts) sel.innerHTML = opts;
  sel.onchange = e => { selected = e.target.value; render(); };
}

function reviewLesions(c) {
  return c.lesion_review?.lesions || c.lesion?.lesions || [];
}

function svgN(value) { return Math.round(Number(value)*1000)/1000; }
function pointPairs(points=[]) {
  const pairs=[]; for(let i=0;i+1<points.length;i+=2) pairs.push([svgN(points[i]),svgN(points[i+1])]); return pairs;
}

function renderImportedShape(a) {
  const g = a?.geometry || {}; const pts = pointPairs(g.points); const stroke = colors[a.canonical_label] || '#FFFFFF';
  const common = `fill="none" stroke="${stroke}" stroke-width="3.5" vector-effect="non-scaling-stroke" class="overlay-imported"`;
  if (g.type === 'rectangle' && pts.length === 2) { const [[x1,y1],[x2,y2]] = pts; return `<rect x="${svgN(Math.min(x1,x2))}" y="${svgN(Math.min(y1,y2))}" width="${svgN(Math.abs(x2-x1))}" height="${svgN(Math.abs(y2-y1))}" ${common}/>`; }
  if (g.type === 'ellipse' && pts.length === 2) { const [[cx,cy],[right,top]] = pts; return `<ellipse cx="${cx}" cy="${cy}" rx="${svgN(Math.abs(right-cx))}" ry="${svgN(Math.abs(top-cy))}" ${common}/>`; }
  if (g.type === 'polygon' && pts.length >= 3) return `<polygon points="${pts.map(p=>p.join(',')).join(' ')}" ${common}/>`;
  if (g.type === 'polyline' && pts.length >= 2) return `<polyline points="${pts.map(p=>p.join(',')).join(' ')}" ${common}/>`;
  if (g.type === 'points' && pts.length >= 1) return pts.map(([x,y]) => `<circle cx="${x}" cy="${y}" r="5" fill="${stroke}" stroke="#FFFFFF" stroke-width="1.5" vector-effect="non-scaling-stroke" class="overlay-imported"/>`).join('');
  return '';
}

function overlaySVG(c) {
  const ai = reviewLesions(c); const imported = Array.isArray(c.annotations) ? c.annotations : [];
  const aiMarkup = ai.map(s => `<rect data-label="${escapeHTML(s.canonical_label)}" x="${s.rectangle[0]}" y="${s.rectangle[1]}" width="${s.rectangle[2]-s.rectangle[0]}" height="${s.rectangle[3]-s.rectangle[1]}" fill="none" stroke="${colors[s.canonical_label]}" stroke-width="2" vector-effect="non-scaling-stroke" class="overlay-ai ${imported.length?'overlay-ai-superseded':''}"/>`).join('');
  const importedMarkup = imported.map(a => `<g data-label="${escapeHTML(a.canonical_label)}">${renderImportedShape(a)}</g>`).join('');
  return `<svg viewBox="0 0 ${c.width} ${c.height}" aria-label="AI suggestions and imported CVAT corrections">${aiMarkup}${importedMarkup}</svg>`;
}

function applyFilters() {
  $$('.overlay-ai').forEach(el => {
    const label = el.dataset.label;
    el.classList.toggle('overlay-hidden', !(filterState[label] && filterState.ai));
  });
  $$('.canvas svg g').forEach(g => {
    const label = g.dataset.label;
    g.classList.toggle('overlay-hidden', !(filterState[label] && filterState.imported));
  });
}

function fitImage() {
  const wrap = $('.canvas-wrap'); const canvas = $('.canvas'); if (!wrap || !canvas) return;
  const img = canvas.querySelector('img'); if (!img || !img.naturalWidth) return;
  const scaleX = wrap.clientWidth / img.naturalWidth;
  const scaleY = wrap.clientHeight / img.naturalHeight;
  viewer.minScale = Math.min(scaleX, scaleY);
  viewer.scale = viewer.minScale;
  viewer.panX = 0; viewer.panY = 0;
  updateTransform();
}

function updateTransform() {
  const canvas = $('.canvas'); if (!canvas) return;
  canvas.style.transform = `translate(${viewer.panX}px, ${viewer.panY}px) scale(${viewer.scale})`;
}

function bindViewer() {
  const wrap = $('.canvas-wrap'); const canvas = $('.canvas'); if (!wrap || !canvas) return;
  const img = canvas.querySelector('img');
  if (img && img.complete) fitImage(); else if (img) img.onload = fitImage;

  wrap.addEventListener('wheel', e => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    viewer.scale = Math.max(viewer.minScale, Math.min(viewer.maxScale, viewer.scale * delta));
    updateTransform();
  }, {passive:false});

  wrap.addEventListener('mousedown', e => {
    viewer.dragging = true; viewer.lastX = e.clientX; viewer.lastY = e.clientY; wrap.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', e => {
    if (!viewer.dragging) return;
    viewer.panX += e.clientX - viewer.lastX; viewer.panY += e.clientY - viewer.lastY;
    viewer.lastX = e.clientX; viewer.lastY = e.clientY; updateTransform();
  });
  window.addEventListener('mouseup', () => { viewer.dragging = false; wrap.style.cursor = 'grab'; });

  $('#viewer-zoom-in')?.addEventListener('click', () => { viewer.scale = Math.min(viewer.maxScale, viewer.scale * 1.25); updateTransform(); });
  $('#viewer-zoom-out')?.addEventListener('click', () => { viewer.scale = Math.max(viewer.minScale, viewer.scale * 0.8); updateTransform(); });
  $('#viewer-fit')?.addEventListener('click', fitImage);
  $('#viewer-toggle')?.addEventListener('change', e => {
    filterState.ai = e.target.checked;
    filterState.imported = e.target.checked;
    $$('.legend-item input').forEach(ch => { if (ch.dataset.filter) ch.checked = e.target.checked; });
    applyFilters();
  });

  $$('.legend-item input').forEach(ch => {
    ch.addEventListener('change', e => {
      filterState[e.target.dataset.filter] = e.target.checked;
      if (e.target.dataset.filter === 'ai' || e.target.dataset.filter === 'imported') {
        $('#viewer-toggle').checked = filterState.ai && filterState.imported;
      }
      applyFilters();
    });
  });
}

function legendBar(c) {
  const counts = {};
  reviewLesions(c).forEach(l => { counts[l.canonical_label] = (counts[l.canonical_label] || 0) + 1; });
  (c.annotations || []).forEach(a => { counts[a.canonical_label] = (counts[a.canonical_label] || 0) + 1; });
  const hasImported = Array.isArray(c.annotations) && c.annotations.length > 0;
  return `<div class="legend-bar">
    <label class="legend-item"><input type="checkbox" id="viewer-toggle" checked> Overlay on</label>
    ${lesionLabels.map(l => `<label class="legend-item ${counts[l]?'':'disabled'}"><input type="checkbox" data-filter="${l}" checked ${counts[l]?'':'disabled'}><span class="legend-swatch" style="background:${colors[l]}"></span>${escapeHTML(l.replaceAll('_',' '))}${counts[l] ? ' <span class="sub">('+counts[l]+')</span>' : ''}</label>`).join('')}
    ${hasImported?`<label class="legend-item"><input type="checkbox" data-filter="imported" checked><span class="legend-swatch" style="background:#1F2937"></span>Imported CVAT</label>`:''}
  </div>`;
}

function imagePanel(c) {
  return `<section class="panel image-panel">
    <div class="viewer-head"><div><strong>${escapeHTML(c.image_id)}</strong> <span>${c.width} × ${c.height} · ${escapeHTML(c.modality)}</span></div>
      <div class="viewer-controls">
        <button class="icon-button" id="viewer-zoom-out" title="Zoom out" aria-label="Zoom out">−</button>
        <button class="icon-button" id="viewer-zoom-in" title="Zoom in" aria-label="Zoom in">+</button>
        <button class="icon-button" id="viewer-fit" title="Fit image" aria-label="Fit image">⤢</button>
      </div>
    </div>
    <div class="canvas-wrap"><div class="canvas"><img src="${c.image_url}" alt="${escapeHTML(c.source_type)} review sample ${escapeHTML(c.image_id)}">${overlaySVG(c)}</div></div>
    ${legendBar(c)}
    <div class="viewer-foot">${escapeHTML(c.source_type)} sample · ${c.source_type==='PUBLIC'?'HRF / MedOtter · viewer JPEG derivative · CC BY 4.0':'Generated synthetic workflow fixture'}<br>No lesion or ordinal grading ground truth is supplied.</div>
  </section>`;
}

function lesionSummary(c) {
  const lesions = reviewLesions(c);
  const counts = {}; lesionLabels.forEach(l => counts[l] = 0); lesions.forEach(l => counts[l.canonical_label]++);
  const rawCount = c.lesion_review?.raw_count ?? lesions.length;
  const shownCount = c.lesion_review?.suggestion_count ?? lesions.length;
  return `<div class="lesion-summary">
    ${lesionLabels.map(l => `<div class="lesion-count"><strong>${counts[l]}</strong><span><span class="swatch" style="background:${colors[l]}"></span>${escapeHTML(l.replaceAll('_',' '))}</span></div>`).join('')}
  </div><p class="help">${shownCount} shown / ${rawCount} raw model output. Display/CVAT suggestions are bounded by configurable thresholds and caps.</p>`;
}

function gradePanel(c) {
  const g = c.global;
  if (!g || g.grade == null) return `<div class="empty-compact">No grade suggestion yet. Run <strong>Analyze</strong> to generate AI suggestions.</div>`;
  return `<div class="grade-card"><div class="grade-number">${g.grade}</div><div class="grade-label"><strong>${grades[g.grade]}</strong><span>AI suggestion · ${Math.round((g.confidence||0)*100)}% model score</span></div></div>
    ${g.probabilities.map((p,i) => `<div class="prob"><span>G${i}</span><span class="bar"><i style="width:${p*100}%"></i></span><span>${Math.round(p*100)}%</span></div>`).join('')}
    <p class="help">Model scores are uncalibrated and are not the probability that a diagnosis is correct.</p>`;
}

function reviewSourceText(c) {
  if (!c.grade_review_source) return '';
  const map = {'AI_ACCEPTED':'AI accepted','AI_CORRECTED':'Clinician corrected','MANUAL':'Manual clinician grade'};
  return map[c.grade_review_source] || c.grade_review_source.replaceAll('_',' ');
}

function actionBar(c) {
  const state = c.state || 'PENDING';
  const imported = Array.isArray(c.annotations) && c.annotations.length > 0;
  const advancedUrl = c.cvat?.job_url || c.cvat?.task_url;
  return `<div class="action-bar">
    <div class="status">Review status: ${badge(state)} ${c.reviewed_grade != null ? '· Recorded grade '+c.reviewed_grade : ''}</div>
    <div class="actions">
      <button class="primary" data-review="ACCEPT" ${!c.global || c.global.grade == null ? 'disabled' : ''}>Accept</button>
      <button data-review="CORRECT_GRADE" ${!c.global || c.global.grade == null ? 'disabled' : ''}>Adjust Grade</button>
      <button class="warn" data-review="MARK_INCORRECT" ${!c.global || c.global.grade == null ? 'disabled' : ''}>Needs Annotation</button>
      <button class="danger" data-review="ESCALATE">Escalate</button>
      <button class="secondary" id="advanced-edit" ${advancedUrl ? '' : ''}>Advanced Edit</button>
    </div>
  </div>`;
}

function worklist() {
  $('#content').innerHTML = heading('Worklist','Select a case to review AI grade and lesion suggestions.',`<span class="tag">${cases.filter(c=>c.source_type==='PUBLIC').length} public samples</span>`)+
    `<div class="worklist-controls"><input id="search" type="search" placeholder="Search case ID" aria-label="Search case ID"><select id="filter" aria-label="Review state"><option value="ALL">All cases</option><option value="PENDING">Pending</option><option value="REVIEWED">Reviewed</option><option value="NEEDS_CORRECTION">Needs annotation</option><option value="ESCALATED">Escalated</option></select></div>
    <section class="panel table-panel"><table><thead><tr><th>Image</th><th>Source</th><th>AI grade</th><th>Review status</th><th></th></tr></thead><tbody id="rows"></tbody></table></section>`;
  const rows = () => {
    const q = $('#search').value.toLowerCase();
    const filter = $('#filter').value;
    $('#rows').innerHTML = cases.filter(c => c.image_id.toLowerCase().includes(q) && (filter==='ALL' || c.state===filter)).map(c => `<tr><td><div class="sample"><img class="thumb" src="${c.image_url}" alt=""><div><div class="id">${escapeHTML(c.image_id)}</div><div class="subcell">CFP · ${c.width} × ${c.height}</div></div></div></td><td>${escapeHTML(c.source_type)}</td><td>${c.global?.grade != null ? c.global.grade+' · '+grades[c.global.grade] : '—'}</td><td>${badge(c.state)}</td><td><button class="text-button" data-open="${escapeHTML(c.image_id)}">Review</button></td></tr>`).join('');
    $$('[data-open]').forEach(b => b.onclick = () => { selected = b.dataset.open; location.hash = 'case'; });
  };
  rows(); $('#search').oninput = rows; $('#filter').onchange = rows;
}

function caseReview(c) {
  const reviewSource = reviewSourceText(c);
  const hasLesions = !!(c.lesion_review || c.lesion);
  const imported = Array.isArray(c.annotations) && c.annotations.length > 0;
  $('#content').innerHTML = heading('Case Review','Inspect the retinal image, grade suggestion, and lesion findings. Record a clinician decision.',`<span class="tag">${escapeHTML(c.image_id)}</span>`)+
    `<div class="review-layout"><div class="viewer-column">${imagePanel(c)}` +
    (hasLesions ? `<section class="panel"><div class="section-head"><h2>Lesion findings</h2>${c.lesion_review_state ? badge(c.lesion_review_state) : ''}</div>${lesionSummary(c)}${imported?`<p class="help">${c.annotations.length} CVAT-imported shapes are overlaid as solid geometry; original AI boxes remain as faded dashed provenance.</p>`:''}</section>` : '') +
    `<section class="panel"><div class="section-head"><h2>Review history</h2>${badge(c.state)}</div>${c.events.length?`<ol class="history">${c.events.slice(-8).map(e=>`<li>${escapeHTML(e.action.replaceAll('_',' '))}${e.reviewer?' · '+escapeHTML(e.reviewer):''}${e.comment?' — '+escapeHTML(e.comment):''}</li>`).join('')}</ol>`:'<p class="sub">No review decisions yet.</p>'}</section></div>` +
    `<section class="panel ai-panel"><div class="section-head"><h2>AI Review</h2><span class="kicker" style="margin:0">GRADE</span></div>${gradePanel(c)}<hr class="rule"><div class="section-head"><h2>Lesion summary</h2></div>${hasLesions?lesionSummary(c):'<p class="sub">Run Analyze to generate lesion suggestions.</p>'}` +
    `<hr class="rule"><h3>Warnings</h3><ul class="warnings">${(c.global?.warnings||c.lesion?.warnings||['Research use only']).map(w=>`<li>${escapeHTML(w)}</li>`).join('')}</ul>` +
    `<hr class="rule"><h3>Your review</h3>${c.reviewed_grade!=null?`<div class="review-result"><strong>Recorded grade ${c.reviewed_grade}</strong><span>${grades[c.reviewed_grade]}${reviewSource?' · '+escapeHTML(reviewSource):''}</span></div>`:''}` +
    `<label class="field" for="reviewer">Reviewer name</label><input id="reviewer" autocomplete="name" value="${escapeHTML(reviewer)}" placeholder="Name for the review record">` +
    `<label class="field" for="comment">Review note <span>(optional)</span></label><textarea id="comment" maxlength="1000" placeholder="Add a note for the audit trail"></textarea>` +
    `<div id="grade-adjust" style="display:none"><label class="field" for="grade">Corrected grade</label><select id="grade">${grades.map((g,i)=>`<option value="${i}">${i} · ${g}</option>`).join('')}</select></div>` +
    `<details><summary>Model & provenance</summary><dl class="meta"><dt>Grade model</dt><dd>${escapeHTML(c.global?.model_id || (c.source_type==='SYNTHETIC'?'Synthetic fixture':'Not run'))}</dd><dt>Lesion model</dt><dd>${escapeHTML(c.lesion?.model_id || (c.source_type==='SYNTHETIC'?'Synthetic fixture':'Not run'))}</dd><dt>Image source</dt><dd>${escapeHTML(c.source_type)}</dd></dl></details></section></div>` +
    actionBar(c) +
    `<div style="text-align:center;margin-top:18px"><button class="secondary" id="run-analyze">${c.global || c.lesion ? 'Run Analyze again' : 'Analyze case'}</button></div>`;

  bindViewer();
  bindReview(c);
  $('#run-analyze').onclick = () => analyzeCase(c);
  $('#advanced-edit').onclick = () => advancedEdit(c);
  $$('[data-review="CORRECT_GRADE"]').forEach(b => b.onclick = () => {
    const adj = $('#grade-adjust');
    if (adj.style.display === 'none') { adj.style.display = 'block'; b.textContent = 'Confirm Adjusted Grade'; b.classList.add('primary'); }
    else submitReview(c, 'CORRECT_GRADE');
  });
}

function modelsPage() {
  $('#content').innerHTML = heading('Models & Audit','Provider readiness, supported modality, provenance, and limitations.')+
    `<div class="models">${models.map(m=>`<section class="panel model-card"><div class="section-head"><h2>${escapeHTML(m.model_id)}</h2>${badge(m.status)}</div><dl class="meta"><dt>Task</dt><dd>${escapeHTML(m.task)}</dd><dt>Modality</dt><dd>${escapeHTML(m.modalities.join(', '))}</dd>${m.revision?`<dt>Source revision</dt><dd class="mono">${escapeHTML(m.revision)}</dd>`:''}</dl>${m.preprocessing?`<details><summary>Preprocessing</summary><p>${escapeHTML(m.preprocessing)}</p></details>`:''}<ul class="warnings">${m.warnings.map(w=>`<li>${escapeHTML(w)}</li>`).join('')}</ul></section>`).join('')}</div><p class="help">Configured assets are verified when loaded. Each response carries checkpoint hashes and image provenance. UWF is unsupported. No scientific champion or performance claim is made here.</p>`;
}

function analyzeCase(c) {
  const globalModel = c.source_type === 'SYNTHETIC' ? 'mock-global' : 'retfound-aptos5';
  const lesionModel = c.source_type === 'SYNTHETIC' ? 'mock-lesion' : 'prism-dr-5fold';
  action(async () => {
    await api('/v1/infer/global', {image_id:c.image_id, model_id:globalModel, modality:c.modality});
    await api('/v1/infer/lesion-roi', {image_id:c.image_id, model_id:lesionModel, modality:c.modality});
  }, 'AI grade and lesion suggestions ready for review.');
}

async function advancedEdit(c) {
  if (busy) return;
  busy = true; $$('button').forEach(b => b.disabled = true); status('Preparing CVAT advanced edit…');
  try {
    let mapping = c.cvat;
    if (!mapping) {
      mapping = await api(`/v1/cases/${c.image_id}/cvat/send`, {});
    }
    const url = mapping.job_url || mapping.task_url;
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
    else throw new Error('CVAT task prepared but no URL was returned.');
    await load();
    status('CVAT advanced editor opened.', 'success');
  } catch (e) {
    status(e.message, 'error');
  } finally {
    busy = false;
    render();
  }
}

function submitReview(c, actionType) {
  const grade = actionType === 'CORRECT_GRADE' ? Number($('#grade').value) : null;
  action(() => api(`/v1/cases/${c.image_id}/review`, {
    revision: c.revision, action: actionType, reviewer: reviewer.trim(),
    comment: $('#comment')?.value || '', grade
  }), 'Review recorded.');
}

function bindReview(c) {
  const rev = $('#reviewer');
  if (rev) rev.oninput = e => { reviewer = e.target.value; sessionStorage.setItem('reviewer', reviewer); };
  $$('[data-review]').forEach(b => {
    if (b.dataset.review === 'CORRECT_GRADE') return;
    b.onclick = () => submitReview(c, b.dataset.review);
  });
}

function render() {
  const page = nav();
  $$('[data-nav]').forEach(a => a.classList.toggle('active', a.dataset.nav === page));
  current = cases.find(c => c.image_id === selected) || cases[0];
  if (current) selected = current.image_id;
  updateCaseSelector();
  if (page === 'worklist') worklist();
  else if (page === 'models') modelsPage();
  else if (current) caseReview(current);
  else $('#content').innerHTML = '<p>No samples available.</p>';
  if (window.DR_PREVIEW) {
    $$('[data-review],#run-analyze,#advanced-edit').forEach(e => e.disabled = true);
    $$('a[href^="/v1/"]').forEach(e => e.remove());
  }
}

async function load() { [cases, models] = await Promise.all([api('/v1/cases'), api('/v1/models')]); render(); }
window.addEventListener('hashchange', () => { status(''); render(); });
load().catch(e => status(e.message, 'error'));
