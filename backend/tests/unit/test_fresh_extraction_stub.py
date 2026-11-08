"""Unit tests for the fresh_extraction stub (Task 15 precondition only).

Missing GEMINI_API_KEY -> configuration error, no OCR/Gemini performed. The
module must not import google-generativeai at top level.
"""

from __future__ import annotations

import pytest

from series76_data.pipeline.extractor_fresh import (
    FreshExtractionConfigError,
    FreshExtractionExtractor,
    require_gemini_api_key,
)


def test_missing_key_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(FreshExtractionConfigError):
        require_gemini_api_key()
    with pytest.raises(FreshExtractionConfigError):
        FreshExtractionExtractor().extract()


def test_empty_key_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(FreshExtractionConfigError):
        require_gemini_api_key()


def test_module_does_not_import_generativeai_at_top_level() -> None:
    import series76_data.pipeline.extractor_fresh as fresh

    # No google client bound in the module namespace.
    assert "genai" not in vars(fresh)
    assert "google" not in vars(fresh)
