// CNKI 批量下载（通过真实 Edge + CDP）
// 流程：按标题精确检索 -> 校验作者/来源/年份 -> 打开详情页 -> 点 PDF下载 -> 回退 CAJ下载
// 输出：Downloads 目录中的文件 + 台账 TSV
const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const DL = process.env.DL_DIR || 'C:\\Users\\ASUS\\Downloads';
const REFS = process.env.REF_FILE || 'E:\\harness\\aic\\refs.json';
const LEDGER = process.env.LEDGER || 'E:\\harness\\aic\\download_ledger.tsv';
const DELAY = Number(process.env.DELAY_MS || 4000);

import fs from 'node:fs';
import path from 'node:path';

const refs = JSON.parse(fs.readFileSync(REFS, 'utf8'));

const targets = await (await fetch(`${BASE}/json/list`)).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', () => rej(new Error('ws fail'))); });
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
function send(method, params = {}) { const i = ++id; return new Promise((res, rej) => { pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, 120000); }); }
async function ev(expr) { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 300)); return r.result.value; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function snap() { const s = new Map(); for (const f of fs.readdirSync(DL)) { try { s.set(f, fs.statSync(path.join(DL, f)).size); } catch {} } return s; }
// 找到新出现的、且大小稳定的文件
async function waitNewFile(before, timeoutMs = 60000) {
  const t0 = Date.now();
  let cand = null, lastSize = -1, stable = 0;
  while (Date.now() - t0 < timeoutMs) {
    await sleep(1500);
    const now = snap();
    const news = [...now.entries()].filter(([k]) => !before.has(k));
    if (news.length) {
      news.sort((a, b) => b[1] - a[1]);
      const [name, size] = news[0];
      if (name === cand && size === lastSize) { stable++; if (stable >= 2 && size > 0) return { name, size }; }
      else { cand = name; lastSize = size; stable = 0; }
    }
  }
  return null;
}
const norm = (s) => (s || '').replace(/\s+/g, '').replace(/[（）()【】\[\]，,。.、；;：:""'']/g, '');

const rows = [['#', '状态', '题名(清单)', '匹配题名', '作者', '来源', '日期', '格式', '文件名', '大小KB', '详情页']];
const t0 = Date.now();

for (const ref of refs) {
  const line = [];
  let status = '未找到', fmt = '', fname = '', sizeKB = '', detailUrl = '', matched = '';
  try {
    // 1) 精确检索
    const q = encodeURIComponent(ref.title);
    await send('Page.enable');
    await send('Page.navigate', { url: `https://kns.cnki.net/kns8s/defaultresult/index?kw=${q}&korder=TI` });
    await sleep(DELAY + 2500);

    const cap = await ev(`JSON.stringify({title: document.title, needVerify: /安全验证|验证/.test(document.title)})`);
    const capInfo = JSON.parse(cap);
    if (capInfo.needVerify) { status = 'CAPTCHA拦截'; throw new Error('captcha'); }

    // 2) 取第一行并校验
    const first = await ev(`(() => {
      const tr = document.querySelector('table.result-table-list tbody tr');
      if (!tr) return null;
      const cell = (c) => { const e = tr.querySelector('td.' + c); return e ? e.innerText.replace(/\\s+/g,' ').trim() : ''; };
      const a = tr.querySelector('td.name a');
      return JSON.stringify({ name: cell('name'), author: cell('author'), source: cell('source'), date: cell('date'), href: a ? a.getAttribute('href') : null });
    })()`);
    if (!first) { status = '检索无结果'; throw new Error('no result'); }
    const f = JSON.parse(first);
    matched = f.name;
    detailUrl = f.href || '';

    // 标题必须高度一致（防止匹配到同主题的其他文章）
    const a1 = norm(ref.title), a2 = norm(f.name);
    if (!(a2.includes(a1) || a1.includes(a2))) { status = '标题不匹配(已跳过)'; }
    else {
      // 机构文献（农业农村部公告、团体标准、报纸）没有个人作者，跳过作者校验
      const noAuthor = !ref.firstAuthor;
      const authorOk = noAuthor || f.author.includes(ref.firstAuthor);
      const srcOk = !ref.source || norm(f.source).includes(norm(ref.source)) || norm(ref.source).includes(norm(f.source));
      if (!authorOk || !srcOk) status = '元数据存疑';
      else status = noAuthor ? '匹配(机构文献)' : '匹配';

      if (status.startsWith('匹配') && detailUrl) {
        // 3) 打开详情页
        await send('Page.navigate', { url: detailUrl.startsWith('http') ? detailUrl : 'https://kns.cnki.net' + detailUrl });
        await sleep(DELAY);
        const avail = JSON.parse(await ev(`JSON.stringify({
          hasPdf: !!document.querySelector('#pdfDown'),
          hasCaj: !!document.querySelector('#cajDown'),
          pdfVisible: (() => { const e = document.querySelector('#pdfDown'); return e ? e.offsetParent !== null : false; })(),
          cajVisible: (() => { const e = document.querySelector('#cajDown'); return e ? e.offsetParent !== null : false; })()
        })`));

        const before = snap();
        if (avail.hasPdf && avail.pdfVisible) { await ev(`document.querySelector('#pdfDown').click(); 'ok'`); fmt = 'PDF'; }
        else if (avail.hasCaj && avail.cajVisible) { await ev(`document.querySelector('#cajDown').click(); 'ok'`); fmt = 'CAJ'; }
        else { status = '无可下载按钮'; }

        if (fmt) {
          const got = await waitNewFile(before, 70000);
          if (got) { fname = got.name; sizeKB = Math.round(got.size / 1024); status = '成功(' + fmt + ')'; }
          else { status = '下载未落盘'; fmt = ''; }
        }
      }
    }
  } catch (e) {
    if (status === '未找到') status = '异常:' + e.message.slice(0, 40);
  }

  rows.push([ref.no, status, ref.title, matched, ref.firstAuthor || '', ref.source || '', ref.year || '', fmt, fname, sizeKB, detailUrl.slice(0, 120)]);
  const elapsed = ((Date.now() - t0) / 1000).toFixed(0);
  console.log(`[${ref.no}/50] ${status} | ${ref.title.slice(0, 26)} | ${fname || '-'} | ${elapsed}s`);
  fs.writeFileSync(LEDGER, rows.map((r) => r.join('\t')).join('\n'), 'utf8');
  await sleep(1200);
}

const ok = rows.filter((r) => String(r[1]).startsWith('成功')).length;
console.log(`\n完成：成功 ${ok} / ${refs.length}，台账：${LEDGER}`);
process.exit(0);
