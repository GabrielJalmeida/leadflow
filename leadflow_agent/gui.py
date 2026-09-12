from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .contracts import research_contract
from .errors import classify_error
from .export import export_report
from .models import SearchGoal
from .profiles import PROFILES, get_profile
from .runtime import RunBudget, RunController
from .segments import grouped_segments, resolve_segment
from .storage import LeadStore


@dataclass(slots=True)
class GuiSearchConfig:
    segment: str
    city: str
    state: str = ""
    country: str = "Brazil"
    limit: int = 10
    profile: str = "website-sales"
    provider: str = "auto"
    investigate: bool = True
    audit_websites: bool = True
    browser_audit: bool = False
    visual_audit: bool = False


def validate_gui_config(config: GuiSearchConfig) -> GuiSearchConfig:
    config.segment = config.segment.strip()
    config.city = config.city.strip()
    config.state = config.state.strip()
    config.country = config.country.strip() or "Brazil"

    if not config.segment:
        raise ValueError("Informe o segmento.")
    if not config.city:
        raise ValueError("Informe a cidade.")
    if config.limit < 1 or config.limit > 100:
        raise ValueError("A quantidade deve ficar entre 1 e 100 leads.")
    if config.profile not in PROFILES:
        raise ValueError(f"Perfil desconhecido: {config.profile}")
    if config.provider not in {"auto", "tavily", "brave", "outscraper"}:
        raise ValueError(f"Provider desconhecido: {config.provider}")
    return config


