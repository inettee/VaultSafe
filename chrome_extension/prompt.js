"use strict";

const savePrompt = (() => {
  const QUESTION = "Lưu tài khoản này vào VaultSafe?";
  let current = null;

  function dismiss() {
    if (!current) return;
    clearTimeout(current.expires);
    current.host.remove();
    current.username = current.password = "";
    current = null;
  }

  function show(site, username, password) {
    dismiss();
    const host = document.createElement("div");
    host.id = "vaultsafe-save-prompt";
    const shadow = host.attachShadow({mode: "closed"});
    shadow.innerHTML = `
      <style>
        :host { all: initial; position: fixed; top: 16px; right: 16px; z-index: 2147483647;
          width: min(360px, calc(100vw - 32px)); color-scheme: dark; }
        section { box-sizing: border-box; padding: 18px; border: 1px solid #425b81;
          border-radius: 14px; background: #101c32; color: #f1f5f9;
          font: 14px/1.5 system-ui, sans-serif; box-shadow: 0 10px 32px #0008; }
        h2 { margin: 0 0 12px; font-size: 17px; }
        dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; margin: 0; }
        dt, p { color: #bacbe2; }
        dd { margin: 0; overflow-wrap: anywhere; }
        p { margin: 12px 0; }
        footer { display: flex; justify-content: end; gap: 8px; }
        button { border: 0; border-radius: 7px; padding: 7px 12px; background: #26364f;
          color: white; font: inherit; cursor: pointer; }
        button[data-save] { background: #2563eb; }
        button:disabled { opacity: .55; cursor: default; }
        .sr-only { position: absolute; width: 1px; height: 1px; clip-path: inset(50%); overflow: hidden; }
        [hidden] { display: none; }
      </style>
      <section role="region" aria-labelledby="title">
        <h2 id="title">${QUESTION}</h2>
        <dl><dt>Website</dt><dd data-site></dd><dt data-user-label>Tên đăng nhập</dt><dd data-user></dd>
          <dt>Mật khẩu</dt><dd aria-label="Đã che mật khẩu">••••••••</dd>
          <dt>Hồ sơ đích</dt><dd data-profile>Đang kiểm tra…</dd></dl>
        <p role="status"></p>
        <footer><button data-dismiss>Bỏ qua</button><button data-save disabled>Lưu</button></footer>
      </section>`;
    const state = {host, username, password, session: newSaveSession(), disconnected: true,
      expiresAt: Date.now() + OFFER_TIMEOUT};
    current = state;
    state.expires = setTimeout(dismiss, OFFER_TIMEOUT);
    const find = (selector) => shadow.querySelector(selector);
    const title = find("h2");
    const feedback = find("p");
    const profile = find("[data-profile]");
    const save = find("[data-save]");
    const skip = find("[data-dismiss]");
    find("[data-site]").textContent = site;
    find("[data-user]").textContent = username;
    find("[data-user-label]").hidden = find("[data-user]").hidden = !username;
    document.body.append(host);

    function finish(message) {
      state.username = state.password = "";
      feedback.textContent = message;
      save.hidden = true;
      skip.textContent = "Đóng";
    }

    function unavailable(code) {
      state.disconnected = true;
      if (profile.textContent === "Đang kiểm tra…") profile.textContent = "Chưa sẵn sàng";
      const opening = code === "locked" || code === "app_closed";
      feedback.textContent = (opening ? "Chưa lưu. Hãy mở khóa VaultSafe. " : "") +
        (STATUS_TEXT[code] || STATUS_TEXT.host_error);
      save.textContent = "Thử lại";
    }

    async function checkStatus(retry) {
      const response = await state.session.status();
      if (current !== state) return;
      if (response.code === "ready") {
        state.disconnected = false;
        profile.textContent = response.profile;
        feedback.textContent = retry ? "Kiểm tra hồ sơ đích rồi bấm Lưu." : "";
        save.textContent = "Lưu";
      } else if (response.code === "target_changed") {
        finish(STATUS_TEXT.target_changed);
      } else {
        unavailable(response.code);
      }
      save.disabled = false;
    }

    skip.addEventListener("click", dismiss);
    save.addEventListener("keydown", (event) => {
      if (event.repeat) event.preventDefault();
    });
    save.addEventListener("click", async (event) => {
      if (!event.isTrusted || event.detail > 1 || save.disabled) return;
      if (Date.now() >= state.expiresAt) {
        dismiss();
        return;
      }
      save.disabled = true;
      if (state.disconnected) {
        await checkStatus(true);
        return;
      }
      skip.disabled = true;
      feedback.textContent = "Đang lưu…";
      save.textContent = "Đang lưu…";
      const response = await state.session.save({username: state.username, password: state.password});
      if (current !== state) return;
      skip.disabled = false;
      save.disabled = false;
      if (response.code === "target_changed") {
        finish(STATUS_TEXT.target_changed);
      } else if (response.code === "confirm_update") {
        title.textContent = "Cập nhật mật khẩu?";
        feedback.textContent = "Mục này đã có trong kho với mật khẩu khác.";
        save.textContent = "Cập nhật";
      } else if (response.code === "saved") {
        title.textContent = `Đã lưu vào ${profile.textContent}`;
        find("dl").hidden = true;
        finish(title.textContent);
        feedback.classList.add("sr-only");
        clearTimeout(state.expires);
        state.expires = setTimeout(dismiss, 2800);
      } else if (["duplicate", "ambiguous", "invalid"].includes(response.code)) {
        finish(STATUS_TEXT[response.code]);
      } else {
        feedback.textContent = STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
        title.textContent = QUESTION;
        save.textContent = "Lưu";
        if (connectionUnavailable(response.code)) {
          unavailable(response.code);
        }
      }
    });
    void checkStatus(false);
  }

  window.addEventListener("pagehide", dismiss);
  return {show, dismiss};
})();
