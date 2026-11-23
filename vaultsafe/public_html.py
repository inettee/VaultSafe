"""Tải HTML công khai bằng GET, với đích DNS được kiểm tra trước khi kết nối."""

from dataclasses import dataclass, field
from enum import Enum
import http.client
import ipaddress
from queue import Empty, Queue
import socket
from socket import socket as Socket
import ssl
from threading import BoundedSemaphore, Thread, Timer
from time import monotonic
from urllib.parse import urljoin

from .link_checker import Link, parse_link, public_address


MAX_HTML_BYTES = 512 * 1024
MAX_REDIRECTS = 3
TOTAL_TIMEOUT = 10.0
IDLE_TIMEOUT = 3.0
REDIRECT_CODES = {301, 302, 303, 307, 308}
_DNS_SLOTS = BoundedSemaphore(2)


class FetchStatus(Enum):
    OK = "Đã đọc HTML công khai."
    SENSITIVE = "Chỉ phân tích cục bộ vì URL có thể chứa thông tin nhạy cảm."
    NON_PUBLIC = "Không tải HTML vì đích nội bộ hoặc không có địa chỉ IP công khai hợp lệ."
    DNS = "Không phân giải được tên máy chủ. Kiểm tra DNS hoặc kết nối mạng."
    NETWORK = "Không kết nối được tới máy chủ. Kiểm tra kết nối mạng."
    TIMEOUT = "Đã quá thời gian chờ khi tải trang."
    TLS = "Không tải trang do lỗi TLS. VaultSafe giữ kiểm tra chứng chỉ."
    NON_HTML = "Máy chủ không trả HTML công khai có thể đọc được."
    TOO_LARGE = "HTML vượt giới hạn 512 KiB."
    REDIRECT = "Không tiếp tục vì chuyển hướng không hợp lệ hoặc vượt giới hạn."
    HTTP = "Máy chủ trả lỗi hoặc phản hồi HTTP không hợp lệ."


@dataclass(frozen=True, slots=True)
class FetchResult:
    status: FetchStatus
    redirects: tuple[Link, ...]
    body: bytes | None = field(default=None, repr=False)
    encoding: str | None = None


class _FetchError(Exception):
    def __init__(self, status):
        super().__init__(status.value)
        self.status = status


def _remaining(deadline):
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise _FetchError(FetchStatus.TIMEOUT)
    return seconds


def _lookup(hostname, port, deadline):
    if not _DNS_SLOTS.acquire(blocking=False):
        raise _FetchError(FetchStatus.DNS)
    result = Queue(maxsize=1)

    def resolve():
        try:
            # The trailing dot makes the lookup absolute, without the OS search suffix.
            result.put(socket.getaddrinfo(hostname + ".", port, type=socket.SOCK_STREAM))
        except OSError:
            result.put([])
        finally:
            _DNS_SLOTS.release()

    worker = Thread(target=resolve, daemon=True, name="vaultsafe-link-dns")
    try:
        worker.start()
    except RuntimeError:
        _DNS_SLOTS.release()
        raise _FetchError(FetchStatus.DNS) from None
    try:
        return result.get(timeout=_remaining(deadline))
    except Empty:
        raise _FetchError(FetchStatus.TIMEOUT) from None


def _public_addresses(link, deadline):
    if link.local_host:
        raise _FetchError(FetchStatus.NON_PUBLIC)
    if link.address is not None:
        return (link.address,)
    records = _lookup(link.hostname, link.port, deadline)
    addresses = {}
    for family, _, _, _, sockaddr in records:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        try:
            raw_address = sockaddr[0]
            address = ipaddress.ip_address(raw_address)
            scoped = "%" in raw_address or (family == socket.AF_INET6 and sockaddr[3])
            if scoped or not public_address(address):
                raise ValueError
        except (IndexError, ValueError):
            raise _FetchError(FetchStatus.NON_PUBLIC) from None
        addresses[address] = None
    if not addresses:
        raise _FetchError(FetchStatus.DNS)
    # Prefer IPv4 when both families are available. All fallback addresses are verified above.
    return tuple(sorted(addresses, key=lambda address: address.version))


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, link, addresses, deadline):
        self.default_port = 443 if link.scheme == "https" else 80
        super().__init__(link.hostname, link.port, timeout=IDLE_TIMEOUT)
        self._addresses = addresses
        self._deadline = deadline
        self._tls = ssl.create_default_context() if link.scheme == "https" else None

    def connect(self):
        last_error = None
        for address in self._addresses:
            seconds = min(IDLE_TIMEOUT, _remaining(self._deadline))
            family = socket.AF_INET if address.version == 4 else socket.AF_INET6
            wire = Socket(family, socket.SOCK_STREAM)
            wire.settimeout(seconds)
            endpoint = (str(address), self.port) if address.version == 4 else (str(address), self.port, 0, 0)
            try:
                wire.connect(endpoint)
            except OSError as error:
                wire.close()
                last_error = error
                continue
            try:
                if self._tls:
                    wire.settimeout(min(IDLE_TIMEOUT, _remaining(self._deadline)))
                    wire = self._tls.wrap_socket(wire, server_hostname=self.host)
            except (OSError, _FetchError):
                wire.close()
                raise
            self.sock = wire
            return
        raise last_error or _FetchError(FetchStatus.DNS)


