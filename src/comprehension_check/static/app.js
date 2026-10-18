"use strict";

// Markdown ビューアの実践/作成モード制御。
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

  function setMode(next) {
    mode = next;
    doc.classList.toggle("mode-practice", next === "practice");
    doc.classList.toggle("mode-create", next === "create");
    if (practiceTools) practiceTools.hidden = next !== "practice";
    if (createHint) createHint.hidden = next !== "create";
    modeButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === next));
    window.getSelection().removeAllRanges();
  }

  modeButtons.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  // 実践: 全て表示 / 全て隠す
  const revealAll = document.getElementById("reveal-all");
  const hideAll = document.getElementById("hide-all");
  if (revealAll)
    revealAll.addEventListener("click", () =>
      doc.querySelectorAll(".cloze").forEach((c) => c.classList.add("revealed"))
    );
  if (hideAll)
    hideAll.addEventListener("click", () =>
      doc.querySelectorAll(".cloze").forEach((c) => c.classList.remove("revealed"))
    );

  // クリック: 実践=開閉トグル、作成=削除
  doc.addEventListener("click", (e) => {
    const cz = e.target.closest(".cloze");
    if (!cz) return;
    if (mode === "practice") {
      cz.classList.toggle("revealed");
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

  // 作成: 選択範囲を穴として登録
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
