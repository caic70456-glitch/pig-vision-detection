// 探测结果行结构 + 打开第一篇详情页看下载控件
const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const targets = await (await fetch(`${BASE}/json/list`)).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', () => rej(new Error('ws fail'))); });
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
function send(method, params = {}) { const i = ++id; return new Promise((res, rej) => { pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, 90000); }); }
async function ev(expr) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 500)); return r.result.value; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 1) 结果行结构
const rows = await ev(`JSON.stringify([...document.querySelectorAll('table.result-table-list tbody tr')].slice(0,3).map(tr => ({
  cls: tr.className,
  cells: [...tr.children].map(td => ({cls: td.className, txt: td.innerText.replace(/\\s+/g,' ').slice(0,70)})),
  links: [...tr.querySelectorAll('a')].map(a=>({t:a.innerText.trim().slice(0,30), h:a.getAttribute('href')})).slice(0,6)
})), null, 1)`);
console.log('ROWS>', rows);

// 2) 打开第一篇详情页
const firstHref = await ev(`(() => {
  const a = document.querySelector('table.result-table-list tbody tr a.fz14, table.result-table-list tbody tr td.name a, table.result-table-list tbody tr a');
  return a ? a.getAttribute('href') : null;
})()`);
console.log('FIRST HREF>', firstHref);

if (firstHref) {
  await send('Page.enable');
  await send('Page.navigate', { url: firstHref.startsWith('http') ? firstHref : 'https://kns.cnki.net' + firstHref });
  await sleep(8000);
  const detail = await ev(`JSON.stringify({
    url: location.href,
    title: document.title,
    h1: (document.querySelector('h1')||{}).innerText,
    buttons: [...document.querySelectorAll('a,button,li')].map(e=>e.innerText && e.innerText.trim()).filter(t=>t && /下载|PDF|CAJ|HTML|收藏|引用|阅读/.test(t)).slice(0,20),
    downloadEls: [...document.querySelectorAll('a,button,li')].filter(e=>/下载/.test(e.innerText||'')).map(e=>({tag:e.tagName, cls:e.className, id:e.id, onclick:(e.getAttribute('onclick')||'').slice(0,120), href:e.getAttribute('href')})).slice(0,10)
  }, null, 1)`);
  console.log('DETAIL>', detail);
}
process.exit(0);
