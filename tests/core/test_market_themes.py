from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.storage.db import migrate_market_db
from radar.core.market import refresh_market_theme_normalization


def test_refresh_market_theme_normalization_merges_clean_source_names(tmp_path: Path):
    config = _config(tmp_path)
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        migrate_market_db(conn)
        _insert_current(conn, "dc_concept:CPO", "concept", "CPO概念", "dc_concept", "CPO", "dc_concept_cons")
        _insert_current(conn, "kpl_list:CPO", "theme", "CPO", "kpl_list", "CPO", "kpl_list")
        _insert_span(conn, "dc_concept:CPO", "concept", "CPO概念", "dc_concept", "CPO", "dc_concept_cons", 3)
        _insert_span(conn, "kpl_list:CPO", "theme", "CPO", "kpl_list", "CPO", "kpl_list", 2)
        conn.commit()
    finally:
        conn.close()

    result = refresh_market_theme_normalization(config, rebuild_anchor_derivatives=False)

    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        node_count = conn.execute("SELECT COUNT(*) FROM theme_nodes").fetchone()[0]
        links = conn.execute("SELECT source, source_name FROM theme_source_links ORDER BY source").fetchall()
        membership = conn.execute(
            """
            SELECT role, confidence, source_count, sources_json, reasons_json
            FROM stock_theme_memberships
            WHERE ts_code = '300394.SZ'
            """
        ).fetchone()
    finally:
        conn.close()

    assert result.theme_count == 1
    assert result.source_link_count == 2
    assert result.membership_count == 1
    assert result.covered_stock_count == 1
    assert result.current_stock_count == 1
    assert result.coverage_ratio == 1.0
    assert node_count == 1
    assert links == [("dc_concept", "CPO概念"), ("kpl_list", "CPO")]
    assert membership[0] == "elastic"
    assert membership[1] >= 0.7
    assert membership[2] == 2
    assert len(json.loads(membership[3])) == 2
    assert json.loads(membership[4]) == ["dc_concept:CPO概念: 光模块", "kpl_list:CPO: AI硬件"]


def test_refresh_market_theme_normalization_derives_specific_theme_from_reason(tmp_path: Path):
    config = _config(tmp_path)
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        migrate_market_db(conn)
        _insert_current(conn, "kpl:AI硬件", "theme", "AI硬件", "kpl_concept_cons", "000025.KP", "kpl_concept_cons")
        _insert_span(
            conn,
            "kpl:AI硬件",
            "theme",
            "AI硬件",
            "kpl_concept_cons",
            "000025.KP",
            "kpl_concept_cons",
            4,
            reason="旗下贝思科主要从事MLCC用钛酸钡及配方粉研发生产",
        )
        conn.commit()
    finally:
        conn.close()

    result = refresh_market_theme_normalization(config, rebuild_anchor_derivatives=False)

    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        node = conn.execute("SELECT theme_name, theme_type, aliases_json FROM theme_nodes").fetchone()
        link = conn.execute("SELECT source_name FROM theme_source_links").fetchone()
    finally:
        conn.close()

    assert result.theme_count == 1
    assert node[0] == "MLCC"
    assert node[1] == "theme"
    assert json.loads(node[2]) == ["AI硬件", "MLCC"]
    assert link[0] == "AI硬件"


def test_refresh_market_theme_normalization_merges_cpo_light_communication_aliases(tmp_path: Path):
    config = _config(tmp_path)
    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        migrate_market_db(conn)
        _insert_current(conn, "kpl:CPO", "theme", "CPO", "kpl_list", "CPO", "kpl_list")
        _insert_current(
            conn,
            "kpl:光通信设备",
            "theme",
            "光通信设备",
            "kpl_concept_cons",
            "000065.KP",
            "kpl_concept_cons",
        )
        _insert_span(conn, "kpl:CPO", "theme", "CPO", "kpl_list", "CPO", "kpl_list", 1, reason="通信")
        _insert_span(
            conn,
            "kpl:光通信设备",
            "theme",
            "光通信设备",
            "kpl_concept_cons",
            "000065.KP",
            "kpl_concept_cons",
            2,
            reason="100G PAM4 EML 光芯片正在送样",
        )
        conn.commit()
    finally:
        conn.close()

    result = refresh_market_theme_normalization(config, rebuild_anchor_derivatives=False)

    conn = sqlite3.connect(tmp_path / "market.sqlite3")
    try:
        node = conn.execute("SELECT theme_name, aliases_json FROM theme_nodes").fetchone()
        membership = conn.execute("SELECT source_count FROM stock_theme_memberships").fetchone()
    finally:
        conn.close()

    assert result.theme_count == 1
    assert node[0] == "CPO/光通信"
    assert json.loads(node[1]) == ["CPO", "CPO/光通信", "光通信设备"]
    assert membership[0] == 2


def _config(tmp_path: Path) -> RadarConfig:
    return RadarConfig(
        config_dir=tmp_path,
        data_dir=tmp_path,
        secrets=RadarSecrets(),
        market={"database": tmp_path / "market.sqlite3"},
    )


def _insert_current(
    conn: sqlite3.Connection,
    anchor_key: str,
    anchor_type: str,
    anchor_name: str,
    anchor_source: str,
    source_code: str,
    member_source: str,
) -> None:
    conn.execute(
        """
        INSERT INTO market_anchor_current_members (
            anchor_key, anchor_type, anchor_name, anchor_source, source_code,
            member_source, ts_code, stock_name, reason, latest_trade_date,
            hot_score, anchor_metadata_json, member_metadata_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, '300394.SZ', '天孚通信', NULL, '20260605', NULL, '{}', '{}', 'now')
        """,
        (anchor_key, anchor_type, anchor_name, anchor_source, source_code, member_source),
    )


def _insert_span(
    conn: sqlite3.Connection,
    anchor_key: str,
    anchor_type: str,
    anchor_name: str,
    anchor_source: str,
    source_code: str,
    member_source: str,
    seen_days: int,
    reason: str | None = None,
) -> None:
    reason = reason or ("光模块" if anchor_source == "dc_concept" else "AI硬件")
    conn.execute(
        """
        INSERT INTO market_anchor_member_spans (
            anchor_key, anchor_type, anchor_name, anchor_source, source_code,
            member_source, ts_code, stock_name, first_seen_date, last_seen_date,
            seen_days, latest_reason, latest_hot_score, anchor_metadata_json,
            member_metadata_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, '300394.SZ', '天孚通信', '20260604', '20260605',
                  ?, ?, NULL, '{}', '{}', 'now')
        """,
        (anchor_key, anchor_type, anchor_name, anchor_source, source_code, member_source, seen_days, reason),
    )
