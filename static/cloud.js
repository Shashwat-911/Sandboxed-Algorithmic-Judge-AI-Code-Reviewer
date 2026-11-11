// Public-host capabilities; enforcement lives in cloud_app.py and browser_worker.py.
document.querySelector('#run-tests').disabled = true;
document.querySelector('#use-ai').disabled = true;
document.querySelector('.options').insertAdjacentHTML('afterend', '<p class="muted">Public demo: source analysis, reports, and real Chromium workshop tests. Docker tests, native scripts, and Ollama AI require the private runtime. Files are temporary; download your report before leaving.</p>');
pw('mode').replaceChildren(new Option('Guided commands', 'commands'));
pw('browser').replaceChildren(new Option('Chromium', 'chromium'));
pw('style').closest('label').hidden = true;
pw('trusted').closest('label').hidden = true;
pw('commands').disabled = false;
function cloudExample() {
  pw('commands').value = '# Live Chromium demo: add and complete a task\ngoto "https://sandbox-demo.invalid/workshop"\nexpect-title "Workshop task board"\nfill "#task" "Ship my Playwright project"\nclick "#add"\nexpect-text "#tasks" "Ship my Playwright project"\ncheck "#tasks input"\nexpect-text "#count" "1 completed"\nscreenshot';
}
pw('example').onclick = cloudExample;
pw('mode').onchange = cloudExample;
pw('hint').textContent = 'Public demo runs on the included task board. Edit actions and assertions, then run.';
document.querySelector('.command-pane .editor-label span').textContent = 'LIVE CHROMIUM / GUIDED MODE';
cloudExample();
