from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from ..models import BrowserAudit, Evidence, Lead, utc_now_iso
from .website_auditor import UnsafeWebsiteUrl, validate_public_http_url


class BrowserAuditUnavailable(RuntimeError):
    """Raised when the optional Playwright browser runtime is not installed."""


@dataclass(slots=True)
class BrowserAuditOutcome:
    audit: BrowserAudit
    reused: bool = False


Runner = Callable[[str, float, Path], BrowserAudit]


class BrowserAuditor:
    """Deterministic browser/UX audit using an optional real Chromium runtime.

    This phase deliberately does not judge aesthetics. It measures observable
    browser behaviour: mobile overflow, visible contact CTAs, navigation density,
    runtime errors, and captures screenshots for later visual review.
    """

    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or _run_playwright

    def audit(
        self,
        lead: Lead,
        *,
        timeout: float = 12.0,
        max_age_days: int = 7,
        force: bool = False,
        artifacts_dir: str | Path = "output/browser-audits",
    ) -> BrowserAuditOutcome:
        if not lead.website:
            raise ValueError("lead has no website to browser-audit")

        if not force and _audit_is_fresh(lead.browser_audit, lead.website, max_age_days=max_age_days):
            assert lead.browser_audit is not None
            return BrowserAuditOutcome(audit=lead.browser_audit, reused=True)

        validate_public_http_url(lead.website)
        target_dir = _artifact_dir(Path(artifacts_dir), lead)
        target_dir.mkdir(parents=True, exist_ok=True)
        audit = self.runner(lead.website, timeout, target_dir)
        lead.browser_audit = audit
        lead.evidence.append(
            Evidence(
                source="browser_audit",
                kind="browser_audit",
                target_field="website",
                url=audit.final_url or lead.website,
                detail=_evidence_detail(audit),
                confidence=0.90 if audit.loaded else 0.65,
            )
        )
        return BrowserAuditOutcome(audit=audit, reused=False)


def score_browser_signals(
    *,
    loaded: bool,
    mobile_overflow: bool,
    visible_contact_cta_count: int,
    nav_link_count: int,
    console_error_count: int,
    page_error_count: int,
) -> tuple[int, list[str]]:
    score = 0
    findings: list[str] = []

    if loaded:
        score += 25
    else:
        findings.append("página não carregou no navegador real")

    if loaded and not mobile_overflow:
        score += 20
    elif loaded:
        findings.append("overflow horizontal detectado no viewport mobile")

    if visible_contact_cta_count > 0:
        score += 20
    else:
        findings.append("nenhum CTA de contato visível detectado")

    if nav_link_count >= 3:
        score += 15
    elif loaded:
        findings.append("navegação principal muito limitada ou não detectada")

    if console_error_count == 0:
        score += 10
    else:
        findings.append(f"{console_error_count} erro(s) de console detectado(s)")

    if page_error_count == 0:
        score += 10
    else:
        findings.append(f"{page_error_count} erro(s) de página/JavaScript detectado(s)")

    return max(0, min(score, 100)), findings


