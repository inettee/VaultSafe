"use strict";

// Automatic offers use an explicit first-party success signal on these test routes.
const HTTPS_DEMO_ROOT = "https://vaultsafe-demo.test:8766/vaultsafe-demo/";
const DIALOG_DEMO_ROOT = "https://vaultsafe-dialog.test:8766/vaultsafe-demo/";
const AUTO_SITES = Object.freeze({
  localhost: "http://localhost:8765/vaultsafe-demo/",
  redirect: HTTPS_DEMO_ROOT + "login",
  account: HTTPS_DEMO_ROOT + "account?flow=",
});
const INLINE_DEMOS = Object.freeze({
  [HTTPS_DEMO_ROOT + "inline"]: "https_demo",
  [DIALOG_DEMO_ROOT + "inline"]: "https_dialog_demo",
  [DIALOG_DEMO_ROOT + "steps"]: "https_dialog_demo",
});
const FLOW_ID = /^[0-9a-f]{32}$/;
const NAVIGATION_TIMEOUT = 12_000;
const OFFER_TIMEOUT = 90_000;
const FORM_OFFER_TIMEOUT = 25_000;

function flowFromUrl(url) {
  if (!url?.startsWith(AUTO_SITES.account)) return "";
  const flow = url.slice(AUTO_SITES.account.length);
  return validFlow(flow) ? flow : "";
}

function validFlow(flow) {
  return typeof flow === "string" && flow.length === 32 && FLOW_ID.test(flow);
}

function inlineDemoSite(url) {
  return Object.hasOwn(INLINE_DEMOS, url) ? INLINE_DEMOS[url] : "";
}

function validDemoCredentials(username, password) {
  return typeof username === "string" &&
    /^[a-z0-9][a-z0-9._-]{0,63}@example\.test$/.test(username) &&
    ["DemoOnly!123", "DemoOnly!456"].includes(password);
}