def lead_row_values(lead: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    opportunity = lead.get("opportunity") or {}
    contact = lead.get("contact") or {}
    website = lead.get("website") or {}
    opportunity_type = opportunity.get("type") or "unknown"
    actionable = "READY" if opportunity.get("actionable") else "VERIFY"
    return (
        str(opportunity.get("score", 0)),
        str(lead.get("name") or "Sem nome"),
        str(opportunity_type).replace("_", " ").upper(),
        actionable,
        str(contact.get("phone") or "—"),
        str(website.get("url") or "—"),
    )


def _format_lead_detail(lead: dict[str, Any]) -> str:
    location = lead.get("location") or {}
    contact = lead.get("contact") or {}
    website = lead.get("website") or {}
    identity = lead.get("identity") or {}
    opportunity = lead.get("opportunity") or {}

    identity_confidence = round(float(identity.get("confidence") or 0) * 100)
    lines = [
        str(lead.get("name") or "Sem nome"),
        "=" * 64,
        f"Opportunity Fit: {opportunity.get('score', 0)}/100",
        f"Tipo: {str(opportunity.get('type') or 'unknown').upper()}",
        f"Estado: {'READY' if opportunity.get('actionable') else 'VERIFY'}",
        f"Oferta sugerida: {opportunity.get('service_fit') or '—'}",
        "",
        "CONTATO",
        f"Telefone: {contact.get('phone') or '—'}",
        f"Email: {contact.get('email') or '—'}",
        f"Social: {', '.join(contact.get('socials') or []) or '—'}",
        "",
        "LOCALIZAÇÃO",
        f"Cidade/UF: {location.get('city') or '—'} / {location.get('state') or '—'}",
        f"País: {location.get('country') or '—'}",
        "",
        "IDENTIDADE",
        f"Estado: {str(identity.get('status') or 'unverified').upper()}",
        f"Identity Match: {identity_confidence}%",
        "",
        "WEBSITE",
        f"URL: {website.get('url') or '—'}",
        f"Estado: {str(website.get('status') or 'unknown').upper()}",
        f"Technical Health: {_score_or_dash(website.get('technical_score'))}",
        f"Browser UX: {_score_or_dash(website.get('browser_ux_score'))}",
        f"Visual Quality: {_score_or_dash(website.get('visual_score'))}",
    ]

    reasons = opportunity.get("reasons") or []
    cautions = opportunity.get("cautions") or []
    if reasons:
        lines.extend(["", "POR QUE É OPORTUNIDADE"])
        lines.extend(f"• {item}" for item in reasons)
    if cautions:
        lines.extend(["", "ATENÇÃO"])
        lines.extend(f"• {item}" for item in cautions)
    return "\n".join(lines)


def _score_or_dash(value: Any) -> str:
    return "—" if value is None else f"{value}/100"


def _run_gui_search(
    config: GuiSearchConfig,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Execute GUI v0 through the same core used by the CLI.

    The UI consumes only research_contract(), so later visual rewrites do not
    couple themselves to the full internal Lead dataclass.
    """

    # Imported lazily to keep `import leadflow_agent.gui` cheap and to avoid
    # creating a second provider-construction path during the first GUI phase.
    from .cli import _build_agent

    config = validate_gui_config(config)
    settings = Settings.load()
    if config.investigate and not settings.gemini_api_key:
        raise ValueError("Investigator requer Gemini configurado. Rode `leadflow setup`.")
    if config.visual_audit and not settings.gemini_api_key:
        raise ValueError("Visual IA requer Gemini configurado. Rode `leadflow setup`.")
    if config.browser_audit and importlib.util.find_spec("playwright") is None:
        raise ValueError('Browser/UX requer Playwright. Instale com `pip install -e ".[browser]"`.')

    controller = RunController(
        RunBudget(
            max_search_calls=20,
            max_llm_calls=30,
            max_website_audits=25,
            max_browser_audits=10,
            max_visual_audits=10,
        ),
        cancel_check=cancel_check,
    )
    selected_provider, agent = _build_agent(
        settings,
        no_ai=False,
        provider_name=config.provider,
        use_cache=True,
        refresh_cache=False,
        cache_ttl_days=14,
        use_memory=True,
        run_controller=controller,
    )

    preset = resolve_segment(config.segment)
    segment = preset.label if preset is not None else config.segment
    goal = SearchGoal(
        segment=segment,
        city=config.city,
        state=config.state,
        country=config.country,
        limit=config.limit,
        prefer_no_website=True,
    )
    lead_filter = get_profile(config.profile).filters()

    audit_websites = config.audit_websites or config.browser_audit or config.visual_audit
    browser_audit = config.browser_audit or config.visual_audit
    bounded = min(config.limit, 3)
    report = agent.research(
        goal,
        max_queries=6,
        investigate=config.investigate,
        investigation_limit=bounded,
        investigation_budget=2,
        audit_websites=audit_websites,
        audit_limit=bounded,
        audit_timeout=8.0,
        audit_ttl_days=7,
        browser_audit=browser_audit,
        browser_audit_limit=bounded,
        browser_timeout=12.0,
        browser_audit_ttl_days=7,
        visual_audit=config.visual_audit,
        visual_audit_limit=bounded,
        visual_audit_ttl_days=14,
        lead_filter=lead_filter,
        filter_pool_multiplier=2,
    )

    csv_path, json_path = export_report(report)
    store = LeadStore(settings.db_path)
    try:
        run_id = store.save_report(report)
        total = store.count_leads()
    finally:
        store.close()

    return {
        "contract": research_contract(report),
        "provider": selected_provider,
        "csv_path": str(csv_path.resolve()),
        "json_path": str(json_path.resolve()),
        "run_id": run_id,
        "total_leads": total,
    }


def launch_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:
        print(
            "A GUI v0 requer Tkinter. No Windows, use a instalação oficial do Python; "
            "no Linux, instale o pacote Tk da sua distribuição.",
            file=sys.stderr,
        )
        return 2

    class LeadFlowGUI:
        def __init__(self, root: Any):
            self.root = root
            self.root.title("LeadFlow — Frontend v0")
            self.root.geometry("1180x760")
            self.root.minsize(980, 620)
            self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
            self.cancel_event = threading.Event()
            self.worker: threading.Thread | None = None
            self.leads: list[dict[str, Any]] = []

            self._build_style(ttk)
            self._build_ui(tk, ttk, messagebox)
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.after(100, self._drain_events)

        def _build_style(self, ttk: Any) -> None:
            style = ttk.Style(self.root)
            available = set(style.theme_names())
            for preferred in ("vista", "xpnative", "winnative", "clam"):
                if preferred in available:
                    try:
                        style.theme_use(preferred)
                    except Exception:
                        pass
                    break
            style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
            style.configure("Status.TLabel", font=("Segoe UI", 9, "bold"))

        def _build_ui(self, tk: Any, ttk: Any, messagebox: Any) -> None:
            self.messagebox = messagebox
            outer = ttk.Frame(self.root, padding=10)
            outer.pack(fill="both", expand=True)

            ttk.Label(outer, text="LeadFlow", style="Title.TLabel").pack(anchor="w")
            ttk.Label(outer, text="Frontend v0 — funcional primeiro, visual depois").pack(anchor="w", pady=(0, 8))

            search_box = ttk.LabelFrame(outer, text="Pesquisar leads", padding=8)
            search_box.pack(fill="x")

            presets: list[str] = []
            for items in grouped_segments().values():
                presets.extend(item.label for item in items)
            presets = sorted(dict.fromkeys(presets), key=str.casefold)

            self.segment_var = tk.StringVar(value="Marcenaria")
            self.city_var = tk.StringVar(value="Praia Grande")
            self.state_var = tk.StringVar(value="SP")
            self.limit_var = tk.IntVar(value=10)
            self.profile_var = tk.StringVar(value="website-sales")
            self.provider_var = tk.StringVar(value="auto")
            self.investigate_var = tk.BooleanVar(value=True)
            self.audit_var = tk.BooleanVar(value=True)
            self.browser_var = tk.BooleanVar(value=False)
            self.visual_var = tk.BooleanVar(value=False)

            fields = ttk.Frame(search_box)
            fields.pack(fill="x")

            ttk.Label(fields, text="Segmento").grid(row=0, column=0, sticky="w")
            ttk.Combobox(fields, textvariable=self.segment_var, values=presets, width=31).grid(row=1, column=0, padx=(0, 8), sticky="ew")
            ttk.Label(fields, text="Cidade").grid(row=0, column=1, sticky="w")
            ttk.Entry(fields, textvariable=self.city_var, width=27).grid(row=1, column=1, padx=(0, 8), sticky="ew")
            ttk.Label(fields, text="UF").grid(row=0, column=2, sticky="w")
            ttk.Entry(fields, textvariable=self.state_var, width=7).grid(row=1, column=2, padx=(0, 8), sticky="ew")
            ttk.Label(fields, text="Leads").grid(row=0, column=3, sticky="w")
            ttk.Spinbox(fields, from_=1, to=100, textvariable=self.limit_var, width=7).grid(row=1, column=3, padx=(0, 8), sticky="ew")
            ttk.Label(fields, text="Perfil").grid(row=0, column=4, sticky="w")
            ttk.Combobox(fields, textvariable=self.profile_var, values=tuple(PROFILES.keys()), state="readonly", width=18).grid(row=1, column=4, padx=(0, 8), sticky="ew")
            ttk.Label(fields, text="Provider").grid(row=0, column=5, sticky="w")
            ttk.Combobox(fields, textvariable=self.provider_var, values=("auto", "tavily", "brave", "outscraper"), state="readonly", width=12).grid(row=1, column=5, sticky="ew")
            fields.columnconfigure(0, weight=1)
            fields.columnconfigure(1, weight=1)

            options = ttk.Frame(search_box)
            options.pack(fill="x", pady=(8, 0))
            ttk.Checkbutton(options, text="Investigar", variable=self.investigate_var).pack(side="left", padx=(0, 12))
            ttk.Checkbutton(options, text="Auditar site", variable=self.audit_var).pack(side="left", padx=(0, 12))
            ttk.Checkbutton(options, text="Browser/UX", variable=self.browser_var).pack(side="left", padx=(0, 12))
            ttk.Checkbutton(options, text="Visual IA", variable=self.visual_var).pack(side="left", padx=(0, 12))
            self.search_button = ttk.Button(options, text="BUSCAR LEADS", command=self.start_search)
            self.search_button.pack(side="right")
            self.cancel_button = ttk.Button(options, text="Cancelar", command=self.cancel_search, state="disabled")
            self.cancel_button.pack(side="right", padx=(0, 8))

            status_bar = ttk.Frame(outer)
            status_bar.pack(fill="x", pady=(8, 5))
            self.status_var = tk.StringVar(value="Pronto.")
            ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
            self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=180)
            self.progress.pack(side="right")

            body = ttk.Panedwindow(outer, orient="vertical")
            body.pack(fill="both", expand=True)
            results_frame = ttk.LabelFrame(body, text="Resultados", padding=5)
            log_frame = ttk.LabelFrame(body, text="Resumo da execução", padding=5)
            body.add(results_frame, weight=3)
            body.add(log_frame, weight=1)

            columns = ("score", "name", "type", "status", "phone", "website")
            self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", selectmode="browse")
            headings = {"score": "Fit", "name": "Empresa", "type": "Oportunidade", "status": "Estado", "phone": "Telefone", "website": "Website"}
            widths = {"score": 60, "name": 260, "type": 140, "status": 80, "phone": 150, "website": 340}
            for key in columns:
                self.tree.heading(key, text=headings[key])
                self.tree.column(key, width=widths[key], anchor="w")
            self.tree.column("score", anchor="center")
            self.tree.column("status", anchor="center")
            self.tree.pack(side="left", fill="both", expand=True)
            scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
            scroll.pack(side="right", fill="y")
            self.tree.configure(yscrollcommand=scroll.set)
            self.tree.bind("<Double-1>", self.open_selected_lead)

            self.log = tk.Text(log_frame, height=9, wrap="word", font=("Consolas", 9))
            self.log.pack(side="left", fill="both", expand=True)
            log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
            log_scroll.pack(side="right", fill="y")
            self.log.configure(yscrollcommand=log_scroll.set)

            hint = ttk.Frame(outer)
            hint.pack(fill="x", pady=(5, 0))
            ttk.Label(hint, text="Dê duplo clique em um lead para abrir os detalhes.").pack(side="left")
            ttk.Button(hint, text="Como configurar APIs", command=self._show_setup_help).pack(side="right")

        def _show_setup_help(self) -> None:
            self.messagebox.showinfo(
                "Configuração",
                "As chaves continuam no fluxo BYOK atual.\n\n"
                "Abra o terminal na pasta do projeto e execute:\n\n"
                "leadflow setup\n\nDepois volte para esta janela.",
            )

        def _config(self) -> GuiSearchConfig:
            return GuiSearchConfig(
                segment=self.segment_var.get(),
                city=self.city_var.get(),
                state=self.state_var.get(),
                limit=int(self.limit_var.get()),
                profile=self.profile_var.get(),
                provider=self.provider_var.get(),
                investigate=bool(self.investigate_var.get()),
                audit_websites=bool(self.audit_var.get()),
                browser_audit=bool(self.browser_var.get()),
                visual_audit=bool(self.visual_var.get()),
            )

        def start_search(self) -> None:
            if self.worker is not None and self.worker.is_alive():
                return
            try:
                config = validate_gui_config(self._config())
            except (TypeError, ValueError) as exc:
                self.messagebox.showerror("Busca inválida", str(exc))
                return

            self.cancel_event.clear()
            self.leads = []
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.log.delete("1.0", "end")
            self._append_log(
                f"Segmento: {config.segment}\nCidade: {config.city}/{config.state}\n"
                f"Leads: {config.limit}\nPerfil: {config.profile}\nProvider: {config.provider}\n\n"
            )
            self.status_var.set("Pesquisando...")
            self.search_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")
            self.progress.start(12)

            self.worker = threading.Thread(target=self._worker_run, args=(config,), daemon=True)
            self.worker.start()

        def _worker_run(self, config: GuiSearchConfig) -> None:
            try:
                result = _run_gui_search(config, cancel_check=self.cancel_event.is_set)
                self.events.put(("done", result))
            except Exception as exc:
                settings = Settings.load()
                public = classify_error(exc, secrets=settings.secret_values())
                self.events.put(("error", f"{public.code.value}: {public.message}"))

        def _drain_events(self) -> None:
            try:
                while True:
                    kind, payload = self.events.get_nowait()
                    if kind == "done":
                        self._finish_search(payload)
                    elif kind == "error":
                        self._finish_error(str(payload))
            except queue.Empty:
                pass
            finally:
                self.root.after(100, self._drain_events)

        def _append_log(self, text: str) -> None:
            self.log.insert("end", text)
            self.log.see("end")

        def _finish_search(self, result: dict[str, Any]) -> None:
            self.progress.stop()
            self.search_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")

            contract = result["contract"]
            run = contract.get("run") or {}
            self.leads = [item for item in contract.get("leads") or [] if isinstance(item, dict)]
            self._render_results()
            status = str(run.get("status") or "completed")
            self.status_var.set(f"{len(self.leads)} leads — {status}.")
            self._append_log(
                f"Status: {status}\n"
                f"Provider: {result.get('provider')}\n"
                f"Retornados: {run.get('returned_results', len(self.leads))}/{run.get('requested_results', '?')}\n"
                f"Uso: {run.get('usage', {})}\n"
                f"CSV: {result.get('csv_path')}\n"
                f"JSON: {result.get('json_path')}\n"
                f"DB: pesquisa #{result.get('run_id')} | {result.get('total_leads')} leads acumulados\n"
            )
            if status == "cancelled":
                self._append_log("\nA execução foi cancelada com segurança pelo RunController.\n")

        def _finish_error(self, detail: str) -> None:
            self.progress.stop()
            self.search_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            self.status_var.set("Falha na pesquisa.")
            self._append_log(detail + "\n")
            self.messagebox.showerror("LeadFlow", detail)

        def _render_results(self) -> None:
            for item in self.tree.get_children():
                self.tree.delete(item)
            for index, lead in enumerate(self.leads):
                self.tree.insert("", "end", iid=str(index), values=lead_row_values(lead))

        def cancel_search(self) -> None:
            if self.worker is None or not self.worker.is_alive():
                return
            self.cancel_event.set()
            self.status_var.set("Cancelamento solicitado...")
            self.cancel_button.configure(state="disabled")

        def open_selected_lead(self, _event: Any = None) -> None:
            selection = self.tree.selection()
            if not selection:
                return
            try:
                lead = self.leads[int(selection[0])]
            except (IndexError, ValueError):
                return

            window = tk.Toplevel(self.root)
            window.title(str(lead.get("name") or "Lead"))
            window.geometry("760x620")
            content = ttk.Frame(window, padding=10)
            content.pack(fill="both", expand=True)
            text = tk.Text(content, wrap="word", font=("Consolas", 10))
            text.pack(fill="both", expand=True)
            text.insert("1.0", _format_lead_detail(lead))
            text.configure(state="disabled")

            buttons = ttk.Frame(content)
            buttons.pack(fill="x", pady=(8, 0))
            website = (lead.get("website") or {}).get("url")
            if website:
                ttk.Button(buttons, text="Abrir website", command=lambda: webbrowser.open(str(website))).pack(side="left")
            socials = (lead.get("contact") or {}).get("socials") or []
            if socials:
                ttk.Button(buttons, text="Abrir social", command=lambda: webbrowser.open(str(socials[0]))).pack(side="left", padx=(6, 0))
            ttk.Button(buttons, text="Fechar", command=window.destroy).pack(side="right")

        def _on_close(self) -> None:
            self.cancel_event.set()
            self.root.destroy()

    root = tk.Tk()
    LeadFlowGUI(root)
    root.mainloop()
    return 0
