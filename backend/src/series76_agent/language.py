"""Deterministic response-language resolution (Req 9.5).

The response language is the natural language of the last user turn, unless
the user explicitly asks for a switch. A turn with no detectable natural
language (a part number, an ordinal, numbers only) keeps the previous turn's
language. Part numbers and units never influence detection.
"""

from __future__ import annotations

import re
import unicodedata

from series76_agent.domain.enums import Language

_EN_WORDS = frozenset(
    """the an and or of for with what which who is are was show me compare give find list
    does do how many more less than between need needs want recommend recommendation parts
    part please that this it one first second third to on at by from all any can you my
    speed current fastest highest lowest best only also about tell details detail look
    search filter enclosure supply service torque available documented notes note convert
    into should would could your these those their there here where when why if not same
    other which best""".split()
)
_ES_WORDS = frozenset(
    """el la los las un una unos unas de del y que qué cuál cuáles cual cuales con para por
    es son muestra muéstrame muestrame dame compara busca buscar lista necesito quiero
    recomienda recomiéndame recomiendame recomendación partes parte velocidad corriente
    segundo segunda primero primera tercero tercera en entre más mas menos cuántos cuantos
    cuántas ese esa este esta eso favor mi tengo hay sin sobre también tambien cómo como
    dónde donde cuándo cuando datos convierte convertir alimentación servicio envolvente
    notas nota mismo misma otro otra tiene tienen puedes podrías dime detalles solo sólo""".split()
)
_ES_MARKERS = re.compile(r"[ñáéíóú¿¡]")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

_SWITCH_TO_EN = re.compile(
    r"\b(in english|answer in english|reply in english|respond in english|" r"en ingl[eé]s)\b",
    re.IGNORECASE,
)
_SWITCH_TO_ES = re.compile(
    r"\b(in spanish|answer in spanish|reply in spanish|respond in spanish|"
    r"en espa[nñ]ol|en castellano)\b",
    re.IGNORECASE,
)


def explicit_switch(message: str) -> Language | None:
    """An explicit language request in the message, if any."""

    to_en = bool(_SWITCH_TO_EN.search(message))
    to_es = bool(_SWITCH_TO_ES.search(message))
    if to_en and not to_es:
        return Language.EN
    if to_es and not to_en:
        return Language.ES
    return None


def detect_language(message: str, *, ignore: tuple[str, ...] = ()) -> Language | None:
    """Detect ES/EN from natural-language words; ``None`` if undetectable.

    ``ignore`` removes known identifiers (part numbers) before detection.
    """

    text = message
    for token in ignore:
        if token:
            text = text.replace(token, " ")
    lowered = unicodedata.normalize("NFC", text.lower())
    words = _WORD.findall(lowered)
    es = sum(1 for w in words if w in _ES_WORDS)
    en = sum(1 for w in words if w in _EN_WORDS)
    if _ES_MARKERS.search(lowered):
        es += 1
    if es == 0 and en == 0:
        return None
    if es == en:
        return None
    return Language.ES if es > en else Language.EN


def resolve_language(
    message: str,
    previous: Language | None,
    *,
    ignore: tuple[str, ...] = (),
    default: Language = Language.EN,
) -> Language:
    """Apply the Req 9.5 rule: explicit switch > detected > previous > default."""

    switched = explicit_switch(message)
    if switched is not None:
        return switched
    detected = detect_language(message, ignore=ignore)
    if detected is not None:
        return detected
    return previous if previous is not None else default
