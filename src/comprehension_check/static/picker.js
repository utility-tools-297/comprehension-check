"use strict";

// 「参照…」で OS のファイル選択ダイアログを開き、選ばれた絶対パスを入力欄へ入れて登録する。
// （ローカル実行前提。ダイアログはサーバ＝このPC上で開く）
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("pick-btn");
  const input = document.getElementById("path-input");
  const form = document.getElementById("add-form");
  if (!btn || !input || !form) return;

  btn.addEventListener("click", () => {
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "選択中…";
    fetch("/pick-file", { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        if (d.path) {
          input.value = d.path;
          form.submit();
        }
      })
      .catch(() => {})
      .finally(() => {
        btn.disabled = false;
        btn.textContent = label;
      });
  });
});
