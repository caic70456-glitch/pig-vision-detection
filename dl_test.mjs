// 单篇下载测试：点击 #pdfDown，观察是否真正落盘
const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const DL = process.env.DL_DIR || 'C:\\Users\\ASUS\\Downloads';

import fs from 'node:fs';
import path from 'node:path';

const targets = await (await fetch(`${BASE}/json/list`)).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', () => rej(new Error('ws fail'))); });
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
function send(method, params = {}) { const i = ++id; return new Promise((res, rej) => { pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, 120000); }); }
async function ev(expr) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400)); return r.result.value; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function snapshot() {
  const set = new Set();
  for (const f of fs.readdirSync(DL)) {
    const st = fs.statSync(path.join(DL, f));
    set.add(f + '|' + st.size);
  }
  return set;
}
const before = snapshot();
console.log('BEFORE 文件数:', before.size);

// 用 CDP 事件监听下载（Browser 域需要 browser target，这里先靠文件系统观察 + 页面提示）
const info = await ev(`(() => {
  const pdf = document.querySelector('#pdfDown');
  const caj = document.querySelector('#cajDown');
  const title = (document.querySelector('h1')||{}).innerText;
  return JSON.stringify({
    url: location.href,
    docTitle: document.title,
    hasPdf: !!pdf, hasCaj: !!caj,
    pdfHref: pdf ? pdf.getAttribute('href') : null,
    pdfVisible: pdf ? (pdf.offsetParent !== null) : null,
    pdfText: pdf ? pdf.innerText : null
  });
})()`);
console.log('PAGE>', info);

// 触发下载（真实点击语义）
const clicked = await ev(`(() => {
  const a = document.querySelector('#pdfDown');
  if (!a) return 'no #pdfDown';
  a.click();
  return 'clicked';
})()`);
console.log('CLICK>', clicked);

// 等待落盘
let found = null;
for (let i = 0; i < 40; i++) {
  await sleep(1500);
  const now = snapshot();
  for (const k of now) {
    if (!before.has(k)) { found = k; break; }
  }
  if (found) break;
}
console.log('NEW FILE>', found || '（未检测到新文件）');
if (!found) {
  const state = await ev(`JSON.stringify({title: document.title, url: location.href, bodySnippet: document.body.innerText.slice(0,300)})`);
  console.log('PAGE STATE>', state);
}
process.exit(0);
