"use strict";

// ---------- pixel sprites ----------

const FACE_BASE = [
  "....oooooooo....",
  "..oohhhfffffoo..",
  ".ohhffffffffffo.",
  ".ohffffffffffso.",
  "ohffffffffffffso",
  "offfffffffffffso",
  "offfffffffffffso",
  "offfffffffffffso",
  "offfffffffffffso",
  "offfffffffffffso",
  "offfffffffffffso",
  "offfffffffffffso",
  ".offfffffffffso.",
  ".osfffffffffsso.",
  "..oossssssssoo..",
  "....oooooooo....",
];

const PALETTE = {
  o: "#031008",
  f: "#5fc46a",
  s: "#3a9a4a",
  h: "#b8f2a0",
  e: "#031008",
  w: "#ffffff",
  m: "#031008",
  b: "#f28a9a",
};
const ERROR_PALETTE = { ...PALETTE, f: "#9fb894", s: "#6f8a66", h: "#d4e3cc" };

// Each feature is [x, y, rows]; "." leaves the base pixel as is.
const EYE = ["we", "ee", "ee"];
const FACES = {
  idle: [
    [4, 5, EYE],
    [10, 5, EYE],
    [7, 10, ["mm"]],
  ],
  blink: [
    [4, 7, ["ee"]],
    [10, 7, ["ee"]],
    [7, 10, ["mm"]],
  ],
  thinking: [
    [5, 4, ["we", "ee"]],
    [11, 4, ["we", "ee"]],
    [9, 10, ["mm"]],
  ],
  searching: [
    [3, 5, ["wwe", "wee", "eee"]],
    [10, 5, ["wwe", "wee", "eee"]],
    [7, 10, ["mm", "mm"]],
  ],
  happy: [
    [3, 6, [".e.", "e.e"]],
    [10, 6, [".e.", "e.e"]],
    [5, 10, ["m....m", ".mmmm."]],
    [2, 9, ["bb"]],
    [12, 9, ["bb"]],
  ],
  error: [
    [3, 5, ["e.e", ".e.", "e.e"]],
    [10, 5, ["e.e", ".e.", "e.e"]],
    [5, 10, [".mmmm.", "m....m"]],
  ],
};

function faceSvg(state) {
  const grid = FACE_BASE.map((row) => row.split(""));
  for (const [x0, y0, rows] of FACES[state]) {
    rows.forEach((row, dy) =>
      [...row].forEach((ch, dx) => {
        if (ch !== ".") grid[y0 + dy][x0 + dx] = ch;
      }),
    );
  }
  const palette = state === "error" ? ERROR_PALETTE : PALETTE;
  let rects = "";
  grid.forEach((row, y) =>
    row.forEach((ch, x) => {
      if (ch !== ".") rects += `<rect x="${x}" y="${y}" width="1" height="1" fill="${palette[ch]}"/>`;
    }),
  );
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">${rects}</svg>`;
}

// ---------- DOM ----------

const $ = (id) => document.getElementById(id);
const faceEl = $("face");
const statusEl = $("status-text");
const chatLog = $("chat-log");
const input = $("input");
const sendButton = $("send");
const newChatButton = $("new-chat");
const tableEl = $("csv-table");
const ctxBar = $("ctx-bar");
const ctxValue = $("ctx-value");

const STATUS_TEXT = {
  idle: "なんでも聞いてね!",
  thinking: "かんがえ中",
  happy: "こたえたよ! 根拠の行をハイライトしたよ",
  error: "うまくいかなかった…",
};

let faceState = "idle";
let idleTimer = null;
const tableRows = new Map(); // 1-based row number -> <tr>
let columns = [];

function setFace(state, text) {
  faceState = state;
  faceEl.className = `face ${state}`;
  faceEl.innerHTML = faceSvg(state);
  statusEl.textContent = text ?? STATUS_TEXT[state];
  statusEl.classList.toggle("busy", state === "thinking" || state === "searching");
  clearTimeout(idleTimer);
  if (state === "happy" || state === "error") idleTimer = setTimeout(() => setFace("idle"), 6000);
}

