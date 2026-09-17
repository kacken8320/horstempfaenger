from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect

# langdetect ist nicht-deterministisch ohne festen Seed.
DetectorFactory.seed = 0

ALLOWED_LANGUAGES = ("de", "en")
FALLBACK_LANGUAGE = "en"


def detect_language(text: str) -> str:
    """Erkennt die Sprache von `text`. Bei Unsicherheit/Fehler: Fallback auf Englisch."""
    text = text.strip()
    if not text:
        return FALLBACK_LANGUAGE
    try:
        return detect(text)
    except LangDetectException:
        return FALLBACK_LANGUAGE
