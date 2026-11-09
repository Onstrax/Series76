"""Typed-placeholder rendering of user-visible text (Req 8.1, 8.2, 12.1, 12.7).

Visible text is assembled from :class:`Segment`s. Only these segment kinds may
introduce a digit:

* :class:`Fig` — a figure of the turn's verified figure set (Spec 2 fact or
  deterministic derivation), rendered with its unit and context;
* :class:`Pn` — a part number present in a typed Spec 2 result;
* :class:`Count` — an integer count produced by a Spec 2 operation;
* :class:`Note` — the literal text of a documented source note;
* :class:`UserEcho` — a token the user typed (a declared requirement or the
  part number they asked about), always labeled as theirs;
* :class:`Ident` — a non-technical identifier (edition label, plan revision,
  correlation id).

:class:`Lit` (template text) is **rejected at construction if it contains a
digit** (outside a tiny vocabulary of non-figure labels such as "S4"). So a
rendered answer cannot contain a number that did not come from a typed slot —
which is what :func:`untraceable_digit_runs` re-checks on the final string.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: Label vocabulary that contains digits but is not a technical figure.
NON_FIGURE_TOKENS: frozenset[str] = frozenset({"S4"})

_DIGIT_RUN = re.compile(r"\d+")
_TOKEN = re.compile(r"[A-Za-z]*\d[\w]*")


class RenderError(ValueError):
    """A literal carried a digit, or a slot referenced an unbound value."""


def _strip_vocab(text: str) -> str:
    out = text
    for token in NON_FIGURE_TOKENS:
        out = re.sub(rf"\b{re.escape(token)}\b", "", out)
    return out


def literal_is_digit_free(text: str) -> bool:
    """True iff ``text`` has no digit outside the non-figure vocabulary."""
    return not any(ch.isdigit() for ch in _strip_vocab(text))


@dataclass(frozen=True, slots=True)
class Lit:
    """Template text. Must not contain a digit (no free numbers)."""

    text: str

    def __post_init__(self) -> None:
        if not literal_is_digit_free(self.text):
            raise RenderError(f"literal text may not contain a number: {self.text!r}")


@dataclass(frozen=True, slots=True)
class Fig:
    """A placeholder bound to one figure id of the verified figure set."""

    figure_id: str
    with_context: bool = True


@dataclass(frozen=True, slots=True)
class Pn:
    """A placeholder bound to a part number present in a typed Spec 2 result."""

    part_number: str


@dataclass(frozen=True, slots=True)
class Count:
    """A placeholder bound to a named integer count of the figure set."""

    name: str


@dataclass(frozen=True, slots=True)
class Note:
    """A placeholder bound to a documented source note (literal text)."""

    note_key: str


@dataclass(frozen=True, slots=True)
class UserEcho:
    """A token the user typed (declared requirement / queried PN), quoted."""

    text: str


@dataclass(frozen=True, slots=True)
class Ident:
    """A non-technical identifier (edition label, plan revision, reference)."""

    text: str


Segment = Lit | Fig | Pn | Count | Note | UserEcho | Ident


@dataclass(frozen=True, slots=True)
class Span:
    """Where a slot's rendering sits in the final text."""

    start: int
    end: int
    kind: str
    ref: str


@dataclass(frozen=True, slots=True)
class RenderedText:
    """Final text plus the provenance spans of every slot rendering."""

    text: str
    spans: tuple[Span, ...]
    figure_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SlotResolver:
    """Callbacks that turn slots into strings, failing on unbound references."""

    figure: Callable[[str, bool], str]
    part_number: Callable[[str], str]
    count: Callable[[str], str]
    note: Callable[[str], str]


def render(segments: Sequence[Segment], resolver: SlotResolver) -> RenderedText:
    """Render segments to text, recording a span for each slot."""

    pieces: list[str] = []
    spans: list[Span] = []
    figure_ids: list[str] = []
    cursor = 0

    def emit(text: str, kind: str | None, ref: str = "") -> None:
        nonlocal cursor
        pieces.append(text)
        if kind is not None and text:
            spans.append(Span(cursor, cursor + len(text), kind, ref))
        cursor += len(text)

    for seg in segments:
        if isinstance(seg, Lit):
            emit(seg.text, None)
        elif isinstance(seg, Fig):
            emit(resolver.figure(seg.figure_id, seg.with_context), "figure", seg.figure_id)
            figure_ids.append(seg.figure_id)
        elif isinstance(seg, Pn):
            emit(resolver.part_number(seg.part_number), "part_number", seg.part_number)
        elif isinstance(seg, Count):
            emit(resolver.count(seg.name), "count", seg.name)
        elif isinstance(seg, Note):
            emit(resolver.note(seg.note_key), "note", seg.note_key)
        elif isinstance(seg, UserEcho):
            emit(f"“{seg.text}”", "user", seg.text)
        elif isinstance(seg, Ident):
            emit(seg.text, "identifier", seg.text)
        else:  # pragma: no cover - exhaustive over Segment
            raise RenderError(f"unknown segment {seg!r}")
    return RenderedText(text="".join(pieces), spans=tuple(spans), figure_ids=tuple(figure_ids))


def untraceable_digit_runs(rendered: RenderedText) -> list[str]:
    """Digit runs of the text that are not inside any slot span.

    Non-figure vocabulary tokens (e.g. "S4") are ignored. An empty list means
    every visible number originates from a typed placeholder.
    """

    out: list[str] = []
    for match in _DIGIT_RUN.finditer(rendered.text):
        start, end = match.span()
        inside = any(s.start <= start and end <= s.end for s in rendered.spans)
        if inside:
            continue
        token_match = None
        for tok in _TOKEN.finditer(rendered.text):
            if tok.start() <= start and end <= tok.end():
                token_match = tok.group(0)
                break
        if token_match in NON_FIGURE_TOKENS:
            continue
        out.append(match.group(0))
    return out


def parse_template(template: str, slots: dict[str, Sequence[Segment] | Segment]) -> list[Segment]:
    """Expand ``"... {name} ..."`` into segments, substituting slot segments.

    Every literal piece becomes a :class:`Lit` (and is therefore digit-checked).
    """

    out: list[Segment] = []
    for piece in re.split(r"(\{[a-z_]+\})", template):
        if not piece:
            continue
        if piece.startswith("{") and piece.endswith("}"):
            name = piece[1:-1]
            if name not in slots:
                raise RenderError(f"template slot {name!r} not supplied")
            value = slots[name]
            if isinstance(value, Lit | Fig | Pn | Count | Note | UserEcho | Ident):
                out.append(value)
            else:
                out.extend(value)
        else:
            out.append(Lit(piece))
    return out


def join(items: Sequence[Sequence[Segment]], separator: str = ", ") -> list[Segment]:
    """Join several segment lists with a literal separator."""

    out: list[Segment] = []
    for index, item in enumerate(items):
        if index:
            out.append(Lit(separator))
        out.extend(item)
    return out
