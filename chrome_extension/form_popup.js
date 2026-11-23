"use strict";

(() => {
  const panel = document.getElementById("form-offer");
  const site = document.getElementById("form-site");
  const profile = document.getElementById("form-profile");
  const save = document.getElementById("form-save");
  const skip = document.getElementById("form-skip");
  const find = document.getElementById("form-find");
  const message = document.getElementById("form-message");
  let active;
  let offer;
  let looking = false;

  function close(text = "") {
    offer = null;
    panel.hidden = true;
    message.textContent = text;
  }

  async function load(op, showError = true) {
    if (looking) return;
    looking = find.disabled = save.disabled = true;
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true}).catch(() => []);
      const response = await vaultRequest({op, tabId: tab?.id});
      if (!response.id) {
        close(showError ? STATUS_TEXT[response.code] || STATUS_TEXT.form_missing : "");
        return;
      }
      active = tab.id;
      showConnection(response);
      const ready = response.code === "ready";
      offer = {id: response.id, ready, update: response.update};
      site.textContent = response.site;
      if (ready || panel.hidden) profile.textContent = response.profile || "Chưa sẵn sàng";
      save.textContent = ready ? offer.update ? "Cập nhật" : "Lưu" : "Thử lại";
      skip.disabled = false;
      message.textContent = ready ? "" : STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
      panel.hidden = false;
    } finally {
      looking = find.disabled = save.disabled = false;
    }
  }

  find.addEventListener("click", (event) => {
    if (event.isTrusted && !offer) void load("form_find");
  });
  skip.addEventListener("click", (event) => {
    if (!event.isTrusted || !offer) return;
    void vaultRequest({op: "form_skip", tabId: active, id: offer.id});
    close();
  });
  save.addEventListener("keydown", (event) => {
    if (event.repeat) event.preventDefault();
  });
  save.addEventListener("click", async (event) => {
    if (!event.isTrusted || event.detail > 1 || save.disabled || !offer) return;
    if (!offer.ready) {
      await load("form_context");
      return;
    }
    const previous = offer;
    save.disabled = skip.disabled = find.disabled = true;
    message.textContent = "Đang xử lý…";
    const response = await vaultRequest({op: "form_save", tabId: active, id: previous.id, update: previous.update});
    save.disabled = skip.disabled = find.disabled = false;
    if (offer !== previous) return;
    if (response.code === "saved") {
      close(`Đã lưu vào ${profile.textContent}`);
    } else if (["duplicate", "target_changed", "form_missing", "form_empty"].includes(response.code)) {
      void vaultRequest({op: "form_skip", tabId: active, id: previous.id});
      close(STATUS_TEXT[response.code]);
    } else {
      previous.update = response.update ?? previous.update;
      previous.ready = !connectionUnavailable(response.code);
      save.textContent = previous.update ? "Cập nhật" : previous.ready ? "Lưu" : "Thử lại";
      message.textContent = previous.update ? "Cập nhật mật khẩu đã lưu?"
        : STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
    }
  });

  chrome.runtime.onMessage.addListener((event, sender) => {
    if (sender.id === chrome.runtime.id && !sender.tab &&
        event?.op === "form_ended" && offer?.id === event.id) close(STATUS_TEXT.form_missing);
  });
  void load("form_context", false).then(() => {
    if (!offer) void checkConnection();
  });
})();
