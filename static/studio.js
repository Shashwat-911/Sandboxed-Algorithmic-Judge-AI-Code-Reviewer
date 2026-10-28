// Browser commands execute through the local Playwright worker, never eval().
const studio = document.createElement('section');
studio.className = 'studio';
studio.id = 'playwright';
studio.innerHTML = `
 <div class="studio-heading"><div><div class="eyebrow">PLAYWRIGHT / BROWSER LAB</div><h2>Write a journey. Watch it run.</h2><p>Real browser actions, assertions, screenshots, and traces in one workspace.</p></div><span id="pw-ready" class="badge">Checking engine…</span></div>
 <div class="studio-toolbar"><label>Editor <select id="pw-mode"><option value="suite">Repository test suite</option><option value="javascript">JavaScript Playwright</option><option value="typescript">TypeScript Playwright</option><option value="commands">Guided commands</option><option value="python">Native Python Playwright</option></select></label><label>Browser <select id="pw-browser"><option value="chromium">Chromium</option><option value="firefox">Firefox</option><option value="webkit">WebKit</option></select></label><label>Code format <select id="pw-style"><option value="body">Commands inside one test</option><option value="file">Complete test file</option></select></label><span id="pw-project">Standalone browser run · select a project below to link it</span><button class="secondary" id="pw-example">Load workshop example</button></div>
 <div class="studio-grid"><div class="command-pane"><div class="editor-label"><label for="pw-commands">COMMAND EDITOR</label><span>NATIVE PLAYWRIGHT + GUIDED MODE</span></div><textarea id="pw-commands" wrap="off" spellcheck="false" aria-describedby="pw-hint"></textarea><label><input type="checkbox" id="pw-trusted"> I trust this repository and code to run locally and install its test dependencies.</label><div class="editor-footer"><span id="pw-hint">One command per line. Quote values with spaces.</span><button id="pw-run">▶ Run journey</button></div>
 <details><summary>Command reference</summary><pre>goto "http://localhost:3000"
click "text=Sign in"
fill "#email" "student@example.com"
press "#email" "Tab"
check "#terms"
select "#course" "engineering"
hover "nav"
expect-visible "h1"
expect-text "h1" "Welcome"
expect-title "My app"
expect-url "http://localhost:3000/home"
screenshot</pre><p>Selectors use Playwright syntax. Assertions auto-wait up to 5 seconds. A failed step stops the journey; remaining steps are skipped. A fresh browser context is used each run. Commands are not Python, JavaScript, or shell code.</p></details></div>
 <div class="preview-pane"><div class="editor-label"><span>BROWSER SNAPSHOT</span><span id="pw-progress">Ready for your first run</span></div><div id="pw-preview"><div class="preview-empty"><span>◉</span><h3>Your browser evidence lives here</h3><p>Run the workshop example to interact with a local demo.<br>Select any completed step to inspect its screenshot.</p></div></div></div></div>
 <div id="pw-notice" role="status" aria-live="polite"></div>
 <div class="studio-results"><div class="run-history"><h3>RECENT BROWSER RUNS</h3><div id="pw-history"></div></div><div class="run-detail"><div class="tabs" role="tablist" aria-label="Browser evidence"><button role="tab" aria-selected="true" data-evidence="steps" class="active">Steps</button><button role="tab" aria-selected="false" data-evidence="console">Console</button><button role="tab" aria-selected="false" data-evidence="network">Network</button><button role="tab" aria-selected="false" data-evidence="artifacts">Artifacts</button></div><div id="pw-evidence">No execution yet. Run a journey to collect evidence.</div></div></div>`;
