from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.tushare import cache
from radar.core.tushare.client import call

THS_INDEX_FIELDS = "ts_code,name,count,exchange,list_date,type"
THS_MEMBER_FIELDS = "ts_code,con_code,con_name,weight,in_date,out_date,is_new"

ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class ThsConceptRefreshResult:
    refreshed_at: datetime
    concept_count: int
    refreshed_member_count: int
    skipped_member_count: int
    member_row_count: int
    force: bool

    def metadata(self) -> dict[str, Any]:
        return {
            "refreshed_at": self.refreshed_at.isoformat(),
            "concept_count": self.concept_count,
            "refreshed_member_count": self.refreshed_member_count,
            "skipped_member_count": self.skipped_member_count,
            "member_row_count": self.member_row_count,
            "force": self.force,
        }


def refresh_ths_concepts(
    config: RadarConfig,
    *,
    force: bool = True,
    progress: ProgressCallback | None = None,
) -> ThsConceptRefreshResult:
    """全量刷新同花顺概念缓存。

    概念和成分股是一组关系快照。只按缺口补 ths_member 会保留已移出概念的旧成员，
    进而污染盘前预测的个股-概念映射，所以这里始终重建整组 ths_index/ths_member 缓存。
    """

    refreshed_at = datetime.now()
    index_rows = _fetch_ths_index(config, use_cache=False)
    concepts = _concept_rows(index_rows)
    total = len(concepts)
    refreshed = 0
    skipped = 0
    member_rows = 0
    fetched_members: list[tuple[str, list[dict[str, Any]]]] = []
    _emit_progress(progress, total=total, refreshed=0, skipped=0, member_rows=0, stage="拉取概念列表")

    for index, concept in enumerate(concepts, start=1):
        ts_code = concept["ts_code"]
        rows = _fetch_ths_members(config, ts_code, use_cache=False)
        fetched_members.append((ts_code, rows))
        refreshed += 1
        member_rows += len(rows)
        if index == total or index % 10 == 0:
            _emit_progress(
                progress,
                total=total,
                refreshed=refreshed,
                skipped=skipped,
                member_rows=member_rows,
                stage=f"刷新成分 {index}/{total}",
            )

    _replace_ths_cache(config, index_rows, fetched_members)
    _emit_progress(
        progress,
        total=total,
        refreshed=refreshed,
        skipped=skipped,
        member_rows=member_rows,
        stage="写入概念缓存",
    )

    return ThsConceptRefreshResult(
        refreshed_at=refreshed_at,
        concept_count=total,
        refreshed_member_count=refreshed,
        skipped_member_count=skipped,
        member_row_count=member_rows,
        force=True,
    )


def _fetch_ths_index(config: RadarConfig, *, use_cache: bool = True) -> list[dict[str, Any]]:
    return call(
        config,
        "ths_index",
        params={"exchange": "A", "type": "N"},
        fields=THS_INDEX_FIELDS,
        cache_ttl=0,
        use_cache=use_cache,
    )


def _fetch_ths_members(config: RadarConfig, ts_code: str, *, use_cache: bool = True) -> list[dict[str, Any]]:
    return call(
        config,
        "ths_member",
        params={"ts_code": ts_code},
        fields=THS_MEMBER_FIELDS,
        cache_ttl=0,
        use_cache=use_cache,
    )


def _replace_ths_cache(
    config: RadarConfig,
    index_rows: list[dict[str, Any]],
    member_rows: list[tuple[str, list[dict[str, Any]]]],
) -> None:
    cache.clear(config.market_database_path, "ths_index")
    cache.clear(config.market_database_path, "ths_member")
    cache.put(
        config.market_database_path,
        "ths_index",
        {"exchange": "A", "type": "N"},
        index_rows,
        fields=THS_INDEX_FIELDS,
    )
    for ts_code, rows in member_rows:
        cache.put(
            config.market_database_path,
            "ths_member",
            {"ts_code": ts_code},
            rows,
            fields=THS_MEMBER_FIELDS,
        )


def _concept_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    concepts: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        ts_code = str(row.get("ts_code") or "").strip()
        if not ts_code or ts_code in seen:
            continue
        seen.add(ts_code)
        concepts.append({"ts_code": ts_code, "name": str(row.get("name") or "").strip()})
    return concepts


def _emit_progress(
    progress: ProgressCallback | None,
    *,
    total: int,
    refreshed: int,
    skipped: int,
    member_rows: int,
    stage: str,
) -> None:
    if progress is None:
        return
    progress(
        {
            "stage": stage,
            "concept_count": total,
            "refreshed_member_count": refreshed,
            "skipped_member_count": skipped,
            "member_row_count": member_rows,
        }
    )
