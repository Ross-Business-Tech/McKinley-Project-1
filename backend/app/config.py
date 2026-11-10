"""Runtime configuration. Provider secrets come from the environment or backend/.env only (server-side)."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

ProviderName = Literal["gemini", "openrouter", "ollama", "mock", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # ---- where this runs ----
    # local = a developer machine (defaults stay convenient). hosted = ANY shared deployment (Render, a team demo):
    # startup refuses unsafe settings (see hosted_problems). "hosted" does not mean production ready.
    app_env: Literal["local", "hosted"] = "local"
    # Demo personas (the "Demo sign-in" picker) let anyone act as any SYNTHETIC account. That is NOT authentication.
    # Unset = on for APP_ENV=local, off for hosted. DEMO_PERSONAS_ENABLED=true is refused on a hosted backend
    # (hosted_problems). See app/auth.py and docs/security/AUTHORIZATION_BOUNDARIES.md.
    demo_personas_enabled: bool | None = None
    # Structured understanding layer (app/understanding.py): rules (default, deterministic) | model | auto. The model
    # pass may only add acts/entities; it never mutates state, grants access or confirms a save.
    understanding_provider: Literal["rules", "model", "auto"] = "rules"
    understanding_timeout_seconds: float = 5.0

    # ---- default target used by /api/chat ----
    llm_provider: ProviderName = "openrouter"
    llm_model: str = "nvidia/nemotron-3.5-super-vl:free"
    # Generic overrides for the *default* provider (optional; provider-specific values below also work).
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None

    # ---- shared generation settings (identical for baseline and aware) ----
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_tokens: int = Field(default=4000, ge=128, le=16000)
    llm_timeout_seconds: float = Field(default=60, gt=0, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    # ---- provider-specific ----
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_title: str = "McKinley AI Prototype (synthetic data)"
    ollama_base_url: str = "http://localhost:11434"
    anthropic_api_key: SecretStr | None = None
    # Gemini Developer API (Google AI Studio key). The intended provider for deployed environments.
    # gemini-3.6-flash: stable model listed in Google's model docs (checked 2026-11-10); verify with
    # `uv run python -m app.live_eval.preflight` once a key exists. Change it deliberately, never silently.
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.6-flash"
    # Thinking depth, pinned so a server-side default change can't silently alter evaluations. Empty = the model's
    # default (recorded as such). Levels per Google's thinking guide; verify which ones the model accepts.
    gemini_thinking_level: Literal["", "minimal", "low", "medium", "high"] = ""
    # OpenRouter unified `reasoning` parameter. Empty = the model's default (not sent). "none" turns reasoning off;
    # the other values set its effort. Recorded on every call; never changes the model.
    openrouter_reasoning_effort: Literal["", "none", "minimal", "low", "medium", "high"] = ""
    # Central live-call budget: 0 = unlimited. Counted across processes when LLM_CALL_LEDGER is set (one JSON line
    # per real model call, metadata only: no prompts, no replies, no keys). Mock calls are never counted.
    llm_call_budget: int = 0
    llm_call_ledger: Path | None = None
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # ---- evaluation targets offered in the dashboard: "provider:model" comma-separated ----
    eval_targets: str = (
        "mock:mock-deterministic-v1,"
        "openrouter:nvidia/nemotron-3.5-super-vl:free,"
        "openrouter:google/gemma-4-31b-it:free,"
        "openrouter:dots-studio/dots-3-note-preview:free,"
        "ollama:llama3.2,"
        "gemini:gemini-3.6-flash"
    )

    # ---- decision gate (see docs/architecture/decision-gate.md) ----
    # rules = deterministic only (default, free) | llm = structured-output LLM gate | jev = EXPERIMENTAL Jev.
    # Rules always run as the safety floor; external gates fall back to rules on any failure.
    decision_gate_provider: Literal["rules", "llm", "jev"] = "rules"
    decision_gate_llm_target: str | None = None  # provider:model; defaults to the chat default target
    # Allow the browser to pick a gate per turn / run LLM gate comparisons. Local demo convenience; set False on
    # any shared deployment (each llm/jev call costs money and sends the message to that provider).
    gate_override_enabled: bool = False  # GATE_OVERRIDE_ENABLED=true for local experiments only
    decision_gate_timeout_seconds: float = Field(default=8, gt=0, le=60)
    typesafe_api_key: SecretStr | None = None
    # Staff/eval/diagnostics routes: loopback-only unless this token is set (then the X-Staff-Token header).
    staff_api_token: SecretStr | None = None
    typesafe_base_url: str = "https://api.typesafe.ai"
    # ---- semantic safety classifier (layer 2, see docs/safety/safety-evaluation.md) ----
    # auto = run when the target provider is ready (has a key) and is not the mock; off = never. One extra model call
    # per non-baseline turn. It never removes a rules alert; it may only drop the broad 911 care line (policy R7).
    safety_classifier: Literal["auto", "off"] = "auto"
    safety_classifier_target: str | None = None  # provider:model; defaults to the chat default target
    safety_classifier_timeout_seconds: float = Field(default=6, gt=0, le=60)
    jev_model: str = "jev-latest"

    # ---- local paths ----
    data_path: Path = Path("data/um_ai_sprint_sample_residents.xlsx")
    db_path: Path = Path("data/mckinley_demo.sqlite3")
    # Optional Postgres connection string (for example Supabase). When set it replaces the SQLite file above.
    database_url: SecretStr | None = None
    # Where synthetic resident data comes from: auto = the workbook file if present, else the database tables
    # loaded by `python -m app.seed_synthetic` (a hosted backend has no git-ignored XLSX); file; database.
    resident_data_source: Literal["auto", "file", "database"] = "auto"
    prompt_path: Path = REPO_DIR / "prompts" / "mckinley_system_prompt.md"
    eval_results_path: Path = REPO_DIR / "evals" / "actual_results.json"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @model_validator(mode="after")
    def _provider_default_model(self) -> "Settings":
        """LLM_PROVIDER=gemini without an explicit LLM_MODEL uses GEMINI_MODEL (one model per run, chosen up front)."""
        if self.llm_provider == "gemini" and ("llm_model" not in self.model_fields_set or not self.llm_model.strip()):
            self.llm_model = self.gemini_model
        if self.llm_provider == "gemini" and not self.llm_model.startswith("gemini"):
            raise ValueError(f"LLM_PROVIDER=gemini but LLM_MODEL={self.llm_model!r} is not a Gemini model; leave "
                             "LLM_MODEL empty to use GEMINI_MODEL")
        return self

    def resolve(self, p: Path) -> Path:
        return p if p.is_absolute() else BACKEND_DIR / p

    @property
    def demo_personas_allowed(self) -> bool:
        """Effective switch: demo personas only on a local deployment (never on APP_ENV=hosted)."""
        if self.app_env == "hosted":
            return False
        return True if self.demo_personas_enabled is None else self.demo_personas_enabled

    def hosted_problems(self) -> list[str]:
        """Settings that are unsafe on a shared deployment. Messages never contain secret values."""
        if self.app_env != "hosted":
            return []
        out = []
        origins = self.cors_origin_list
        if not origins or any(o == "*" or "*" in o for o in origins):
            out.append("CORS_ORIGINS must list the exact website address(es); wildcards are not allowed")
        elif not all(re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", o) for o in origins):
            out.append("each CORS_ORIGINS entry must be a bare origin like https://site.vercel.app (no path)")
        if any(o.startswith(("http://localhost", "http://127.0.0.1")) for o in origins):
            out.append("CORS_ORIGINS must not include localhost addresses on a hosted backend")
        if any(o.startswith("http://") for o in origins if not o.startswith(("http://localhost", "http://127."))):
            out.append("CORS_ORIGINS must use https:// addresses")
        token = self.staff_api_token.get_secret_value().strip() if self.staff_api_token else ""
        if len(token) < 24 or len(set(token)) < 8:
            out.append("STAFF_API_TOKEN must be set (24+ random characters) so staff routes are not open")
        if self.gate_override_enabled:
            out.append("GATE_OVERRIDE_ENABLED must be false")
        if self.demo_personas_enabled:
            out.append("DEMO_PERSONAS_ENABLED must be false: demo personas are not authentication, so a shared "
                       "deployment must not let anyone act as a resident account")
        if not (self.database_url and self.database_url.get_secret_value().strip()):
            out.append("DATABASE_URL must be set (a hosted backend's local SQLite file is lost on every restart)")
        return out

    @property
    def cors_origin_list(self) -> list[str]:
        # browsers send the origin without a trailing slash; a pasted "https://x.vercel.app/" would block every request
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip().rstrip("/")]

    def api_key_for(self, provider: str) -> str | None:
        specific = {"openrouter": self.openrouter_api_key, "anthropic": self.anthropic_api_key,
                    "gemini": self.gemini_api_key}.get(provider)
        key = specific or (self.llm_api_key if provider == self.llm_provider else None)
        value = key.get_secret_value().strip() if key else ""
        return value or None

    def base_url_for(self, provider: str) -> str | None:
        if provider == self.llm_provider and self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        return {"openrouter": self.openrouter_base_url, "ollama": self.ollama_base_url}.get(provider)


@lru_cache
def get_settings() -> Settings:
    return Settings()
