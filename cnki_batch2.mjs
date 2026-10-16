// CNKI 批量下载 v2（加固版）
// 改进：去掉 Page.enable；每篇新建 CDP 连接；导航/求值带重试；健康检查；熔断；断点续传
const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const DL = process.env.DL_DIR || 'C:\\Users\\ASUS\\Downloads';
const REFS = process.env.REF_FILE || 'E:\\harness\\aic\\refs.json';
const LEDGER = process.env.LEDGER || 'E:\\harness\\aic\\download_ledger.tsv';
const DELAY = Number(process.env.DELAY_MS || 3500);
const ONLY = process.env.ONLY ? process.env.ONLY.split(',').map(Number) : null;

import fs from 'node:fs';
import path from 'node:path';

const refs = JSON.parse(fs.readFileSync(REFS, 'utf8')).filter((r) => !ONLY || ONLY.includes(r.no));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- 连接与调用 ----------
function makeClient(ws) {
  let id = 0; const pending = new Map();
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
  });
  return function send(method, params = {}, ms = 30000) {
    const i = ++id;
    return new Promise((res, rej) => {
      pending.set(i, { res, rej });
      try { ws.send(JSON.stringify({ id: i, method, params })); } catch (e) { pending.delete(i); return rej(new Error('ws send: ' + e.message)); }
      setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, ms);
    });
  };
}
async function connect() {
  const targets = await (await fetch(`${BASE}/json/list`, { signal: AbortSignal.timeout(10000) })).json();
  const page = targets.find((t) => t.type === 'page');
  if (!page) throw new Error('无 page target');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error('ws open timeout')), 10000);
    ws.addEventListener('open', () => { clearTimeout(t); res(); });
    ws.addEventListener('error', () => { clearTimeout(t); rej(new Error('ws error')); });
  });
  return { send: makeClient(ws), close: () => { try { ws.close(); } catch {} } };
}
async function ev(send, expr, ms = 25000) {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true }, ms);
  if (r.exceptionDetails) throw new Error('页面异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 200));
  return r.result.value;
}
// 带重试的导航
async function goto(send, url, waitMs, tries = 3) {
  for (let a = 0; a < tries; a++) {
    try {
      await send('Page.navigate', { url }, 30000);
      await sleep(waitMs);
      const ok = await ev(send, 'document.readyState', 15000);
      return ok;
    } catch (e) {
      if (a === tries - 1) throw e;
      await sleep(2000);
    }
  }
}

// ---------- 文件监听 ----------
function snap() { const s = new Map(); for (const f of fs.readdirSync(DL)) { try { s.set(f, fs.statSync(path.join(DL, f)).size); } catch {} } return s; }
async function waitNewFile(before, timeoutMs = 75000) {
  const t0 = Date.now();
  let cand = null, lastSize = -1, stable = 0;
  while (Date.now() - t0 < timeoutMs) {
    await sleep(1500);
    const news = [...snap().entries()].filter(([k]) => !before.has(k)).sort((a, b) => b[1] - a[1]);
    if (news.length) {
      const [name, size] = news[0];
      if (name === cand && size === lastSize) { if (++stable >= 2 && size > 0) return { name, size }; }
      else { cand = name; lastSize = size; stable = 0; }
    }
  }
  return null;
}
const norm = (s) => (s || '').replace(/\s+/g, '').replace(/[（）()【】\[\]，,。.、；;：:""'']/g, '');

// ---------- 台账 ----------
const HEAD = ['#', '状态', '题名(清单)', '匹配题名', '作者', '来源', '日期', '格式', '文件名', '大小KB', '详情页'];
let rows = [HEAD];
const done = new Set();
if (fs.existsSync(LEDGER)) {
  const old = fs.readFileSync(LEDGER, 'utf8').split('\n').filter(Boolean).map((l) => l.split('\t'));
  for (const r of old.slice(1)) {
    if (String(r[1] || '').startsWith('成功')) { rows.push(r); done.add(Number(r[0])); }
  }
}
const flush = () => fs.writeFileSync(LEDGER, rows.map((r) => r.join('\t')).join('\n'), 'utf8');

// ---------- 主循环 ----------
console.log(`待处理 ${refs.length} 篇；已完成跳过 ${done.size} 篇`);
const t0 = Date.now();
let consecutiveFail = 0;
const failures = [];

