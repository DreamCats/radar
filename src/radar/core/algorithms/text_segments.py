from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextSegment:
    index: int
    start: int
    end: int
    text: str


def split_text_segments(text: str, *, max_segment_chars: int = 280) -> list[TextSegment]:
    """按通用文本结构切段；不包含任何业务词表。"""

    if max_segment_chars < 20:
        raise ValueError("max_segment_chars 必须大于等于 20")
    if not text:
        return [TextSegment(index=0, start=0, end=0, text="")]

    breaks = _structural_breaks(text)
    pieces: list[tuple[int, int]] = []
    for start, end in zip(breaks, breaks[1:]):
        pieces.extend(_split_long_piece(text, start, end, max_segment_chars))

    segments: list[TextSegment] = []
    for start, end in pieces:
        segment_text = text[start:end].strip()
        if not segment_text:
            continue
        segments.append(TextSegment(index=len(segments), start=start, end=end, text=segment_text))
    return segments or [TextSegment(index=0, start=0, end=len(text), text=text.strip())]


def segment_for_position(segments: list[TextSegment], position: int | None) -> TextSegment:
    if not segments:
        return TextSegment(index=0, start=0, end=0, text="")
    if position is None:
        return segments[0]
    for segment in segments:
        if segment.start <= position < segment.end:
            return segment
    return segments[-1]


def _structural_breaks(text: str) -> list[int]:
    breaks = {0, len(text)}
    for match in re.finditer(r"\n+|(?<=[。；;])", text):
        breaks.add(match.end())
    for match in re.finditer(r"(?m)^\s*(?:\d+[、.．]|[一二三四五六七八九十]+[、.]|[#【])", text):
        breaks.add(match.start())
    return sorted(breaks)


def _split_long_piece(
    text: str,
    start: int,
    end: int,
    max_segment_chars: int,
) -> list[tuple[int, int]]:
    if end - start <= max_segment_chars:
        return [(start, end)]

    pieces: list[tuple[int, int]] = []
    current = start
    while current < end:
        target = min(current + max_segment_chars, end)
        split_at = _best_split(text, current, target, end)
        pieces.append((current, split_at))
        current = split_at
    return pieces


def _best_split(text: str, start: int, target: int, end: int) -> int:
    if target >= end:
        return end
    window_start = max(start + 20, target - 80)
    for index in range(target, window_start, -1):
        if text[index - 1] in "，,、/／|｜ ":
            return index
    return target
