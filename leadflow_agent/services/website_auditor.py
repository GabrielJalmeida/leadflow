from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..models import Evidence, Lead, WebsiteAudit, WebsiteStatus, utc_now_iso


MAX_HTML_BYTES = 1_000_000
DEFAULT_USER_AGENT = "LeadFlow/0.1 (+local website audit; respectful single-page check)"


class UnsafeWebsiteUrl(ValueError):
    """Raised when an audit URL could target a local/private network resource."""


class WebsiteResolutionError(RuntimeError):
    """Raised when a public hostname cannot be resolved operationally.

    This is deliberately separate from :class:`UnsafeWebsiteUrl`: a DNS outage
    or resolver failure is inconclusive evidence about the customer's website
    and must never be treated as a security block or a commercial defect.
    """


@dataclass(slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int | None
    response_time_ms: int | None
    redirect_count: int
    content_type: str
    body: bytes
    error: str | None = None
    blocked: bool = False


@dataclass(slots=True)
class WebsiteAuditOutcome:
    audit: WebsiteAudit
    reused: bool = False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class _SignalsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._title_parts: list[str] = []
        self.has_meta_description = False
        self.has_viewport = False
        self.form_count = 0
        self.has_whatsapp = False
        self.has_tel_link = False
        self.has_email_link = False

    @property
    def title(self) -> str:
        return " ".join(" ".join(self._title_parts).split()).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attr = {str(k).casefold(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = attr.get("name", "").casefold()
            if name == "description" and attr.get("content", "").strip():
                self.has_meta_description = True
            if name == "viewport" and attr.get("content", "").strip():
                self.has_viewport = True
        elif tag == "form":
            self.form_count += 1
        elif tag == "a":
            href = attr.get("href", "").strip().casefold()
            if href.startswith("tel:"):
                self.has_tel_link = True
            if href.startswith("mailto:"):
                self.has_email_link = True
            if (
                href.startswith("whatsapp:")
                or "wa.me/" in href
                or "api.whatsapp.com/" in href
                or "web.whatsapp.com/" in href
            ):
                self.has_whatsapp = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self._title_parts.append(data.strip())


class WebsiteFetcher:
    """Fetches one public webpage with bounded redirects/body size.

    Every redirect target is revalidated to prevent a public URL from bouncing
    the local desktop app into localhost/RFC1918/link-local resources.
    """

    def __init__(
        self,
        *,
        resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
        max_redirects: int = 5,
        max_bytes: int = MAX_HTML_BYTES,
    ) -> None:
        self.resolver = resolver
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self._opener = build_opener(_NoRedirect())

    def fetch(self, url: str, *, timeout: float = 8.0) -> FetchResult:
        requested = url
        current = url
        redirects = 0
        started = time.monotonic()

        while True:
            try:
                validate_public_http_url(current, resolver=self.resolver)
            except WebsiteResolutionError as exc:
                return FetchResult(
                    requested_url=requested,
                    final_url=current,
                    status_code=None,
                    response_time_ms=_elapsed_ms(started),
                    redirect_count=redirects,
                    content_type="",
                    body=b"",
                    error=str(exc),
                    blocked=False,
                )
            except UnsafeWebsiteUrl as exc:
                return FetchResult(
                    requested_url=requested,
                    final_url=current,
                    status_code=None,
                    response_time_ms=_elapsed_ms(started),
                    redirect_count=redirects,
                    content_type="",
                    body=b"",
                    error=str(exc),
                    blocked=True,
                )

            req = Request(
                current,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                },
                method="GET",
            )
            try:
                with self._opener.open(req, timeout=timeout) as response:
                    body = response.read(self.max_bytes + 1)[: self.max_bytes]
                    return FetchResult(
                        requested_url=requested,
                        final_url=response.geturl() or current,
                        status_code=int(getattr(response, "status", 200)),
                        response_time_ms=_elapsed_ms(started),
                        redirect_count=redirects,
                        content_type=response.headers.get("Content-Type", ""),
                        body=body,
                    )
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    if not location:
                        return _http_error_result(requested, current, exc, redirects, started, self.max_bytes)
                    if redirects >= self.max_redirects:
                        return FetchResult(
                            requested_url=requested,
                            final_url=current,
                            status_code=exc.code,
                            response_time_ms=_elapsed_ms(started),
                            redirect_count=redirects,
                            content_type=exc.headers.get("Content-Type", ""),
                            body=b"",
                            error=f"redirect limit exceeded ({self.max_redirects})",
                        )
                    current = urljoin(current, location)
                    redirects += 1
                    continue
                return _http_error_result(requested, current, exc, redirects, started, self.max_bytes)
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                return FetchResult(
                    requested_url=requested,
                    final_url=current,
                    status_code=None,
                    response_time_ms=_elapsed_ms(started),
                    redirect_count=redirects,
                    content_type="",
                    body=b"",
                    error=_friendly_network_error(exc),
                )


class WebsiteAuditor:
    def __init__(self, fetcher: WebsiteFetcher | None = None) -> None:
        self.fetcher = fetcher or WebsiteFetcher()

    def audit(
        self,
        lead: Lead,
        *,
        timeout: float = 8.0,
        max_age_days: int = 7,
        force: bool = False,
    ) -> WebsiteAuditOutcome:
        if not lead.website:
            raise ValueError("lead has no website to audit")

        if not force and _audit_is_fresh(lead.website_audit, lead.website, max_age_days=max_age_days):
            assert lead.website_audit is not None
            return WebsiteAuditOutcome(audit=lead.website_audit, reused=True)

        result = self.fetcher.fetch(lead.website, timeout=timeout)
        audit = _build_audit(result)
        lead.website_audit = audit

        if result.blocked:
            # A safety block says nothing about whether the public business site
            # exists, so do not convert PRESENT into UNREACHABLE.
            pass
        elif result.status_code is None:
            lead.website_status = WebsiteStatus.UNREACHABLE
        else:
            lead.website_status = WebsiteStatus.PRESENT

        lead.evidence.append(
            Evidence(
                source="website_audit",
                kind="website_audit",
                target_field="website",
                url=audit.final_url or lead.website,
                detail=_audit_evidence_detail(audit),
                # A local/network failure is weak evidence about the website
                # itself. Keep it visible without presenting it as a confident
                # commercial signal.
                confidence=0.90 if audit.reachable else 0.25,
            )
        )
        return WebsiteAuditOutcome(audit=audit, reused=False)


def validate_public_http_url(
    url: str,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise UnsafeWebsiteUrl(f"invalid URL: {exc}") from exc

    if parsed.scheme.casefold() not in {"http", "https"}:
        raise UnsafeWebsiteUrl("only http/https website URLs are allowed")
    if not parsed.hostname:
        raise UnsafeWebsiteUrl("website URL has no hostname")
    if parsed.username or parsed.password:
        raise UnsafeWebsiteUrl("credentials in website URLs are not allowed")

    host = parsed.hostname.strip().rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafeWebsiteUrl("local/private host blocked")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeWebsiteUrl("non-public IP blocked")
        return

    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError as exc:
        raise UnsafeWebsiteUrl("invalid URL port") from exc

    try:
        resolved = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WebsiteResolutionError(f"hostname resolution failed: {exc}") from exc
    if not resolved:
        raise WebsiteResolutionError("hostname did not resolve")

    addresses: set[str] = set()
    for item in resolved:
        try:
            addresses.add(str(item[4][0]))
        except (IndexError, TypeError):
            continue
    if not addresses:
        raise WebsiteResolutionError("hostname did not resolve to an IP address")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise WebsiteResolutionError("hostname resolved to an invalid IP") from exc
        if not ip.is_global:
            raise UnsafeWebsiteUrl(f"hostname resolved to non-public IP {address}")


def _build_audit(result: FetchResult) -> WebsiteAudit:
    parser = _SignalsParser()
    html_like = "html" in result.content_type.casefold() or result.body.lstrip().startswith((b"<", b"<!"))
    if result.body and html_like:
        text = result.body.decode("utf-8", errors="replace")
        try:
            parser.feed(text)
        except Exception:
            # Malformed HTML must never crash a batch audit.
            pass

    reachable = result.status_code is not None and not result.blocked
    uses_https = urlsplit(result.final_url).scheme.casefold() == "https" if result.final_url else False
    healthy_status = result.status_code is not None and 200 <= result.status_code < 400
    has_contact_path = (
        parser.has_whatsapp
        or parser.has_tel_link
        or parser.has_email_link
        or parser.form_count > 0
    )

    score = 0
    if reachable:
        score += 25
    if healthy_status:
        score += 15
    if uses_https:
        score += 15
    if parser.title:
        score += 10
    if parser.has_meta_description:
        score += 10
    if parser.has_viewport:
        score += 10
    if has_contact_path:
        score += 15

    findings: list[str] = []
    if result.blocked:
        findings.append("URL bloqueada pela proteção de rede local/privada")
    elif not reachable:
        findings.append("site não respondeu à auditoria")
    if result.status_code is not None and result.status_code >= 400:
        findings.append(f"resposta HTTP {result.status_code}")
    if reachable and not uses_https:
        findings.append("site sem HTTPS")
    if reachable and html_like and not parser.title:
        findings.append("página sem <title> detectável")
    if reachable and html_like and not parser.has_meta_description:
        findings.append("meta description não detectada")
    if reachable and html_like and not parser.has_viewport:
        findings.append("meta viewport não detectada")
    if reachable and html_like and not has_contact_path:
        findings.append("nenhum formulário/tel/e-mail/WhatsApp detectado no HTML inicial")
    if result.redirect_count >= 3:
        findings.append(f"cadeia longa de redirects ({result.redirect_count})")
    if result.error:
        findings.append(result.error)

    return WebsiteAudit(
        requested_url=result.requested_url,
        final_url=result.final_url,
        reachable=reachable,
        blocked=result.blocked,
        status_code=result.status_code,
        response_time_ms=result.response_time_ms,
        redirect_count=result.redirect_count,
        content_type=result.content_type,
        uses_https=uses_https,
        title=parser.title or None,
        has_meta_description=parser.has_meta_description,
        has_viewport=parser.has_viewport,
        form_count=parser.form_count,
        has_whatsapp=parser.has_whatsapp,
        has_tel_link=parser.has_tel_link,
        has_email_link=parser.has_email_link,
        technical_score=max(0, min(score, 100)),
        findings=findings,
        error=result.error,
        audited_at=utc_now_iso(),
    )


def _http_error_result(
    requested: str,
    current: str,
    exc: HTTPError,
    redirects: int,
    started: float,
    max_bytes: int,
) -> FetchResult:
    try:
        body = exc.read(max_bytes + 1)[:max_bytes]
    except Exception:
        body = b""
    return FetchResult(
        requested_url=requested,
        final_url=current,
        status_code=int(exc.code),
        response_time_ms=_elapsed_ms(started),
        redirect_count=redirects,
        content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
        body=body,
        error=f"HTTP {exc.code}",
    )


def _friendly_network_error(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    return str(reason or exc)


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _audit_is_fresh(audit: WebsiteAudit | None, website: str, *, max_age_days: int) -> bool:
    if audit is None:
        return False
    if _normalize_url(audit.requested_url) != _normalize_url(website):
        return False
    try:
        observed = datetime.fromisoformat(audit.audited_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return observed.astimezone(timezone.utc) >= cutoff


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()


def _audit_evidence_detail(audit: WebsiteAudit) -> str:
    status = audit.status_code if audit.status_code is not None else "network_error"
    return (
        f"HTTP={status}; HTTPS={audit.uses_https}; technical_score={audit.technical_score}; "
        f"redirects={audit.redirect_count}; blocked={audit.blocked}"
    )
