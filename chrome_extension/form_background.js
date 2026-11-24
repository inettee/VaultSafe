"use strict";

const formOffers = new Map();

function sendToForm(offer, op) {
  return chrome.tabs.sendMessage(offer.tabId, {op, id: offer.id}, {documentId: offer.documentId})
    .catch(() => ({code: "form_missing"}));
}

function clearFormOffer(tabId, notify = true) {
  const offer = formOffers.get(tabId);
  if (!offer) return;
  formOffers.delete(tabId);
  clearTimeout(offer.timer);
  clearTimeout(offer.openTimer);
  void chrome.action.setBadgeText({tabId, text: ""}).catch(() => {});
  void sendToForm(offer, "form_release");
  if (notify) void chrome.runtime.sendMessage({op: "form_ended", id: offer.id}).catch(() => {});
}

async function activeFormTab(tabId, {requireWindowFocus = false} = {}) {
  if (!Number.isInteger(tabId)) return null;
  try {
    const tab = await chrome.tabs.get(tabId);
    const url = manualUrl(tab.url);
    if (!tab.active || !url.startsWith("https://")) return null;
    // The trusted toolbar popup can take focus away from its Chrome window.
    if (requireWindowFocus && !(await chrome.windows.get(tab.windowId)).focused) return null;
    return {...tab, url, documentUrl: tab.url};
  } catch {
    // The tab or browser window may have closed.
  }
  return null;
}

async function locateForm(tabId) {
  const tab = await activeFormTab(tabId);
  if (!tab) return {code: "form_tab_inactive"};
  const request = {op: "form_locate"};
  let located;
  try {
    located = await chrome.tabs.sendMessage(tabId, request, {frameId: 0});
  } catch {
    // A tab opened before the extension was loaded or reloaded has no listener yet.
    if (tab.url.startsWith(HTTPS_DEMO_ROOT) || tab.url.startsWith(DIALOG_DEMO_ROOT)) {
      return {code: "form_unavailable"};
    }
    try {
      const [top] = await chrome.scripting.executeScript({
        target: {tabId, frameIds: [0]},
        files: ["sites.js", "protocol.js", "form_login.js"],
      });
      const current = await activeFormTab(tabId);
      if (!top?.documentId || current?.documentUrl !== tab.documentUrl) {
        return {code: "form_stale"};
      }
      located = await chrome.tabs.sendMessage(tabId, request, {documentId: top.documentId});
    } catch {
      return {code: "form_unavailable"};
    }
  }
  if (located?.code === "pending") return formContext(tabId, "form_stale");
  const code = ["form_not_detected", "form_ambiguous"].includes(located?.code) ?
    located.code : "form_stale";
  return {code};
}

function offerCurrent(offer, tab) {
  return !!tab && formOffers.get(offer.tabId) === offer &&
    Date.now() < offer.expires && tab.url === offer.url;
}

async function formContext(tabId, missingCode = "form_missing") {
  const offer = formOffers.get(tabId);
  if (!offer || !offerCurrent(offer, await activeFormTab(tabId))) return {code: missingCode};
  const response = await nativeRequest({op: "status"});
  if (!offerCurrent(offer, await activeFormTab(tabId))) return {code: missingCode};
  if (response.code === "ready") {
    if (offer.target && offer.target !== response.target) {
      clearFormOffer(tabId, false);
      return {code: "target_changed"};
    }
    offer.target = response.target;
  }
  return {id: offer.id, site: new URL(offer.url).hostname, profile: response.profile,
    code: response.code, update: Boolean(offer.confirmation), automatic: offer.automatic};
}

async function saveForm(message) {
  const offer = formOffers.get(message.tabId);
  if (!offer || offer.id !== message.id || !offer.target) return {code: "form_missing"};
  if (offer.busy) return {code: "busy"};
  if (message.update !== Boolean(offer.confirmation)) {
    return {code: "review_update", update: Boolean(offer.confirmation)};
  }
  offer.busy = true;
  try {
    if (!offerCurrent(offer, await activeFormTab(offer.tabId))) return {code: "form_missing"};
    const status = await nativeRequest({op: "status"});
    if (status.code !== "ready") return {code: status.code};
    if (status.target !== offer.target) {
      clearFormOffer(offer.tabId, false);
      return {code: "target_changed"};
    }
    if (!offerCurrent(offer, await activeFormTab(offer.tabId))) return {code: "form_missing"};

    const result = await sendToForm(offer, "form_read");
    if (!offerCurrent(offer, await activeFormTab(offer.tabId))) return {code: "form_missing"};
    if (!result || result.code !== "form_data") return {code: result?.code || "form_missing"};
    const fields = {url: offer.url, username: result.username, password: result.password};
    if (!manualFields(fields)) return {code: "form_empty"};
    const request = {op: message.update ? "update" : "save", site: "manual", target: offer.target, ...fields};
    if (message.update) request.confirmation = offer.confirmation;
    const response = await nativeRequest(request);
    offer.confirmation = response.code === "confirm_update" ? response.confirmation : "";
    if (["saved", "duplicate", "target_changed"].includes(response.code) && formOffers.get(offer.tabId) === offer) {
      clearFormOffer(offer.tabId, false);
    }
    return {code: response.code, update: Boolean(offer.confirmation)};
  } finally {
    offer.busy = false;
  }
}

async function formMessage(message, sender, popup) {
  if (message.op === "form_offer" || message.op === "form_gone") {
    const tabId = sender.tab?.id;
    const url = manualUrl(sender.url);
    if (!url.startsWith("https://") || sender.frameId !== 0 ||
        !Number.isInteger(tabId) || !sender.documentId || !validFlow(message.id)) return {code: "invalid"};
    if (message.op === "form_gone") {
      const offer = formOffers.get(tabId);
      if (offer?.id === message.id && offer.documentId === sender.documentId) clearFormOffer(tabId);
      return {code: "cleared"};
    }
    if (sender.documentLifecycle !== "active") return {code: "invalid"};
    clearFormOffer(tabId);
    const offer = {id: message.id, tabId, url, documentId: sender.documentId,
      expires: Date.now() + FORM_OFFER_TIMEOUT, target: "", confirmation: "", busy: false,
      automatic: message.automatic === true};
    formOffers.set(tabId, offer);
    offer.timer = setTimeout(() => clearFormOffer(tabId), FORM_OFFER_TIMEOUT);
    if (offer.automatic) {
      void chrome.action.setBadgeText({tabId, text: "?"}).catch(() => {});
      offer.openTimer = setTimeout(async () => {
        const tab = await activeFormTab(tabId, {requireWindowFocus: true});
        if (offerCurrent(offer, tab)) await chrome.action.openPopup({windowId: tab.windowId}).catch(() => {});
      }, 200);
    }
    return {code: "pending"};
  }
  if (!popup) return {code: "invalid"};
  if (message.op === "form_context") return formContext(message.tabId);
  if (message.op === "form_find") return locateForm(message.tabId);
  if (message.op === "form_save") return saveForm(message);
  if (message.op === "form_skip") {
    if (formOffers.get(message.tabId)?.id === message.id) clearFormOffer(message.tabId, false);
    return {code: "cleared"};
  }
  return {code: "invalid"};
}
