"""Handle Chrome requests through the open desktop session."""

from concurrent.futures import Future, TimeoutError
import hashlib
import hmac
from queue import Empty, Full, Queue
import secrets
from urllib.parse import urlsplit

from .browser_protocol import SITES, encode_message, manual_hostname, valid_request
from .errors import ConflictError, SessionClosedError, VaultError
from .link_checker import InvalidLink, Risk, inspect_url, parse_link, resembles_domains


def _origin(url):
    try:
        parsed = urlsplit(url)
        if parsed.username is None and parsed.hostname:
            port = parsed.port if parsed.port is not None else {"https": 443, "http": 80}.get(parsed.scheme)
            return parsed.scheme, parsed.hostname, port
    except ValueError:
        pass
    return None


def _check_tab(profile, url):
    try:
        report = inspect_url(url)
    except InvalidLink:
        return {"code": "check_invalid"}

    source = report.source
    match, similar_domain = "none", None
    for account in profile.accounts.values():
        if account.kind != "login" or account.trashed or not account.url:
            continue
        try:
            saved = parse_link(account.url)
        except InvalidLink:
            continue
        if source.hostname == saved.hostname:
            match = "hostname"
        elif match != "hostname" and saved.registered_domain is not None and source.site == saved.site:
            match = "domain"
        if (similar_domain is None and saved.registered_domain is not None
                and source.site != saved.site and resembles_domains(source, (saved.site,))):
            similar_domain = saved.site

    risk = max(report.risk, Risk.REVIEW if similar_domain else Risk.NONE)
    return {
        "code": "tab_checked", "profile": profile.name,
        "hostname": source.hostname, "domain": source.registered_domain,
        "risk": risk.label, "match": match, "similar_domain": similar_domain,
        "findings": [item.reason for item in report.findings],
    }


class BrowserRequests:
    def __init__(self, service, on_saved):
        self._service = service
        self._on_saved = on_saved
        self._session = None
        self._target = ""
        self._confirmation_key = secrets.token_bytes(32)

    def set_session(self, session):
        self._session = session
        self._target = secrets.token_hex(16) if session is not None else ""

    def handle(self, request):
        if not valid_request(request):
            return {"code": "invalid"}
        session = self._session
        if session is None:
            return {"code": "locked"}
        try:
            profile, revision = session.versioned_profile()
            target = {"target": self._target, "profile": profile.name}
            if request["op"] == "status":
                return {"code": "ready", **target}
            if request["op"] == "check_tab":
                return _check_tab(profile, request["url"])
            if request["target"] != self._target:
                return {"code": "target_changed", **target}
            return self._save(session, profile, revision, request)
        except SessionClosedError:
            return {"code": "locked"}
        except ConflictError:
            return {"code": "conflict"}
        except VaultError:
            return {"code": "write_error"}

    def _save(self, session, profile, revision, request):
        username, password = request["username"], request["password"]
        site = request.get("site", "localhost")
        if site == "manual":
            login_url = request["url"]
            service_name = manual_hostname(login_url)
        else:
            service_name, login_url = SITES[site]
        origin = _origin(login_url)
        matches = [account for account in profile.accounts.values()
                   if account.kind == "login" and not account.trashed
                   and account.username == username and _origin(account.url) == origin]
        if any(account.password == password for account in matches):
            return {"code": "duplicate"}
        if len(matches) > 1:
            return {"code": "ambiguous"}
        previous = matches[0] if matches else None
        if previous:
            payload = encode_message([self._target, revision, site, login_url, previous.id, username, password])
            confirmation = hmac.new(self._confirmation_key, payload, hashlib.sha256).hexdigest()
            if request["op"] == "save":
                return {"code": "confirm_update", "confirmation": confirmation}
            if not hmac.compare_digest(request["confirmation"], confirmation):
                return {"code": "review_update"}
        elif request["op"] == "update":
            return {"code": "review_update"}

        values = dict(kind="login", username=username, password=password,
                      service=previous.service if previous else service_name,
                      url=previous.url if previous else login_url,
                      notes=previous.notes if previous else "",
                      folder_id=previous.folder_id if previous else "")
        account = self._service.save_account(
            session, previous.id if previous else None, values, expected_revision=revision,
        )
        self._on_saved(account.id)
        return {"code": "saved"}


class BrowserBridge(BrowserRequests):
    def __init__(self, app, on_saved):
        from .browser_ipc import PipeServer

        super().__init__(app.service, lambda account_id: app.after_idle(on_saved, account_id))
        self._app = app
        self._pending = Queue(maxsize=1)
        self._server = PipeServer(self._enqueue)
        self._timer = app.after(50, self._poll)

    def _enqueue(self, request):
        result = Future()
        try:
            self._pending.put_nowait((request, result))
            return result.result(timeout=4)
        except Full:
            return {"code": "busy"}
        except TimeoutError:
            result.cancel()
            return {"code": "busy"}

    def _poll(self):
        try:
            request, result = self._pending.get_nowait()
        except Empty:
            pass
        else:
            if result.set_running_or_notify_cancel():
                try:
                    response = self.handle(request)
                except Exception:
                    response = {"code": "write_error"}
                result.set_result(response)
        self._timer = self._app.after(50, self._poll)

    def close(self):
        self._app.after_cancel(self._timer)
        self.set_session(None)
        try:
            _, result = self._pending.get_nowait()
        except Empty:
            pass
        else:
            if result.set_running_or_notify_cancel():
                result.set_result({"code": "app_closed"})
        self._server.close()
