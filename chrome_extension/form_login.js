"use strict";

(() => {
  let candidate;
  let gesture;
  let observer;
  let timer;

  function visible(input) {
    return input.getClientRects().length > 0 && getComputedStyle(input).visibility === "visible";
  }

  function passwordOrCode(input) {
    const autocomplete = input.autocomplete.split(/\s+/);
    return autocomplete.includes("new-password") || autocomplete.includes("one-time-code") ||
      /(?:^|[^a-z])(otp|pin|passcode|verification|captcha)(?:$|[^a-z])/i.test(input.name);
  }

  function loginFields(form) {
    if (!(form instanceof HTMLFormElement) || !form.isConnected) return null;
    const inputs = Array.from(form.elements).filter((element) => element instanceof HTMLInputElement);
    const passwords = inputs.filter((input) => input.type === "password");
    if (passwords.length !== 1 || inputs.some(passwordOrCode)) return null;
    const [password] = passwords;
    if (!visible(password)) return null;
    const usernames = inputs.filter((input) => ["text", "email", "tel"].includes(input.type) && visible(input));
    const marked = usernames.filter((input) => input.autocomplete.split(/\s+/).includes("username"));
    const choices = marked.length ? marked : usernames;
    return choices.length === 1 ? {username: choices[0], password} : null;
  }

  function sameOrigin(action) {
    try {
      return new URL(action, location.href).origin === location.origin;
    } catch {
      return false;
    }
  }

  function currentCandidate(id) {
    if (!candidate || candidate.id !== id || location.href !== candidate.href ||
        Date.now() >= candidate.expires || candidate.form.action !== candidate.action) return null;
    const fields = loginFields(candidate.form);
    return fields && fields.username === candidate.username && fields.password === candidate.password
      ? candidate : null;
  }

  function release(notify = true) {
    if (!candidate) return;
    const {id} = candidate;
    candidate = null;
    observer.disconnect();
    clearTimeout(timer);
    if (notify) void vaultRequest({op: "form_gone", id});
  }

  async function offer(form, fields, automatic) {
    release();
    const id = crypto.randomUUID().replaceAll("-", "");
    candidate = {id, form, ...fields, action: form.action, href: location.href,
      expires: Date.now() + FORM_OFFER_TIMEOUT};
    observer = new MutationObserver(() => {
      if (!currentCandidate(id)) release();
    });
    observer.observe(document, {childList: true, subtree: true, attributes: true,
      attributeFilter: ["action", "autocomplete", "form", "hidden", "style", "class", "type", "name"]});
    timer = setTimeout(release, FORM_OFFER_TIMEOUT);
    const result = await vaultRequest({op: "form_offer", id, automatic});
    if (result.code !== "pending" && candidate?.id === id) release(false);
    return result;
  }

  function markGesture(form) {
    const marker = {form};
    gesture = marker;
    setTimeout(() => {
      if (gesture === marker) gesture = null;
    }, 0);
  }

  window.addEventListener("click", (event) => {
    if (!event.isTrusted) return;
    const submitter = event.target.closest?.("button, input");
    if (submitter?.form && ["submit", "image"].includes(submitter.type)) {
      markGesture(submitter.form);
    }
  }, true);
  window.addEventListener("keydown", (event) => {
    if (event.isTrusted && !event.repeat && !event.isComposing && event.key === "Enter" && event.target.form) {
      markGesture(event.target.form);
    }
  }, true);
  window.addEventListener("submit", (event) => {
    const form = event.target;
    if (!event.isTrusted || gesture?.form !== form) return;
    gesture = null;
    const fields = loginFields(form);
    const submitter = event.submitter;
    const action = submitter?.hasAttribute("formaction") ? submitter.formAction : form.action;
    if (fields && sameOrigin(action) && sameOrigin(form.action)) void offer(form, fields, true);
  }, true);
  window.addEventListener("input", (event) => {
    if (event.target === candidate?.username || event.target === candidate?.password) release();
  }, true);
  window.addEventListener("pagehide", () => release());
  window.addEventListener("popstate", () => release());
  window.addEventListener("hashchange", () => release());

  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id || sender.tab || !message) return;
    if (message.op === "form_locate") {
      const forms = Array.from(document.forms).filter((form) => sameOrigin(form.action))
        .map((form) => ({form, fields: loginFields(form)})).filter(({fields}) => fields);
      const selected = forms.find(({form}) => document.activeElement?.form === form) ||
        (forms.length === 1 ? forms[0] : null);
      if (!selected) {
        reply({code: "form_missing"});
        return;
      }
      void offer(selected.form, selected.fields, false).then(reply);
      return true;
    }
    if (message.op === "form_release" && candidate?.id === message.id) release(false);
    if (message.op !== "form_read") return;
    const original = currentCandidate(message.id);
    if (!original) {
      reply({code: "form_missing"});
      return;
    }
    // The worker requests these values only after a trusted click in the Chrome popup.
    const username = original.username.value.trim();
    const password = original.password.value;
    reply(manualFields({url: manualUrl(original.href), username, password})
      ? {code: "form_data", username, password}
      : {code: "form_empty"});
  });
})();
