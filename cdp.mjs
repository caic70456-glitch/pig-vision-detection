// 极简 CDP 客户端：通过 Node 内置 WebSocket 驱动 Edge
// 用法: node cdp.mjs <command> [args...]
const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;

async function listTargets() {
  const r = await fetch(`${BASE}/json/list`);
  return r.json();
}

class Session {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.events = [];
    ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
      } else if (msg.method) {
        this.events.push(msg);
      }
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify(payload));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`timeout: ${method}`));
        }
      }, 60000);
    });
  }
}

async function connect() {
  const targets = await listTargets();
  const page = targets.find((t) => t.type === 'page');
  if (!page) throw new Error('没有可用的 page target');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res);
    ws.addEventListener('error', () => rej(new Error('WebSocket 连接失败')));
  });
  return { session: new Session(ws), page };
}

// 允许浏览器把 result 里的 promise 解析完再返回
async function evaluate(session, expression) {
  const r = await session.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (r.exceptionDetails) {
    throw new Error('页面脚本异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 300));
  }
  return r.result.value;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const cmd = process.argv[2];

if (cmd === 'version') {
  const r = await fetch(`${BASE}/json/version`);
  console.log(JSON.stringify(await r.json(), null, 2));
} else if (cmd === 'targets') {
  console.log(JSON.stringify(await listTargets(), null, 2));
} else if (cmd === 'navigate') {
  const url = process.argv[3];
  const { session } = await connect();
  await session.send('Page.enable');
  await session.send('Page.navigate', { url });
  await sleep(Number(process.argv[4] || 6000));
  const info = await evaluate(session, `JSON.stringify({url:location.href,title:document.title,ready:document.readyState})`);
  console.log(info);
} else if (cmd === 'eval') {
  const { session } = await connect();
  console.log(await evaluate(session, process.argv[3]));
} else if (cmd === 'echo') {
  const { session, page } = await connect();
  console.log(JSON.stringify({ url: page.url, title: page.title }, null, 2));
  console.log(await evaluate(session, process.argv[3] || '"ok"'));
} else {
  console.log('commands: version | targets | navigate <url> [waitMs] | eval <expr> | echo [expr]');
}
process.exit(0);
