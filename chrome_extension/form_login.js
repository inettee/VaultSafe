"use strict";

(() => {
  const LOGIN_REGION = '[role~="form"]';
  const ACTION_CONTROL = 'button, input[type="button"], input[type="submit"], input[type="image"], [role="button"]';
  const LOGIN_LABELS = new Set(["đăng nhập", "sign in", "signin", "log in", "login", "log on"]);
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

  function regionOf(element) {
    return element.form || element.closest(`form, ${LOGIN_REGION}`);
  }

  function loginFields(region, {manual = false, loose = false} = {}) {
    if (!region.isConnected) return null;
    const controls = region instanceof HTMLFormElement ? region.elements : region.querySelectorAll("input");
    const inputs = Array.from(controls).filter((element) => element instanceof HTMLInputElement &&
      regionOf(element) === (loose ? null : region) && !element.matches(":disabled") &&
      (!manual || visible(element)));
    const passwords = inputs.filter((input) => input.type === "password");
    if (passwords.length !== 1 || inputs.some(passwordOrCode)) return null;
    const [password] = passwords;
    if (!visible(password)) return null;
    const usernames = inputs.filter((input) => ["text", "email", "tel"].includes(input.type) && visible(input));
    const marked = usernames.filter((input) => input.autocomplete.split(/\s+/).includes("username"));
    if (loose) {
      const [input] = usernames;
      const identifier = input && (marked.includes(input) || ["email", "tel"].includes(input.type) ||
        /^(?:e-?mail|username|user_name|login|identifier|phone|email_or_phone)$/i.test(input.name || input.id));
      if (usernames.length !== 1 || !identifier) return null;
    }
    const choices = marked.length ? marked : usernames;
    return choices.length === 1 ? {username: choices[0], password} : null;
  }

  function actionLabel(control) {
    if (!control) return "";
    if (control instanceof HTMLInputElement && !["button", "submit", "image"].includes(control.type)) return "";
    const label = control.getAttribute("aria-label") ||
      (control instanceof HTMLInputElement ? control.value || control.alt : control.textContent);
    return label.trim().toLowerCase().replace(/\s+/g, " ");
  }

  function loginAction(control) {
    return !!control && !control.matches(':disabled, [aria-disabled="true"]') &&
      visible(control) && LOGIN_LABELS.has(actionLabel(control));
  }

  function looseLoginFields(region) {
    const fields = loginFields(region, {manual: true, loose: true});
    if (!fields) return null;
    const buttons = [...region.querySelectorAll(ACTION_CONTROL)].filter((control) =>
      !regionOf(control) && loginAction(control));
    return buttons.length === 1 ? fields : null;
  }

  function looseLoginRegion() {
    const passwords = [...document.querySelectorAll('input[type="password"]')]
      .filter((input) => !input.matches(":disabled") && visible(input));
    const [password] = passwords;
    if (passwords.length !== 1 || regionOf(password)) return null;
    for (let region = password.parentElement; region && region !== document.body; region = region.parentElement) {
      const fields = looseLoginFields(region);
      if (fields?.password === password) return {region, fields, loose: true};
    }
    return null;
  }

  function alternativeAction(control) {
    return /\b(?:google|apple|facebook|microsoft|passkey|oauth|sso|otp|sign ?up|register)\b|mã xác minh|mã xác thực|đăng ký|tạo tài khoản/i
      .test(actionLabel(control));
  }

  function regionAction(region) {
    return region instanceof HTMLFormElement ? region.action : location.href;
  }

  function sameOrigin(action) {
    try {
      return new URL(action, location.href).origin === location.origin;
    } catch {
      return false;
    }
  }

  function validAction(region, control) {
    return sameOrigin(regionAction(region)) &&
      (!control?.hasAttribute("formaction") || sameOrigin(control.formAction));
  }

  function validManualAction(region) {
    try {
      const page = new URL(location.href);
      const action = new URL(regionAction(region), page);
      const bareHostname = (url) => url.hostname.replace(/^www\./, "");
      return action.protocol === "https:" && page.protocol === "https:" && action.port === page.port &&
        !action.username && !action.password && bareHostname(action) === bareHostname(page);
    } catch {
      return false;
    }
  }

  function currentCandidate(id) {
    if (!candidate || candidate.id !== id || location.href !== candidate.href ||
        Date.now() >= candidate.expires || regionAction(candidate.region) !== candidate.action) return null;
    const fields = candidate.loose ? looseLoginFields(candidate.region) :
      loginFields(candidate.region, {manual: !candidate.automatic});
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

  async function offer(region, fields, automatic, loose = false) {
    release();
    const id = crypto.randomUUID().replaceAll("-", "");
    candidate = {id, region, ...fields, automatic, loose, action: regionAction(region), href: location.href,
      expires: Date.now() + FORM_OFFER_TIMEOUT};
    observer = new MutationObserver(() => {
      if (!currentCandidate(id)) release();
    });
    observer.observe(document, {childList: true, subtree: true, attributes: true,
      attributeFilter: ["action", "autocomplete", "form", "hidden", "style", "class", "type", "name",
        "role", "disabled"]});
    timer = setTimeout(release, FORM_OFFER_TIMEOUT);
    const result = await vaultRequest({op: "form_offer", id, automatic});
    if (result.code !== "pending" && candidate?.id === id) release(false);
    return result;
  }

  function markGesture(region, control, mayUseScript, scriptHandled) {
    const fields = mayUseScript && validAction(region, control) ? loginFields(region) : null;
    const marker = {region, href: location.href, action: regionAction(region)};
    gesture = marker;
    setTimeout(() => {
      if (gesture !== marker) return;
      gesture = null;
      // Some JavaScript forms handle the click or Enter without a submit event.
      if (!fields || !scriptHandled() || marker.href !== location.href || marker.action !== regionAction(region) ||
          !validAction(region, control)) return;
      const current = loginFields(region);
      if (current?.password === fields.password && current.username === fields.username) {
        void offer(region, current, true);
      }
    }, 0);
  }

  window.addEventListener("click", (event) => {
    if (!event.isTrusted || event.button !== 0) return;
    const control = event.target.closest?.(ACTION_CONTROL);
    if (!control || alternativeAction(control)) return;
    const region = regionOf(control);
    const nativeSubmit = !!control.form && ["submit", "image"].includes(control.type);
    const namedLogin = loginAction(control);
    if (region && (nativeSubmit || namedLogin)) {
      markGesture(region, control, namedLogin, () => !nativeSubmit || event.defaultPrevented);
    }
  }, true);

  window.addEventListener("keydown", (event) => {
    if (!event.isTrusted || event.repeat || event.isComposing || event.key !== "Enter") return;
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const region = regionOf(input);
    if (!region) return;
    const fields = loginFields(region);
    if (!fields || (input !== fields.username && input !== fields.password)) return;
    const controls = new Set(region.querySelectorAll(ACTION_CONTROL));
    if (region instanceof HTMLFormElement) {
      for (const control of region.elements) {
        if (control.matches(ACTION_CONTROL)) controls.add(control);
      }
    }
    const loginButtons = [...controls].filter((control) =>
      regionOf(control) === region && loginAction(control));
    const [control] = loginButtons;
    if (input.form || loginButtons.length === 1) {
      markGesture(region, control, loginButtons.length === 1, () => event.defaultPrevented);
    }
  }, true);

  window.addEventListener("submit", (event) => {
    const form = event.target;
    if (!event.isTrusted || gesture?.region !== form) return;
    gesture = null;
    const fields = loginFields(form);
    if (fields && !alternativeAction(event.submitter) && validAction(form, event.submitter)) {
      void offer(form, fields, true);
    }
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
      const candidates = [...document.forms, ...document.querySelectorAll(LOGIN_REGION)];
      const regions = [...new Set(candidates)].filter(validManualAction)
        .map((region) => ({region, fields: loginFields(region, {manual: true})})).filter(({fields}) => fields);
      const unmarked = looseLoginRegion();
      if (unmarked) regions.push(unmarked);
      const focused = document.activeElement;
      const focusedRegion = focused && regionOf(focused);
      const selected = regions.find(({region, fields}) =>
        focusedRegion === region || focused === fields.username || focused === fields.password) ||
        (regions.length === 1 && !(focused instanceof HTMLInputElement) && !focusedRegion ? regions[0] : null);
      if (!selected) {
        reply({code: regions.length ? "form_ambiguous" : "form_not_detected"});
        return;
      }
      void offer(selected.region, selected.fields, false, selected.loose).then(reply);
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