setInterval(() => {
  if (faceState !== "idle") return;
  faceEl.innerHTML = faceSvg("blink");
  setTimeout(() => {
    if (faceState === "idle") faceEl.innerHTML = faceSvg("idle");
  }, 160);
}, 3800);

// ---------- table ----------

function isNumeric(value) {
  return value.trim() !== "" && !Number.isNaN(Number(value.replace(/,/g, "")));
}

function renderTable({ columns: cols, rows }) {
  columns = cols;
  const numeric = cols.map((c) => rows.some((r) => r[c].trim()) && rows.every((r) => !r[c].trim() || isNumeric(r[c])));
  const long = cols.map((c) => rows.reduce((n, r) => n + r[c].length, 0) / Math.max(rows.length, 1) > 16);

  const headRow = document.createElement("tr");
  headRow.innerHTML = `<th class="rownum">#</th>`;
  cols.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    headRow.append(th);
  });
  tableEl.tHead.replaceChildren(headRow);

  const body = tableEl.tBodies[0];
  body.replaceChildren();
  tableRows.clear();
  rows.forEach((row, i) => {
    const tr = document.createElement("tr");
    const num = document.createElement("td");
    num.className = "rownum";
    num.textContent = i + 1;
    tr.append(num);
    cols.forEach((c, j) => {
      const td = document.createElement("td");
      td.textContent = row[c];
      if (numeric[j]) td.classList.add("num");
      if (long[j]) td.classList.add("long");
      tr.append(td);
    });
    body.append(tr);
    tableRows.set(i + 1, tr);
  });
}

function applyEvidence(evidence) {
  for (const tr of tableRows.values()) {
    tr.classList.remove("ev-row");
    for (const td of tr.cells) td.classList.remove("ev-cell");
  }
  if (!evidence) return;
  for (const n of evidence.rows) tableRows.get(n)?.classList.add("ev-row");
  for (const [n, column] of evidence.cells) {
    const index = columns.indexOf(column);
    const td = tableRows.get(n)?.cells[index + 1];
    if (td) {
      td.classList.remove("ev-cell");
      void td.offsetWidth; // restart the blink animation
      td.classList.add("ev-cell");
    }
  }
  const first = Math.min(...evidence.rows);
  tableRows.get(first)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function mergeEvidence(a, b) {
  const rows = new Set([...a.rows, ...b.rows]);
  const cells = new Map([...a.cells, ...b.cells].map((c) => [c.join("\u0000"), c]));
  return { rows: [...rows].sort((x, y) => x - y), cells: [...cells.values()] };
}

// ---------- context bar ----------

const SEGMENTS = 20;
ctxBar.innerHTML = "<i></i>".repeat(SEGMENTS);

function updateContext(tokens, limit) {
  const ratio = limit ? Math.min(tokens / limit, 1) : 0;
  const on = Math.ceil(ratio * SEGMENTS);
  [...ctxBar.children].forEach((seg, i) => seg.classList.toggle("on", i < on));
  ctxBar.classList.toggle("warn", ratio >= 0.6 && ratio < 0.85);
  ctxBar.classList.toggle("full", ratio >= 0.85);
  ctxValue.textContent = limit
    ? `${tokens.toLocaleString()} / ${limit.toLocaleString()}`
    : `${tokens.toLocaleString()} tok`;
}

// ---------- chat ----------

function timeNow() {
  return new Date().toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

// Models often answer in Markdown; render only bold and inline code, keep the rest as text.
function renderMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^#{1,6}\s+/gm, "");
}

function addMessage(role, text) {
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  const body = document.createElement("div");
  body.className = "msg-body";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.innerHTML = role === "user" ? `<span>既読</span><span>${timeNow()}</span>` : `<span>${timeNow()}</span>`;

  if (role === "agent") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerHTML = faceSvg("idle");
    const name = document.createElement("div");
    name.className = "msg-name";
    name.textContent = "AGENT";
    body.append(name);
    msg.append(avatar);
  }
  const row = document.createElement("div");
  row.className = "bubble-row";
  row.append(bubble, meta);
  body.append(row);
  msg.append(body);
  chatLog.append(msg);
  chatLog.scrollTop = chatLog.scrollHeight;
  return { msg, body, bubble };
}

