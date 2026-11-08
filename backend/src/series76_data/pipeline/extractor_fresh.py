"""fresh_extraction Extractor — stub (Spec 1, Task 15; full impl is separate).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
Extractor (fresh_extraction) and § Two Ingestion Modes.

``fresh_extraction`` re-derives candidates from the PDF using local OCR plus
Gemini and **requires** a non-empty ``GEMINI_API_KEY`` from the process
environment (Req 2.4). If the key is absent it reports a configuration error and
performs **no** OCR/Gemini (Req 2.5). Its output is never published directly.

The full OCR + Gemini implementation needs optional dependencies (the ``ocr``
extra) and is delivered separately. This module is a clearly-marked stub: it
verifies the credential precondition and never imports ``google-generativeai``
at module top level, so importing it is cheap and side-effect free. Attempting a
run without the key raises a configuration error before any extraction.
"""

from __future__ import annotations

import os


class FreshExtractionConfigError(RuntimeError):
    """Raised when fresh_extraction is attempted without required configuration.

    This is a *configuration* error (a missing credential), not an ingestion
    taxonomy failure: no document/row/cell unit has been processed yet, so no
    taxonomy code applies. No OCR or Gemini call is made when it is raised.
    """


def require_gemini_api_key() -> str:
    """Return a non-empty ``GEMINI_API_KEY`` or raise a configuration error.

    Raises:
        FreshExtractionConfigError: if ``GEMINI_API_KEY`` is unset or empty. No
            OCR/Gemini work is performed (Req 2.5).
    """

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise FreshExtractionConfigError(
            "fresh_extraction requires a non-empty GEMINI_API_KEY; "
            "no OCR or Gemini extraction was performed"
        )
    return key


class FreshExtractionExtractor:
    """Stub for the fresh_extraction mode.

    The OCR + Gemini path (and its optional dependencies) is implemented
    separately. This stub enforces the credential precondition and refuses to
    run otherwise.
    """

    def extract(self) -> None:
        """Check configuration, then signal that the full path is not wired here.

        Raises:
            FreshExtractionConfigError: if ``GEMINI_API_KEY`` is missing (checked
                first, so a misconfiguration is reported before anything else),
                or — when the key is present — to indicate the OCR/Gemini
                implementation is delivered separately (no top-level import of
                ``google-generativeai`` happens in this module).
        """

        require_gemini_api_key()
        raise FreshExtractionConfigError(
            "fresh_extraction OCR + Gemini implementation is delivered separately "
            "(optional 'ocr' dependency extra); this stub does not perform it"
        )
