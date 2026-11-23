"use strict";

importScripts("sites.js", "protocol.js", "form_background.js");

const pending = new Map();

function clearPending(tabId) {
  const login = pending.get(tabId);
  if (login) clearTimeout(login.timer);
  pending.delete(tabId);
}

function clearTab(tabId) {
  clearPending(tabId);
  clearFormOffer(tabId);
}

chrome.tabs.onRemoved.addListener(clearTab);
chrome.tabs.onReplaced.addListener((_addedTabId, removedTabId) => clearTab(removedTabId));
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.url || change.status === "loading" || change.discarded) clearFormOffer(tabId);
  const login = pending.get(tabId);
  if (login && (change.url || change.status === "complete") &&
      flowFromUrl(change.url || tab.url) !== login.flow) {
    clearPending(tabId);
  }
});

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || !message || typeof message !== "object") {
    return;
  }
  const popup = sender.url === chrome.runtime.getURL("popup.html");
  if (message.op === "check_tab") {
    if (!popup || sender.tab || Object.keys(message).length !== 1) {
      reply({code: "invalid"});
      return;
    }
    void checkActiveTab().then(reply, () => reply({code: "host_error"}));
    return true;
  }
  if (typeof message.op === "string" && message.op.startsWith("form_")) {
    void formMessage(message, sender, popup && !sender.tab).then(reply, () => reply({code: "form_missing"}));
    return true;
  }
  const tabId = sender.tab?.id;
  const topFrame = sender.frameId === 0 && Number.isInteger(tabId);
  const demo = topFrame && sender.url === AUTO_SITES.localhost;
  const source = topFrame && sender.url === AUTO_SITES.redirect;
  const flow = topFrame ? flowFromUrl(sender.url) : "";
  const httpsSite = flow ? "https_demo" : topFrame ? inlineDemoSite(sender.url) : "";
  if (source && message.op === "stage_https" &&
      validFlow(message.flow) && validDemoCredentials(message.username, message.password)) {
    clearPending(tabId);
    pending.set(tabId, {
      flow: message.flow, username: message.username, password: message.password,
      expires: Date.now() + NAVIGATION_TIMEOUT,
      timer: setTimeout(() => clearPending(tabId), NAVIGATION_TIMEOUT),
    });
    reply({code: "staged"});
    return;
  }
  if (flow && message.op === "take_https") {
    const login = pending.get(tabId);
    if (login?.flow !== flow || message.flow !== flow) {
      reply({code: "no_pending"});
      return;
    }
    clearPending(tabId);
    if (Date.now() < login.expires) {
      reply({code: "pending", username: login.username, password: login.password});
    } else {
      reply({code: "no_pending"});
    }
    return;
  }
  let request;
  if (message.op === "status" && (demo || httpsSite || popup)) {
    request = {op: "status"};
  } else {
    request = saveRequest(message, demo, httpsSite, popup);
  }
  if (!request) {
    reply({code: "invalid"});
    return;
  }
  sendNative(request, reply);
  return true;
});

async function checkActiveTab() {
  const options = {active: true, currentWindow: true};
  const [tab] = await chrome.tabs.query(options);
  const url = checkTabUrl(tab?.url);
  if (!url || !Number.isInteger(tab.id)) return {code: "check_invalid"};
  const response = await nativeRequest({op: "check_tab", url});
  const [current] = await chrome.tabs.query(options);
  return current?.id === tab.id && checkTabUrl(current.url) === url ? response : {code: "check_tab_changed"};
}

function nativeRequest(request) {
  return new Promise((resolve) => sendNative(request, resolve));
}

function sendNative(request, reply) {
  chrome.runtime.sendNativeMessage(HOST_NAME, request, (response) => {
    const error = chrome.runtime.lastError;
    if (error) {
      const missing = /native messaging host not found|specified native messaging host not found/i;
      reply({code: missing.test(error.message) ? "host_missing" : "host_error"});
    } else {
      reply(response ?? {code: "host_error"});
    }
  });
}

function saveRequest(message, localhost, httpsSite, popup) {
  const {op, target, username, password, confirmation, url} = message;
  if (!["save", "update"].includes(op) || !validFlow(target) ||
      (op === "update" && (typeof confirmation !== "string" || !/^[0-9a-f]{64}$/.test(confirmation)))) {
    return null;
  }
  const request = {op, target, username, password};
  if (popup && manualFields(message)) {
    request.site = "manual";
    request.url = url;
  } else if ((localhost || httpsSite) && validDemoCredentials(username, password)) {
    if (httpsSite) request.site = httpsSite;
  } else {
    return null;
  }
  if (op === "update") request.confirmation = confirmation;
  return request;
}
