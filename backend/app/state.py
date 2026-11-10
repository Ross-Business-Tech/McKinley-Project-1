"""Process-wide app state (settings, workbook, store, LLM gateway) created at startup."""

import logging
from dataclasses import dataclass

from app.chat_engine import EngineDeps
from app.config import Settings, get_settings
from app.context import Workbook, WorkbookError, load_workbook
from app.db import Store
from app.llm import LLMGateway

log = logging.getLogger("mckinley")


@dataclass
class AppState:
    deps: EngineDeps
    store: Store
    data_error: str | None


_state: AppState | None = None


def build_state(settings: Settings | None = None, gateway: LLMGateway | None = None,
                workbook: Workbook | None = None, store: Store | None = None) -> AppState:
    settings = settings or get_settings()
    data_error = None
    if workbook is None:
        try:
            workbook = load_workbook(settings.resolve(settings.data_path))
            for w in workbook.warnings:
                log.warning("workbook: %s", w)
        except WorkbookError as e:
            data_error = str(e)
            log.warning("workbook unavailable: %s", e)
    db_url = settings.database_url.get_secret_value().strip() if settings.database_url else ""
    store = store or Store(settings.resolve(settings.db_path), database_url=db_url or None)
    deps = EngineDeps(settings=settings, llm=gateway or LLMGateway(settings), store=store, workbook=workbook)
    return AppState(deps=deps, store=store, data_error=data_error)


def set_state(state: AppState) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = build_state()
    return _state
