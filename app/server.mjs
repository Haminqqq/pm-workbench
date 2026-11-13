// PM 中台：本機網頁 + Claude Agent SDK。只綁 127.0.0.1，不對外。
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { query } from "@anthropic-ai/claude-agent-sdk";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");               // pm-workbench
const PORT = Number(process.env.PM_PORT || 3737);
const CONFIG = readJson(path.join(HERE, "config.json"), {});
const ACTIONS = readJson(path.join(HERE, "actions.json"), []);
const LOG_DIR = path.join(HERE, "log");
fs.mkdirSync(LOG_DIR, { recursive: true });

function readJson(p, d) { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return d; } }
function today() { return new Date().toISOString().slice(0, 10); }
function logLine(obj) { fs.appendFileSync(path.join(LOG_DIR, today() + ".jsonl"), JSON.stringify({ t: Date.now(), ...obj }) + "\n"); }

// ---------- 狀態 ----------
const clients = new Set();                  // SSE
const state = { running: false, sessionId: null, mode: CONFIG.permissionMode || "default", pending: null, history: [] };
const pendingResolvers = new Map();         // requestId -> resolve(PermissionResult)
const alwaysAllow = new Set(CONFIG.alwaysAllow || ["Read", "Glob", "Grep", "LS", "TodoWrite", "TodoRead", "WebFetch", "WebSearch", "Skill", "ToolSearch"]);

function emit(ev) {
  const line = `data: ${JSON.stringify(ev)}\n\n`;
  for (const res of clients) res.write(line);
  if (ev.type !== "delta") { state.history.push(ev); if (state.history.length > 400) state.history.shift(); logLine(ev); }
}

// ---------- 使用者輸入佇列（streaming input mode）----------
const inbox = [];
let wake = null;
function pushUser(text) {
  inbox.push({ type: "user", message: { role: "user", content: text }, parent_tool_use_id: null });
  if (wake) { const w = wake; wake = null; w(); }
}
async function* userStream() {
  while (true) {
    if (inbox.length) { yield inbox.shift(); continue; }
    await new Promise(r => (wake = r));
  }
}

// ---------- 權限 / 提問 ----------
async function canUseTool(toolName, input, opts) {
  if (toolName === "AskUserQuestion") {
    return ask({ kind: "question", toolName, input, requestId: opts.toolUseID });
  }
  if (alwaysAllow.has(toolName)) return { behavior: "allow", updatedInput: input };
  return ask({ kind: "permission", toolName, input, requestId: opts.toolUseID, reason: opts.decisionReason || "" });
}
function ask(req) {
  state.pending = req;
  emit({ type: "ask", ...req });
  return new Promise(resolve => pendingResolvers.set(req.requestId, resolve));
}
function answer(requestId, body) {
  const resolve = pendingResolvers.get(requestId);
  if (!resolve) return false;
  pendingResolvers.delete(requestId); state.pending = null;
  const req = state.history.findLast?.(h => h.type === "ask" && h.requestId === requestId);
  if (body.deny) { resolve({ behavior: "deny", message: body.message || "使用者拒絕" }); emit({ type: "answered", requestId, text: "✖ 拒絕" }); return true; }
  if (req?.kind === "question") {
    resolve({ behavior: "allow", updatedInput: { questions: req.input.questions, answers: body.answers || {} } });
    emit({ type: "answered", requestId, text: Object.entries(body.answers || {}).map(([q, a]) => `${q} → ${Array.isArray(a) ? a.join("、") : a}`).join("\n") });
  } else {
    if (body.always && req) alwaysAllow.add(req.toolName);
    resolve({ behavior: "allow", updatedInput: req?.input || {} });
    emit({ type: "answered", requestId, text: "✔ 允許" + (body.always ? "（這次 session 都允許）" : "") });
  }
  return true;
}

// ---------- Claude 主迴圈 ----------
let q = null;
async function ensureAgent(cont) {
  if (q) return;
  const options = {
    cwd: ROOT,
    settingSources: ["user", "project"],
    permissionMode: state.mode,
    includePartialMessages: true,
    canUseTool,
    systemPrompt: { type: "preset", preset: "claude_code", append: CONFIG.systemAppend || "妳在「PM 中台」裡跟她對話：回覆繁體中文、短句；要她決定的事用 AskUserQuestion 問，不要用文字問；每個流程先摘要、再提問、她同意才執行；絕不寄信、不自動貼進 Teams。" },
    env: { ...process.env },
  };
  if (cont) options.continue = true;               // 接續這個資料夾最近一次對話（終端機或中台都算）
  if (CONFIG.model) options.model = CONFIG.model;
  if (CONFIG.pathToClaudeCodeExecutable) options.pathToClaudeCodeExecutable = CONFIG.pathToClaudeCodeExecutable;
  q = query({ prompt: userStream(), options });
  (async () => {
    try {
      for await (const m of q) handle(m);
    } catch (e) {
      emit({ type: "error", text: String(e?.message || e) });
    } finally {
      q = null; state.running = false; emit({ type: "status", running: false, text: "Claude 已停止，下一個指令會重新啟動" });
    }
  })();
}