for (const ref of refs) {
  if (done.has(ref.no)) { console.log(`[${ref.no}] 跳过（已完成）`); continue; }
  if (consecutiveFail >= 4) { console.log('连续失败达 4 次，熔断退出，请检查浏览器状态'); break; }

  let status = '未找到', fmt = '', fname = '', sizeKB = '', detailUrl = '', matched = '';
  let cli = null;
  try {
    cli = await connect();
    const { send } = cli;

    // 1) 精确检索（题名）
    await goto(send, `https://kns.cnki.net/kns8s/defaultresult/index?kw=${encodeURIComponent(ref.title)}&korder=TI`, DELAY + 3000);

    const title = await ev(send, 'document.title', 15000);
    if (/安全验证|验证/.test(title)) { status = 'CAPTCHA拦截'; throw new Error('captcha'); }

    const first = await ev(send, `(() => {
      const tr = document.querySelector('table.result-table-list tbody tr');
      if (!tr) return null;
      const cell = (c) => { const e = tr.querySelector('td.' + c); return e ? e.innerText.replace(/\\s+/g,' ').trim() : ''; };
      const a = tr.querySelector('td.name a');
      return JSON.stringify({ name: cell('name'), author: cell('author'), source: cell('source'), date: cell('date'), href: a ? a.getAttribute('href') : null });
    })()`, 15000);
    if (!first) { status = '检索无结果'; throw new Error('no result'); }
    const f = JSON.parse(first);
    matched = f.name; detailUrl = f.href || '';

    const a1 = norm(ref.title), a2 = norm(f.name);
    if (!(a2.includes(a1) || a1.includes(a2))) { status = '标题不匹配'; }
    else {
      const noAuthor = !ref.firstAuthor;
      const authorOk = noAuthor || f.author.includes(ref.firstAuthor);
      const srcOk = !ref.source || norm(f.source).includes(norm(ref.source)) || norm(ref.source).includes(norm(f.source));
      if (!authorOk || !srcOk) status = '元数据存疑';
      else status = noAuthor ? '匹配(机构)' : '匹配';

      if (status.startsWith('匹配') && detailUrl) {
        await goto(send, detailUrl.startsWith('http') ? detailUrl : 'https://kns.cnki.net' + detailUrl, DELAY);
        const avail = JSON.parse(await ev(send, `JSON.stringify({
          p: (() => { const e = document.querySelector('#pdfDown'); return e ? e.offsetParent !== null : false; })(),
          c: (() => { const e = document.querySelector('#cajDown'); return e ? e.offsetParent !== null : false; })()
        })`, 15000));

        const before = snap();
        if (avail.p) { await ev(send, `document.querySelector('#pdfDown').click(); 'ok'`, 15000); fmt = 'PDF'; }
        else if (avail.c) { await ev(send, `document.querySelector('#cajDown').click(); 'ok'`, 15000); fmt = 'CAJ'; }
        else status = '无可下载按钮';

        if (fmt) {
          const got = await waitNewFile(before);
          if (got) { fname = got.name; sizeKB = Math.round(got.size / 1024); status = '成功(' + fmt + ')'; }
          else { status = '下载未落盘'; fmt = ''; }
        }
      }
    }
    if (status.startsWith('成功')) consecutiveFail = 0; else consecutiveFail++;
  } catch (e) {
    if (status === '未找到' || !status.startsWith('匹配')) {
      if (status === '未找到') status = '异常:' + e.message.slice(0, 30);
    }
    consecutiveFail++;
  } finally {
    if (cli) cli.close();
  }

  if (!status.startsWith('成功')) failures.push(ref.no);
  rows.push([ref.no, status, ref.title, matched, ref.firstAuthor || '', ref.source || '', ref.year || '', fmt, fname, sizeKB, detailUrl.slice(0, 100)]);
  console.log(`[${ref.no}] ${status} | ${ref.title.slice(0, 24)} | ${fname || '-'} | ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  flush();
  await sleep(1200);
}

const ok = rows.filter((r) => String(r[1]).startsWith('成功')).length;
console.log(`\n完成：成功 ${ok} 篇；失败编号 ${failures.join(',') || '无'}；台账 ${LEDGER}`);
process.exit(0);
