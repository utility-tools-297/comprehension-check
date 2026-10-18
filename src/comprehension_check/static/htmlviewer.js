"use strict";

// HTML ビューア。元 HTML を同一オリジンの iframe に表示し、親からその DOM を操作して
// マスクを重ねる。リフローするため穴は座標でなくアンカーで保持する:
//   text: {exact, prefix, suffix} を本文から再探索し span で包む（リフロー追従）。
//   rect: {selector, x, y, w, h} 対象要素の矩形上にマスクを重ねる（要素基準で再配置）。
document.addEventListener("DOMContentLoaded", () => {
  const host = document.querySelector(".html-doc");
  const frame = document.getElementById("html-frame");
  const toolbar = document.getElementById("toolbar");
  if (!host || !frame || !toolbar) return;

  const docId = host.dataset.docId;
  const statusEl = document.getElementById("status");
  const htmlStatus = document.getElementById("html-status");
  const createHint = document.getElementById("create-hint");
  const practiceTools = toolbar.querySelector(".practice-tools");
  const createTools = toolbar.querySelector(".create-tools");
  const blankCount = document.getElementById("blank-count");
  const modeButtons = toolbar.querySelectorAll(".mode-switch:not(.tool-switch) button[data-mode]");
  const toolButtons = toolbar.querySelectorAll(".tool-switch button[data-tool]");
  const makeBlankBtn = document.getElementById("make-blank");

  const CTX = 40; // 前後文脈として保持する文字数
  let mode = "practice";
  let tool = "text";
  let fdoc = null; // iframe の document
  let fwin = null; // iframe の window
  let overlay = null; // 矩形マスクを載せる層
  let rectBlanks = []; // 位置再計算用に矩形穴を保持
  let pending = null; // 作成待ちの選択（「穴を作成」で確定）
  let pendingPreview = null; // 作成待ちの矩形プレビュー要素

  const INJECTED_CSS = `
    .cc-mask { border-radius: 3px; }
    /* テキスト穴: 隠蔽時も表示(revealed)時も枠線を残して「どこが穴か」を示す。 */
    html.cc-mode-practice .cc-text { color: transparent; background: #cbd5e1; box-shadow: inset 0 0 0 2px #475569; cursor: pointer; }
    html.cc-mode-practice .cc-text * { color: transparent !important; }
    html.cc-mode-practice .cc-text.cc-revealed { color: inherit; background: transparent; box-shadow: inset 0 0 0 2px #475569; }
    html.cc-mode-practice .cc-text.cc-revealed * { color: inherit !important; }
    html.cc-mode-create .cc-text { background: #fef3c7; box-shadow: inset 0 0 0 1px #f59e0b; cursor: pointer; }
    /* 矩形マスクは iframe ビューポート基準(fixed)で配置し、内部スクロールに追従させる。 */
    .cc-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 2147482000; }
    .cc-rect { position: absolute; z-index: 2147483000; pointer-events: auto; border-radius: 2px; }
    /* 矩形穴: 隠蔽時も表示時も枠線を残す。 */
    html.cc-mode-practice .cc-rect { background: #cbd5e1; box-shadow: inset 0 0 0 2px #475569; cursor: pointer; }
    html.cc-mode-practice .cc-rect.cc-revealed { background: transparent; box-shadow: inset 0 0 0 2px #475569; }
    html.cc-mode-create .cc-rect { background: rgba(245,158,11,0.25); box-shadow: inset 0 0 0 2px #d97706; cursor: pointer; }
    .cc-rect-preview { position: absolute; z-index: 2147483001; border: 1.5px dashed #f59e0b; background: rgba(245,158,11,0.15); pointer-events: none; }
    /* 正誤コントロール（穴ごと: 正解/不正解ボタン＋回数）。overlay(fixed) 内に配置する。 */
    .cc-attempt { position: absolute; transform: translateX(-100%); display: flex; gap: 2px; z-index: 2147483100; pointer-events: auto; font: 11px/1 sans-serif; }
    .cc-attempt .cc-atk { display: inline-flex; align-items: center; gap: 2px; border: 1px solid #cbd5e1; background: #fff; border-radius: 4px; padding: 1px 4px; cursor: pointer; color: #334155; }
    .cc-attempt .cc-ok { color: #15803d; }
    .cc-attempt .cc-ng { color: #b91c1c; }
    .cc-attempt .cc-memo { color: #2563eb; }
    .cc-attempt .cc-memo.cc-has-note { background: #dbeafe; border-color: #93c5fd; }
    html.cc-mode-practice .cc-attempt.cc-revealed { display: none; }
    /* メモ本文のポップ（作成=プロンプト編集／実践=クリックで表示切替）。 */
    .cc-note { position: absolute; top: 100%; right: 0; margin-top: 4px; max-width: 260px; min-width: 120px;
      padding: 6px 8px; background: #fffbeb; border: 1px solid #fcd34d; border-radius: 6px; color: #334155;
      font: 12px/1.5 sans-serif; white-space: pre-wrap; word-break: break-word;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 2147483200; pointer-events: auto; }
    .cc-note[hidden] { display: none; }
  `;

  function showStatus(msg) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.hidden = false;
    window.clearTimeout(showStatus._t);
    showStatus._t = window.setTimeout(() => (statusEl.hidden = true), 4000);
  }

  function applyModeClass() {
    if (!fdoc) return;
    const root = fdoc.documentElement;
    root.classList.toggle("cc-mode-practice", mode === "practice");
    root.classList.toggle("cc-mode-create", mode === "create");
  }

  function setMode(next) {
    mode = next;
    if (practiceTools) practiceTools.hidden = next !== "practice";
    if (createTools) createTools.hidden = next !== "create";
    if (createHint) createHint.hidden = next !== "create";
    modeButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === next));
    applyModeClass();
    clearPending();
  }

  function setTool(next) {
    tool = next;
    toolButtons.forEach((b) => b.classList.toggle("active", b.dataset.tool === next));
    clearPending();
  }

  modeButtons.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  toolButtons.forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));

  // ---- 作成の2段階化: 選択/ドラッグで「作成待ち」にし、「穴を作成」で確定する ----
  function clearPending() {
    pending = null;
    if (pendingPreview) {
      pendingPreview.remove();
      pendingPreview = null;
    }
    if (fwin) fwin.getSelection().removeAllRanges();
    if (makeBlankBtn) makeBlankBtn.disabled = true;
  }

  function stagePending(p, preview) {
    pending = p;
    if (pendingPreview && pendingPreview !== preview) pendingPreview.remove();
    pendingPreview = preview || null;
    if (makeBlankBtn) makeBlankBtn.disabled = false;
  }

  if (makeBlankBtn) {
    makeBlankBtn.addEventListener("click", () => {
      if (!pending) return;
      postBlank(pending.kind, pending.payload);
      clearPending();
    });
  }

  // ---- テキストノード索引（本文の連結文字列と各ノードの開始位置） ----
  function buildTextIndex() {
    const nodes = [];
    let text = "";
    const walker = fdoc.createTreeWalker(fdoc.body, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        const p = n.parentNode;
        if (!p) return NodeFilter.FILTER_REJECT;
        const tag = p.nodeName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let node = walker.nextNode();
    while (node) {
      nodes.push({ node, start: text.length });
      text += node.data;
      node = walker.nextNode();
    }
    return { nodes, text };
  }

  // 連結文字列上の [startOff, endOff) を span で包む（複数ノードに跨り得る）。
  function wrapRange(nodes, startOff, endOff, blankId) {
    const targets = [];
    for (const { node, start } of nodes) {
      const nend = start + node.data.length;
      if (nend <= startOff || start >= endOff) continue;
      targets.push({ node, from: Math.max(startOff, start) - start, to: Math.min(endOff, nend) - start });
    }
    for (const { node, from, to } of targets) {
      let target = node;
      if (from > 0) target = target.splitText(from);
      if (to - from < target.data.length) target.splitText(to - from);
      const span = fdoc.createElement("span");
      span.className = "cc-mask cc-text";
      span.dataset.blankId = blankId;
      target.parentNode.insertBefore(span, target);
      span.appendChild(target);
    }
  }

  // アンカーに一致する [start,end) を本文から探す（前後文脈を優先、無ければ最初の一致）。
  function findAnchor(text, exact, prefix, suffix) {
    if (!exact) return null;
    const hits = [];
    let i = text.indexOf(exact);
    while (i !== -1) {
      hits.push(i);
      i = text.indexOf(exact, i + 1);
    }
    if (!hits.length) return null;
    for (const h of hits) {
      const before = text.slice(Math.max(0, h - prefix.length), h);
      const after = text.slice(h + exact.length, h + exact.length + suffix.length);
      const okPre = !prefix || before.endsWith(prefix) || prefix.endsWith(before);
      const okSuf = !suffix || after.startsWith(suffix) || suffix.startsWith(after);
      if (okPre && okSuf) return { start: h, end: h + exact.length };
    }
    return { start: hits[0], end: hits[0] + exact.length };
  }

  // ---- 矩形マスクの位置計算（要素基準・リフロー時に再計算） ----
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el === fdoc.body) return "body";
    const parts = [];
    while (el && el.nodeType === 1 && el !== fdoc.body) {
      let sel = el.nodeName.toLowerCase();
      const parent = el.parentNode;
      if (parent && parent.children) {
        const same = Array.from(parent.children).filter((c) => c.nodeName === el.nodeName);
        if (same.length > 1) sel += `:nth-of-type(${same.indexOf(el) + 1})`;
      }
      parts.unshift(sel);
      el = parent;
    }
    return "body > " + parts.join(" > ");
  }

  function positionRect(mask, b) {
    const el = fdoc.querySelector(b.payload.selector);
    if (!el) {
      mask.style.display = "none";
      return;
    }
    mask.style.display = "";
    // overlay は fixed（ビューポート基準）なので、矩形もビューポート座標で配置する。
    const box = el.getBoundingClientRect();
    mask.style.left = box.left + b.payload.x * box.width + "px";
    mask.style.top = box.top + b.payload.y * box.height + "px";
    mask.style.width = b.payload.w * box.width + "px";
    mask.style.height = b.payload.h * box.height + "px";
  }

  function positionAllRects() {
    if (!overlay) return;
    for (const b of rectBlanks) {
      const mask = overlay.querySelector(`.cc-rect[data-blank-id="${b.id}"]`);
      if (mask) positionRect(mask, b);
    }
  }

  // 正誤コントロールを穴の矩形の右上に合わせる（テキストは span、矩形はマスクを基準に）。
  function positionControl(ctl) {
    const id = ctl.dataset.blankId;
    let box = null;
    if (ctl.dataset.kind === "text") {
      const span = fdoc.querySelector(`.cc-text[data-blank-id="${id}"]`);
      if (span) box = span.getClientRects()[0] || span.getBoundingClientRect();
    } else {
      const mask = overlay.querySelector(`.cc-rect[data-blank-id="${id}"]`);
      if (mask && mask.style.display !== "none") box = mask.getBoundingClientRect();
    }
    if (!box) {
      ctl.style.display = "none";
      return;
    }
    ctl.style.display = "";
    ctl.style.left = box.right + "px";
    ctl.style.top = box.top + "px";
  }

  function positionAllControls() {
    if (!overlay) return;
    overlay.querySelectorAll(".cc-attempt").forEach(positionControl);
  }

  // rect の位置を決めてから control を合わせる（control は rect 位置を参照するため）。
  function repositionAll() {
    positionAllRects();
    positionAllControls();
  }

  function setControlCounts(ctl, counts) {
    const spans = ctl.querySelectorAll(".cc-n");
    spans[0].textContent = String(counts.correct || 0);
    spans[1].textContent = String(counts.incorrect || 0);
  }

  function makeControl(blankId, kind, counts, note) {
    const ctl = fdoc.createElement("div");
    ctl.className = "cc-attempt";
    ctl.dataset.blankId = blankId;
    ctl.dataset.kind = kind;
    const ok = fdoc.createElement("button");
    ok.type = "button";
    ok.className = "cc-atk cc-ok";
    ok.dataset.result = "correct";
    ok.title = "正解を記録";
    ok.innerHTML = '&#10003;<span class="cc-n"></span>';
    const ng = fdoc.createElement("button");
    ng.type = "button";
    ng.className = "cc-atk cc-ng";
    ng.dataset.result = "incorrect";
    ng.title = "不正解を記録";
    ng.innerHTML = '&#10007;<span class="cc-n"></span>';
    const memo = fdoc.createElement("button");
    memo.type = "button";
    memo.className = "cc-atk cc-memo";
    memo.title = "メモ";
    memo.textContent = "✎"; // ✎
    const pop = fdoc.createElement("div");
    pop.className = "cc-note";
    pop.hidden = true;
    ctl.append(ok, ng, memo, pop);
    setControlCounts(ctl, counts || { correct: 0, incorrect: 0 });
    applyNote(ctl, note || "");
    return ctl;
  }

  // メモを反映（登録済みなら✎を強調し、ポップ内容も更新）。
  function applyNote(ctl, note) {
    ctl.dataset.note = note || "";
    const memo = ctl.querySelector(".cc-memo");
    if (memo) memo.classList.toggle("cc-has-note", !!(note && note.trim()));
    const pop = ctl.querySelector(".cc-note");
    if (pop && !pop.hidden) pop.textContent = note && note.trim() ? note : "（メモなし）";
  }

  // メモ操作: 作成=プロンプトで編集、実践=クリックで表示/非表示。
  function onMemo(ctl) {
    const id = ctl.dataset.blankId;
    if (mode === "create") {
      const v = window.prompt("メモ（作成）", ctl.dataset.note || "");
      if (v === null) return;
      saveNote(id, v, ctl);
      return;
    }
    const pop = ctl.querySelector(".cc-note");
    if (!pop) return;
    if (pop.hidden) {
      const n = ctl.dataset.note || "";
      pop.textContent = n.trim() ? n : "（メモなし）";
      pop.hidden = false;
    } else {
      pop.hidden = true;
    }
  }

  function saveNote(id, note, ctl) {
    const body = new URLSearchParams({ note });
    fetch(`/documents/${docId}/html-blanks/${id}/note`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => (d.ok ? applyNote(ctl, d.note) : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function recordAttempt(id, result) {
    const body = new URLSearchParams({ blank_id: id, result });
    fetch(`/documents/${docId}/attempts`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) {
          showStatus(d.error);
          return;
        }
        const ctl = overlay.querySelector(`.cc-attempt[data-blank-id="${id}"]`);
        if (ctl) setControlCounts(ctl, d.counts);
      })
      .catch(() => showStatus("通信に失敗しました。"));
  }

  // ---- 穴の取得・描画 ----
  function loadBlanks() {
    return fetch(`/documents/${docId}/html-blanks`)
      .then((r) => r.json())
      .then((d) => renderBlanks(d.blanks || []))
      .catch(() => showStatus("穴の読み込みに失敗しました。"));
  }

  function renderBlanks(blanks) {
    // 既存マスクを撤去（テキストは span を解いて元に戻す）。
    fdoc.querySelectorAll(".cc-text").forEach((span) => {
      const parent = span.parentNode;
      while (span.firstChild) parent.insertBefore(span.firstChild, span);
      parent.removeChild(span);
      parent.normalize();
    });
    if (overlay) overlay.innerHTML = "";
    rectBlanks = blanks.filter((b) => b.kind === "rect");
    if (blankCount) blankCount.textContent = `穴 ${blanks.length} 個`;

    for (const b of blanks) {
      if (b.kind === "text") {
        const index = buildTextIndex();
        const hit = findAnchor(index.text, b.payload.exact || "", b.payload.prefix || "", b.payload.suffix || "");
        if (hit) wrapRange(index.nodes, hit.start, hit.end, b.id);
      } else if (b.kind === "rect") {
        const mask = fdoc.createElement("div");
        mask.className = "cc-mask cc-rect";
        mask.dataset.blankId = b.id;
        overlay.appendChild(mask);
        positionRect(mask, b);
      }
    }
    // 正誤コントロールを穴ごとに作る（overlay 内に配置し、位置はマスク/テキストに合わせる）。
    for (const b of blanks) {
      overlay.appendChild(makeControl(b.id, b.kind, b.counts, b.note));
    }
    positionAllControls();
    applyModeClass();
  }

  function postBlank(kind, payload) {
    const body = new URLSearchParams({ kind, payload: JSON.stringify(payload) });
    fetch(`/documents/${docId}/html-blanks`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => (d.ok ? loadBlanks() : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function deleteBlank(id) {
    fetch(`/documents/${docId}/html-blanks/${id}/delete`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => (d.ok ? loadBlanks() : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function toggleBlank(id) {
    const revealed = fdoc.querySelector(`.cc-mask[data-blank-id="${id}"]`)?.classList.contains("cc-revealed");
    fdoc
      .querySelectorAll(`.cc-mask[data-blank-id="${id}"]`)
      .forEach((m) => m.classList.toggle("cc-revealed", !revealed));
    // 正誤コントロール（回数）も穴に合わせて表示/非表示する。
    const ctl = overlay.querySelector(`.cc-attempt[data-blank-id="${id}"]`);
    if (ctl) ctl.classList.toggle("cc-revealed", !revealed);
  }

  function revealAll(revealed) {
    if (!fdoc) return;
    fdoc.querySelectorAll(".cc-mask, .cc-attempt").forEach((m) => m.classList.toggle("cc-revealed", revealed));
  }
  document.getElementById("reveal-all")?.addEventListener("click", () => revealAll(true));
  document.getElementById("hide-all")?.addEventListener("click", () => revealAll(false));

  // ---- iframe 内の操作ハンドラ ----
  function onFrameClick(e) {
    // 正誤/メモボタン: 穴の開閉・削除には波及させない。
    const atk = e.target.closest(".cc-attempt .cc-atk");
    if (atk) {
      e.preventDefault();
      e.stopPropagation();
      const ctl = atk.closest(".cc-attempt");
      if (atk.classList.contains("cc-memo")) {
        onMemo(ctl);
      } else if (mode === "practice") {
        // 正誤の記録は実践モードのみ（作成モードでは回数の表示だけ）。
        recordAttempt(ctl.dataset.blankId, atk.dataset.result);
      }
      return;
    }
    if (e.target.closest(".cc-note")) return; // メモ本文クリックは無視（読む/選択用）
    const m = e.target.closest(".cc-mask");
    if (m) {
      const id = m.dataset.blankId;
      if (mode === "practice") {
        e.preventDefault();
        toggleBlank(id);
      } else if (mode === "create") {
        e.preventDefault();
        // 確認は親ウィンドウの confirm を使う（sandbox の iframe は allow-modals が無く
        // fwin.confirm が常に false を返すため、再クリックで削除できなかった）。
        if (window.confirm("この穴を削除しますか？")) deleteBlank(id);
      }
      return;
    }
    // 登録した HTML 以外のページへ遷移させない（別ページに隠しがあるかも、という混乱を避ける）。
    // 同一ページ内アンカー（#...）とページ内スクリプト（javascript:）はそのまま許可する。
    const link = e.target.closest("a[href]");
    if (link) {
      const raw = link.getAttribute("href") || "";
      if (raw.startsWith("#") || /^javascript:/i.test(raw)) return;
      if (fwin && stripHash(link.href) === stripHash(fwin.location.href)) return; // 同一ページ
      e.preventDefault();
      showStatus("別ページへは移動しません（この HTML だけを表示しています）。");
    }
  }

  // テキスト選択で穴を作る。
  function onFrameMouseUp() {
    if (!(mode === "create" && tool === "text")) return;
    const sel = fwin.getSelection();
    if (!sel || sel.isCollapsed) return;
    const exact = sel.toString();
    if (!exact.trim()) return;
    const range = sel.getRangeAt(0);
    // 既存の穴と重なる選択は拒否（初期仕様）。
    if (range.cloneContents().querySelector(".cc-mask") ||
        fwin.getSelection().anchorNode?.parentElement?.closest(".cc-mask")) {
      showStatus("既存の穴と重なる範囲には作成できません。");
      return;
    }
    const pre = fdoc.createRange();
    pre.setStart(fdoc.body, 0);
    pre.setEnd(range.startContainer, range.startOffset);
    const prefix = pre.toString().slice(-CTX);
    const suf = fdoc.createRange();
    suf.setStart(range.endContainer, range.endOffset);
    suf.setEnd(fdoc.body, fdoc.body.childNodes.length);
    const suffix = suf.toString().slice(0, CTX);
    // 即作成せず「作成待ち」にする（選択は見た目として残す）。
    stagePending({ kind: "text", payload: { exact, prefix, suffix } }, null);
  }

  // 矩形ドラッグで図・画像の一部を穴にする。
  let draw = null;
  function onFrameMouseDown(e) {
    if (!(mode === "create" && tool === "rect")) return;
    if (e.target.closest(".cc-mask")) return; // 既存マスクは削除クリック優先
    clearPending(); // 直前の作成待ちは破棄して描き直す
    draw = { x0: e.clientX, y0: e.clientY, el: e.target, preview: null };
    e.preventDefault();
  }
  function onFrameMouseMove(e) {
    if (!draw) return;
    // overlay は fixed なのでプレビューもビューポート座標で描く。
    const x = Math.min(e.clientX, draw.x0);
    const y = Math.min(e.clientY, draw.y0);
    const w = Math.abs(e.clientX - draw.x0);
    const h = Math.abs(e.clientY - draw.y0);
    if (!draw.preview) {
      draw.preview = fdoc.createElement("div");
      draw.preview.className = "cc-rect-preview";
      overlay.appendChild(draw.preview);
    }
    Object.assign(draw.preview.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
  }
  function onFrameMouseUpRect(e) {
    if (!draw) return;
    const d = draw;
    draw = null;
    const w = Math.abs(e.clientX - d.x0);
    const h = Math.abs(e.clientY - d.y0);
    if (w < 5 || h < 5) {
      if (d.preview) d.preview.remove();
      return;
    }
    // ドラッグ範囲の中心にある要素を対象にし、その要素内の正規化サブ矩形を保存。
    const cx = (e.clientX + d.x0) / 2;
    const cy = (e.clientY + d.y0) / 2;
    const el = fdoc.elementFromPoint(cx, cy) || d.el;
    if (!el || el.nodeType !== 1) {
      if (d.preview) d.preview.remove();
      showStatus("対象の要素が特定できませんでした。");
      return;
    }
    const box = el.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) {
      if (d.preview) d.preview.remove();
      return;
    }
    const left = Math.min(e.clientX, d.x0);
    const top = Math.min(e.clientY, d.y0);
    const payload = {
      selector: cssPath(el),
      x: (left - box.left) / box.width,
      y: (top - box.top) / box.height,
      w: w / box.width,
      h: h / box.height,
    };
    stagePending({ kind: "rect", payload }, d.preview || null);
  }

  // ---- 初期化（iframe 読み込み後） ----
  function stripHash(u) {
    return (u || "").split("#")[0];
  }

  // 保存元サイトの origin を得る（Chrome の「保存元 URL」コメント→og:url→canonical の順）。
  function pageOrigin() {
    const walker = fdoc.createTreeWalker(fdoc, NodeFilter.SHOW_COMMENT);
    for (let c = walker.nextNode(); c; c = walker.nextNode()) {
      const m = /saved from url=\(\d+\)(\S+)/.exec(c.data || "");
      if (m) {
        try {
          return new URL(m[1]).origin;
        } catch (err) {
          /* 次の手がかりへ */
        }
      }
    }
    const og = fdoc.querySelector('meta[property="og:url"]');
    const can = fdoc.querySelector('link[rel="canonical"]');
    const url = (og && og.getAttribute("content")) || (can && can.getAttribute("href")) || "";
    try {
      return url ? new URL(url).origin : null;
    } catch (err) {
      return null;
    }
  }

  // <picture> の壊れた <source>（ローカル未保存の root 絶対URL）への対処。
  // 「完全」保存は <img src> をローカル化しても <source srcset> を root 絶対パスのまま残すことが
  // あり（PC版画像は未保存）、デスクトップ幅で図が出ない。元サイト origin が分かれば source を
  // 元サイトの絶対URLへ書き換えて読み込み（外部可の前提）、読めない場合（オフライン・404）は
  // ローカル保存版（多くはSP版）へ退避する。origin 不明なら source を外してローカル img に委ねる。
  function fixPictures() {
    const assetBase = `/documents/${docId}/asset/`;
    const origin = pageOrigin();
    fdoc.querySelectorAll("picture").forEach((pic) => {
      const img = pic.querySelector("img");
      const localSrc = img ? img.getAttribute("src") : "";
      let changed = false;
      pic.querySelectorAll("source[srcset]").forEach((s) => {
        const first = (s.getAttribute("srcset") || "").split(",")[0].trim().split(/\s+/)[0];
        if (!first) return;
        let abs;
        try {
          abs = new URL(first, fdoc.baseURI);
        } catch (err) {
          return;
        }
        const local = abs.origin === fwin.location.origin && abs.pathname.startsWith(assetBase);
        if (local) return; // ローカルに在る source はそのまま
        if (origin && abs.origin === fwin.location.origin) {
          // root 絶対（＝未保存）を元サイトの絶対URLへ。外部から読む。
          s.setAttribute("srcset", origin + abs.pathname + abs.search);
          changed = true;
        } else if (!origin) {
          s.remove(); // origin 不明 → source を外してローカル img に委ねる
          changed = true;
        }
      });
      if (img && localSrc) {
        // source が読めない（オフライン・404）ときはローカル保存版へ退避。
        img.addEventListener("error", function onErr() {
          img.removeEventListener("error", onErr);
          pic.querySelectorAll("source").forEach((s) => s.remove());
          img.setAttribute("src", localSrc);
        });
        if (changed) img.setAttribute("src", localSrc); // 再選択を促す（source 優先で再評価）
      }
    });
  }

  function initFrame() {
    try {
      fdoc = frame.contentDocument;
      fwin = frame.contentWindow;
      if (!fdoc || !fwin || !fdoc.body) throw new Error("no document");
    } catch (err) {
      if (htmlStatus) htmlStatus.textContent = "HTML を読み込めませんでした。";
      return;
    }
    if (fdoc.querySelector(".cc-overlay")) return; // この文書は初期化済み
    // マスク用スタイルと矩形の層を注入（元ファイルは変更しない）。
    const style = fdoc.createElement("style");
    style.textContent = INJECTED_CSS;
    fdoc.head.appendChild(style);
    overlay = fdoc.createElement("div");
    overlay.className = "cc-overlay";
    fdoc.body.appendChild(overlay);
    fixPictures();

    fdoc.addEventListener("click", onFrameClick, true);
    // フォーム送信も別ページへの遷移につながるため無効化する。
    fdoc.addEventListener("submit", (e) => e.preventDefault(), true);
    fdoc.addEventListener("mouseup", onFrameMouseUp);
    fdoc.addEventListener("mousedown", onFrameMouseDown);
    fdoc.addEventListener("mousemove", onFrameMouseMove);
    fdoc.addEventListener("mouseup", onFrameMouseUpRect);

    // iframe は実ビューポート高(CSS)を持ち内部スクロールする。元ページが高さを
    // ビューポート基準(height:100%/100vh 等)で組むため scrollHeight 追従では高さが
    // 伸びず空白化する。ここでは高さを変えず、矩形マスクをスクロール/リフローに追従させる。
    if (window.ResizeObserver) new fwin.ResizeObserver(repositionAll).observe(fdoc.body);
    window.addEventListener("resize", repositionAll);
    // 内部スクロール（内側のスクロールコンテナ）も捕捉して矩形・コントロールを追従させる。
    fdoc.addEventListener("scroll", repositionAll, true);

    if (htmlStatus) htmlStatus.hidden = true;
    setMode("practice");
    setTool("text");
    loadBlanks().then(repositionAll);
  }

  // 表示を「登録した HTML」に固定する。最初に読めた URL を基準にし、以後 iframe が
  // 別 URL へ遷移したら（リンクをすり抜けた・ページ自身のスクリプトが遷移した等）
  // 元ページへ引き戻す。暴走（連続自動遷移）対策に連続回数を制限する。
  let expectedHref = null;
  let navLock = 0;
  function onFrameLoad() {
    let here = null;
    try {
      here = frame.contentWindow.location.href;
    } catch (e) {
      here = null;
    }
    if (expectedHref === null && here) expectedHref = here;
    if (expectedHref && here && stripHash(here) !== stripHash(expectedHref)) {
      if (navLock++ < 5) {
        showStatus("この HTML だけを表示します（別ページへは移動しません）。");
        try {
          frame.contentWindow.location.replace(expectedHref);
        } catch (e) {
          frame.setAttribute("src", expectedHref);
        }
        return; // 引き戻した結果の load で初期化される
      }
      showStatus("このページは別ページへ自動遷移しようとするため、表示を停止しました。");
      return;
    }
    navLock = 0;
    initFrame();
  }

  // src はテンプレートがマークアップで出力済み（JS 代入だと sandbox フレームで
  // 描画されない個体があるため）。defer 実行時点で読み込み済みなら即処理、まだなら
  // load を待つ。二重初期化は initFrame 内の overlay 有無チェックで無害。
  frame.addEventListener("load", onFrameLoad);
  try {
    const d = frame.contentDocument;
    if (d && d.readyState === "complete" && d.body && d.body.childNodes.length) {
      onFrameLoad();
    }
  } catch (e) {
    /* まだアクセスできない場合は load を待つ */
  }
});
