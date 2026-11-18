/* The web chat page (#30). Rules: docs/reference/web.md, *The page*.
   Built from the screens of docs/discovery/prototypes/web-ui.html; talks to the JSON API of src/web/app.py. */
"use strict";

const T = JSON.parse(document.getElementById("texts").textContent);
const STORE = "vn-tax-law-rag.conversations";  // localStorage key (choice 7A)
const MAX_CONVERSATIONS = 50;
const POLL_MS = 2000;
const WIDE = 1280;  // from here the source panel sits beside the answer and the first source opens by itself
const LINK_WORDS = { amends: "được sửa đổi, bổ sung bởi", replaces: "được thay thế bởi", repeals: "bị bãi bỏ bởi" };

const $ = s => document.querySelector(s);
const app = $("#app"), inner = $("#thread-inner"), input = $("#composer-input");
const ic = (id, cls = "icon icon-sm") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = u => /^https?:\/\//i.test(u || "") ? u : "#";
const dmy = iso => iso ? iso.split("-").reverse().join("/") : "không rõ";
const seconds = s => s.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/* ---------- state ---------- */
let status = "loading";      // the API's: loading, ready, error
let conversations = read();  // newest first; each {id, title, updated, turns: [{question, answer, vote}]}
let current = null;          // the open conversation, or null for a new one
let pending = null;          // {question, started, failed: null | "error" | "quota"}
let panel = null;            // [turn index, source number]
let documents = null;
let timer = null, lastFocus = null, toDelete = null;

