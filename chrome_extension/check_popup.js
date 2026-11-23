"use strict";

const checkTabButton = document.getElementById("check-tab");
const tabCheckStatus = document.getElementById("tab-status");
const tabCheckResult = document.getElementById("tab-result");
const tabCheckFindings = document.getElementById("tab-findings");

function renderTabCheck(response) {
  document.getElementById("tab-risk").textContent = response.risk;
  document.getElementById("tab-hostname").textContent = response.hostname;
  document.getElementById("tab-domain").textContent = response.domain || "Không xác định";
  document.getElementById("tab-profile").textContent = `Hồ sơ đối chiếu: ${response.profile}`;
  const matches = {
    hostname: "Hostname trùng với URL của một mục đăng nhập đã lưu.",
    domain: "Cùng tên miền đăng ký với một mục đã lưu, nhưng hostname khác.",
    none: "Không tìm thấy tên miền này trong các mục đăng nhập đang hoạt động.",
  };
  const lines = [matches[response.match] || matches.none, ...response.findings];
  if (response.similar_domain) {
    lines.push(`Hostname trông giống ${response.similar_domain} trong kho và thuộc tên miền khác.`);
  }
  tabCheckFindings.replaceChildren(...lines.map((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    return item;
  }));
  tabCheckResult.hidden = false;
}

checkTabButton.addEventListener("click", async (event) => {
  if (!event.isTrusted || checkTabButton.disabled) return;
  checkTabButton.disabled = true;
  tabCheckResult.hidden = true;
  tabCheckStatus.textContent = "Đang đối chiếu tên miền…";
  const response = await vaultRequest({op: "check_tab"});
  if (response.code === "tab_checked" && Array.isArray(response.findings)) {
    tabCheckStatus.textContent = "Đã đối chiếu tên miền.";
    renderTabCheck(response);
  } else {
    tabCheckStatus.textContent = STATUS_TEXT[response.code] || STATUS_TEXT.host_error;
  }
  checkTabButton.disabled = false;
});
