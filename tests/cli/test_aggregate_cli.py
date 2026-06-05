from __future__ import annotations

from datetime import datetime

from click.testing import CliRunner

from radar.cli.main import main
from radar.core.usecases.aggregation import (
    AggregateTopic,
    AggregateTopicEvidence,
    AggregateTopicsResult,
    RefineAggregateTopicsResult,
    RefinedTheme,
    RefinedThemeStock,
    RelatedStock,
)


def test_aggregate_topics_command_invokes_core_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_aggregate(
        config,
        *,
        trade_date,
        extractor_version,
        source,
        categories,
        min_classification_confidence,
        min_messages,
        limit,
        evidence_limit,
        start_time,
        end_time,
    ):
        calls.append(
            {
                "database": config.database_path,
                "trade_date": trade_date,
                "extractor_version": extractor_version,
                "source": source,
                "categories": categories,
                "min_classification_confidence": min_classification_confidence,
                "min_messages": min_messages,
                "limit": limit,
                "evidence_limit": evidence_limit,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        return AggregateTopicsResult(
            trade_date=trade_date,
            extractor_version=extractor_version,
            start_time=start_time,
            end_time=end_time,
            categories=categories,
            min_classification_confidence=min_classification_confidence,
            scoped_message_count=3,
            anchored_message_count=2,
            topic_count=1,
            topics=[
                AggregateTopic(
                    name="玻璃基板",
                    anchor_types=["concept"],
                    message_count=2,
                    anchor_count=2,
                    score=4.2,
                    latest_time=datetime.fromisoformat("2026-06-04T10:00:00"),
                    category_distribution={"research": 1, "recommendation": 1},
                    related_stocks=[RelatedStock(name="沃格光电", count=2)],
                    evidence=[
                        AggregateTopicEvidence(
                            message_id="m1",
                            message_time=datetime.fromisoformat("2026-06-04T10:00:00"),
                            category="research",
                            classification_confidence=0.9,
                            anchor_confidence=0.95,
                            sender="sender",
                            group_name="投研群",
                            raw_content="玻璃基板继续发酵",
                            stocks=["沃格光电"],
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr("radar.cli.aggregate.aggregate_topics", fake_aggregate)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "aggregate",
            "topics",
            "--trade-date",
            "20260604",
            "--extractor-version",
            "test-anchor",
            "--source",
            "group_message",
            "--category",
            "research",
            "--category",
            "recommendation",
            "--min-classification-confidence",
            "0.75",
            "--min-messages",
            "2",
            "--limit",
            "10",
            "--evidence-limit",
            "1",
            "--start",
            "2026-06-04",
            "--end",
            "2026-06-05",
        ],
    )

    assert result.exit_code == 0
    assert "aggregate/topics: topics=1 scoped=3 anchored=2 extractor=test-anchor" in result.output
    assert "1. 玻璃基板 score=4.2 messages=2" in result.output
    assert "stocks=沃格光电(2)" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "trade_date": "20260604",
            "extractor_version": "test-anchor",
            "source": "个人群",
            "categories": ["research", "recommendation"],
            "min_classification_confidence": 0.75,
            "min_messages": 2,
            "limit": 10,
            "evidence_limit": 1,
            "start_time": datetime.fromisoformat("2026-06-04T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-05T00:00:00"),
        }
    ]


def test_aggregate_refine_command_invokes_core_usecase(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_refine(
        config,
        *,
        trade_date,
        extractor_version,
        source,
        categories,
        min_classification_confidence,
        min_messages,
        candidate_limit,
        evidence_limit,
        batch_size,
        max_concurrency,
        provider_name,
        provider_names,
        force,
        start_time,
        end_time,
    ):
        calls.append(
            {
                "database": config.database_path,
                "trade_date": trade_date,
                "extractor_version": extractor_version,
                "source": source,
                "categories": categories,
                "min_classification_confidence": min_classification_confidence,
                "min_messages": min_messages,
                "candidate_limit": candidate_limit,
                "evidence_limit": evidence_limit,
                "batch_size": batch_size,
                "max_concurrency": max_concurrency,
                "provider_name": provider_name,
                "provider_names": provider_names,
                "force": force,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        local_result = AggregateTopicsResult(
            trade_date=trade_date,
            extractor_version=extractor_version,
            start_time=start_time,
            end_time=end_time,
            categories=categories,
            min_classification_confidence=min_classification_confidence,
            scoped_message_count=3,
            anchored_message_count=2,
            topic_count=1,
            topics=[],
        )
        return RefineAggregateTopicsResult(
            run_id="run1",
            input_hash="hash1",
            status="succeeded",
            trade_date=trade_date,
            extractor_version=extractor_version,
            prompt_version="test-prompt",
            candidate_count=1,
            theme_count=1,
            llm_batch_count=1,
            failed_llm_batches=0,
            max_concurrency=max_concurrency,
            local_result=local_result,
            themes=[
                RefinedTheme(
                    theme_name="玻璃基板设备链",
                    summary="玻璃基板继续发酵",
                    confidence=0.8,
                    actionability_score=82,
                    novelty="continuing",
                    related_stocks=[RefinedThemeStock(name="联得装备", confidence=0.7)],
                    evidence_message_ids=["m1"],
                )
            ],
        )

    monkeypatch.setattr("radar.cli.aggregate.refine_aggregate_topics", fake_refine)

    result = CliRunner().invoke(
        main,
        [
            "--config-dir",
            str(_config_dir(tmp_path)),
            "aggregate",
            "refine",
            "--trade-date",
            "20260604",
            "--extractor-version",
            "test-anchor",
            "--source",
            "group_message",
            "--category",
            "research",
            "--min-classification-confidence",
            "0.75",
            "--min-messages",
            "2",
            "--candidate-limit",
            "10",
            "--evidence-limit",
            "2",
            "--batch-size",
            "5",
            "--max-concurrency",
            "2",
            "--provider-pool",
            "p1",
            "--provider-pool",
            "p2",
            "--force",
            "--start",
            "2026-06-04",
            "--end",
            "2026-06-05",
        ],
    )

    assert result.exit_code == 0
    assert "aggregate/refine: status=succeeded themes=1 candidates=1 batches=1" in result.output
    assert "1. 玻璃基板设备链 action=82.0" in result.output
    assert calls == [
        {
            "database": tmp_path / "radar.sqlite3",
            "trade_date": "20260604",
            "extractor_version": "test-anchor",
            "source": "个人群",
            "categories": ["research"],
            "min_classification_confidence": 0.75,
            "min_messages": 2,
            "candidate_limit": 10,
            "evidence_limit": 2,
            "batch_size": 5,
            "max_concurrency": 2,
            "provider_name": None,
            "provider_names": ["p1", "p2"],
            "force": True,
            "start_time": datetime.fromisoformat("2026-06-04T00:00:00"),
            "end_time": datetime.fromisoformat("2026-06-05T00:00:00"),
        }
    ]


def _config_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        f"""
storage:
  data_dir: {tmp_path}
  database: {tmp_path / "radar.sqlite3"}
""",
        encoding="utf-8",
    )
    return config_dir
