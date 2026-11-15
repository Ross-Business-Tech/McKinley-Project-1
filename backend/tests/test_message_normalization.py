"""Startup + input normalization: the backend must import, and every Unicode line break becomes one newline.

Regression: the U+2028/U+2029 keys of chat_engine._LINE_BREAKS were once stored as raw invisible characters, which an
editor stripped, leaving empty keys and a ValueError at import. Keep them as escapes."""

import importlib

import pytest


def test_the_app_imports():
    assert importlib.import_module("app.main").app is not None


def test_line_break_table_uses_single_character_keys():
    from app.chat_engine import _LINE_BREAKS
    assert set(_LINE_BREAKS) == {ord(c) for c in "\r  \x0b\x0c\x85"}


@pytest.mark.parametrize("sep", ["\r\n", "\r", " ", " ", "\x0b", "\x0c", "\x85", "\n \r\n"])
def test_unicode_line_breaks_become_one_newline(sep):
    from app.chat_engine import clean_message
    assert clean_message(f"my sink{sep}is leaking") == "my sink\nis leaking"


def test_spaces_collapse_and_long_break_runs_stay_bounded():
    from app.chat_engine import clean_message
    assert clean_message("  my   sink \t is leaking  ") == "my sink is leaking"
    assert clean_message("if my dad " + " " * 1985 + "x") == "if my dad\nx"
