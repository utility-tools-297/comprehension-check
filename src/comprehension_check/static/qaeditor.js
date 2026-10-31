"use strict";

// Q&A作問エディタ：問題・答えの行を追加/削除/並べ替えして、answer を穴にした Markdown を作る/更新する。
// 送信は form-encoded（items=JSON）。作成はサーバーが 303 でビューアへ、編集は JSON を返す。
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("qa-form");
  const list = document.getElementById("qa-items");
  const addBtn = document.getElementById("qa-add");
  const statusEl = document.getElementById("status");
  if (!form || !list) return;

  const action = form.dataset.action;
  const mode = form.dataset.mode;

  function showStatus(msg) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.hidden = false;
  }

  let initial = [];
  try {
    initial = JSON.parse(document.getElementById("qa-initial").textContent || "[]") || [];
  } catch (e) {
    initial = [];
  }

  function makeRow(item) {
    const li = document.createElement("li");
    li.className = "qa-item";
    if (item && item.number != null) li.dataset.number = String(item.number);
    li.innerHTML =
      '<div class="qa-fields">' +
      '<label class="qa-q">問題<textarea class="qa-question" rows="2"></textarea></label>' +
      '<label class="qa-a">答え<textarea class="qa-answer" rows="2"></textarea></label>' +
      "</div>" +
      '<div class="qa-rowbtns">' +
      '<button type="button" class="btn-ghost qa-up" title="上へ">↑</button>' +
      '<button type="button" class="btn-ghost qa-down" title="下へ">↓</button>' +
      '<button type="button" class="btn-ghost qa-del" title="削除">×</button>' +
      "</div>";
    li.querySelector(".qa-question").value = item ? item.question || "" : "";
    li.querySelector(".qa-answer").value = item ? item.answer || "" : "";
    return li;
  }

  function addRow(item) {
    list.appendChild(makeRow(item));
  }

  if (initial.length) initial.forEach(addRow);
  else addRow(null);

  if (addBtn) addBtn.addEventListener("click", () => addRow(null));

  // 行の並べ替え（上/下）と削除。
  list.addEventListener("click", (e) => {
    const li = e.target.closest(".qa-item");
    if (!li) return;
    if (e.target.closest(".qa-del")) {
      li.remove();
      if (!list.children.length) addRow(null);
      return;
    }
    if (e.target.closest(".qa-up")) {
      const prev = li.previousElementSibling;
      if (prev) list.insertBefore(li, prev);
      return;
    }
    if (e.target.closest(".qa-down")) {
      const next = li.nextElementSibling;
      if (next) list.insertBefore(next, li);
    }
  });

  function collect() {
    const items = [];
    list.querySelectorAll(".qa-item").forEach((li) => {
      const q = li.querySelector(".qa-question").value;
      const a = li.querySelector(".qa-answer").value;
      if (!q.trim() && !a.trim()) return;
      const o = { question: q, answer: a };
      if (li.dataset.number) o.number = Number(li.dataset.number);
      items.push(o);
    });
    return items;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const items = collect();
    if (!items.length) {
      showStatus("1問以上入力してください。");
      return;
    }
    const body = new URLSearchParams();
    body.set("items", JSON.stringify(items));
    if (mode === "create") {
      const t = document.getElementById("qa-title");
      const d = document.getElementById("qa-dest");
      body.set("title", t ? t.value : "");
      body.set("dest", d ? d.value : "");
    }
    fetch(action, { method: "POST", body })
      .then((r) => {
        const ct = r.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
          return r.json().then((d) => {
            if (d.ok) location.href = action.replace(/\/qa$/, ""); // 編集 → ビューアへ
            else showStatus(d.error || "保存に失敗しました。");
          });
        }
        // 作成: サーバーが 303 でビューアへ。fetch は追従するので最終 URL へ移動。
        if (r.redirected) location.href = r.url;
        else showStatus("作成に失敗しました。");
        return null;
      })
      .catch(() => showStatus("通信に失敗しました。"));
  });
});
