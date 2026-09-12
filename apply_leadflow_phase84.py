from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ORIGINALS: dict[Path, str | None] = {}


def path(rel: str) -> Path:
    return ROOT / rel


def read(rel: str) -> str:
    p = path(rel)
    if not p.exists():
        raise RuntimeError(f"arquivo não encontrado: {rel}")
    return p.read_text(encoding="utf-8")


def write(rel: str, content: str) -> None:
    p = path(rel)
    if p not in ORIGINALS:
        ORIGINALS[p] = p.read_text(encoding="utf-8") if p.exists() else None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: trecho esperado não encontrado de forma única (count={n})")
    return text.replace(old, new, 1)


def rollback() -> None:
    for p, content in ORIGINALS.items():
        if content is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(content, encoding="utf-8")


try:
    # validation.py — explicit phone classification.
    validation = '''from __future__ import annotations

import re
from enum import Enum


class PhoneKind(str, Enum):
    MOBILE = "mobile"
    FIXED_LINE = "fixed_line"
    OTHER = "other"
    INVALID = "invalid"


def phone_digits(value: str | None) -> str:
    return re.sub(r"\\D+", "", value or "")


def classify_phone(value: str | None, *, country: str = "Brazil") -> PhoneKind:
    """Classify a phone structurally without claiming that it is active."""
    digits = phone_digits(value)
    if not digits:
        return PhoneKind.INVALID

    if country.casefold() in {"brazil", "br", "brasil"}:
        if digits.startswith("55") and len(digits) in {12, 13}:
            digits = digits[2:]
        if len(digits) == 11:
            ddd, subscriber = digits[:2], digits[2:]
            if ddd[0] != "0" and subscriber.startswith("9"):
                return PhoneKind.MOBILE
            return PhoneKind.INVALID
        if len(digits) == 10:
            ddd, subscriber = digits[:2], digits[2:]
            if ddd[0] != "0" and subscriber[:1] in {"2", "3", "4", "5"}:
                return PhoneKind.FIXED_LINE
            return PhoneKind.INVALID
        return PhoneKind.INVALID

    return PhoneKind.OTHER if 7 <= len(digits) <= 15 else PhoneKind.INVALID


def is_digital_contact_phone(value: str | None, *, country: str = "Brazil") -> bool:
    return classify_phone(value, country=country) in {PhoneKind.MOBILE, PhoneKind.OTHER}


def is_plausible_phone(value: str | None, *, country: str = "Brazil") -> bool:
    """Cheap structural validation; it does not prove a number is active."""
    return classify_phone(value, country=country) != PhoneKind.INVALID
'''
    current = read("leadflow_agent/validation.py")
    if "def phone_digits" not in current:
        raise RuntimeError("validation.py não parece ser o arquivo esperado")
    write("leadflow_agent/validation.py", validation)

    # quality.py — fixed lines remain valid evidence, but are removed from digital-first actionable contact.
    q = read("leadflow_agent/quality.py")
    q = replace_once(q, "from .validation import is_plausible_phone\n", "from .validation import is_digital_contact_phone, is_plausible_phone\n", "quality import")
    q = re.sub(
        r'def sanitize_lead_fields\(lead: Lead\) -> int:\n.*?\n\ndef _host',
        '''def sanitize_lead_fields(lead: Lead, *, digital_only: bool = False) -> int:\n    """Remove invalid fields and fixed lines from digital-first actionable contact."""\n    removed = 0\n    invalid = lead.phone and not is_plausible_phone(lead.phone, country=lead.country)\n    not_digital = lead.phone and digital_only and not is_digital_contact_phone(lead.phone, country=lead.country)\n    if invalid or not_digital:\n        lead.phone = None\n        lead.field_confidence.pop("phone", None)\n        removed += 1\n    return removed\n\n\ndef _host''',
        q,
        count=1,
        flags=re.S,
    )
    if "digital_only: bool" not in q:
        raise RuntimeError("quality sanitizer não foi atualizado")
    write("leadflow_agent/quality.py", q)

    # dedupe.py — domain / Instagram / provider / mobile are anchors; fixed line is not identity.
    dedupe = '''from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from .models import Lead, WebsiteStatus
from .validation import is_digital_contact_phone


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_phone(value: str | None) -> str:
    return re.sub(r"\\D+", "", value or "")


def _website_domain(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
    except ValueError:
        return ""
    host = parsed.netloc.casefold().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _instagram_identity(socials: list[str]) -> str:
    reserved = {"p", "reel", "reels", "stories", "explore", "accounts", "direct", "tv"}
    for value in socials:
        try:
            parsed = urlparse(value)
        except ValueError:
            continue
        host = parsed.netloc.casefold().split(":", 1)[0]
        if host not in {"instagram.com", "www.instagram.com"}:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0].casefold() not in reserved:
            return parts[0].casefold()
    return ""


def _same_local_identity(a: Lead, b: Lead) -> bool:
    return (
        normalize_text(a.name) == normalize_text(b.name)
        and normalize_text(a.city) == normalize_text(b.city)
        and normalize_text(a.state) == normalize_text(b.state)
    )


def lead_key(lead: Lead) -> str:
    domain = _website_domain(lead.website)
    if domain:
        return f"domain:{domain}"
    instagram = _instagram_identity(lead.socials)
    if instagram:
        return f"instagram:{instagram}"
    provider_id = (lead.provider_id or "").strip()
    if provider_id:
        return f"provider:{lead.source_provider}:{provider_id}"
    if is_digital_contact_phone(lead.phone, country=lead.country):
        phone = normalize_phone(lead.phone)
        if len(phone) >= 8:
            return f"mobile:{phone}"
    return f"name:{normalize_text(lead.name)}|{normalize_text(lead.city)}|{normalize_text(lead.state)}"


def find_duplicate_key(existing: dict[str, Lead], incoming: Lead) -> str | None:
    direct = lead_key(incoming)
    if direct in existing:
        return direct

    incoming_domain = _website_domain(incoming.website)
    incoming_instagram = _instagram_identity(incoming.socials)
    incoming_mobile = normalize_phone(incoming.phone) if is_digital_contact_phone(incoming.phone, country=incoming.country) else ""

    for key, current in existing.items():
        current_domain = _website_domain(current.website)
        current_instagram = _instagram_identity(current.socials)
        current_mobile = normalize_phone(current.phone) if is_digital_contact_phone(current.phone, country=current.country) else ""

        if incoming_domain and current_domain and incoming_domain == current_domain:
            return key
        if incoming_instagram and current_instagram and incoming_instagram == current_instagram:
            return key
        if incoming.provider_id and current.provider_id and incoming.source_provider == current.source_provider and incoming.provider_id == current.provider_id:
            return key
        if incoming_mobile and current_mobile and incoming_mobile == current_mobile:
            return key

        if not _same_local_identity(current, incoming):
            continue
        if incoming_domain and current_domain and incoming_domain != current_domain:
            continue
        if incoming_instagram and current_instagram and incoming_instagram != current_instagram:
            continue
        if incoming_mobile and current_mobile and incoming_mobile != current_mobile:
            continue
        return key
    return None


def merge_leads(current: Lead, incoming: Lead) -> Lead:
    for attr in (
        "address", "email", "website", "rating", "review_count",
        "latitude", "longitude", "provider_id", "provider_url",
    ):
        if getattr(current, attr) in (None, "") and getattr(incoming, attr) not in (None, ""):
            setattr(current, attr, getattr(incoming, attr))

    if incoming.phone:
        current_is_digital = is_digital_contact_phone(current.phone, country=current.country)
        incoming_is_digital = is_digital_contact_phone(incoming.phone, country=incoming.country)
        if not current.phone or (incoming_is_digital and not current_is_digital):
            current.phone = incoming.phone

    if current.website:
        current.website_status = WebsiteStatus.PRESENT
    elif current.website_status == WebsiteStatus.UNKNOWN and incoming.website_status != WebsiteStatus.UNKNOWN:
        current.website_status = incoming.website_status

    current.discovery_confidence = max(current.discovery_confidence, incoming.discovery_confidence)
    for field_name, confidence in incoming.field_confidence.items():
        current.field_confidence[field_name] = max(current.field_confidence.get(field_name, 0.0), confidence)

    current.socials = list(dict.fromkeys([*current.socials, *incoming.socials]))
    current.categories = list(dict.fromkeys([*current.categories, *incoming.categories]))
    current.evidence.extend(incoming.evidence)
    if incoming.discovered_query and incoming.discovered_query not in current.discovered_query.split(" | "):
        current.discovered_query = " | ".join(filter(None, [current.discovered_query, incoming.discovered_query]))
    return current
'''
    write("leadflow_agent/dedupe.py", dedupe)

    # opportunity.py — contactability only rewards useful digital channels.
    o = read("leadflow_agent/opportunity.py")
    if "from .validation import is_digital_contact_phone" not in o:
        o = o.replace(")\n\n\n@dataclass(slots=True)\nclass _Components", ")\nfrom .validation import is_digital_contact_phone\n\n\n@dataclass(slots=True)\nclass _Components", 1)
    o = re.sub(
        r'def _contactability\(lead: Lead\) -> tuple\[int, list\[str\]\]:\n.*?\n\ndef _activity',
        '''def _contactability(lead: Lead) -> tuple[int, list[str]]:\n    score = 0\n    reasons: list[str] = []\n    social_values = [value.casefold() for value in lead.socials]\n    has_instagram = any("instagram.com" in value for value in social_values)\n    has_explicit_whatsapp = any(\n        "wa.me/" in value or "api.whatsapp.com" in value or "whatsapp.com/send" in value\n        for value in social_values\n    )\n    if is_digital_contact_phone(lead.phone, country=lead.country) or has_explicit_whatsapp:\n        score += 15\n        reasons.append("canal digital direto disponível +15")\n    if has_instagram:\n        score += 6\n        reasons.append("Instagram disponível +6")\n    if lead.email:\n        score += 4\n        reasons.append("e-mail disponível +4")\n    return min(score, 25), reasons\n\n\ndef _activity''',
        o,
        count=1,
        flags=re.S,
    )
    if "canal digital direto disponível +15" not in o:
        raise RuntimeError("opportunity contactability não foi atualizado")
    write("leadflow_agent/opportunity.py", o)

    # filters.py — fixed line alone does not count as useful prospecting contact.
    f = read("leadflow_agent/filters.py")
    if "from .validation import is_digital_contact_phone" not in f:
        f = f.replace("from .models import Lead, OpportunityType, WebsiteStatus\n", "from .models import Lead, OpportunityType, WebsiteStatus\nfrom .validation import is_digital_contact_phone\n", 1)
    if "def _has_useful_contact" not in f:
        f = f.replace(
            "def _presence_matches(value: bool, requirement: Presence) -> bool:\n",
            '''def _has_explicit_whatsapp(lead: Lead) -> bool:\n    return any(\n        token in (url or "").lower()\n        for url in lead.socials\n        for token in ("wa.me/", "api.whatsapp.com", "whatsapp.com/send")\n    )\n\n\ndef _has_useful_contact(lead: Lead) -> bool:\n    return bool(\n        lead.email\n        or _has_instagram(lead)\n        or _has_explicit_whatsapp(lead)\n        or is_digital_contact_phone(lead.phone, country=lead.country)\n    )\n\n\ndef _presence_matches(value: bool, requirement: Presence) -> bool:\n''',
            1,
        )
    f = f.replace("_presence_matches(bool(lead.phone), spec.phone)", "_presence_matches(is_digital_contact_phone(lead.phone, country=lead.country), spec.phone)")
    f = f.replace("spec.require_any_contact and not (lead.phone or lead.email or lead.socials)", "spec.require_any_contact and not _has_useful_contact(lead)")
    write("leadflow_agent/filters.py", f)

    # contact.py — never offer a fixed line as WhatsApp without explicit WhatsApp evidence.
    c = read("leadflow_agent/contact.py")
    if "from .validation import is_digital_contact_phone" not in c:
        c = c.replace("from urllib.parse import parse_qs, quote, urlparse\n", "from urllib.parse import parse_qs, quote, urlparse\n\nfrom .validation import is_digital_contact_phone\n", 1)
    c = re.sub(r'def _looks_like_brazil_mobile\(.*?\n\n\n', '', c, count=1, flags=re.S)
    c = c.replace(
        "    if phone and _looks_like_brazil_mobile(phone):\n",
        "    raw_phone = contact.get(\"phone\")\n    if phone and is_digital_contact_phone(raw_phone, country=str(location.get(\"country\") or \"Brazil\")):\n",
        1,
    )
    c = re.sub(
        r'\n    if phone:\n        return ContactRoute\(\n            channel="whatsapp_test",.*?\n        \)\n',
        '\n',
        c,
        count=1,
        flags=re.S,
    )
    write("leadflow_agent/contact.py", c)

    # agent.py — use entity matching, digital-only sanitation and explicit partial quota reason.
    a = read("leadflow_agent/agent.py")
    a = a.replace("from .dedupe import lead_key, merge_leads\n", "from .dedupe import find_duplicate_key, lead_key, merge_leads\n", 1)
    a = replace_once(a, "        filter_pool_multiplier: int = 2,\n    ) -> ResearchReport:\n", "        filter_pool_multiplier: int = 2,\n        digital_contact_only: bool = False,\n    ) -> ResearchReport:\n", "agent parameter")
    a = a.replace("sanitize_lead_fields(lead)", "sanitize_lead_fields(lead, digital_only=digital_contact_only)")
    a = replace_once(
        a,
        '''                key = lead_key(lead)\n                if key in unique:\n                    duplicates_removed += 1\n                    merge_leads(unique[key], lead)\n                else:\n                    unique[key] = lead\n''',
        '''                key = lead_key(lead)\n                duplicate_key = find_duplicate_key(unique, lead)\n                if duplicate_key is not None:\n                    duplicates_removed += 1\n                    merge_leads(unique[duplicate_key], lead)\n                else:\n                    unique[key] = lead\n''',
        "agent duplicate block",
    )
    marker = '''                    except Exception as exc:\n                        errors.append(f"{lead.name}: investigation failed: {exc}")\n\n        website_audits_run = 0\n'''
    repl = '''                    except Exception as exc:\n                        errors.append(f"{lead.name}: investigation failed: {exc}")\n                    invalid_fields_removed += sanitize_lead_fields(\n                        lead, digital_only=digital_contact_only\n                    )\n\n        website_audits_run = 0\n'''
    a = replace_once(a, marker, repl, "agent investigation sanitation")
    if "quota parcial:" not in a:
        a = a.replace(
            "        cache_after = _cache_snapshot(self.web_search)\n",
            '''        if len(leads) < goal.limit and controller.stop_reason is None:\n            controller.stop_reason = (\n                f"quota parcial: {len(leads)}/{goal.limit} leads elegíveis após descoberta, "\n                "deduplicação e filtros"\n            )\n\n        cache_after = _cache_snapshot(self.web_search)\n''',
            1,
        )
    write("leadflow_agent/agent.py", a)

    # planner.py — if Gemini returns only 2-3 queries, fill the retrieval budget deterministically.
    p = read("leadflow_agent/planner.py")
    if "def _expand_plan_to_budget" not in p:
        old = '''def build_plan(goal: SearchGoal, llm: LLMProvider | None, *, max_queries: int = 6) -> QueryPlan:\n    if llm is None:\n        return BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)\n    try:\n        return llm.plan_queries(goal, max_queries=max_queries)\n    except Exception as exc:\n        fallback = BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)\n        fallback.rationale = f"LLM planner falhou ({exc}); usando fallback determinístico."\n        fallback.generated_by = "basic:fallback"\n        return fallback\n'''
        new = '''def _expand_plan_to_budget(plan: QueryPlan, goal: SearchGoal, *, max_queries: int) -> QueryPlan:\n    base = goal.segment.strip()\n    folded = base.casefold()\n    supplements = [\n        base, f"{base} empresa", f"{base} profissional", f"{base} serviços",\n        f"{base} orçamento", f"{base} Instagram", f"{base} WhatsApp",\n        f"{base} contato", f"{base} negócios locais", f"{base} região",\n    ]\n    if "marcenar" in folded or "móveis planejados" in folded or "moveis planejados" in folded:\n        supplements = [\n            base, "móveis planejados", "marceneiro", "móveis sob medida",\n            "fabricação de móveis sob medida", "marcenaria artesanal",\n            "projetos de marcenaria", "móveis personalizados",\n            "fábrica de móveis planejados", "planejados sob medida",\n        ]\n    combined: list[str] = []\n    for query in [*plan.queries, *supplements]:\n        query = " ".join(query.split())\n        if query and query.casefold() not in {item.casefold() for item in combined}:\n            combined.append(query)\n        if len(combined) >= max(1, max_queries):\n            break\n    plan.queries = combined\n    return plan\n\n\ndef build_plan(goal: SearchGoal, llm: LLMProvider | None, *, max_queries: int = 6) -> QueryPlan:\n    if llm is None:\n        plan = BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)\n        return _expand_plan_to_budget(plan, goal, max_queries=max_queries)\n    try:\n        plan = llm.plan_queries(goal, max_queries=max_queries)\n        return _expand_plan_to_budget(plan, goal, max_queries=max_queries)\n    except Exception as exc:\n        fallback = BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)\n        fallback.rationale = f"LLM planner falhou ({exc}); usando fallback determinístico."\n        fallback.generated_by = "basic:fallback"\n        return _expand_plan_to_budget(fallback, goal, max_queries=max_queries)\n'''
        p = replace_once(p, old, new, "planner expansion")
    write("leadflow_agent/planner.py", p)

    # search_service.py defaults.
    s = read("leadflow_agent/search_service.py")
    s = s.replace("    max_queries: int = 6\n", "    max_queries: int = 10\n", 1)
    s = s.replace("    filter_pool_multiplier: int = 2\n", "    filter_pool_multiplier: int = 5\n    contact_strategy: str = \"digital-first\"\n", 1)
    s = s.replace(
        '''    if not 1 <= int(request.filter_pool_multiplier) <= 5:\n        raise ValueError("filter_pool_multiplier deve ficar entre 1 e 5")\n''',
        '''    if not 1 <= int(request.filter_pool_multiplier) <= 8:\n        raise ValueError("filter_pool_multiplier deve ficar entre 1 e 8")\n    if request.contact_strategy not in {"digital-first", "multichannel"}:\n        raise ValueError("contact_strategy deve ser digital-first ou multichannel")\n''',
        1,
    )
    s = replace_once(s, "        filter_pool_multiplier=request.filter_pool_multiplier,\n    )\n", "        filter_pool_multiplier=request.filter_pool_multiplier,\n        digital_contact_only=request.contact_strategy == \"digital-first\",\n    )\n", "search agent call")
    write("leadflow_agent/search_service.py", s)

    # api.py defaults and domain mapping.
    api = read("leadflow_agent/api.py")
    api = api.replace("    max_queries: int = Field(default=6, ge=1, le=20)\n", "    max_queries: int = Field(default=10, ge=1, le=20)\n", 1)
    api = api.replace("    filter_pool_multiplier: int = Field(default=2, ge=1, le=5)\n", "    filter_pool_multiplier: int = Field(default=5, ge=1, le=8)\n    contact_strategy: Literal[\"digital-first\", \"multichannel\"] = \"digital-first\"\n", 1)
    api = replace_once(api, "            filter_pool_multiplier=self.filter_pool_multiplier,\n", "            filter_pool_multiplier=self.filter_pool_multiplier,\n            contact_strategy=self.contact_strategy,\n", "api domain mapping")
    write("leadflow_agent/api.py", api)

    # contracts.py quota metadata.
    co = read("leadflow_agent/contracts.py")
    if '"quota_fulfilled"' not in co:
        co = co.replace(
            '            "returned_results": len(report.leads),\n            "usage": {\n',
            '            "returned_results": len(report.leads),\n            "quota_fulfilled": len(report.leads) >= report.goal.limit,\n            "shortfall": max(0, report.goal.limit - len(report.leads)),\n            "usage": {\n',
            1,
        )
    write("leadflow_agent/contracts.py", co)

    # profiles copy.
    pr = read("leadflow_agent/profiles.py")
    pr = pr.replace('"phone-first", "Phone First", "Leads com telefone disponível.",', '"phone-first", "Phone First", "Leads com celular disponível para contato digital.",')
    write("leadflow_agent/profiles.py", pr)

    # Regression tests.
    test = '''from __future__ import annotations\n\nimport unittest\n\nfrom leadflow_agent.agent import LeadResearchAgent\nfrom leadflow_agent.contact import resolve_contact_route\nfrom leadflow_agent.dedupe import find_duplicate_key, lead_key\nfrom leadflow_agent.filters import LeadFilterSpec, assess_filter\nfrom leadflow_agent.models import IdentityStatus, Lead, QueryPlan, SearchGoal, WebsiteStatus\nfrom leadflow_agent.planner import build_plan\nfrom leadflow_agent.quality import sanitize_lead_fields\nfrom leadflow_agent.scoring import score_lead\nfrom leadflow_agent.search_service import SearchRequest\nfrom leadflow_agent.validation import PhoneKind, classify_phone, is_digital_contact_phone\n\n\nclass _ShortPlanner:\n    name = "short"\n    def plan_queries(self, goal, *, max_queries=10):\n        return QueryPlan(queries=[goal.segment, "móveis planejados"], generated_by=self.name)\n\n\nclass _QuotaLocal:\n    name = "quota-local"\n    def __init__(self):\n        self.calls = []\n    def search_places(self, query, goal, *, count=20):\n        index = len(self.calls)\n        self.calls.append(query)\n        phone = f"13 34{index:02d}-12{index:02d}" if index < 5 else f"13 9{80000000 + index:08d}"\n        return [Lead(name=f"Empresa {index}", city=goal.city, state=goal.state, phone=phone, source_provider=self.name, discovered_query=query, identity_status=IdentityStatus.MATCHED, identity_confidence=0.99, website_status=WebsiteStatus.NOT_FOUND)]\n\n\nclass Phase84LeadQualityTests(unittest.TestCase):\n    def test_phone_classifier(self):\n        self.assertEqual(classify_phone("(13) 99152-5154"), PhoneKind.MOBILE)\n        self.assertEqual(classify_phone("(13) 3471-2700"), PhoneKind.FIXED_LINE)\n        self.assertFalse(is_digital_contact_phone("(13) 3471-2700"))\n\n    def test_digital_sanitizer_removes_fixed(self):\n        lead = Lead(name="Paris", phone="(13) 3471-2700")\n        self.assertEqual(sanitize_lead_fields(lead, digital_only=True), 1)\n        self.assertIsNone(lead.phone)\n\n    def test_same_domain_dedupes_different_phones(self):\n        a = Lead(name="Paris", city="Praia Grande", state="SP", phone="(13) 99152-5154", website="https://www.planejadosparis.com.br")\n        b = Lead(name="Paris", city="Praia Grande", state="SP", phone="(13) 3471-2700", website="https://planejadosparis.com.br/")\n        self.assertEqual(lead_key(a), lead_key(b))\n\n    def test_distinct_mobiles_same_name_remain_separate(self):\n        a = Lead(name="Empresa X", city="Praia Grande", state="SP", phone="(13) 99111-1111")\n        b = Lead(name="Empresa X", city="Praia Grande", state="SP", phone="(13) 99222-2222")\n        self.assertIsNone(find_duplicate_key({lead_key(a): a}, b))\n\n    def test_fixed_line_not_whatsapp(self):\n        route = resolve_contact_route({"contact": {"phone": "(13) 3471-2700", "socials": []}, "location": {"country": "Brazil"}})\n        self.assertEqual(route.channel, "none")\n\n    def test_fixed_plus_instagram_prefers_instagram(self):\n        route = resolve_contact_route({"contact": {"phone": "(13) 3471-2700", "socials": ["https://www.instagram.com/parisplanejados/"]}, "location": {"country": "Brazil"}})\n        self.assertEqual(route.channel, "instagram")\n\n    def test_fixed_line_no_contactability(self):\n        lead = Lead(name="Fixed", phone="(13) 3471-2700", website_status=WebsiteStatus.NOT_FOUND, identity_status=IdentityStatus.MATCHED, identity_confidence=0.99)\n        score_lead(lead)\n        self.assertEqual(lead.opportunity.contactability_score, 0)\n\n    def test_fixed_only_fails_useful_contact_filter(self):\n        self.assertFalse(assess_filter(Lead(name="Fixed", phone="(13) 3471-2700"), LeadFilterSpec(require_any_contact=True)).accepted)\n\n    def test_defaults(self):\n        request = SearchRequest(segment="marcenaria", city="Praia Grande")\n        self.assertEqual(request.max_queries, 10)\n        self.assertEqual(request.filter_pool_multiplier, 5)\n        self.assertEqual(request.contact_strategy, "digital-first")\n\n    def test_short_plan_expands_to_budget(self):\n        plan = build_plan(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10), _ShortPlanner(), max_queries=10)\n        self.assertEqual(len(plan.queries), 10)\n\n    def test_more_rounds_fill_filtered_quota(self):\n        provider = _QuotaLocal()\n        agent = LeadResearchAgent(local_search=provider, llm=_ShortPlanner())\n        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=5), max_queries=10, lead_filter=LeadFilterSpec(require_any_contact=True), filter_pool_multiplier=5, digital_contact_only=True)\n        self.assertEqual(len(report.leads), 5)\n        self.assertEqual(len(report.queries_executed), 10)\n        self.assertTrue(all(is_digital_contact_phone(lead.phone) for lead in report.leads))\n\n\nif __name__ == "__main__":\n    unittest.main()\n'''
    write("tests/test_phase84_lead_quality.py", test)

    # Syntax-check every modified Python file before keeping any change.
    for pth in ORIGINALS:
        if pth.suffix == ".py":
            compile(pth.read_text(encoding="utf-8"), str(pth), "exec")

except Exception as exc:
    rollback()
    print(f"[ERRO] Nenhuma alteração foi mantida: {exc}")
    sys.exit(1)

print("Phase 8.4 aplicada com sucesso.")
print(f"Arquivos alterados: {len(ORIGINALS)}")
print("Agora rode:")
print("  python -m unittest discover -s tests -v")
print("  git diff --check")
print("Depois reinicie: leadflow api")
