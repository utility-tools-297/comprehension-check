"use strict";

// PDF ビューア（PDF.js でレイアウト忠実表示＋テキスト/矩形マスク）。
document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("pdf");
  const toolbar = document.getElementById("toolbar");
  if (!root || !toolbar) return;

  const docId = root.dataset.docId;
  const statusEl = document.getElementById("status");
  const pdfStatus = document.getElementById("pdf-status");
  const createHint = document.getElementById("create-hint");
  const practiceTools = toolbar.querySelector(".practice-tools");
  const createTools = toolbar.querySelector(".create-tools");
  const blankCount = document.getElementById("blank-count");
  const modeButtons = toolbar.querySelectorAll(".mode-switch:not(.tool-switch) button[data-mode]");
  const toolButtons = toolbar.querySelectorAll(".tool-switch button[data-tool]");
  const makeBlankBtn = document.getElementById("make-blank");

  let mode = "practice";
  let tool = "text";
  const pageEls = {}; // page番号 -> .pdf-page 要素
  let pending = null; // 作成待ちの選択（「穴を作成」で確定）
  let pendingPreview = null; // 作成待ちの矩形プレビュー要素

  function showStatus(msg) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.hidden = false;
    window.clearTimeout(showStatus._t);
    showStatus._t = window.setTimeout(() => (statusEl.hidden = true), 4000);
  }

  function setMode(next) {
    mode = next;
    root.classList.toggle("mode-practice", next === "practice");
    root.classList.toggle("mode-create", next === "create");
    if (practiceTools) practiceTools.hidden = next !== "practice";
    if (createTools) createTools.hidden = next !== "create";
    if (createHint) createHint.hidden = next !== "create";
    modeButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === next));
    clearPending();
  }

  function setTool(next) {
    tool = next;
    root.classList.toggle("tool-text", next === "text");
    root.classList.toggle("tool-rect", next === "rect");
    toolButtons.forEach((b) => b.classList.toggle("active", b.dataset.tool === next));
    clearPending();
  }

  // ---- 作成の2段階化: 選択/ドラッグで「作成待ち」にし、「穴を作成」で確定する ----
  function clearPending() {
    pending = null;
    if (pendingPreview) {
      pendingPreview.remove();
      pendingPreview = null;
    }
    window.getSelection().removeAllRanges();
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
      postBlank(pending.page, pending.kind, pending.rects);
      clearPending();
    });
  }

  modeButtons.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  toolButtons.forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));

  // ---- 穴の取得・描画 ----
  function loadBlanks() {
    return fetch(`/documents/${docId}/blanks`)
      .then((r) => r.json())
      .then((d) => renderBlanks(d.blanks || []))
      .catch(() => showStatus("穴の読み込みに失敗しました。"));
  }

  // 正誤コントロール（穴ごと: 正解/不正解ボタン＋これまでの回数＋メモ）を作る。
  function makeControl(blankId, counts, note) {
    const ctl = document.createElement("div");
    ctl.className = "attempt-ctl";
    ctl.dataset.blankId = blankId;
    const ok = document.createElement("button");
    ok.type = "button";
    ok.className = "atk ok";
    ok.dataset.result = "correct";
    ok.title = "正解を記録";
    ok.innerHTML = '&#10003;<span class="n"></span>';
    const ng = document.createElement("button");
    ng.type = "button";
    ng.className = "atk ng";
    ng.dataset.result = "incorrect";
    ng.title = "不正解を記録";
    ng.innerHTML = '&#10007;<span class="n"></span>';
    const memo = document.createElement("button");
    memo.type = "button";
    memo.className = "atk memo";
    memo.title = "メモ";
    memo.textContent = "✎"; // ✎
    const pop = document.createElement("div");
    pop.className = "note-pop";
    pop.hidden = true;
    ctl.append(ok, ng, memo, pop);
    setControlCounts(ctl, counts || { correct: 0, incorrect: 0 });
    applyNote(ctl, note || "");
    return ctl;
  }

  function setControlCounts(ctl, counts) {
    const spans = ctl.querySelectorAll(".n");
    spans[0].textContent = String(counts.correct || 0);
    spans[1].textContent = String(counts.incorrect || 0);
  }

  // メモを反映（登録済みなら✎を強調し、ポップ内容も更新）。
  function applyNote(ctl, note) {
    ctl.dataset.note = note || "";
    const memo = ctl.querySelector(".atk.memo");
    if (memo) memo.classList.toggle("has-note", !!(note && note.trim()));
    const pop = ctl.querySelector(".note-pop");
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
    const pop = ctl.querySelector(".note-pop");
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
    fetch(`/documents/${docId}/blanks/${id}/note`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => (d.ok ? applyNote(ctl, d.note) : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function renderBlanks(blanks) {
    root.querySelectorAll(".mask").forEach((m) => m.remove());
    root.querySelectorAll(".attempt-ctl").forEach((c) => c.remove());
    if (blankCount) blankCount.textContent = `穴 ${blanks.length} 個`;
    for (const b of blanks) {
      const page = pageEls[b.page];
      if (!page) continue;
      const layer = page.querySelector(".blank-layer");
      const pw = page.clientWidth;
      const ph = page.clientHeight;
      for (const r of b.rects) {
        const m = document.createElement("div");
        m.className = "mask";
        m.dataset.blankId = b.id;
        m.style.left = r.x * pw + "px";
        m.style.top = r.y * ph + "px";
        m.style.width = r.w * pw + "px";
        m.style.height = r.h * ph + "px";
        layer.appendChild(m);
      }
      // 正誤コントロールは穴ごとに1つ、先頭矩形の右上に置く。
      if (b.rects.length) {
        const r0 = b.rects[0];
        const ctl = makeControl(b.id, b.counts, b.note);
        ctl.style.left = (r0.x + r0.w) * pw + "px";
        ctl.style.top = r0.y * ph + "px";
        layer.appendChild(ctl);
      }
    }
  }

  // 穴の開閉（マスクと正誤コントロールの表示を揃える）。
  function setRevealed(id, revealed) {
    root
      .querySelectorAll(`.mask[data-blank-id="${id}"]`)
      .forEach((x) => x.classList.toggle("revealed", revealed));
    const ctl = root.querySelector(`.attempt-ctl[data-blank-id="${id}"]`);
    if (ctl) ctl.classList.toggle("revealed", revealed);
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
        const ctl = root.querySelector(`.attempt-ctl[data-blank-id="${id}"]`);
        if (ctl) setControlCounts(ctl, d.counts);
      })
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function postBlank(page, kind, rects) {
    const body = new URLSearchParams({
      page: String(page),
      kind,
      rects: JSON.stringify(rects),
    });
    fetch(`/documents/${docId}/blanks`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => (d.ok ? loadBlanks() : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function deleteBlank(id) {
    fetch(`/documents/${docId}/blanks/${id}/delete`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => (d.ok ? loadBlanks() : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  }

  // ---- クリック: 正誤記録 / 実践=開閉 / 作成=削除 ----
  root.addEventListener("click", (e) => {
    const btn = e.target.closest(".attempt-ctl .atk");
    if (btn) {
      e.stopPropagation();
      const ctl = btn.closest(".attempt-ctl");
      if (btn.classList.contains("memo")) {
        onMemo(ctl);
      } else if (mode === "practice") {
        // 正誤の記録は実践モードのみ（作成モードでは回数の表示だけ）。
        recordAttempt(ctl.dataset.blankId, btn.dataset.result);
      }
      return;
    }
    if (e.target.closest(".note-pop")) return; // メモ本文クリックは無視（読む/選択用）
    const m = e.target.closest(".mask");
    if (!m) return;
    const id = m.dataset.blankId;
    if (mode === "practice") {
      setRevealed(id, !m.classList.contains("revealed"));
    } else if (mode === "create") {
      if (window.confirm("この穴を削除しますか？")) deleteBlank(id);
    }
  });

  function revealAll(revealed) {
    root.querySelectorAll(".mask").forEach((m) => m.classList.toggle("revealed", revealed));
    root.querySelectorAll(".attempt-ctl").forEach((c) => c.classList.toggle("revealed", revealed));
  }
  document.getElementById("reveal-all")?.addEventListener("click", () => revealAll(true));
  document.getElementById("hide-all")?.addEventListener("click", () => revealAll(false));

  // ---- 作成: テキスト選択 ----
  function pageOf(node) {
    let el = node.nodeType === 1 ? node : node.parentNode;
    while (el && el !== root) {
      if (el.classList && el.classList.contains("pdf-page")) return el;
      el = el.parentNode;
    }
    return null;
  }

  function mergeRows(rects) {
    const rows = [];
    for (const r of rects) {
      const row = rows.find((x) => Math.abs(x.y - r.y) < r.h * 0.6);
      if (row) {
        const right = Math.max(row.x + row.w, r.x + r.w);
        row.x = Math.min(row.x, r.x);
        row.w = right - row.x;
        row.y = Math.min(row.y, r.y);
        row.h = Math.max(row.h, r.h);
      } else {
        rows.push({ ...r });
      }
    }
    return rows;
  }

  root.addEventListener("mouseup", () => {
    if (!(mode === "create" && tool === "text")) return;
    const sel = window.getSelection();
    if (sel.isCollapsed || !sel.toString().trim()) return;
    const range = sel.getRangeAt(0);
    const page = pageOf(range.startContainer);
    if (!page || page !== pageOf(range.endContainer)) {
      showStatus("同一ページ内で選択してください。");
      return;
    }
    const pr = page.getBoundingClientRect();
    let rects = Array.from(range.getClientRects())
      .filter((r) => r.width > 1 && r.height > 1)
      .map((r) => ({
        x: (r.left - pr.left) / pr.width,
        y: (r.top - pr.top) / pr.height,
        w: r.width / pr.width,
        h: r.height / pr.height,
      }));
    rects = mergeRows(rects);
    if (!rects.length) return;
    // 即作成せず「作成待ち」にする（選択は見た目として残す）。
    stagePending({ page: page.dataset.page, kind: "text", rects }, null);
  });

  // ---- 作成: 矩形ドラッグ ----
  let draw = null;
  function onDown(e) {
    if (!(mode === "create" && tool === "rect")) return;
    if (e.target.classList.contains("mask")) return; // 既存マスクは削除クリック優先
    clearPending(); // 直前の作成待ちは破棄して描き直す
    const layer = e.currentTarget;
    draw = { layer, page: layer.parentNode.dataset.page, x0: e.clientX, y0: e.clientY, el: null };
    e.preventDefault();
  }
  function onMove(e) {
    if (!draw) return;
    const pr = draw.layer.getBoundingClientRect();
    const x = Math.min(e.clientX, draw.x0) - pr.left;
    const y = Math.min(e.clientY, draw.y0) - pr.top;
    const w = Math.abs(e.clientX - draw.x0);
    const h = Math.abs(e.clientY - draw.y0);
    if (!draw.el) {
      draw.el = document.createElement("div");
      draw.el.className = "rect-preview";
      draw.layer.appendChild(draw.el);
    }
    Object.assign(draw.el.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
  }
  function onUp(e) {
    if (!draw) return;
    const d = draw;
    draw = null;
    const pr = d.layer.getBoundingClientRect();
    const x = Math.min(e.clientX, d.x0) - pr.left;
    const y = Math.min(e.clientY, d.y0) - pr.top;
    const w = Math.abs(e.clientX - d.x0);
    const h = Math.abs(e.clientY - d.y0);
    if (w < 5 || h < 5) {
      if (d.el) d.el.remove();
      return;
    }
    // 即作成せず、プレビュー矩形を残して「作成待ち」にする。
    stagePending(
      { page: d.page, kind: "rect", rects: [{ x: x / pr.width, y: y / pr.height, w: w / pr.width, h: h / pr.height }] },
      d.el || null,
    );
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);

  // ---- PDF 描画 ----
  async function renderPdf() {
    if (typeof pdfjsLib === "undefined") {
      if (pdfStatus) pdfStatus.textContent = "PDF.js の読み込みに失敗しました。";
      return;
    }
    pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/pdf.worker.min.js";
    const targetWidth = Math.min(root.clientWidth || 900, 900);
    let pdf;
    try {
      pdf = await pdfjsLib.getDocument(`/documents/${docId}/raw`).promise;
    } catch (err) {
      if (pdfStatus) pdfStatus.textContent = "PDF を開けませんでした。";
      return;
    }
    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n);
      const base = page.getViewport({ scale: 1 });
      const scale = targetWidth / base.width;
      const viewport = page.getViewport({ scale });

      const pageEl = document.createElement("div");
      pageEl.className = "pdf-page";
      pageEl.dataset.page = String(n);
      pageEl.style.width = viewport.width + "px";
      pageEl.style.height = viewport.height + "px";

      const canvas = document.createElement("canvas");
      canvas.className = "pdf-canvas";
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      const textLayer = document.createElement("div");
      textLayer.className = "text-layer";
      textLayer.style.setProperty("--scale-factor", String(scale));
      const blankLayer = document.createElement("div");
      blankLayer.className = "blank-layer";
      blankLayer.addEventListener("mousedown", onDown);

      pageEl.append(canvas, textLayer, blankLayer);
      root.appendChild(pageEl);
      pageEls[n] = pageEl;

      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      const textContent = await page.getTextContent();
      pdfjsLib.renderTextLayer({ textContent, container: textLayer, viewport, textDivs: [] });
    }
    if (pdfStatus) pdfStatus.hidden = true;
    await loadBlanks();
  }

  setMode("practice");
  setTool("text");
  renderPdf();
});
