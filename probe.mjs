// 探测知网检索结果页结构 + 校园网鉴权状态
const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;

const targets = await (await fetch(`${BASE}/json/list`)).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.addEventListener('open', res);
  ws.addEventListener('error', () => rej(new Error('ws fail')));
});
let id = 0;
const pending = new Map();
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id);
    pending.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
});
function send(method, params = {}) {
  const i = ++id;
  return new Promise((res, rej) => {
    pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, 90000);
  });
}
async function ev(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
  return r.result.value;
}

// 1) 校园网鉴权状态（知网用这个接口判断机构是否已登录）
const auth = await ev(`(async () => {
  try {
    const r = await fetch('https://kns.cnki.net/ecph.cnki.net/ecph/api/v1/getLoginStatus', {credentials:'include'});
    return 'getLoginStatus: ' + r.status + ' ' + (await r.text()).slice(0,200);
  } catch (e) { return 'getLoginStatus err: ' + e.message; }
})()`);
console.log('AUTH>', auth);

// 2) 结果页骨架
const struct = await ev(`JSON.stringify({
  url: location.href,
  title: document.title,
  bodyLen: document.body.innerText.length,
  tableRows: document.querySelectorAll('table.result-table-list tbody tr').length,
  resultTables: document.querySelectorAll('table').length,
  classes: [...new Set([...document.querySelectorAll('div,table,li')].map(e=>e.className).filter(c=>typeof c==='string'&&c&&/result|list|item|row|title/i.test(c)))].slice(0,40),
  links: [...document.querySelectorAll('a')].map(a=>a.getAttribute('href')).filter(h=>h&&/kcms|detail|dbcode/i.test(h)).slice(0,8),
  sampleText: document.body.innerText.slice(0, 700)
}, null, 1)`);
console.log('STRUCT>', struct);
process.exit(0);
