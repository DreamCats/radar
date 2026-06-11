from __future__ import annotations

from datetime import datetime

from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceThemeContext,
    build_recognition_context,
    primary_theme,
)
from radar.core.usecases.stock_evidence_chain.theme_quality import apply_theme_quality


def test_theme_quality_promotes_fresh_multi_source_leader():
    theme = StockEvidenceThemeContext(
        theme_id="theme:auto:cpo",
        theme_name="CPO概念",
        theme_type="concept",
        role="elastic",
        confidence=0.82,
        source_count=2,
        latest_trade_date="20260608",
        member_count=24,
        covered_member_count=22,
        return_rank_5d=2,
        stock_return_5d=0.08,
        is_theme_leader=True,
    )

    selected = {"300394.SZ": [theme]}
    apply_theme_quality(selected, as_of=datetime(2026, 6, 8, 15, 0))

    assert theme.quality_label == "主线候选"
    assert theme.quality_score >= 0.72
    assert primary_theme(selected["300394.SZ"]) is theme
    assert "跨来源归属：2 个来源" in theme.quality_reasons


def test_theme_quality_rejects_broad_single_source_candidate():
    theme = StockEvidenceThemeContext(
        theme_id="theme:auto:ai",
        theme_name="AI硬件",
        theme_type="theme",
        role="unknown",
        confidence=0.66,
        source_count=1,
        latest_trade_date="20260608",
        member_count=315,
        covered_member_count=300,
        return_rank_5d=240,
        stock_return_5d=-0.02,
        is_theme_laggard=True,
    )

    selected = {"300000.SZ": [theme]}
    apply_theme_quality(selected, as_of=datetime(2026, 6, 8, 15, 0))
    recognition = build_recognition_context(
        unique_trigger_count=8,
        market_summary={"return_since_first_point": 0.02},
        market_points=[],
        themes=selected["300000.SZ"],
    )

    assert primary_theme(selected["300000.SZ"]) is None
    assert theme.quality_label in {"弱关联", "待确认"}
    assert theme.is_broad_theme is True
    assert any("主题过宽" in item for item in theme.quality_warnings)
    assert any("主叙事暂不确定" in item for item in recognition.missing_evidence)
