"use strict";

const HOST_NAME = "com.vaultsafe.chrome";
const UNSUPPORTED_TEXT = /[\u0000-\u001f\u007f\ud800-\udfff]/u;
const STATUS_TEXT = Object.freeze({
  ready: "VaultSafe đã kết nối.",
  host_missing: "Chưa kết nối với VaultSafe. Mở Thiet-lap-Chrome.exe trong gói Windows rồi chọn Kết nối và mở Chrome.",
  host_error: "Kết nối bị lỗi. Mở lại Thiet-lap-Chrome.exe và bấm Kết nối và mở Chrome. Nếu vừa cập nhật, hãy dùng tiện ích từ gói mới.",
  app_closed: "VaultSafe chưa chạy. Mở ứng dụng và mở đúng kho rồi thử lại.",
  locked: "Kho đang khóa. Mở đúng hồ sơ trong VaultSafe rồi thử lại.",
  busy: "VaultSafe đang bận. Hãy thử lại.",
  saved: "Đã lưu vào VaultSafe.",
  duplicate: "Tài khoản đã có trong kho.",
  check_invalid: "Hãy mở một tab HTTP hoặc HTTPS có địa chỉ hợp lệ để kiểm tra.",
  check_tab_changed: "Tab hoặc tên miền đã thay đổi. Hãy bấm kiểm tra lại.",
  ambiguous: "Có nhiều mục trùng website và tên đăng nhập. Hãy kiểm tra trong VaultSafe.",
  conflict: "Kho đã thay đổi. Hãy khóa, mở lại đúng kho trong VaultSafe rồi thử lại.",
  write_error: "VaultSafe không xác nhận được việc ghi kho. Hãy kiểm tra ứng dụng rồi thử lại.",
  invalid: "Thông tin mục không hợp lệ.",
  target_changed: "Phiên hồ sơ đích đã đổi. Yêu cầu đang chờ đã bị hủy.",
  form_tab_inactive: "VaultSafe chưa xác định được tab HTTPS đang chọn. Chọn tab đăng nhập rồi mở lại tiện ích trên thanh Chrome.",
  form_unavailable: "Chrome chưa cho VaultSafe chạy trên trang này. Kiểm tra quyền truy cập trang của tiện ích rồi thử lại.",
  form_not_detected: "VaultSafe đã mở được trang nhưng chưa nhận diện được cặp ô đăng nhập và mật khẩu trong trang chính. Bạn có thể chọn Nhập thủ công.",
  form_ambiguous: "VaultSafe chưa xác định được biểu mẫu bạn muốn lưu. Bấm vào ô tên đăng nhập hoặc mật khẩu trên trang rồi mở lại tiện ích.",
  form_stale: "Biểu mẫu đã thay đổi hoặc trang đã chuyển trong khi VaultSafe kiểm tra. Hãy mở biểu mẫu rồi thử lại.",
  form_missing: "Biểu mẫu đã thay đổi hoặc trang đã chuyển. Hãy dùng Lưu vào VaultSafe trước khi gửi biểu mẫu, hoặc chọn Nhập thủ công.",
  form_empty: "Hãy điền tên đăng nhập và mật khẩu trên website rồi thử lại, hoặc chọn Nhập thủ công.",
  review_update: "Mục đã thay đổi. Bấm Lưu để kiểm tra lại trước khi cập nhật."
});

function manualUrl(value) {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname ||
        url.username || url.password || url.port === "0") return "";
    url.search = "";
    url.hash = "";
    return url.href.length <= 1024 ? url.href : "";
  } catch {
    return "";
  }
}

function checkTabUrl(value) {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.hostname.length > 254) return "";
    return `${url.protocol}//${url.hostname}/`;
  } catch {
    return "";
  }
}

function manualFields({url, username, password}) {
  return !!url && manualUrl(url) === url &&
    typeof username === "string" && username === username.trim() && username.length > 0 &&
    username.length <= 128 && typeof password === "string" &&
    password.trim().length > 0 && password.length <= 256 &&
    !UNSUPPORTED_TEXT.test(username) && !UNSUPPORTED_TEXT.test(password);
}

async function vaultRequest(request) {
  try {
    return (await chrome.runtime.sendMessage(request)) ?? {code: "host_error"};
  } catch {
    return {code: "host_error"};
  }
}
