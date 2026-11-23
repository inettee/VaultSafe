"""Phân tích URL và bằng chứng tĩnh. Module này không truy cập mạng."""

from dataclasses import dataclass, field
from enum import IntEnum
import ipaddress
import re
import unicodedata
from urllib.parse import parse_qsl, quote, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
import idna
import tldextract


SPLIT_DOMAIN = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True,
    extra_suffixes=("example", "test", "invalid"),
)
URL_MAX_LENGTH = 8192
BRAND_DOMAINS = {
    "Facebook": ("facebook.com",),
    "Steam": ("steampowered.com", "steamcommunity.com"),
}
NO_FORM_DATA = "Chưa đủ dữ liệu để đánh giá form"
PENDING_LOAD = "Chưa tải HTML hoặc kiểm tra chuyển hướng."
PRIVATE_SUFFIXES = {"localhost", "local", "internal", "lan", "test", "example", "invalid", "onion"}
IPV4_NONPUBLIC = tuple(ipaddress.ip_network(cidr) for cidr in ("192.0.0.0/24", "192.88.99.0/24"))
IPV6_UNICAST = ipaddress.ip_network("2000::/3")
IPV6_NONPUBLIC = tuple(ipaddress.ip_network(cidr) for cidr in ("2001::/23", "2002::/16", "3fff::/20"))
NUMBER_LABEL = r"(?:0x[0-9a-f]+|[0-9]+)"
SENSITIVE_KEYS = {
    "access", "accesskey", "accesstoken", "activationcode", "activationtoken",
    "auth", "authcode", "authorization", "authtoken",
    "code", "credential", "emailtoken", "idtoken", "invite", "invitecode", "invitetoken",
    "invitation", "invitationcode", "invitationtoken", "jwt", "key", "nonce", "otp",
    "password", "passwordresettoken", "refreshtoken", "reset",
    "resetcode", "resetkey", "resetpasswordtoken", "resettoken", "secret",
    "session", "sessionid", "sessionkey", "sessiontoken",
    "jsessionid", "phpsessid", "sid", "sig", "signature", "state", "ticket", "token",
    "verificationcode", "verifytoken",
}
SENSITIVE_PATH = re.compile(
    r"(?:^|[/;_.-])(?:reset(?:[-_]?password)?|password[-_]?reset|forgot[-_]?password"
    r"|recover(?:y)?|invite|invitation|magic[-_]?link|verify[-_]?(?:email|account)"
    r"|session(?:[-_]?(?:id|key|token))?|jsessionid|phpsessid|token)(?:$|[=/;_.-])", re.IGNORECASE,
)
OPAQUE = re.compile(r"[a-zA-Z0-9_+\-/=]{24,}\Z")
REWARD_PHRASES = (
    "nhận quà", "nhận skin", "nhận vật phẩm", "nhận thưởng", "tặng vật phẩm", "quà miễn phí",
    "đăng nhập để nhận thưởng", "đăng nhập để nhận quà", "claim your reward", "free skins", "free rewards",
)
PRESSURE_PHRASES = (
    "nhanh tay", "chỉ còn", "sắp hết hạn", "cơ hội cuối", "trong vòng", "claim now", "limited time",
)
STATIC_LIMITS = (
    "Chưa kiểm tra JavaScript, dữ liệu gửi thực tế hoặc quyền sở hữu website.",
)


class Risk(IntEnum):
    NONE = 0
    REVIEW = 1
    HIGH = 2

    @property
    def label(self):
        return ("Chưa phát hiện dấu hiệu rủi ro", "Cần kiểm tra thêm", "Rủi ro cao")[self]


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    reason: str
    evidence: tuple[str, ...] = ()
    risk: Risk = Risk.REVIEW


@dataclass(frozen=True, slots=True)
class SavedSite:
    name: str
    url: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Link:
    scheme: str
    hostname: str
    registered_domain: str | None
    port: int
    target: str = field(repr=False)
    address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    has_userinfo: bool = False
    sensitive: bool = False

    @property
    def site(self):
        return self.registered_domain or self.hostname

    @property
    def url(self):
        host = f"[{self.hostname}]" if isinstance(self.address, ipaddress.IPv6Address) else self.hostname
        port = "" if self.port == (443 if self.scheme == "https" else 80) else f":{self.port}"
        return f"{self.scheme}://{host}{port}{self.target}"

    @property
    def local_host(self):
        if self.address is not None:
            return not public_address(self.address)
        return ("." not in self.hostname or self.hostname.split(".")[-1] in PRIVATE_SUFFIXES
                or self.hostname == "home.arpa" or self.hostname.endswith(".home.arpa"))


