"""Runtime configuration. Provider secrets come from the environment or backend/.env only (server-side)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

ProviderName = Literal["openrouter", "ollama", "mock", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

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
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # ---- evaluation targets offered in the dashboard: "provider:model" comma-separated ----
    eval_targets: str = (
        "mock:mock-deterministic-v1,"
        "openrouter:nvidia/nemotron-3.5-super-vl:free,"
        "openrouter:google/gemma-4-31b-it:free,"
        "openrouter:dots-studio/dots-3-note-preview:free,"
        "ollama:llama3.2"
    )

    # ---- decision gate (see docs/GATE_DESIGN.md) ----
    # rules = deterministic only (default, free) | llm = structured-output LLM gate | jev = EXPERIMENTAL Jev.
    # Rules always run as the safety floor; external gates fall back to rules on any failure.
    decision_gate_provider: Literal["rules", "llm", "jev"] = "rules"
    decision_gate_llm_target: str | None = None  # provider:model; defaults to the chat default target
    # Allow the browser to pick a gate per turn / run LLM gate comparisons. Local demo convenience; set False on
    # any shared deployment (each llm/jev call costs money and sends the message to that provider).
    gate_override_enabled: bool = False  # GATE_OVERRIDE_ENABLED=true for local experiments only
    decision_gate_timeout_seconds: float = Field(default=8, gt=0, le=60)
    typesafe_api_key: SecretStr | None = None
    typesafe_base_url: str = "https://api.typesafe.ai"
    jev_model: str = "jev-latest"

    # ---- local paths ----
    data_path: Path = Path("data/um_ai_sprint_sample_residents.xlsx")
    db_path: Path = Path("data/mckinley_demo.sqlite3")
    prompt_path: Path = REPO_DIR / "prompts" / "mckinley_system_prompt.md"
    eval_results_path: Path = REPO_DIR / "evals" / "actual_results.json"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    def resolve(self, p: Path) -> Path:
        return p if p.is_absolute() else BACKEND_DIR / p

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def api_key_for(self, provider: str) -> str | None:
        specific = {"openrouter": self.openrouter_api_key, "anthropic": self.anthropic_api_key}.get(provider)
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
