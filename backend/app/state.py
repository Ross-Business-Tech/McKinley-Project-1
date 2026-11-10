"""Process-wide app state (settings, workbook, store, LLM gateway) created at startup."""

import logging
from dataclasses import dataclass

from app.chat_engine import EngineDeps
from app.config import Settings, get_settings
from app.context import Workbook, WorkbookError, load_workbook, workbook_from_rows
from app.db import Store
from app.llm import LLMGateway

log = logging.getLogger("mckinley")


@dataclass
class AppState:
    deps: EngineDeps
    store: Store
    data_error: str | None


_state: AppState | None = None


def load_residents(settings: Settings, store: Store) -> tuple[Workbook | None, str | None]:
    """Synthetic resident data from the workbook file or the database tables (RESIDENT_DATA_SOURCE)."""
    mode = settings.resident_data_source
    path = settings.resolve(settings.data_path)
    if mode == "file" or (mode == "auto" and path.exists()):
        try:
            wb = load_workbook(path)
            for w in wb.warnings:
                log.warning("workbook: %s", w)
            return wb, None
        except WorkbookError as e:
            log.warning("workbook unavailable: %s", e)
            return None, str(e)
    rows = store.reference_rows()
    if rows is None:
        msg = ("No resident data: the workbook file is absent and the database has no synthetic reference rows "
               "(run `uv run alembic upgrade head` then `uv run python -m app.seed_synthetic`).")
        log.warning(msg)
        return None, msg
    residents, interactions, meta = rows
    log.info("resident data loaded from the database (%d residents, %s)", len(residents),
             meta.get("source", "unknown source"))
    return workbook_from_rows(residents, interactions, f"database ({meta.get('source', 'synthetic seed')})"), None


def build_state(settings: Settings | None = None, gateway: LLMGateway | None = None,
                workbook: Workbook | None = None, store: Store | None = None) -> AppState:
    settings = settings or get_settings()
    data_error = None
    db_url = settings.database_url.get_secret_value().strip() if settings.database_url else ""
    store = store or Store(settings.resolve(settings.db_path), database_url=db_url or None)
    if workbook is None:
        workbook, data_error = load_residents(settings, store)
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