def _interrupt(wire):
    try:
        wire.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _read_html(response, deadline):
    mime = response.headers.get_content_type()
    if mime not in {"text/html", "application/xhtml+xml"}:
        raise _FetchError(FetchStatus.NON_HTML)
    if response.getheader("Content-Encoding", "identity").strip().lower() != "identity":
        raise _FetchError(FetchStatus.NON_HTML)
    length = response.getheader("Content-Length")
    if length is not None:
        if not length.isascii() or not length.isdigit() or len(length) > 20:
            raise _FetchError(FetchStatus.HTTP)
        if int(length) > MAX_HTML_BYTES:
            raise _FetchError(FetchStatus.TOO_LARGE)
    body = bytearray()
    while True:
        _remaining(deadline)
        part = response.read1(min(16384, MAX_HTML_BYTES + 1 - len(body)))
        if not part:
            break
        body.extend(part)
        if len(body) > MAX_HTML_BYTES:
            raise _FetchError(FetchStatus.TOO_LARGE)
    _remaining(deadline)
    if not body:
        raise _FetchError(FetchStatus.NON_HTML)
    if length is not None and not response.chunked and len(body) != int(length):
        raise _FetchError(FetchStatus.HTTP)
    return bytes(body), response.headers.get_content_charset()


def _get_page(link, addresses, deadline):
    connection = _PinnedConnection(link, addresses, deadline)
    watchdog = None
    try:
        connection.connect()
        # Keep the wire reference even if http.client detaches it on Connection: close.
        watchdog = Timer(_remaining(deadline), _interrupt, (connection.sock,))
        watchdog.daemon = True
        watchdog.start()
        connection.request("GET", link.target, headers={
            "Accept": "text/html, application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
            "User-Agent": "VaultSafe-Link-Checker/1.0",
        })
        with connection.getresponse() as response:
            if response.status in REDIRECT_CODES:
                locations = response.headers.get_all("Location", [])
                if len(locations) != 1 or not locations[0].strip():
                    raise _FetchError(FetchStatus.REDIRECT)
                return locations[0].strip(), None, None
            if response.status != 200:
                raise _FetchError(FetchStatus.HTTP)
            body, encoding = _read_html(response, deadline)
            return None, body, encoding
    finally:
        if watchdog is not None:
            watchdog.cancel()
        connection.close()


def _redirect(source, location):
    try:
        if any(character.isspace() for character in location):
            raise ValueError
        return parse_link(urljoin(source.url, location))
    except ValueError:
        raise _FetchError(FetchStatus.REDIRECT) from None


def fetch_html(source, *, timeout=TOTAL_TIMEOUT):
    """Do not load content for sensitive URLs or follow unverified redirects."""
    deadline = monotonic() + timeout
    link = source
    redirects = []
    try:
        while True:
            if link.sensitive:
                raise _FetchError(FetchStatus.SENSITIVE)
            addresses = _public_addresses(link, deadline)
            location, body, encoding = _get_page(link, addresses, deadline)
            _remaining(deadline)
            if location is None:
                return FetchResult(FetchStatus.OK, tuple(redirects), body, encoding)
            if len(redirects) == MAX_REDIRECTS:
                raise _FetchError(FetchStatus.REDIRECT)
            link = _redirect(link, location)
            redirects.append(link)
    except _FetchError as error:
        status = error.status
    except ssl.SSLError:
        status = FetchStatus.TIMEOUT if monotonic() >= deadline else FetchStatus.TLS
    except TimeoutError:
        status = FetchStatus.TIMEOUT
    except http.client.HTTPException:
        status = FetchStatus.TIMEOUT if monotonic() >= deadline else FetchStatus.HTTP
    except OSError:
        status = FetchStatus.TIMEOUT if monotonic() >= deadline else FetchStatus.NETWORK
    return FetchResult(status, tuple(redirects))