function read() {
  try {
    const value = JSON.parse(localStorage.getItem(STORE) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (e) { return []; }
}
function save() {
  conversations.sort((a, b) => b.updated - a.updated);
  conversations = conversations.slice(0, MAX_CONVERSATIONS);
  try { localStorage.setItem(STORE, JSON.stringify(conversations)); } catch (e) { /* storage full or blocked: kept in memory only */ }
}

/* ---------- the API ---------- */
async function poll() {
  try {
    status = (await (await fetch("api/status")).json()).status;
  } catch (e) { status = "loading"; }
  if (status === "loading") setTimeout(poll, POLL_MS);
  if (status === "ready") loadDocuments();
  render();
}
async function retryLoad() {
  status = "loading"; render();
  try { await fetch("api/load", { method: "POST" }); } catch (e) { /* the poll tells */ }
  poll();
}
async function loadDocuments() {
  if (documents) return;
  try {
    const response = await fetch("api/documents");
    if (response.ok) documents = (await response.json()).documents;
  } catch (e) { return; }
  document.querySelectorAll("[data-count]").forEach(el => { if (documents) el.textContent = documents.length; });
}

async function ask(question) {
  const conversation = current;
  const earlier = conversation ? conversation.turns.map(t => t.question) : [];
  pending = { question, started: Date.now(), failed: null, conversation };
  closePanel(); render(); scrollDown();
  let response, body;
  try {
    response = await fetch("api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify({ question, earlier }) });
    body = await response.json();
  } catch (e) { response = null; }
  if (pending === null || pending.question !== question || pending.conversation !== conversation) return;  // dropped
  if (response && response.ok) {
    const turn = { question: body.question, answer: body, vote: null };
    let target = conversation;
    if (target) { target.turns.push(turn); target.updated = Date.now(); }
    else {
      target = { id: String(Date.now()), title: body.question, updated: Date.now(), turns: [turn] };
      conversations.unshift(target);
      if (current === null) current = target;  // still on the new conversation
    }
    pending = null;
    save(); render();
    if (current === target) { scrollDown(); if (wide() && body.sources.length) openPanel(target.turns.length - 1, 1); }
    return;
  }
  if (response && response.status === 503) { pending = null; status = "loading"; poll(); input.value = question; return; }
  pending.failed = response && response.status === 429 ? "quota" : "error";
  render(); scrollDown();
}

/* ---------- render ---------- */
function chip(ti, n) {
  return n ? `<button class="cite" type="button" data-turn="${ti}" data-src="${n}" aria-label="Nguồn ${n}">${n}</button>`
           : `<span class="cite flag" title="Trích dẫn không có trong văn bản đã tìm được" aria-label="Trích dẫn không kiểm chứng được">?</span>`;
}
const answerHead = (extra = "") => `<div class="a-head"><span class="dot" aria-hidden="true">${ic("scale", "icon")}</span>Trả lời${extra}</div>`;
const notice = () => `<div class="callout callout-info" role="note">${ic("info")}<div>${esc(T.NOTICE)}</div></div>`;

function place(s) {  // "Điều 5, khoản 25"
  return `Điều ${s.article}` + (s.clause ? `, khoản ${s.clause}` : "");
}
function numbers(answer) {  // a source id's number on the page: 1…n, the order of the sources
  return Object.fromEntries(answer.sources.map((s, i) => [s.id, i + 1]));
}

function renderAnswer(turn, ti, many) {
  const a = turn.answer, by = numbers(a);
  const label = many ? `Câu trả lời ${ti + 1}` : "Câu trả lời";
  let h = `<article class="a" aria-label="${label}">${answerHead()}`;
  if (a.not_found) {
    h += `<div class="a-body nf">${a.sentences.map(s => `<p>${esc(s.text)}</p>`).join("")}</div>
      <div class="callout callout-tip">${ic("info")}<div><b>Thử hỏi lại</b><ul>
        <li>nêu rõ loại thuế và đối tượng, ví dụ “hộ kinh doanh”, “thuế thu nhập cá nhân”;</li>
        <li>dẫn số hiệu nếu biết, ví dụ “Điều 9 Luật 48/2024/QH15”;</li>
        <li>xem câu hỏi có nằm trong <button type="button" class="linkbtn" data-act="docs"><span data-count>${documents ? documents.length : "các"}</span> văn bản hiện có</button> không.</li></ul></div></div>`;
  } else {
    const body = a.sentences.length - a.notices;
    const sentence = s => esc(s.text) + s.citations.map(id => chip(ti, by[id])).join("");
    h += `<div class="a-body"><p>${a.sentences.slice(0, body).map(sentence).join(" ")}</p>` +
      (a.notices ? `<p class="notices">${a.sentences.slice(body).map(sentence).join(" ")}</p>` : "") + `</div>`;
    if (a.sources.length) {
      h += `<section class="sources" aria-label="Nguồn của ${label.toLowerCase()}"><h3>Nguồn <span class="count">· ${a.sources.length} điều khoản</span></h3><ol class="src-list">` +
        a.sources.map((s, i) => `<li class="src" data-turn="${ti}" data-row="${i + 1}">
          <button class="src-open" type="button" data-turn="${ti}" data-src="${i + 1}"><span class="cite" aria-hidden="true">${i + 1}</span><span class="src-title"><span class="name">${esc(s.document)}, ${esc(place(s))}${s.amended_by.length ? ` <span class="tag tag-amended">${ic("history", "icon icon-xs")}Đã sửa đổi</span>` : ""}</span><span class="src-meta">${esc(s.title)}</span></span></button>
          <a class="src-ext" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener" aria-label="Mở ${esc(s.document)} trên luatvietnam.vn (tab mới)">${ic("ext")}</a></li>`).join("") + `</ol></section>`;
    }
    if (a.flagged.length) {
      h += `<div class="callout callout-warn" role="note">${ic("warn")}<div>${a.flagged.length > 1 ? "Một số trích dẫn" : "Một trích dẫn"} (mã <b>${a.flagged.map(esc).join(", ")}</b>) không có trong các đoạn văn bản đã tìm được, nên ý đi kèm chip <b>?</b> chưa được kiểm chứng.</div></div>`;
    }
  }
  h += notice() + `<div class="a-actions">
      <button class="btn btn-ghost btn-icon sm" type="button" data-act="copy" data-turn="${ti}" aria-label="Sao chép câu trả lời" title="Sao chép">${ic("copy")}</button>
      <button class="btn btn-ghost btn-icon sm" type="button" aria-pressed="${turn.vote === "up"}" data-vote="up" data-turn="${ti}" aria-label="Câu trả lời hữu ích" title="Hữu ích">${ic("up")}</button>
      <button class="btn btn-ghost btn-icon sm" type="button" aria-pressed="${turn.vote === "down"}" data-vote="down" data-turn="${ti}" aria-label="Câu trả lời chưa đúng" title="Chưa đúng">${ic("down")}</button>
      <span class="sep"></span><span class="time">${seconds(a.seconds)} giây${a.sources.length ? ` · ${a.sources.length} nguồn` : ""}</span>
    </div></article>`;
  return h;
}

function renderPending(p) {
  const q = `<div class="q"><span class="sr-only">Bạn hỏi: </span>${esc(p.question)}</div>`;
  if (!p.failed) {
    return q + `<article class="a" aria-busy="true" aria-label="Đang trả lời">
      ${answerHead(` <span class="live" role="status"><span class="spinner" aria-hidden="true"></span>${esc(T.SPINNER)}</span><span class="elapsed" id="elapsed">${elapsed()}</span>`)}
      <div class="skel" aria-hidden="true"><i style="width:96%"></i><i style="width:88%"></i><i style="width:92%"></i><i style="width:54%"></i></div>
    </article>`;
  }
  return q + `<article class="a" aria-label="Lỗi khi trả lời">${answerHead()}
      <div class="callout callout-bad" role="alert"><div style="display:flex;gap:8px">${ic("alert")}<div><b>${esc(p.failed === "quota" ? T.QUOTA : T.ERROR)}</b>
        <div style="margin-top:4px;color:var(--ink-2)">Câu hỏi chưa được lưu vào hội thoại. Bạn có thể gửi lại.</div>
        <div class="row"><button class="btn btn-outline" type="button" data-act="retry">${ic("retry")}Thử lại</button><button class="btn btn-ghost" type="button" data-act="edit">${ic("edit")}Sửa câu hỏi</button></div></div></div>
      </div></article>`;
}
const elapsed = () => `${Math.max(0, Math.round((Date.now() - pending.started) / 1000))} giây`;

function renderStatus() {
  if (status === "loading") return `<div class="status" role="status" aria-busy="true">
      <div class="badge"><span class="spinner" aria-hidden="true"></span></div>
      <h2>Đang nạp chỉ mục văn bản</h2>
      <p>Lần khởi động đầu mất khoảng 30 giây. Trang tự sẵn sàng khi nạp xong; trong lúc chờ, bạn vẫn xem được các hội thoại cũ.</p>
      <div class="bar" aria-hidden="true"><i></i></div></div>`;
  return `<div class="status bad" role="alert">
      <div class="badge">${ic("alert", "icon")}</div>
      <h2>${esc(T.LOAD_ERROR)}</h2>
      <p>Chỉ mục có thể chưa được dựng hoặc dựng chưa xong. Người vận hành: xem log server và hướng dẫn dựng chỉ mục.</p>
      <div class="actions"><button class="btn btn-primary" type="button" data-act="retry-load">${ic("retry")}Thử lại</button></div></div>`;
}

function renderWelcome() {
  return `<div class="welcome">
      <div class="brand-mark" aria-hidden="true">${ic("scale", "icon")}</div>
      <h2>Hỏi về thuế, nhận câu trả lời kèm điều khoản</h2>
      <p>Trả lời bằng tiếng Việt, chỉ từ <span data-count>${documents ? documents.length : "các"}</span> luật, nghị định, thông tư thuế trong bộ văn bản.</p>
      <ul>
        <li><span class="ic">${ic("quote")}</span><div><b>Mỗi ý có nguồn</b>Dẫn tới văn bản, điều, khoản. Bấm số trích dẫn để đọc nguyên văn.</div></li>
        <li><span class="ic">${ic("history")}</span><div><b>Báo khi luật đã bị sửa</b>Điều khoản đã sửa đổi được nêu rõ, kèm văn bản sửa đổi.</div></li>
        <li><span class="ic">${ic("msg")}</span><div><b>Hỏi tiếp trong cùng hội thoại</b>Ví dụ “còn thuế thu nhập cá nhân thì sao?”.</div></li>
      </ul>
      ${notice()}
    </div>`;
}

function renderHistory() {
  const nav = $("#history");
  const rows = conversations.slice();
  if (pending && !pending.conversation) rows.unshift({ id: "", title: pending.question, updated: Date.now() });
  if (!rows.length) {
    nav.innerHTML = `<div class="hist-empty">${ic("history", "icon")}<div>Chưa có hội thoại nào. Câu hỏi của bạn được lưu trên trình duyệt này.</div></div>`;
    return;
  }
  const today = new Date().setHours(0, 0, 0, 0), week = today - 6 * 864e5;
  const groups = [["Hôm nay", c => c.updated >= today], ["7 ngày trước", c => c.updated < today && c.updated >= week], ["Cũ hơn", c => c.updated < week]];
  const openId = current ? current.id : (pending && !pending.conversation ? "" : null);
  nav.innerHTML = groups.map(([name, test]) => {
    const items = rows.filter(test);
    if (!items.length) return "";
    return `<h2>${name}</h2><ul>` + items.map(c => {
      const open = c.id === openId;
      return `<li class="hist-row${open ? " current" : ""}"><button class="hist-item" type="button" data-act="open" data-id="${esc(c.id)}"${open ? ' aria-current="page"' : ""}><span>${esc(c.title)}</span></button>` +
        (c.id ? `<button class="btn btn-ghost btn-icon sm hist-del" type="button" data-act="ask-del" data-id="${esc(c.id)}" aria-label="Xóa hội thoại “${esc(c.title)}”" title="Xóa">${ic("trash")}</button>` : "") + `</li>`;
    }).join("") + `</ul>`;
  }).join("");
}

function setComposer() {
  const off = status !== "ready", busy = !!(pending && !pending.failed);
  $("#composer").classList.toggle("is-disabled", off);
  input.disabled = off;
  input.placeholder = off ? "Chưa thể đặt câu hỏi lúc này" : T.PLACEHOLDER;
  const send = $("#send");
  send.disabled = off || busy;
  send.innerHTML = busy ? `<span class="spinner" aria-hidden="true"></span>` : ic("send", "icon");
  send.setAttribute("aria-label", busy ? "Đang trả lời, chưa gửi được câu mới" : "Gửi câu hỏi");
}

function render() {
  const turns = current ? current.turns : [];
  const showPending = pending && pending.conversation === current;
  const title = current ? current.title : (showPending ? pending.question : T.NEW_CONVERSATION);
  $("#title").textContent = title;
  document.title = (current || showPending ? title + " · " : "") + T.TITLE;
  const many = turns.length + (showPending ? 1 : 0) > 1;
  let h = turns.map((t, ti) => `<div class="q"><span class="sr-only">Bạn hỏi: </span>${esc(t.question)}</div>` + renderAnswer(t, ti, many)).join("");
  if (showPending) h += renderPending(pending);
  const empty = !h;
  if (empty) h = status === "ready" ? renderWelcome() : renderStatus();
  inner.classList.toggle("center", empty && status !== "ready");
  inner.innerHTML = h;
  renderHistory();
  setComposer();
  clearInterval(timer);
  if (showPending && !pending.failed) timer = setInterval(() => { const e = $("#elapsed"); if (e && pending) e.textContent = elapsed(); }, 1000);
  if (panel) openPanel(...panel);
}
function scrollDown() { const th = $("#thread"); th.scrollTop = th.scrollHeight; }

/* ---------- source panel ---------- */
function wide() { return app.getBoundingClientRect().width >= WIDE; }
function name(provision, sources, by) {  // a link's provision as the reader sees it
  const s = sources.find(x => x.id === provision);
  if (s) return `${s.document}, ${place(s)}`;
  const clause = provision.split(".").slice(1)[0];
  return clause ? `Khoản ${clause}` : `Điều này`;
}
function openPanel(ti, n) {
  const turn = current && current.turns[ti];
  if (!turn || !turn.answer.sources[n - 1]) { closePanel(); return; }
  const a = turn.answer, s = a.sources[n - 1], by = numbers(a);
  panel = [ti, n];
  app.classList.remove("panel-closed");
  $("#panel-h").textContent = current.turns.length > 1 ? `Nguồn · câu trả lời ${ti + 1}` : "Nguồn của câu trả lời";
  $("#panel-tabs").innerHTML = a.sources.map((_, k) => `<button class="cite" role="tab" type="button" data-turn="${ti}" data-src="${k + 1}" aria-selected="${k + 1 === n}" aria-current="${k + 1 === n}" aria-label="Nguồn ${k + 1}">${k + 1}</button>`).join("");
  const retro = s.issued && s.effective && s.effective < s.issued;
  const links = s.amended_by.map(link => {
    const source = by[link.source];
    const what = link.target === s.id ? (s.clause ? "Khoản này" : "Điều này") : name(link.target, a.sources, by);
    return `<div class="amend">${ic("history")}<div><b>Đã được sửa đổi.</b> ${esc(what)} ${esc(LINK_WORDS[link.type] || link.type)} ${esc(name(link.source, a.sources, by))}.` +
      (source ? ` <button type="button" data-turn="${ti}" data-src="${source}">Xem nguồn [${source}]</button>` : "") + `</div></div>`;
  }).join("");
  $("#panel-body").innerHTML = `
    <div><div class="doc-kind">${esc(s.kind)}</div><h3 class="doc-title">${esc(s.document)}</h3><p class="doc-desc">${esc(s.title)}</p></div>
    <dl class="facts"><dt>Vị trí</dt><dd>${esc(place(s))}</dd><dt>Ban hành</dt><dd>${esc(dmy(s.issued))}</dd><dt>Hiệu lực từ</dt><dd>${esc(dmy(s.effective))}${retro ? ` <span class="retro">hồi tố, trước ngày ban hành</span>` : ""}</dd></dl>
    ${links}
    <blockquote class="excerpt"><span class="loc">${esc(s.heading)}</span>${(s.text || "").split("\n").filter(Boolean).map(p => `<p>${esc(p)}</p>`).join("")}</blockquote>`;
  $("#panel-body").scrollTop = 0;
  $("#panel-link").href = safeUrl(s.url);
  document.querySelectorAll(".a-body .cite[data-src]").forEach(c => c.setAttribute("aria-current", String(+c.dataset.turn === ti && +c.dataset.src === n)));
  document.querySelectorAll(".src").forEach(li => li.classList.toggle("active", +li.dataset.turn === ti && +li.dataset.row === n));
}
function closePanel() {
  panel = null;
  app.classList.add("panel-closed");
  document.querySelectorAll(".a-body .cite[aria-current]").forEach(c => c.setAttribute("aria-current", "false"));
  document.querySelectorAll(".src").forEach(li => li.classList.remove("active"));
}

/* ---------- copy ---------- */
function copyText(turn) {
  const a = turn.answer, by = numbers(a);
  const text = a.sentences.map(s => s.text + s.citations.map(id => ` [${by[id] || "?"}]`).join("")).join(" ");
  const sources = a.sources.map((s, i) => `[${i + 1}] ${s.document}, ${place(s)}: ${s.url}`);
  return [text, sources.length ? "Nguồn:\n" + sources.join("\n") : "", T.NOTICE].filter(Boolean).join("\n\n");
}
async function copy(ti) {
  try { await navigator.clipboard.writeText(copyText(current.turns[ti])); toast("Đã sao chép câu trả lời và nguồn"); }
  catch (e) { toast("Chưa sao chép được"); }
}

/* ---------- dialogs, toast ---------- */
function openDelete(id) {
  const c = conversations.find(x => x.id === id); if (!c) return;
  toDelete = id; lastFocus = document.activeElement;
  $("#del-name").textContent = c.title; $("#dlg-delete").hidden = false;
  $("#dlg-delete .btn-outline").focus({ preventScroll: true });
}
function openDocs() {
  lastFocus = document.activeElement; $("#dlg-docs").hidden = false; $("#docs-q").value = ""; drawDocs("");
  $("#docs-q").focus({ preventScroll: true });
  if (!documents) loadDocuments().then(() => drawDocs($("#docs-q").value));
}
function drawDocs(q) {
  if (!documents) { $("#docs").innerHTML = `<div class="docs-none">Danh sách văn bản có khi chỉ mục nạp xong.</div>`; return; }
  q = q.trim().toLowerCase();
  const rows = documents.filter(d => !q || `${d.kind} ${d.number} ${d.title}`.toLowerCase().includes(q));
  const kinds = [...new Set(["Luật", "Nghị định", "Thông tư", ...documents.map(d => d.kind)])];
  const html = kinds.map(k => {
    const g = rows.filter(d => d.kind === k); if (!g.length) return "";
    return `<h3>${esc(k)} · ${g.length}</h3><ul>` + g.map(d => `<li class="doc-row"><div><b>${esc(d.kind)} ${esc(d.number)}</b><span>${esc(d.title)}</span></div>
      <a class="src-ext" href="${esc(safeUrl(d.url))}" target="_blank" rel="noopener" aria-label="Mở ${esc(d.kind)} ${esc(d.number)} trên luatvietnam.vn (tab mới)">${ic("ext")}</a></li>`).join("") + `</ul>`;
  }).join("");
  $("#docs").innerHTML = html || `<div class="docs-none">Không có văn bản nào khớp “${esc(q)}”.</div>`;
}
function closeDialogs() {
  const open = [...document.querySelectorAll(".dlg-layer")].some(d => !d.hidden);
  document.querySelectorAll(".dlg-layer").forEach(d => d.hidden = true);
  if (open && lastFocus) lastFocus.focus();
}
let toastTimer;
function toast(message) {
  $("#toast-t").textContent = message; $("#toast").classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 2400);
}

/* ---------- events ---------- */
function startNew() { current = null; if (pending && pending.failed) pending = null; closePanel(); app.classList.remove("side-open"); render(); input.focus(); }
function open(id) {
  const c = conversations.find(x => x.id === id);
  current = c || null;
  if (pending && pending.failed) pending = null;
  closePanel(); app.classList.remove("side-open"); render();
}

document.addEventListener("click", e => {
  const src = e.target.closest("[data-src]");
  if (src && app.contains(src)) { openPanel(+src.dataset.turn, +src.dataset.src); return; }
  const vote = e.target.closest("[data-vote]");
  if (vote) {
    const turn = current && current.turns[+vote.dataset.turn]; if (!turn) return;
    turn.vote = turn.vote === vote.dataset.vote ? null : vote.dataset.vote;
    save(); render();
    if (turn.vote) toast("Cảm ơn, đã ghi nhận đánh giá");
    return;
  }
  const a = e.target.closest("[data-act]"); if (!a) return;
  const act = a.dataset.act;
  if (act === "dlg-bg" && e.target !== a) return;
  ({
    "new": startNew,
    "open": () => a.dataset.id ? open(a.dataset.id) : (current = null, render()),
    "open-side": () => app.classList.add("side-open"),
    "close-side": () => app.classList.remove("side-open"),
    "scrim": () => { closePanel(); app.classList.remove("side-open"); },
    "close-panel": closePanel,
    "copy": () => copy(+a.dataset.turn),
    "docs": () => { app.classList.remove("side-open"); openDocs(); },
    "ask-del": () => openDelete(a.dataset.id),
    "dlg-close": closeDialogs,
    "dlg-bg": closeDialogs,
    "del-confirm": () => {
      conversations = conversations.filter(c => c.id !== toDelete);
      if (current && current.id === toDelete) { current = null; closePanel(); }
      save(); closeDialogs(); render(); toast("Đã xóa hội thoại");
    },
    "retry": () => { const p = pending; pending = null; current = p.conversation; ask(p.question); },
    "edit": () => { const q = pending.question; pending = null; render(); input.value = q; input.focus(); resize(); },
    "retry-load": retryLoad,
  })[act]?.();
});
$("#docs-q").addEventListener("input", e => drawDocs(e.target.value));
$("#composer").addEventListener("submit", e => {
  e.preventDefault();
  const question = input.value.trim();
  if ($("#send").disabled || !question) return;
  input.value = ""; resize();
  ask(question);
});
function resize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 200) + "px"; }
input.addEventListener("input", resize);
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#composer").requestSubmit(); } });
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if ([...document.querySelectorAll(".dlg-layer")].some(d => !d.hidden)) closeDialogs();
  else { closePanel(); app.classList.remove("side-open"); }
});

document.querySelectorAll("[data-text]").forEach(el => { el.textContent = T[el.dataset.text]; });
document.querySelectorAll("[data-label]").forEach(el => { el.setAttribute("aria-label", T[el.dataset.label]); });
render();
poll();
