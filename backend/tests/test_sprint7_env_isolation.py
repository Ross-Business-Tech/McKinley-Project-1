"""Tests never read backend/.env: a developer's real DATABASE_URL (e.g. Supabase) or provider key there must never
reach a test, a migration or a seed run started by the suite (Sprint 7: a real DATABASE_URL in .env was picked up
by the seed test through get_settings())."""


def test_settings_in_tests_ignore_the_env_file():
    from app.config import Settings, get_settings

    assert Settings.model_config.get("env_file") is None
    s = get_settings()
    assert not (s.database_url and s.database_url.get_secret_value().strip())
    assert not s.openrouter_api_key and not s.gemini_api_key and not s.staff_api_token