function selectBubble(bubble, evidence) {
  chatLog.querySelectorAll(".bubble.selected").forEach((b) => b.classList.remove("selected"));
  bubble.classList.add("selected");
  applyEvidence(evidence);
}

function describeEvidence(evidence) {
  const rows = evidence.rows;
  const shown = rows.slice(0, 8).join(", ") + (rows.length > 8 ? " …" : "");
  return `根拠: 行 ${shown} (${rows.length}件)`;
}

function formatArgs(args) {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
}

async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    if (done) break;
  }
}

function setBusy(busy) {
  input.disabled = busy;
  sendButton.disabled = busy;
  newChatButton.disabled = busy;
  if (!busy) input.focus();
}

async function ask(question) {
  addMessage("user", question);
  const agent = addMessage("agent", "…");
  agent.msg.querySelector(".avatar").innerHTML = faceSvg("thinking");
  const toolLog = document.createElement("div");
  toolLog.className = "tool-log";
  agent.body.append(toolLog);

  setBusy(true);
  setFace("thinking");
  let live = { rows: [], cells: [] };

  const fail = (message) => {
    agent.msg.classList.add("error");
    agent.bubble.textContent = message;
    agent.msg.querySelector(".avatar").innerHTML = faceSvg("error");
    setFace("error");
  };

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (response.status === 409) return fail("いま別の質問に回答中です。少し待ってね。");
    if (!response.ok) return fail(`サーバーエラー (${response.status})`);

    await readEvents(response, (event) => {
      if (event.type === "tool") {
        setFace("searching", `${event.name} でしらべ中`);
        const line = document.createElement("div");
        line.textContent = `${event.name}(${formatArgs(event.arguments)})`;
        toolLog.append(line);
        live = mergeEvidence(live, event.evidence);
        applyEvidence(live);
      } else if (event.type === "answer") {
        agent.bubble.innerHTML = renderMarkdown(event.content || "(空の回答)");
        agent.msg.querySelector(".avatar").innerHTML = faceSvg("happy");
        contextLimit = event.context_limit;
        updateContext(event.context_tokens, contextLimit);
        const evidence = event.evidence;
        if (evidence.rows.length) {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "evidence-chip";
          chip.textContent = describeEvidence(evidence);
          chip.addEventListener("click", () => selectBubble(agent.bubble, evidence));
          agent.body.append(chip);
          agent.bubble.classList.add("has-evidence");
          agent.bubble.addEventListener("click", () => selectBubble(agent.bubble, evidence));
          selectBubble(agent.bubble, evidence);
          setFace("happy");
        } else {
          applyEvidence(null);
          setFace("happy", "こたえたよ!");
        }
      } else if (event.type === "error") {
        fail(`エラー: ${event.message}`);
      }
      chatLog.scrollTop = chatLog.scrollHeight;
    });
  } catch (e) {
    fail(`通信エラー: ${e.message}`);
  } finally {
    setBusy(false);
  }
}

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question || input.disabled) return;
  input.value = "";
  input.style.height = "";
  ask(question);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("composer").requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "";
  input.style.height = `${input.scrollHeight}px`;
});

// The server keeps one conversation; a fresh page starts a fresh one.
async function newConversation(rowCount, columnCount) {
  await fetch("/api/reset", { method: "POST" });
  chatLog.replaceChildren();
  applyEvidence(null);
  updateContext(0, contextLimit);
  setFace("idle");
  addMessage("agent", `こんにちは! ${rowCount}行 × ${columnCount}列のCSVを読みこんだよ。\n質問してね。`);
  input.focus();
}

// ---------- resizable layout ----------

