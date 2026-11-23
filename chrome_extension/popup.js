"use strict";

const statusLine = document.getElementById("status");
const profileLine = document.getElementById("profile");
const refresh = document.getElementById("refresh");
const addCurrent = document.getElementById("add-current");
const form = document.getElementById("manual");
const manualProfile = document.getElementById("manual-profile");
const urlField = document.getElementById("manual-url");
const usernameField = document.getElementById("manual-user");
const passwordField = document.getElementById("manual-password");
const save = document.getElementById("manual-save");
const cancel = document.getElementById("manual-cancel");
const message = document.getElementById("manual-message");
let draft = null;

function showConnection(response) {
  statusLine.textContent = STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
  profileLine.hidden = response.code !== "ready";
  profileLine.textContent = response.code === "ready" ? `Hồ sơ đang mở: ${response.profile}` : "";
}

async function checkConnection() {
  refresh.disabled = true;
  showConnection(await vaultRequest({op: "status"}));
  refresh.disabled = false;
}

refresh.addEventListener("click", checkConnection);

function closeDraft(text = "") {
  if (draft) clearTimeout(draft.timer);
  draft = null;
  form.reset();
  form.hidden = true;
  addCurrent.disabled = false;
  message.textContent = text;
}

function allowEntry(enabled) {
  usernameField.disabled = passwordField.disabled = !enabled;
}

async function checkDestination(state) {
  save.disabled = true;
  allowEntry(false);
  const response = await state.session.status();
  if (draft !== state) return;
  if (response.code === "target_changed") {
    closeDraft(STATUS_TEXT.target_changed);
    return;
  }
  state.ready = response.code === "ready";
  manualProfile.textContent = state.ready ? response.profile : state.profile || "Chưa sẵn sàng";
  if (state.ready) state.profile = response.profile;
  message.textContent = state.ready ? "" : STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
  allowEntry(state.ready);
  save.textContent = state.ready ? "Lưu" : "Thử lại";
  save.disabled = false;
}

addCurrent.addEventListener("click", async (event) => {
  if (!event.isTrusted || addCurrent.disabled) return;
  addCurrent.disabled = true;
  message.textContent = "";
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true}).catch(() => []);
  const url = manualUrl(tab?.url);
  if (!url) {
    closeDraft("Hãy mở một tab HTTP hoặc HTTPS để thêm mục.");
    return;
  }
  const state = {url, session: newSaveSession(), ready: false, profile: "",
    expiresAt: Date.now() + OFFER_TIMEOUT};
  draft = state;
  state.timer = setTimeout(() => closeDraft("Mục chờ đã hết hạn."), OFFER_TIMEOUT);
  urlField.value = url;
  manualProfile.textContent = "Đang kiểm tra…";
  cancel.disabled = false;
  form.hidden = false;
  await checkDestination(state);
  if (draft === state && state.ready) usernameField.focus();
});

cancel.addEventListener("click", () => closeDraft());
save.addEventListener("click", (event) => {
  if (event.detail > 1) event.preventDefault();
});
form.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.repeat) event.preventDefault();
});
form.addEventListener("input", () => {
  if (draft?.ready) {
    draft.session.clearConfirmation();
    save.textContent = "Lưu";
    message.textContent = "";
  }
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!event.isTrusted || !draft || save.disabled) return;
  const state = draft;
  if (Date.now() >= state.expiresAt) {
    closeDraft("Mục chờ đã hết hạn.");
    return;
  }
  if (!state.ready) {
    await checkDestination(state);
    return;
  }
  const fields = {url: state.url, username: usernameField.value.trim(), password: passwordField.value};
  if (!manualFields(fields)) {
    message.textContent = "Kiểm tra tên đăng nhập và mật khẩu.";
    return;
  }
  save.disabled = cancel.disabled = true;
  allowEntry(false);
  save.textContent = message.textContent = "Đang lưu…";
  const response = await state.session.save(fields);
  if (draft !== state) return;
  if (response.code === "saved" || response.code === "duplicate" || response.code === "target_changed") {
    closeDraft(response.code === "saved" ? `Đã lưu vào ${state.profile}` : STATUS_TEXT[response.code]);
    return;
  }
  state.ready = !connectionUnavailable(response.code);
  save.disabled = cancel.disabled = false;
  allowEntry(state.ready);
  if (response.code === "confirm_update") {
    save.textContent = "Cập nhật";
    message.textContent = "Cập nhật mật khẩu? Mục này đã có trong kho với mật khẩu khác.";
  } else {
    save.textContent = state.ready ? "Lưu" : "Thử lại";
    message.textContent = STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
  }
});

window.addEventListener("pagehide", () => closeDraft());
