// Screenshots web pages with headless Chrome, for the slides, the site and checking layouts.
//
//   node tools/shoot.mjs shots.json
//
// shots.json is a list of {url, out, width?, height?, scale?, full?, wait?, eval?}:
//   full: capture the whole page height, not just the window
//   wait: milliseconds to wait after load (charts and slide transitions)
//   eval: JavaScript to run before the capture (scroll, click, hide something)
// Needs Google Chrome (set CHROME if it isn't at the macOS default). Uses the DevTools protocol, like
// record-tour.mjs, so it needs no npm packages.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const shots = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const chrome = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const port = 9300 + Math.floor(Math.random() * 300);
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
  '--force-color-profile=srgb', '--allow-file-access-from-files', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'shoot-'))}`,
  `--remote-debugging-port=${port}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200);
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch {}
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0;
const pending = new Map();
const errors = [];
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || 'exception');
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') errors.push(msg.params.args.map((a) => a.value).join(' '));
});
const send = (method, params = {}) => new Promise((res) => { const n = ++id; pending.set(n, res); ws.send(JSON.stringify({ id: n, method, params })); });
const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;

await send('Page.enable');
await send('Runtime.enable');
await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
let lastUrl = '';
for (const s of shots) {
  const width = s.width || 1280;
  const height = s.height || 800;
  const scale = s.scale || 2;
  errors.length = 0;
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile: false });
  // slide: a reveal.js slide number, counted in reading order from 0 (Quarto nests slides under # sections). The deck loads once; later shots of the same deck just move to the slide.
  if (s.slide == null || s.url !== lastUrl) {
    await send('Page.navigate', { url: s.url });
    for (let i = 0; i < 100; i++) { await sleep(100); if ((await evaluate('document.readyState')) === 'complete') break; }
    lastUrl = s.url;
    if (s.slide != null) await sleep(1200);
  }
  if (s.slide != null) await evaluate(`Reveal.configure({ transition: 'none', backgroundTransition: 'none' }); (() => { const ix = Reveal.getIndices(Reveal.getSlides()[${s.slide}]); Reveal.slide(ix.h, ix.v); })();`);
  await sleep(s.wait ?? 600);
  if (s.eval) { await evaluate(s.eval); await sleep(400); }
  let clip;
  if (s.full) {
    const h = await evaluate('Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)');
    await send('Emulation.setDeviceMetricsOverride', { width, height: Math.min(h, 12000), deviceScaleFactor: scale, mobile: false });
    await sleep(500);
    clip = { x: 0, y: 0, width, height: Math.min(h, 12000), scale: 1 };
  }
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: !!s.full, ...(clip ? { clip } : {}) });
  mkdirSync(dirname(resolve(s.out)), { recursive: true });
  writeFileSync(s.out, Buffer.from(shot.result.data, 'base64'));
  console.log('shot', s.out, errors.length ? 'ERRORS: ' + errors.join(' | ') : '');
}
ws.close();
proc.kill();
process.exit(0);
