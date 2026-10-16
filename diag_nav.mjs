// 诊断：Page.navigate 是否会被卡住（对比 Page.enable 的影响）
const PORT = '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const targets = await (await fetch(`${BASE}/json/list`)).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.addEventListener('open', r); ws.addEventListener('error', () => j(new Error('ws'))); });
let id = 0; const pending = new Map();
const events = [];
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
  else if (m.method) events.push(m.method);
});
function send(method, params = {}, ms = 20000) {
  const i = ++id;
  const t0 = Date.now();
  return new Promise((res, rej) => {
    pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error(`timeout(${Date.now() - t0}ms) ${method}`)); } }, ms);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function tryCall(label, fn) {
  const t0 = Date.now();
  try { const r = await fn(); console.log(`  ✓ ${label} -> ${Date.now() - t0}ms ${r === undefined ? '' : JSON.stringify(r).slice(0, 90)}`); return true; }
  catch (e) { console.log(`  ✗ ${label} -> ${Date.now() - t0}ms ${e.message.slice(0, 90)}`); return false; }
}

console.log('步骤 1: 不带 Page.enable，直接 Page.navigate');
await tryCall('Page.navigate(example.com)', () => send('Page.navigate', { url: 'https://example.com/' }, 25000));
await sleep(3000);
await tryCall('eval(location.href)', async () => (await send('Runtime.evaluate', { expression: 'location.href', returnByValue: true }, 15000)).result.value);

console.log('\n步骤 2: 再试 Page.enable（20s 超时）');
await tryCall('Page.enable', () => send('Page.enable', {}, 20000));

console.log('\n步骤 3: 知网检索页导航');
await tryCall('Page.navigate(kns8s)', () => send('Page.navigate', { url: 'https://kns.cnki.net/kns8s/defaultresult/index?kw=%E7%8C%AA&korder=TI' }, 30000));
await sleep(6000);
await tryCall('eval(title+rows)', async () => {
  const r = await send('Runtime.evaluate', { expression: 'document.title + " | rows=" + document.querySelectorAll("table.result-table-list tbody tr").length', returnByValue: true }, 15000);
  return r.result.value;
});
console.log('\n收到的事件:', [...new Set(events)].slice(0, 12).join(', '));
process.exit(0);