@dataclass(frozen=True, slots=True)
class Inspection:
    source: Link
    findings: tuple[Finding, ...]
    unchecked: tuple[str, ...]
    redirects: tuple[Link, ...] = ()
    title: str = ""

    @property
    def risk(self):
        return max((finding.risk for finding in self.findings), default=Risk.NONE)

    @property
    def destination(self):
        return self.redirects[-1] if self.redirects else self.source


class InvalidLink(ValueError):
    pass


def public_address(address):
    if not address.is_global or address.is_multicast or address.is_reserved or address.is_link_local:
        return False
    if address.version == 6:
        return address in IPV6_UNICAST and not any(address in net for net in IPV6_NONPUBLIC)
    return not any(address in net for net in IPV4_NONPUBLIC)


def _opaque(value):
    return (bool(OPAQUE.fullmatch(value))
            and (any(c.isdigit() for c in value) or any(c.isupper() for c in value)))


def _sensitive_url(path, query, fragment):
    path, query, fragment = (unquote(unquote(part)) for part in (path, query, fragment))
    if any(SENSITIVE_PATH.search(part) for part in (path, fragment)):
        return True
    if any(_opaque(part) for part in path.split("/") + [fragment.removeprefix("/")]):
        return True
    payload = f"{query}&{fragment.replace('?', '&')}"
    try:
        params = parse_qsl(payload, keep_blank_values=True, max_num_fields=128)
    except ValueError:
        return True
    for key, value in params:
        normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
        if (normalized in SENSITIVE_KEYS or _opaque(value)
                or re.search(r"(?:token|password|session|invite)(?:=|%3d)", value, re.I)):
            return True
    return bool(re.search(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.", path + query + fragment))


def parse_link(text):
    url = text.strip()
    if not url or len(url) > URL_MAX_LENGTH:
        raise InvalidLink("Dán một URL HTTP hoặc HTTPS hợp lệ, tối đa 8192 ký tự.")
    if ("\\" in url or re.search(r"%(?![0-9a-fA-F]{2})", url)
            or any(char.isspace() or unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in url)):
        raise InvalidLink("URL chứa ký tự hoặc mã phần trăm không hợp lệ.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise InvalidLink("Tên máy chủ hoặc cổng trong URL không hợp lệ.") from None
    if parts.scheme not in ("http", "https") or not host:
        raise InvalidLink("Cần URL đầy đủ bắt đầu bằng http:// hoặc https://.")
    authority = parts.netloc.rsplit("@", 1)[-1]
    bracketed = "[" in authority or "]" in authority
    if (port == 0 or "%" in host or authority.endswith(":")
            or (bracketed and not re.fullmatch(r"\[[^\[\]]+\](?::[0-9]+)?", authority))):
        raise InvalidLink("Tên máy chủ hoặc cổng trong URL không hợp lệ.")

    host = host.removesuffix(".")
    try:
        address = ipaddress.ip_address(host)
        host = str(address)
        registered = None
    except ValueError:
        address = None
        try:
            host = idna.encode(host, uts46=True, std3_rules=True).decode("ascii").removesuffix(".")
            if re.fullmatch(rf"{NUMBER_LABEL}(?:\.{NUMBER_LABEL}){{0,3}}", host, re.I):
                raise idna.IDNAError
        except idna.IDNAError:
            raise InvalidLink("Hostname không hợp lệ hoặc là cách viết địa chỉ IP không chuẩn.") from None
        registered = SPLIT_DOMAIN(host).top_domain_under_public_suffix or None
    if bracketed and not isinstance(address, ipaddress.IPv6Address):
        raise InvalidLink("Hostname có dấu ngoặc vuông nhưng không phải địa chỉ IPv6.")

    path = quote(parts.path or "/", safe="/%!$&'()*+,;=:@")
    query = quote(parts.query, safe="/?%!$&'()*+,;=:@")
    target = path + ("?" + query if query else "")
    userinfo = parts.username is not None
    return Link(parts.scheme, host, registered, port or (443 if parts.scheme == "https" else 80),
                target, address, userinfo, userinfo or _sensitive_url(parts.path, parts.query, parts.fragment))


def _known_site(link, domains):
    # Exact label boundaries also allow an official subdomain without matching suffix lookalikes.
    return any(link.hostname == domain or link.hostname.endswith("." + domain) for domain in domains)


def _one_edit(first, second):
    if len(first) == len(second):
        return sum(a != b for a, b in zip(first, second)) == 1
    short, long = sorted((first, second), key=len)
    return len(long) == len(short) + 1 and any(
        long[:index] + long[index + 1:] == short for index in range(len(long))
    )


def _lookalike(link, domains):
    tokens = re.split(r"[.\-]", link.hostname)
    roots = {domain.split(".")[0] for domain in domains}
    return any(
        token == root or (len(root) >= 5 and _one_edit(token, root))
        for root in roots for token in tokens if token not in {"www", "com", "net", "org", "example"}
    )


def resembles_domains(link, domains):
    """Look for similar labels outside the given domains and their subdomains."""
    return not _known_site(link, domains) and _lookalike(link, domains)


def _saved_link(saved):
    try:
        return parse_link(saved.url) if saved else None
    except InvalidLink:
        return None


def _link_findings(link, saved, saved_link):
    findings = []
    if link.scheme == "http":
        findings.append(Finding("http", "Trang dùng HTTP. Nội dung trên đường truyền có thể bị thay đổi."))
    if link.address is not None:
        findings.append(Finding("ip", "URL dùng trực tiếp một địa chỉ IP.", (link.hostname,)))
    if link.local_host:
        findings.append(Finding("non_public", "Đích là địa chỉ nội bộ, tên thử hoặc tên không công khai.",
                                (link.hostname,), Risk.NONE))
    if any(label.startswith("xn--") for label in link.hostname.split(".")):
        findings.append(Finding("idn", "Hostname dùng Punycode. Hãy đối chiếu cách viết với tên miền bạn định mở.",
                                (link.hostname,)))
    if link.sensitive:
        reason = ("URL chứa thông tin đứng trước dấu @." if link.has_userinfo
                  else "URL có thể chứa mã đặt lại, mã mời hoặc mã phiên.")
        findings.append(Finding("sensitive", reason + " VaultSafe chỉ phân tích cục bộ.", (link.hostname,)))
    if saved_link and saved_link.site != link.site:
        findings.append(Finding("saved_domain", "Tên miền khác với mục trong kho được chọn.",
                                (link.site, f"{saved.name}: {saved_link.site}")))
    brands = dict(BRAND_DOMAINS)
    if saved_link and saved_link.registered_domain:
        brands.setdefault(saved.name or saved_link.site, (saved_link.site,))
    for brand, domains in brands.items():
        if resembles_domains(link, domains):
            findings.append(Finding("similar_domain", f"Hostname trông giống {brand} nhưng thuộc tên miền khác.",
                                    (link.hostname, link.site, " / ".join(domains))))
    return findings


def inspect_url(text, saved=None):
    source = parse_link(text)
    saved_link = _saved_link(saved)
    unchecked = [PENDING_LOAD, NO_FORM_DATA]
    if saved and not saved_link:
        unchecked.append("URL của mục đã lưu không dùng được để đối chiếu tên miền.")
    if not source.registered_domain and source.address is None:
        unchecked.append("Public Suffix List đi kèm không xác định được tên miền đăng ký của hostname này.")
    return Inspection(source, tuple(_link_findings(source, saved, saved_link)), tuple(unchecked))


def _fold(text):
    return "".join(
        char for char in unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
        if not unicodedata.combining(char)
    )


def _phrases(text, choices):
    folded = " ".join(_fold(text).split())
    return tuple(label for label in choices if re.search(rf"\b{re.escape(_fold(label))}\b", folded))


def _resolved_link(base, target):
    try:
        return parse_link(urljoin(base, target))
    except ValueError:
        return None


def _document_base(tree, page):
    element = tree.find("base", href=True)
    if element:
        link = _resolved_link(page.url, element["href"].strip())
        if link:
            return link.url
    return page.url


def _visible_content(tree):
    for element in tree.select("script, style, noscript, template, iframe, [hidden], [aria-hidden=true], [style]"):
        if element.parent is None:
            continue
        style = re.sub(r"\s+", "", element.get("style", "").lower())
        if (element.name in ("script", "style", "noscript", "template", "iframe")
                or element.has_attr("hidden") or element.get("aria-hidden") == "true"
                or re.search(r"(?:^|;)(?:display:none|visibility:hidden)(?:!important)?(?:;|$)", style)):
            element.decompose()
    return tree.body if tree.body is not None else tree


def _owner(forms_by_id, field):
    if field.has_attr("form"):
        return forms_by_id.get(field["form"])
    return field.find_parent("form")


def _form_destinations(content, passwords, page, base):
    forms_by_id = {}
    for form in content.find_all("form", id=True):
        if form["id"]:
            forms_by_id.setdefault(form["id"], form)
    forms = {}
    for field in passwords:
        form = _owner(forms_by_id, field)
        if form is None:
            forms[None] = [None]
            continue
        if id(form) not in forms:
            action = form.get("action", "").strip()
            forms[id(form)] = [_resolved_link(base, action) if action else page]
    for button in content.find_all(["button", "input"], formaction=True):
        default = "submit" if button.name == "button" else ""
        if button.get("type", default).strip().lower() not in ("submit", "image"):
            continue
        form = _owner(forms_by_id, button)
        if form is not None and id(form) in forms:
            action = button["formaction"].strip()
            forms[id(form)].append(_resolved_link(base, action) if action else page)
    return [destination for matches in forms.values() for destination in matches]


def _linked_providers(content, page, base):
    providers = set()
    for anchor in content.find_all("a", href=True):
        link = _resolved_link(base, anchor["href"].strip())
        if link is not None and link.site != page.site:
            providers.update(brand for brand, domains in BRAND_DOMAINS.items() if _known_site(link, domains))
    return tuple(sorted(providers))


def _page_findings(body, page, saved, encoding):
    tree = BeautifulSoup(body, "html.parser", from_encoding=encoding)
    title = tree.title.get_text(" ", strip=True) if tree.title else ""
    title = " ".join("".join(c for c in title if not unicodedata.category(c).startswith("C")).split())[:160]
    base = _document_base(tree, page)
    content = _visible_content(tree)
    body_text = content.get_text(" ", strip=True)
    rewards = _phrases(f"{title} {body_text}", REWARD_PHRASES)
    pressure = _phrases(f"{title} {body_text}", PRESSURE_PHRASES)
    findings = []
    if rewards:
        findings.append(Finding("reward", "Trang có nội dung mời nhận thưởng hoặc vật phẩm.", rewards, Risk.NONE))
    if pressure:
        findings.append(Finding("pressure", "Trang có lời thúc giục thao tác nhanh.", pressure))
    passwords = [field for field in content.find_all("input")
                 if field.get("type", "").strip().lower() == "password"]
    providers = _linked_providers(content, page, base)
    if providers:
        findings.append(Finding("provider_link", "HTML có liên kết dẫn tới website của nhà cung cấp đăng nhập.",
                                providers, Risk.NONE))
    if not passwords:
        return title, findings, False

    findings.append(Finding("password_form", "HTML có ô nhập mật khẩu ngay trên trang.",
                            (page.hostname,), Risk.NONE))
    destinations = _form_destinations(content, passwords, page, base)
    targets = tuple(sorted({destination.hostname for destination in destinations if destination}))
    foreign = tuple(sorted({destination.hostname for destination in destinations
                            if destination and destination.site != page.site}))
    if targets:
        findings.append(Finding("declared_action", "Đích gửi được khai báo trong HTML.",
                                targets, Risk.NONE))
    if foreign:
        findings.append(Finding("cross_domain_action", "Form khai báo đích gửi sang tên miền khác.", foreign))
    if page.scheme == "http" or any(destination and destination.scheme == "http" for destination in destinations):
        findings.append(Finding("unencrypted_password", "Trang có ô mật khẩu và dùng HTTP hoặc khai báo đích gửi HTTP.",
                                (), Risk.HIGH))

    saved_link = _saved_link(saved)
    mismatch = bool(saved_link and page.site != saved_link.site)
    named_brands = tuple(brand for brand, domains in BRAND_DOMAINS.items()
                         if _phrases(title, (brand,)) and not _known_site(page, domains))
    if named_brands:
        findings.append(Finding("brand_claim", "Tiêu đề nhắc đến thương hiệu, ô mật khẩu nằm trên tên miền khác.",
                                (*named_brands, page.site)))
    if rewards and (foreign or mismatch or named_brands):
        findings.append(Finding("reward_password", "Trang mời nhận thưởng và đặt ô mật khẩu trên tên miền "
                                "khác với mục đối chiếu, thương hiệu hoặc đích gửi đã khai báo.",
                                (page.hostname,), Risk.HIGH))
    return title, findings, bool(destinations and all(destinations))


def inspect_page(report, body, *, redirects=(), saved=None, encoding=None):
    redirects = tuple(redirects)
    findings = list(report.findings)
    unchecked = [item for item in report.unchecked if item not in (PENDING_LOAD, NO_FORM_DATA)]
    for previous, target in zip((report.source, *redirects), redirects):
        if previous.site != target.site:
            findings.append(Finding("redirect_domain", "URL chuyển hướng sang tên miền khác.",
                                    (previous.site, target.site)))
        if previous.scheme == "https" and target.scheme == "http":
            findings.append(Finding("redirect_http", "URL chuyển hướng từ HTTPS sang HTTP.",
                                    (target.hostname,)))
    page = redirects[-1] if redirects else report.source
    if redirects:
        for finding in _link_findings(page, saved, _saved_link(saved)):
            if finding not in findings:
                findings.append(finding)
    title, complete = "", False
    if body:
        title, page_findings, complete = _page_findings(body, page, saved, encoding)
        findings.extend(page_findings)
    if not complete:
        unchecked.append(NO_FORM_DATA)
    unchecked.extend(STATIC_LIMITS)
    return Inspection(report.source, tuple(findings), tuple(unchecked), redirects, title)