// Sizes are stored as shares of the layout (wide) or the viewport height (narrow), so they scale with the window.
const SPLIT_KEY = "csv-agent.split";
const TABLE_H_KEY = "csv-agent.table-h";
const DEFAULT_SPLIT = 0.6;
const DEFAULT_TABLE_H = 0.45;
const narrow = window.matchMedia("(max-width: 860px)");
const layoutEl = document.querySelector(".layout");
const splitter = $("splitter");

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

function loadShare(key, fallback) {
  try {
    const value = Number(localStorage.getItem(key));
    return value > 0 && value < 1 ? value : fallback;
  } catch {
    return fallback;
  }
}

function saveShares() {
  try {
    localStorage.setItem(SPLIT_KEY, String(split));
    localStorage.setItem(TABLE_H_KEY, String(tableH));
  } catch {
    // Storage unavailable: sizes just won't persist.
  }
}

let split = loadShare(SPLIT_KEY, DEFAULT_SPLIT);
let tableH = loadShare(TABLE_H_KEY, DEFAULT_TABLE_H);

function applyShares() {
  const style = document.documentElement.style;
  style.setProperty("--split", `${(split * 100).toFixed(2)}%`);
  style.setProperty("--table-h", `${(tableH * 100).toFixed(2)}vh`);
  splitter.setAttribute("aria-orientation", narrow.matches ? "horizontal" : "vertical");
}

function moveSplit(delta) {
  if (narrow.matches) tableH = clamp(tableH + delta, 0.15, 0.75);
  else split = clamp(split + delta, 0.1, 0.9);
  applyShares();
}

function dragTo(clientX, clientY) {
  if (narrow.matches) {
    const top = document.querySelector(".table-panel").getBoundingClientRect().top;
    tableH = clamp((clientY - top) / window.innerHeight, 0.15, 0.75);
  } else {
    const box = layoutEl.getBoundingClientRect();
    const style = getComputedStyle(layoutEl);
    const left = box.left + parseFloat(style.paddingLeft);
    const width = box.width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    split = clamp((clientX - left) / width, 0.1, 0.9);
  }
  applyShares();
}

splitter.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  splitter.setPointerCapture(e.pointerId);
  splitter.classList.add("dragging");
  document.body.classList.add("resizing");
  document.body.classList.toggle("vertical", narrow.matches);
});

splitter.addEventListener("pointermove", (e) => {
  if (splitter.hasPointerCapture(e.pointerId)) dragTo(e.clientX, e.clientY);
});

function endDrag(e) {
  if (!splitter.hasPointerCapture(e.pointerId)) return;
  splitter.releasePointerCapture(e.pointerId);
  splitter.classList.remove("dragging");
  document.body.classList.remove("resizing", "vertical");
  saveShares();
}
splitter.addEventListener("pointerup", endDrag);
splitter.addEventListener("pointercancel", endDrag);

splitter.addEventListener("dblclick", () => {
  if (narrow.matches) tableH = DEFAULT_TABLE_H;
  else split = DEFAULT_SPLIT;
  applyShares();
  saveShares();
});

splitter.addEventListener("keydown", (e) => {
  const step = e.shiftKey ? 0.1 : 0.02;
  const delta = { ArrowLeft: -step, ArrowUp: -step, ArrowRight: step, ArrowDown: step }[e.key];
  if (delta === undefined) return;
  e.preventDefault();
  moveSplit(delta);
  saveShares();
});

narrow.addEventListener("change", applyShares);
applyShares();

// ---------- startup ----------

let contextLimit = null;

async function init() {
  setFace("idle");
  const icon = document.createElement("link");
  icon.rel = "icon";
  icon.href = `data:image/svg+xml,${encodeURIComponent(faceSvg("happy"))}`;
  document.head.append(icon);
  const [table, status] = await Promise.all([
    fetch("/api/table").then((r) => r.json()),
    fetch("/api/status").then((r) => r.json()),
  ]);
  renderTable(table);
  $("model").textContent = `MODEL: ${status.model}`;
  contextLimit = status.context_limit;
  newChatButton.addEventListener("click", () => newConversation(table.rows.length, table.columns.length));
  await newConversation(table.rows.length, table.columns.length);
}

init();
