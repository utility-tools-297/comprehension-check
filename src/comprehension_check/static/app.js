"use strict";

// Markdown ビューアの実践/作成モード制御＋穴ごとの正誤回数・メモ。
// 回数・メモは内容（ファイル記法）とは別に (doc_id, 穴番号) をキーに DB 管理する。
// コントロールは実践モードのみ本文へ挿入する（作成モードの選択→囲いが本文テキストを数える際、
// コントロールの文字が混ざって出現番目がずれるのを避けるため）。
document.addEventListener("DOMContentLoaded", () => {
  const doc = document.getElementById("doc");
  const toolbar = document.getElementById("toolbar");
  if (!doc || !toolbar) return;

  const docId = doc.dataset.docId;
  const statusEl = document.getElementById("status");
  const createHint = document.getElementById("create-hint");
  const practiceTools = toolbar.querySelector(".practice-tools");
  const modeButtons = toolbar.querySelectorAll(".mode-switch button[data-mode]");
  let mode = "practice";

  function showStatus(msg) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.hidden = false;
    window.clearTimeout(showStatus._t);
    showStatus._t = window.setTimeout(() => {
      statusEl.hidden = true;
    }, 4000);
  }

  // ---- 穴ごとの正誤回数・メモ ----
  let metaByNumber = null; // {number: {counts, note}}（取得後にセット）
  const controls = []; // 現在 DOM に挿入中の {cz, ctl}

  function setCounts(ctl, counts) {
    const ns = ctl.querySelectorAll(".cc-n");
    if (ns.length >= 2) {
      ns[0].textContent = String((counts && counts.correct) || 0);
      ns[1].textContent = String((counts && counts.incorrect) || 0);
    }
  }

  function applyNote(ctl, note) {
    ctl.dataset.note = note || "";
    const memo = ctl.querySelector(".cc-memo");
    if (memo) {
      const has = !!(note && note.trim());
      memo.classList.toggle("cc-has-note", has);
      memo.title = has ? note : "メモ";
    }
  }

  function makeControl(number, counts, note) {
    const ctl = document.createElement("span");
    ctl.className = "md-attempt";
    ctl.dataset.number = String(number);
    ctl.innerHTML =
      '<button type="button" class="md-ok" data-result="correct" title="正解">正<span class="cc-n">0</span></button>' +
      '<button type="button" class="md-ng" data-result="incorrect" title="不正解">誤<span class="cc-n">0</span></button>' +
      '<button type="button" class="cc-memo" title="メモ">✎</button>';
    setCounts(ctl, counts);
    applyNote(ctl, note || "");
    return ctl;
  }

  function syncOne(cz, ctl) {
    ctl.hidden = cz.classList.contains("revealed"); // 穴を表示したら回数・メモも隠す
  }

  function renderControls() {
    controls.forEach((p) => p.ctl.remove());
    controls.length = 0;
    if (mode !== "practice" || !metaByNumber) return;
    doc.querySelectorAll(".cloze").forEach((cz) => {
      const num = Number(cz.dataset.cloze);
      const meta = metaByNumber[num] || { counts: { correct: 0, incorrect: 0 }, note: "" };
      const ctl = makeControl(num, meta.counts, meta.note);
      cz.insertAdjacentElement("afterend", ctl);
      controls.push({ cz, ctl });
      syncOne(cz, ctl);
    });
  }

  fetch(`/documents/${docId}/md-blanks`)
    .then((r) => r.json())
    .then((d) => {
      metaByNumber = {};
      (d.clozes || []).forEach((b) => {
        metaByNumber[b.number] = { counts: b.counts, note: b.note };
      });
      renderControls();
    })
    .catch(() => {});

  function setMode(next) {
    mode = next;
    doc.classList.toggle("mode-practice", next === "practice");
    doc.classList.toggle("mode-create", next === "create");
    if (practiceTools) practiceTools.hidden = next !== "practice";
    if (createHint) createHint.hidden = next !== "create";
    modeButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === next));
    window.getSelection().removeAllRanges();
    renderControls(); // 実践=挿入 / 作成=撤去
  }

  modeButtons.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  // 実践: 全て表示 / 全て隠す（コントロールも同期）
  const revealAll = document.getElementById("reveal-all");
  const hideAll = document.getElementById("hide-all");
  if (revealAll)
    revealAll.addEventListener("click", () => {
      doc.querySelectorAll(".cloze").forEach((c) => c.classList.add("revealed"));
      controls.forEach((p) => syncOne(p.cz, p.ctl));
    });
  if (hideAll)
    hideAll.addEventListener("click", () => {
      doc.querySelectorAll(".cloze").forEach((c) => c.classList.remove("revealed"));
      controls.forEach((p) => syncOne(p.cz, p.ctl));
    });

  // 正誤ボタン: 実践のみ記録。メモボタン: 常時プロンプト編集。
  function recordResult(ctl, result) {
    const number = ctl.dataset.number;
    const body = new URLSearchParams({ number, result });
    fetch(`/documents/${docId}/md-attempts`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) return showStatus(d.error);
        setCounts(ctl, d.counts);
        if (metaByNumber && metaByNumber[number]) metaByNumber[number].counts = d.counts;
      })
      .catch(() => showStatus("通信に失敗しました。"));
  }

  function editNote(ctl) {
    const number = ctl.dataset.number;
    const value = window.prompt("メモ", ctl.dataset.note || "");
    if (value === null) return;
    const body = new URLSearchParams({ number, note: value });
    fetch(`/documents/${docId}/md-note`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) return showStatus(d.error);
        applyNote(ctl, d.note);
        if (metaByNumber && metaByNumber[number]) metaByNumber[number].note = d.note;
      })
      .catch(() => showStatus("通信に失敗しました。"));
  }

  doc.addEventListener("click", (e) => {
    // コントロール（回数・メモ）の操作。穴の開閉・削除には波及させない。
    const resultBtn = e.target.closest(".md-ok, .md-ng");
    if (resultBtn) {
      if (mode === "practice") recordResult(resultBtn.closest(".md-attempt"), resultBtn.dataset.result);
      return;
    }
    const memoBtn = e.target.closest(".cc-memo");
    if (memoBtn) {
      editNote(memoBtn.closest(".md-attempt"));
      return;
    }
    // 穴本体: 実践=開閉トグル、作成=削除。
    const cz = e.target.closest(".cloze");
    if (!cz) return;
    if (mode === "practice") {
      cz.classList.toggle("revealed");
      const pair = controls.find((p) => p.cz === cz);
      if (pair) syncOne(cz, pair.ctl);
      return;
    }
    if (mode === "create") {
      if (!window.getSelection().isCollapsed) return; // 選択ドラッグ中は無視
      if (!window.confirm("この穴を削除しますか？")) return;
      const body = new URLSearchParams({ number: cz.dataset.cloze });
      fetch(`/documents/${docId}/cloze/delete`, { method: "POST", body })
        .then((r) => r.json())
        .then((d) => (d.ok ? location.reload() : showStatus(d.error)))
        .catch(() => showStatus("通信に失敗しました。"));
    }
  });

  // 作成: 選択範囲を穴として登録（コントロールは撤去済みなので本文テキストは汚れない）
  function blockOf(node) {
    let el = node.nodeType === 1 ? node : node.parentNode;
    while (el && el !== doc) {
      if (el.nodeType === 1 && el.hasAttribute("data-ls")) return el;
      el = el.parentNode;
    }
    return null;
  }

  doc.addEventListener("mouseup", () => {
    if (mode !== "create") return;
    const sel = window.getSelection();
    if (sel.isCollapsed) return;
    const selected = sel.toString().trim();
    if (!selected) return;

    const range = sel.getRangeAt(0);
    const block = blockOf(range.startContainer);
    const blockEnd = blockOf(range.endContainer);
    if (!block || block !== blockEnd) {
      showStatus("同一ブロック内で選択してください。");
      return;
    }
    // ブロック先頭から選択開始までのテキストで出現番目を数える
    const pre = document.createRange();
    pre.selectNodeContents(block);
    pre.setEnd(range.startContainer, range.startOffset);
    const preText = pre.toString();
    let occurrence = 0;
    for (let i = preText.indexOf(selected); i !== -1; i = preText.indexOf(selected, i + 1)) {
      occurrence += 1;
    }

    const body = new URLSearchParams({
      line_start: block.dataset.ls,
      line_end: block.dataset.le,
      selected,
      occurrence: String(occurrence),
    });
    fetch(`/documents/${docId}/cloze`, { method: "POST", body })
      .then((r) => r.json())
      .then((d) => (d.ok ? location.reload() : showStatus(d.error)))
      .catch(() => showStatus("通信に失敗しました。"));
  });

  setMode("practice");
});
