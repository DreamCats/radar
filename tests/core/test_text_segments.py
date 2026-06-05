from __future__ import annotations

from radar.core.algorithms.text_segments import split_text_segments


def test_split_text_segments_prefers_list_delimiters_for_long_segments():
    text = "AAA/BBB/CCC/DDD/EEE/FFF/GGG/HHH/III/JJJ"

    segments = split_text_segments(text, max_segment_chars=24)

    assert len(segments) > 1
    assert segments[0].text.endswith("/")
