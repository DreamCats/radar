from __future__ import annotations

from typing import TypeAlias

from radar.core.config import RadarConfig
from radar.core.market_anchors import (
    MarketAnchor,
    MarketAnchorMember,
    TushareCallFn,
    _anchor_id,
    _compact_metadata,
    _float,
    _split_themes,
    _text,
)

LoaderResult: TypeAlias = tuple[list[MarketAnchor], list[MarketAnchorMember], dict[str, int]]


def _load_dc_concepts(config: RadarConfig, trade_date: str, fetch: TushareCallFn) -> LoaderResult:
    anchors: list[MarketAnchor] = []
    members: list[MarketAnchorMember] = []
    concept_rows = fetch(
        config,
        "dc_concept",
        {"trade_date": trade_date},
        "theme_code,trade_date,name,pct_change,hot,sort,strength,z_t_num,lead_stock,lead_stock_code",
    )
    for row in concept_rows:
        code = _text(row.get("theme_code"))
        name = _text(row.get("name"))
        if code and name:
            anchors.append(
                MarketAnchor(
                    anchor_id=_anchor_id("dc_concept", code, trade_date),
                    anchor_type="concept",
                    name=name,
                    source="dc_concept",
                    source_code=code,
                    trade_date=trade_date,
                    hot_score=_float(row.get("hot")),
                    metadata=_compact_metadata(row, {"theme_code", "name", "trade_date", "hot"}),
                )
            )

    member_rows = fetch(
        config,
        "dc_concept_cons",
        {"trade_date": trade_date},
        "ts_code,trade_date,name,theme_code,industry_code,industry,reason,hot_num",
    )
    for row in member_rows:
        theme_code = _text(row.get("theme_code"))
        ts_code = _text(row.get("ts_code"))
        stock_name = _text(row.get("name"))
        if theme_code and ts_code and stock_name:
            members.append(
                MarketAnchorMember(
                    anchor_id=_anchor_id("dc_concept", theme_code, trade_date),
                    ts_code=ts_code,
                    stock_name=stock_name,
                    reason=_text(row.get("reason")) or None,
                    source="dc_concept_cons",
                    trade_date=trade_date,
                    metadata={"hot_num": row.get("hot_num")},
                )
            )
        _append_dc_industry(row, trade_date, anchors, members, ts_code, stock_name, theme_code)
    return anchors, members, {"dc_concept": len(concept_rows), "dc_concept_cons": len(member_rows)}


def _append_dc_industry(
    row: dict,
    trade_date: str,
    anchors: list[MarketAnchor],
    members: list[MarketAnchorMember],
    ts_code: str,
    stock_name: str,
    theme_code: str,
) -> None:
    industry_code = _text(row.get("industry_code"))
    industry = _text(row.get("industry"))
    if not industry_code or not industry:
        return
    anchor_id = _anchor_id("dc_industry", industry_code, trade_date)
    anchors.append(
        MarketAnchor(
            anchor_id=anchor_id,
            anchor_type="industry",
            name=industry,
            source="dc_concept_cons",
            source_code=industry_code,
            trade_date=trade_date,
            hot_score=_float(row.get("hot_num")),
        )
    )
    if ts_code and stock_name:
        members.append(
            MarketAnchorMember(
                anchor_id=anchor_id,
                ts_code=ts_code,
                stock_name=stock_name,
                reason=_text(row.get("reason")) or None,
                source="dc_concept_cons",
                trade_date=trade_date,
                metadata={"theme_code": theme_code, "hot_num": row.get("hot_num")},
            )
        )


def _load_kpl_concepts(config: RadarConfig, trade_date: str, fetch: TushareCallFn) -> LoaderResult:
    anchors: list[MarketAnchor] = []
    members: list[MarketAnchorMember] = []
    list_rows = fetch(
        config,
        "kpl_list",
        {"trade_date": trade_date},
        "ts_code,name,trade_date,lu_desc,tag,theme,status,hot_num",
    )
    for row in list_rows:
        _append_kpl_list_row(row, trade_date, anchors, members)

    cons_rows = fetch(
        config,
        "kpl_concept_cons",
        {"trade_date": trade_date},
        "ts_code,name,con_name,con_code,trade_date,desc,hot_num",
    )
    for row in cons_rows:
        _append_kpl_concept_row(row, trade_date, anchors, members)
    return anchors, members, {"kpl_list": len(list_rows), "kpl_concept_cons": len(cons_rows)}


def _append_kpl_list_row(
    row: dict,
    trade_date: str,
    anchors: list[MarketAnchor],
    members: list[MarketAnchorMember],
) -> None:
    ts_code = _text(row.get("ts_code"))
    stock_name = _text(row.get("name"))
    for theme in _split_themes(_text(row.get("theme"))):
        anchor_id = _anchor_id("kpl_theme", theme, trade_date)
        anchors.append(
            MarketAnchor(
                anchor_id=anchor_id,
                anchor_type="theme",
                name=theme,
                aliases=[theme],
                source="kpl_list",
                source_code=theme,
                trade_date=trade_date,
                metadata=_compact_metadata(row, {"ts_code", "name", "trade_date", "theme"}),
            )
        )
        if ts_code and stock_name:
            members.append(
                MarketAnchorMember(
                    anchor_id=anchor_id,
                    ts_code=ts_code,
                    stock_name=stock_name,
                    reason=_text(row.get("lu_desc")) or _text(row.get("status")) or None,
                    source="kpl_list",
                    trade_date=trade_date,
                    metadata={"tag": row.get("tag"), "status": row.get("status")},
                )
            )


def _append_kpl_concept_row(
    row: dict,
    trade_date: str,
    anchors: list[MarketAnchor],
    members: list[MarketAnchorMember],
) -> None:
    code = _text(row.get("ts_code"))
    name = _text(row.get("name"))
    con_code = _text(row.get("con_code"))
    con_name = _text(row.get("con_name"))
    if not code or not name:
        return
    anchor_id = _anchor_id("kpl_concept", code, trade_date)
    anchors.append(
        MarketAnchor(
            anchor_id=anchor_id,
            anchor_type="theme",
            name=name,
            source="kpl_concept_cons",
            source_code=code,
            trade_date=trade_date,
            hot_score=_float(row.get("hot_num")),
        )
    )
    if con_code and con_name:
        members.append(
            MarketAnchorMember(
                anchor_id=anchor_id,
                ts_code=con_code,
                stock_name=con_name,
                reason=_text(row.get("desc")) or None,
                source="kpl_concept_cons",
                trade_date=trade_date,
                metadata={"hot_num": row.get("hot_num")},
            )
        )


def _load_tdx_concepts(config: RadarConfig, trade_date: str, fetch: TushareCallFn) -> LoaderResult:
    rows = fetch(
        config,
        "tdx_index",
        {"trade_date": trade_date, "idx_type": "概念板块"},
        "ts_code,trade_date,name,idx_type,idx_count,total_mv,float_mv",
    )
    anchors = [
        MarketAnchor(
            anchor_id=_anchor_id("tdx_index", _text(row.get("ts_code")), trade_date),
            anchor_type="concept",
            name=_text(row.get("name")),
            source="tdx_index",
            source_code=_text(row.get("ts_code")),
            trade_date=trade_date,
            metadata=_compact_metadata(row, {"ts_code", "name", "trade_date"}),
        )
        for row in rows
        if _text(row.get("ts_code")) and _text(row.get("name"))
    ]
    return anchors, [], {"tdx_index": len(rows)}


LOADERS = (_load_dc_concepts, _load_kpl_concepts, _load_tdx_concepts)
