// 只读检测：当前知网对本机/本机构的授权状态，绝不点击下载
const PORT = '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const targets = await (await fetch(`${BASE}/json/list`)).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.addEventListener('open', r); ws.addEventListener('error', () => j(new Error('ws'))); });
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
function send(method, params = {}, ms = 30000) { const i = ++id; return new Promise((res, rej) => { pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, ms); }); }
async function ev(expr, ms = 25000) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true }, ms); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 300)); return r.result.value; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 打开一篇已下载过的论文详情页（不点下载）
const url = process.argv[2] || 'https://kns.cnki.net/kcms2/article/abstract?v=Y48PYOiatWevuNzBFcZyF-AjyIQCZfF5vdZwOq9dtcwm9CHP_5Higslywd3ym4607mJpNd0eiHkymAOcdTjKcq7IAnGQAVGdqBmFQjEGZLtXwO1jaaKgZIkONyXql5rnEdT5Ji8c7HyTAVtxyFZI5nFVBNBMEncDkTV-zZWo-nOi45RlxnUSGA==';
await send('Page.navigate', { url }, 40000);
await sleep(7000);

const st = await ev(`JSON.stringify({
  url: location.href,
  title: document.title,
  institution: (() => { const e = document.querySelector('.eclogin, .top-login, #Ecp_login, .head-login'); return e ? e.innerText.replace(/\\s+/g,' ').slice(0,120) : '(未找到机构区)'; })(),
  headText: (document.querySelector('.head, .top, header') || {}).innerText ? document.querySelector('.head, .top, header').innerText.replace(/\\s+/g,' ').slice(0,200) : '',
  hasPdfBtn: (() => { const e = document.querySelector('#pdfDown'); return e ? (e.offsetParent !== null) : false; })(),
  hasCajBtn: (() => { const e = document.querySelector('#cajDown'); return e ? (e.offsetParent !== null) : false; })(),
  payHints: (document.body.innerText.match(/充值|付费|购买|余额|付费下载|已用完|超出|额度|限流|访问过于频繁|稍后再试|机构未|未订购|无权限/g) || []).slice(0, 12),
  bodySnippet: document.body.innerText.replace(/\\s+/g,' ').slice(0, 500)
}, null, 1)`);
console.log(st);
process.exit(0);
