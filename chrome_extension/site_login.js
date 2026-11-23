"use strict";

(() => {
  const url = location.href;
  const flow = flowFromUrl(url);
  if (flow) {
    if (document.querySelector('meta[name="vaultsafe-demo-flow"]')?.content !== flow) return;
    let left = false;
    window.addEventListener("pagehide", () => { left = true; }, {once: true});
    void vaultRequest({op: "take_https", flow}).then((response) => {
      if (!left && response.code === "pending") {
        savePrompt.show(location.hostname, response.username, response.password);
      }
    });
    return;
  }

  const redirect = url === AUTO_SITES.redirect;
  const localhost = url === AUTO_SITES.localhost;
  if (!redirect && !localhost && !inlineDemoSite(url)) return;
  let lastFlow = "";
  document.addEventListener("vaultsafe-demo-login-start", savePrompt.dismiss);
  document.addEventListener("vaultsafe-demo-login-success", async (event) => {
    const {method, flow, username, password} = event.detail || {};
    if (method !== "password" || !validFlow(flow) || flow === lastFlow ||
        !validDemoCredentials(username, password)) return;
    lastFlow = flow;
    if (redirect) {
      await vaultRequest({op: "stage_https", flow, username, password});
      document.dispatchEvent(new CustomEvent("vaultsafe-https-demo-received", {detail: flow}));
    } else {
      savePrompt.show(location.hostname, username, password);
    }
  });
})();
