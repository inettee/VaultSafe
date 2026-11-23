"use strict";

// A destination belongs to one offer. Losing the connection never changes it.
function newSaveSession() {
  let target = "";
  let confirmation = "";
  return {
    async status() {
      if (target === null) return {code: "target_changed"};
      const response = await vaultRequest({op: "status"});
      if (response.code === "ready") {
        if (target && target !== response.target) {
          target = null;
          confirmation = "";
          return {code: "target_changed"};
        }
        target = response.target;
      }
      return response;
    },
    async save(fields) {
      if (!target) return {code: target === null ? "target_changed" : "locked"};
      const request = confirmation
        ? {...fields, op: "update", target, confirmation}
        : {...fields, op: "save", target};
      const response = await vaultRequest(request);
      if (response.code === "target_changed") target = null;
      confirmation = response.code === "confirm_update" ? response.confirmation : "";
      return response;
    },
    clearConfirmation() {
      confirmation = "";
    }
  };
}

function connectionUnavailable(code) {
  return ["locked", "app_closed", "host_missing", "host_error"].includes(code);
}
