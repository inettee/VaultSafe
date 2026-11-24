"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function fixture({hasListener = false, moved = false, denied = false, windowFocused = true,
  locatedCode = ""} = {}) {
  const origin = "https://form-fixture.test";
  const id = "a".repeat(32);
  const tab = {id: 7, active: true, windowId: 1, url: origin + "/login"};
  const calls = [];
  const timers = [];
  const sender = {tab, url: tab.url, frameId: 0, documentId: "login-doc", documentLifecycle: "active"};
  const context = vm.createContext({
    URL,
    setTimeout: (callback) => timers.push(callback),
    clearTimeout: () => {},
    chrome: {
      tabs: {
        get: async () => tab,
        sendMessage: async (_tabId, {op}, scope) => {
          calls.push([op, scope.documentId ?? scope.frameId]);
          if (op === "form_read") return {code: "form_data", username: "demo@example.test", password: "Fixture only!"};
          if (op === "form_release") return undefined;
          if (!hasListener && !scope.documentId) throw new Error("Receiving end does not exist");
          if (locatedCode) return {code: locatedCode};
          return request({op: "form_offer", id}, sender, false);
        },
      },
      windows: {get: async () => ({focused: windowFocused})},
      action: {
        setBadgeText: async () => {},
        openPopup: async () => calls.push(["openPopup"]),
      },
      scripting: {
        executeScript: async ({target, files}) => {
          calls.push(["inject", target.frameIds[0], files.at(-1)]);
          if (denied) throw new Error("Permission denied");
          if (moved) tab.url += "?redirect=1";
          return [{documentId: "login-doc"}];
        },
      },
    },
    nativeRequest: async ({op}) => {
      calls.push([op]);
      if (op === "save") return {code: "saved"};
      return {code: "ready", profile: "Fixture Vault", target: "b".repeat(32)};
    },
  });
  for (const name of ["sites.js", "protocol.js", "form_background.js"]) {
    const source = fs.readFileSync(path.join(__dirname, "..", "chrome_extension", name), "utf8");
    vm.runInContext(source, context, {filename: name});
  }
  const request = vm.runInContext("formMessage", context);
  return {
    calls,
    tab,
    find: (popup = true) => request({op: "form_find", tabId: tab.id}, {}, popup),
    save: () => request({op: "form_save", tabId: tab.id, id, update: false}, {}, true),
    offerAutomatically: async () => {
      await request({op: "form_offer", id, automatic: true}, sender, false);
      await timers.at(-1)();
    },
  };
}

test("manual lookup reconnects to the top document without reading the form", async () => {
  const {find, calls} = fixture();
  const result = await find();
  assert.equal(result.code, "ready");
  assert.equal(result.site, "form-fixture.test");
  assert.equal(result.automatic, false);
  assert.deepEqual(calls, [
    ["form_locate", 0], ["inject", 0, "form_login.js"], ["form_locate", "login-doc"], ["status"],
  ]);
});

test("an existing listener does not get injected a second time", async () => {
  const {find, calls} = fixture({hasListener: true});
  assert.equal((await find()).code, "ready");
  assert.deepEqual(calls, [["form_locate", 0], ["status"]]);
});

test("navigation during reconnection discards the lookup", async () => {
  const {find, calls} = fixture({moved: true});
  assert.equal((await find()).code, "form_stale");
  assert.deepEqual(calls, [["form_locate", 0], ["inject", 0, "form_login.js"]]);
});

test("toolbar focus does not block locating or saving from the active tab", async () => {
  const {find, save, calls} = fixture({hasListener: true, windowFocused: false});
  assert.equal((await find()).code, "ready");
  assert.deepEqual(calls, [["form_locate", 0], ["status"]]);
  assert.equal((await save()).code, "saved");
  assert.deepEqual(calls.slice(2), [["status"], ["form_read", "login-doc"], ["save"], ["form_release", "login-doc"]]);
});

test("an inactive tab cannot be found or read from the toolbar", async () => {
  const {find, save, tab, calls} = fixture({hasListener: true, windowFocused: false});
  assert.equal((await find()).code, "ready");
  tab.active = false;
  assert.equal((await save()).code, "form_missing");
  assert.equal((await find()).code, "form_tab_inactive");
  assert.deepEqual(calls, [["form_locate", 0], ["status"]]);
});

test("automatic popup still requires focus on the Chrome window", async () => {
  const background = fixture({windowFocused: false});
  const foreground = fixture({windowFocused: true});
  await background.offerAutomatically();
  await foreground.offerAutomatically();
  assert.deepEqual(background.calls, []);
  assert.deepEqual(foreground.calls, [["openPopup"]]);
});

test("the popup can distinguish an unmatched form from an ambiguous form", async () => {
  for (const code of ["form_not_detected", "form_ambiguous"]) {
    const {find, calls} = fixture({hasListener: true, locatedCode: code});
    assert.equal((await find()).code, code);
    assert.deepEqual(calls, [["form_locate", 0]]);
  }
});

test("a denied injection reports tab access, and a content script cannot request injection", async () => {
  const {find, calls} = fixture({denied: true});
  assert.equal((await find(false)).code, "invalid");
  assert.deepEqual(calls, []);
  assert.equal((await find()).code, "form_unavailable");
  assert.deepEqual(calls, [["form_locate", 0], ["inject", 0, "form_login.js"]]);
});