def _run_playwright(url: str, timeout: float, artifacts_dir: Path) -> BrowserAudit:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserAuditUnavailable(
            'Playwright não instalado. Rode: pip install -e ".[browser]" e depois '
            'python -m playwright install chromium'
        ) from exc

    requested = url
    final_url = url
    status_code: int | None = None
    console_errors = 0
    page_errors = 0
    desktop_path = artifacts_dir / "desktop.webp"
    mobile_path = artifacts_dir / "mobile.webp"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                desktop = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    device_scale_factor=1,
                )
                mobile = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=1,
                    is_mobile=True,
                    has_touch=True,
                )
                try:
                    _protect_context(desktop)
                    _protect_context(mobile)

                    dpage = desktop.new_page()
                    mpage = mobile.new_page()
                    dpage.set_default_timeout(timeout * 1000)
                    mpage.set_default_timeout(timeout * 1000)

                    def _console(msg):
                        nonlocal console_errors
                        if msg.type == "error":
                            console_errors += 1

                    def _page_error(_exc):
                        nonlocal page_errors
                        page_errors += 1

                    mpage.on("console", _console)
                    mpage.on("pageerror", _page_error)

                    response = mpage.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    final_url = mpage.url or url
                    validate_public_http_url(final_url)
                    status_code = response.status if response is not None else None

                    # Desktop capture is intentionally separate: it becomes useful
                    # later for visual/AI review without changing this deterministic score.
                    dpage.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    dpage.screenshot(path=str(desktop_path), full_page=True, type="webp", quality=72)

                    mobile_metrics = mpage.evaluate(
                        r"""
                        () => {
                          const visible = (el) => {
                            const r = el.getBoundingClientRect();
                            const s = getComputedStyle(el);
                            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                          };
                          const fold = innerHeight;
                          const contactTerms = /(whatsapp|contato|contact|orçamento|orcamento|fale|ligue|telefone|chamar|solicite|pedir orçamento)/i;
                          const candidates = [...document.querySelectorAll('a,button,[role="button"]')];
                          const contactCtas = candidates.filter((el) => {
                            if (!visible(el)) return false;
                            const r = el.getBoundingClientRect();
                            if (r.top > fold) return false;
                            const href = (el.getAttribute('href') || '');
                            const text = (el.innerText || el.getAttribute('aria-label') || '').trim();
                            return /^tel:|^mailto:|wa\.me|whatsapp/i.test(href) || contactTerms.test(text);
                          });
                          const navLinks = [...document.querySelectorAll('nav a, header a')].filter(visible);
                          return {
                            overflow: document.documentElement.scrollWidth > innerWidth + 4,
                            contactCtas: contactCtas.length,
                            navLinks: navLinks.length,
                          };
                        }
                        """
                    )
                    mpage.screenshot(path=str(mobile_path), full_page=True, type="webp", quality=72)

                    score, findings = score_browser_signals(
                        loaded=True,
                        mobile_overflow=bool(mobile_metrics.get("overflow")),
                        visible_contact_cta_count=int(mobile_metrics.get("contactCtas") or 0),
                        nav_link_count=int(mobile_metrics.get("navLinks") or 0),
                        console_error_count=console_errors,
                        page_error_count=page_errors,
                    )
                    return BrowserAudit(
                        requested_url=requested,
                        final_url=final_url,
                        loaded=True,
                        status_code=status_code,
                        mobile_overflow=bool(mobile_metrics.get("overflow")),
                        visible_contact_cta_count=int(mobile_metrics.get("contactCtas") or 0),
                        nav_link_count=int(mobile_metrics.get("navLinks") or 0),
                        console_error_count=console_errors,
                        page_error_count=page_errors,
                        ux_score=score,
                        desktop_screenshot=str(desktop_path),
                        mobile_screenshot=str(mobile_path),
                        findings=findings,
                        audited_at=utc_now_iso(),
                    )
                finally:
                    desktop.close()
                    mobile.close()
            finally:
                browser.close()
    except UnsafeWebsiteUrl:
        raise
    except (PlaywrightTimeoutError, PlaywrightError, OSError, ValueError) as exc:
        score, findings = score_browser_signals(
            loaded=False,
            mobile_overflow=False,
            visible_contact_cta_count=0,
            nav_link_count=0,
            console_error_count=console_errors,
            page_error_count=page_errors,
        )
        findings.append(str(exc))
        return BrowserAudit(
            requested_url=requested,
            final_url=final_url,
            loaded=False,
            status_code=status_code,
            ux_score=score,
            desktop_screenshot=str(desktop_path) if desktop_path.exists() else None,
            mobile_screenshot=str(mobile_path) if mobile_path.exists() else None,
            findings=findings,
            error=str(exc),
            audited_at=utc_now_iso(),
        )


def _protect_context(context) -> None:  # noqa: ANN001
    def handle(route):  # noqa: ANN001
        request_url = route.request.url
        scheme = urlsplit(request_url).scheme.casefold()
        if scheme in {"data", "blob", "about"}:
            route.continue_()
            return
        if scheme not in {"http", "https"}:
            route.abort()
            return
        try:
            validate_public_http_url(request_url)
        except UnsafeWebsiteUrl:
            route.abort()
            return
        route.continue_()

    context.route("**/*", handle)


def _artifact_dir(root: Path, lead: Lead) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", lead.name.casefold()).strip("-")[:48] or "lead"
    anchor = (lead.website or lead.provider_url or lead.name).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(anchor).hexdigest()[:10]
    return root / f"{slug}-{digest}"


def _evidence_detail(audit: BrowserAudit) -> str:
    return (
        f"ux_score={audit.ux_score}; mobile_overflow={audit.mobile_overflow}; "
        f"visible_contact_ctas={audit.visible_contact_cta_count}; "
        f"console_errors={audit.console_error_count}; page_errors={audit.page_error_count}"
    )


def _audit_is_fresh(audit: BrowserAudit | None, website: str, *, max_age_days: int) -> bool:
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
    return observed.astimezone(timezone.utc) >= (
        datetime.now(timezone.utc) - timedelta(days=max_age_days)
    )


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()