let textBuf = "";
function handle(m) {
  if (m.type === "system" && m.subtype === "init") { state.sessionId = m.session_id; emit({ type: "status", running: true, text: `已連線（${m.model}）`, sessionId: m.session_id, started: true }); return; }
  if (m.type === "stream_event") {
    const ev = m.event;
    if (ev.type === "content_block_delta" && ev.delta?.type === "text_delta") { textBuf += ev.delta.text; emit({ type: "delta", text: ev.delta.text }); }
    return;
  }
  if (m.type === "assistant") {
    for (const b of m.message?.content || []) {
      if (b.type === "tool_use" && b.name !== "AskUserQuestion") emit({ type: "tool", name: b.name, input: summarizeInput(b.name, b.input) });
    }
    if (textBuf) { emit({ type: "assistant", text: textBuf }); textBuf = ""; }
    return;
  }
  if (m.type === "result") {
    state.running = false;
    emit({ type: "done", ok: m.subtype === "success", cost: m.total_cost_usd, turns: m.num_turns, errors: m.errors || [] });
  }
}
function summarizeInput(name, input) {
  if (!input) return "";
  if (name === "Bash") return input.command || "";
  if (input.file_path) return input.file_path;
  if (input.pattern) return input.pattern;
  const s = JSON.stringify(input); return s.length > 160 ? s.slice(0, 160) + "…" : s;
}

// ---------- HTTP ----------
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml" };
function json(res, code, obj) { res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" }); res.end(JSON.stringify(obj)); }
function body(req) { return new Promise(r => { let s = ""; req.on("data", c => s += c); req.on("end", () => { try { r(JSON.parse(s || "{}")); } catch { r({}); } }); }); }

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/api/events") {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
    res.write(`data: ${JSON.stringify({ type: "hello", actions: ACTIONS, state: { running: state.running, mode: state.mode, pending: state.pending, history: state.history.slice(-120) } })}\n\n`);
    clients.add(res); req.on("close", () => clients.delete(res)); return;
  }
  if (url.pathname === "/api/run" && req.method === "POST") {
    const b = await body(req); const text = String(b.text || "").trim();
    if (!text) return json(res, 400, { error: "empty" });
    if (state.pending) return json(res, 409, { error: "先回答畫面上的問題" });
    const cont = !!b.continue && !q;
    await ensureAgent(cont); state.running = true; emit({ type: "user", text: (cont ? "（接續上次對話）" : "") + text }); pushUser(text); return json(res, 200, { ok: true });
  }
  if (url.pathname === "/api/answer" && req.method === "POST") {
    const b = await body(req); return json(res, answer(b.requestId, b) ? 200 : 404, { ok: true });
  }
  if (url.pathname === "/api/stop" && req.method === "POST") {
    if (q) { try { await q.interrupt(); } catch { } } emit({ type: "status", running: false, text: "已中斷" }); state.running = false; return json(res, 200, { ok: true });
  }
  if (url.pathname === "/api/mode" && req.method === "POST") {
    const b = await body(req); state.mode = b.mode || "default";
    if (q) { try { await q.setPermissionMode(state.mode); } catch { } }
    emit({ type: "status", running: state.running, text: `權限模式：${state.mode}` }); return json(res, 200, { ok: true });
  }
  if (url.pathname === "/api/open" && req.method === "POST") {   // 用預設程式開本機檔案（CRD、截圖）
    const b = await body(req); const p = path.resolve(ROOT, String(b.path || ""));
    if (!p.startsWith(ROOT) && !(CONFIG.openRoots || []).some(r => p.startsWith(r))) return json(res, 403, { error: "不在允許的資料夾" });
    const { spawn } = await import("node:child_process"); spawn("cmd", ["/c", "start", "", p], { detached: true, stdio: "ignore" }).unref(); return json(res, 200, { ok: true });
  }
  // 靜態檔
  let fp = path.join(HERE, "public", url.pathname === "/" ? "index.html" : url.pathname);
  if (!fp.startsWith(path.join(HERE, "public"))) { res.writeHead(403); return res.end(); }
  if (!fs.existsSync(fp)) { res.writeHead(404); return res.end("not found"); }
  res.writeHead(200, { "Content-Type": MIME[path.extname(fp)] || "application/octet-stream" }); fs.createReadStream(fp).pipe(res);
});
server.listen(PORT, "127.0.0.1", () => console.log(`PM 中台：http://127.0.0.1:${PORT}  （工作資料夾 ${ROOT}）`));
