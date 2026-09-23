/* Shared presenter engine for RETINAL_REVIEW_DEMO and TECHNICAL_BRIEFING.
   Inlined into the published HTML by scripts/docs/build_docs.py. No network, no storage.

   Scene contract:
     <section class="scene" data-title="..." data-steps="N">   N = number of presenter reveals
     [data-step="n"]      visible from step n
     [data-until="m"]     hidden again after step m (state replacement)
     [data-dim="a-b"]     dimmed while a <= step <= b (attention control)
     [data-zoom='{"2":"scale(1.8) translate(-20%,-10%)"}']  on .zin: transform for the latest step key <= step
     [data-hotspot="key"] positioned from the #hotspot-data JSON (percent of the captured frame)
   Keys: Space / Right / PageDown / Enter = next reveal; Left / PageUp / Backspace = previous;
         Home / End = first / last scene; F = fullscreen.
   QA hooks: #N opens scene N; ?all=1 reveals every step of that scene; window.rrwDeck. */
(() => {
  const stage = document.getElementById('stage');
  const scenes = [...document.querySelectorAll('.scene')];
  const title = document.querySelector('#chrome .title');
  const count = document.querySelector('#chrome .count');
  const dots = document.querySelector('#chrome .dots');
  const progress = document.getElementById('progress');
  const help = document.getElementById('help');
  let hotspots = {};
  try { hotspots = JSON.parse(document.getElementById('hotspot-data')?.textContent || '{}'); } catch (e) { hotspots = {}; }

  document.querySelectorAll('[data-hotspot]').forEach((el) => {
    const box = hotspots[el.dataset.hotspot];
    if (!box) { el.style.display = 'none'; return; }
    const pad = Number(el.dataset.pad || 0.6);
    el.style.left = (box.left - pad) + '%';
    el.style.top = (box.top - pad) + '%';
    el.style.width = (box.width + 2 * pad) + '%';
    el.style.height = (box.height + 2 * pad) + '%';
  });

  let index = 0;
  let step = 0;
  const maxStep = (s) => Number(s.dataset.steps || 0);

  function fit() {
    const scale = Math.min(window.innerWidth / 1600, window.innerHeight / 900);
    stage.style.transform = `translate(-50%, -50%) scale(${scale})`;
  }

  function applyScene(scene) {
    scene.querySelectorAll('[data-step]').forEach((el) => el.classList.toggle('on', Number(el.dataset.step) <= step));
    scene.querySelectorAll('[data-until]').forEach((el) => el.classList.toggle('gone', step > Number(el.dataset.until)));
    scene.querySelectorAll('[data-dim]').forEach((el) => {
      const [a, b] = el.dataset.dim.split('-').map(Number);
      el.classList.toggle('dimmed', step >= a && step <= (Number.isFinite(b) ? b : 999));
    });
    scene.querySelectorAll('[data-zoom]').forEach((el) => {
      let map = {};
      try { map = JSON.parse(el.dataset.zoom); } catch (e) { map = {}; }
      const key = Object.keys(map).map(Number).filter((k) => k <= step).sort((x, y) => y - x)[0];
      el.style.transform = key === undefined ? '' : map[key];
    });
  }

  function render() {
    scenes.forEach((s, i) => {
      s.classList.toggle('active', i === index);
      s.setAttribute('aria-hidden', i === index ? 'false' : 'true');
    });
    const scene = scenes[index];
    applyScene(scene);
    stage.classList.toggle('dark', scene.dataset.dark === 'true');
    title.textContent = scene.dataset.title || '';
    count.textContent = String(index + 1).padStart(2, '0') + ' / ' + String(scenes.length).padStart(2, '0');
    dots.innerHTML = '';
    for (let i = 1; i <= maxStep(scene); i++) {
      const d = document.createElement('i');
      if (i <= step) d.className = 'on';
      dots.appendChild(d);
    }
    const total = scenes.reduce((n, s) => n + maxStep(s) + 1, 0);
    const done = scenes.slice(0, index).reduce((n, s) => n + maxStep(s) + 1, 0) + step + 1;
    progress.style.width = (done / total * 100) + '%';
    document.title = `${String(index + 1).padStart(2, '0')} ${scene.dataset.title} · ${document.body.dataset.deck || 'Retinal Review Workbench'}`;
    if (location.hash !== '#' + (index + 1)) history.replaceState(null, '', '#' + (index + 1) + location.search);
  }

  function next() {
    if (step < maxStep(scenes[index])) step++;
    else if (index < scenes.length - 1) { index++; step = 0; }
    render();
  }
  function prev() {
    if (step > 0) step--;
    else if (index > 0) { index--; step = maxStep(scenes[index]); }
    render();
  }
  function go(i, full) { index = Math.max(0, Math.min(scenes.length - 1, i)); step = full ? maxStep(scenes[index]) : 0; render(); }

  document.addEventListener('keydown', (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    help?.classList.add('hide');
    switch (e.key) {
      case 'ArrowRight': case ' ': case 'PageDown': case 'Enter': e.preventDefault(); next(); break;
      case 'ArrowLeft': case 'PageUp': case 'Backspace': e.preventDefault(); prev(); break;
      case 'Home': e.preventDefault(); go(0); break;
      case 'End': e.preventDefault(); go(scenes.length - 1, true); break;
      case 'f': case 'F':
        if (!document.fullscreenElement) document.documentElement.requestFullscreen?.(); else document.exitFullscreen?.();
        break;
      default: break;
    }
  });
  document.querySelector('.nav.next')?.addEventListener('click', next);
  document.querySelector('.nav.prev')?.addEventListener('click', prev);
  window.addEventListener('resize', fit);

  const start = parseInt(location.hash.slice(1), 10);
  if (start >= 1 && start <= scenes.length) index = start - 1;
  if (new URLSearchParams(location.search).get('all') === '1') step = maxStep(scenes[index]);
  window.rrwDeck = {
    next, prev, go,
    state: () => ({ index, step, scenes: scenes.length, maxStep: maxStep(scenes[index]) }),
    outline: () => scenes.map((s) => ({ title: s.dataset.title, steps: maxStep(s) })),
  };
  fit();
  render();
})();