document.querySelector('.intake').before(studio);
let browserRun = null, browserPoll = null, evidenceTab = 'steps', activeRun = null, previewStep = null;
const pw = id => document.getElementById('pw-' + id);
function example() {
  pw('commands').value = `# Workshop: add a task and verify the result\ngoto "${location.origin}/static/workshop.html"\nexpect-title "Workshop task board"\nfill "#task" "Ship my Playwright project"\nclick "#add"\nexpect-text "#tasks" "Ship my Playwright project"\ncheck "#tasks input"\nexpect-text "#count" "1 completed"\nscreenshot`;
}
example();
pw('example').onclick = () => {pw('mode').value='commands'; pw('mode').onchange(); example();};
pw('mode').onchange = () => {
 const mode=pw('mode').value;
 pw('commands').disabled=mode==='suite';
 if(mode==='suite') {pw('commands').value='Run the selected repository’s existing Playwright tests using its configuration and webServer.';}
 else if(mode==='python') {pw('commands').value=`page.goto('${location.origin}/static/workshop.html')\nexpect(page).to_have_title('Workshop task board')`;}
 else if(mode==='commands') {example();}
 else if(pw('style').value==='file') {pw('commands').value="import { test, expect } from '@playwright/test';\n\ntest('Studio script', async ({ page }) => {\n  await page.goto('/');\n  await expect(page.locator('body')).toBeVisible();\n});";}
 else {pw('commands').value="await page.goto('/');\nawait expect(page.locator('body')).toBeVisible();";}
 pw('hint').textContent=mode==='commands'?'One command per line.':mode==='python'?'Python sync API: page, context, browser, expect, project_files. Navigate to a running app URL.':'Uses the selected repository configuration, baseURL and webServer. Full-file mode supports imports, fixtures and test declarations.';
};
pw('style').onchange = () => { if(['javascript','typescript'].includes(pw('mode').value)) pw('mode').onchange(); };
pw('mode').onchange();
async function browserHistory() {
  const rows = await api('/api/playwright/runs');
  pw('history').innerHTML = rows.map(r => `<button class="${r.id === activeRun ? 'selected' : ''}" data-run="${escapeHTML(r.id)}">${escapeHTML(r.browser)} · ${escapeHTML(r.status)}<small>${new Date(r.created_at).toLocaleString()}</small></button>`).join('') || '<p>No browser runs yet.</p>';
  pw('history').querySelectorAll('[data-run]').forEach(b => b.onclick = () => {pw('run').disabled = false; openRun(b.dataset.run, true);});
}
function artifactUrl(name) {return `/api/playwright/runs/${browserRun.id}/artifacts/${encodeURIComponent(name)}`;}
function snapshot(index) {
  const step = browserRun?.steps[index];
  if (!step?.screenshot) return;
  previewStep = index;
  pw('preview').innerHTML = `<a href="${artifactUrl(step.screenshot)}" target="_blank" rel="noopener"><img src="${artifactUrl(step.screenshot)}" alt="Browser after step ${index+1}: ${escapeHTML(step.command)}"></a><p>Step ${index+1} · ${escapeHTML(step.command)} · ${escapeHTML(step.status)}</p>`;
}
function renderEvidence() {
  const r = browserRun;
  if (!r) return;
  document.querySelectorAll('[data-evidence]').forEach(b => {b.classList.toggle('active', b.dataset.evidence === evidenceTab); b.setAttribute('aria-selected', String(b.dataset.evidence === evidenceTab));});
  if (evidenceTab === 'steps') {
    pw('evidence').innerHTML = r.steps.map((s,i) => `<article class="browser-step"><button class="secondary" data-step="${i}" ${s.screenshot ? '' : 'disabled'}>${String(i+1).padStart(2,'0')}</button><div><code>${escapeHTML(s.command)} ${escapeHTML(s.args.join(' '))}</code><small>Line ${s.line} ${s.duration_ms == null ? '' : '· '+s.duration_ms+' ms'}</small>${s.error ? `<pre>${escapeHTML(s.error)}</pre>` : ''}</div>${badge(s.status)}</article>`).join('') || 'Waiting for the browser worker…';
    pw('evidence').querySelectorAll('[data-step]').forEach(b => b.onclick = () => snapshot(Number(b.dataset.step)));
  }
  if (evidenceTab === 'console') pw('evidence').innerHTML = `<p class="muted">Browser console and uncaught page errors · first 200 events</p><pre>${escapeHTML(r.output || (r.console||[]).map(m => `[${m.type}] ${m.text}`).join('\n') || (r.mode==='suite'||r.mode==='javascript'||r.mode==='typescript' ? 'Native runner output is in execution.log under Artifacts; page events are in Playwright traces.' : 'No console messages captured.'))}</pre>`;
  if (evidenceTab === 'network') pw('evidence').innerHTML = `<p class="muted">Observed responses and failed requests · first 200 events</p>${r.network.map(n => `<div class="network-row">${badge(n.status)} <code>${escapeHTML(n.method)} ${escapeHTML(n.url)}</code></div>`).join('') || '<p>Native runs capture network evidence in Playwright traces. Open Artifacts to inspect it.</p>'}`;
  if (evidenceTab === 'artifacts') pw('evidence').innerHTML = ['javascript','typescript','suite'].includes(r.mode) ? `<h3>PLAYWRIGHT RUN EVIDENCE</h3><p>${escapeHTML(r.note||'')}</p><pre>${escapeHTML(JSON.stringify(r.counts||{},null,2))}</pre>${r.artifacts.filter(n=>!n.startsWith('html-report/')||n==='html-report/index.html').map(n=>`<p><a href="${artifactUrl(n)}" target="_blank" rel="noopener">${escapeHTML(n)}</a></p>`).join('')}` : `<h3>REPRODUCE & DEBUG</h3><p><a class="download" href="${artifactUrl('test_browser.py')}">↓ Python script</a><a class="download" href="${artifactUrl('result.json')}">↓ Run JSON</a>${r.artifacts.includes('trace.zip') ? `<a class="download" href="${artifactUrl('trace.zip')}">↓ Playwright trace</a>` : ''}</p><p>Open the downloaded trace with <code>python -m playwright show-trace trace.zip</code> or <a href="https://trace.playwright.dev" target="_blank" rel="noopener">Playwright Trace Viewer ↗</a>.</p><p class="muted">Runs and artifacts are saved locally in .atf/browser-runs. The exported Python script reproduces the commands. A passed journey only confirms its listed assertions.</p>`;
}
async function openRun(id, restore = false) {
  activeRun = id;
  clearTimeout(browserPoll);
  try {
    const r = await api('/api/playwright/runs/' + id);
    if (activeRun !== id) return;
    if (browserRun?.id !== id) {previewStep = null; pw('preview').innerHTML = '<div class="preview-empty"><p>Waiting for a browser snapshot…</p></div>';}
    browserRun = r;
    if (restore) {if(r.project_id && selected!==r.project_id) await select(r.project_id); pw('style').value=r.script_style||'body'; pw('mode').value=r.mode||'commands'; pw('commands').disabled=r.mode==='suite'; pw('commands').value = r.commands; pw('browser').value = r.browser;}
    const pending = ['queued', 'running'].includes(r.status);
    pw('run').disabled = pending;
    pw('progress').textContent = `${r.phase || r.status.toUpperCase()} · ${r.steps.filter(s=>s.status==='passed').length}/${r.steps.length} steps passed`;
    pw('notice').textContent = r.error || (pending ? 'Playwright is executing your journey. Evidence updates as each step completes.' : `${r.status === 'passed' ? 'Journey passed' : 'Journey did not pass'} · ${r.duration_ms || 0} ms · ${r.browser}`);
    renderEvidence();
    if (previewStep === null || pending) {
      const latest = r.steps.map((s,i)=>s.screenshot ? i : -1).filter(i=>i>=0).pop();
      if (latest != null) snapshot(latest);
    }
    await browserHistory();
    if (!pending && selected && selected === r.project_id) {const updated=await api('/api/projects/'+selected); current=updated.report; render('playwright');}
    if (pending && activeRun === id) browserPoll = setTimeout(() => openRun(id), 800);
  } catch(e) {pw('notice').textContent = e.message; pw('run').disabled = false;}
}
pw('run').onclick = async () => {
  pw('run').disabled = true; pw('notice').textContent = 'Validating commands…'; previewStep = null;
  try {
    const r = await api('/api/playwright/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode:pw('mode').value, script_style:pw('style').value, trusted:pw('trusted').checked, commands:pw('commands').value, browser:pw('browser').value, project_id:selected})});
    await openRun(r.id);
  } catch(e) {pw('notice').textContent=e.message; pw('run').disabled=false;}
};
document.querySelectorAll('[data-evidence]').forEach(b => b.onclick = () => {evidenceTab=b.dataset.evidence; renderEvidence();});
api('/api/playwright/status').then(r => {pw('ready').textContent = r.installed ? 'PLAYWRIGHT INSTALLED' : 'SETUP REQUIRED'; if(!r.installed) pw('notice').textContent='Install requirements-demo.txt, then run: '+r.setup;}).catch(e=>pw('notice').textContent=e.message);
browserHistory().catch(e=>pw('notice').textContent=e.message);
document.addEventListener('project-selected', e => {pw('trusted').checked=false;pw('project').textContent='Linked project: '+e.detail.name;});
