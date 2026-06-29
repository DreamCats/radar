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
THS_MEMBER_TTL_SECONDS = 30 * 86_400

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
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> ThsConceptRefreshResult:
    """手动刷新同花顺概念缓存；概念列表刷新，成分按概念代码增量补缺。"""

    refreshed_at = datetime.now()
    index_rows = _fetch_ths_index(config)
    concepts = _concept_rows(index_rows)
    total = len(concepts)
    refreshed = 0
    skipped = 0
    member_rows = 0
    _emit_progress(progress, total=total, refreshed=0, skipped=0, member_rows=0, stage="刷新概念列表")

    for index, concept in enumerate(concepts, start=1):
        ts_code = concept["ts_code"]
        cached = None if force else _cached_member_rows(config, ts_code)
        if cached is not None:
            skipped += 1
            member_rows += len(cached)
        else:
            rows = _fetch_ths_members(config, ts_code)
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

    return ThsConceptRefreshResult(
        refreshed_at=refreshed_at,
        concept_count=total,
        refreshed_member_count=refreshed,
        skipped_member_count=skipped,
        member_row_count=member_rows,
        force=force,
    )


def _fetch_ths_index(config: RadarConfig) -> list[dict[str, Any]]:
    return call(
        config,
        "ths_index",
        params={"exchange": "A", "type": "N"},
        fields=THS_INDEX_FIELDS,
        cache_ttl=0,
        use_cache=True,
    )


def _fetch_ths_members(config: RadarConfig, ts_code: str) -> list[dict[str, Any]]:
    return call(
        config,
        "ths_member",
        params={"ts_code": ts_code},
        fields=THS_MEMBER_FIELDS,
        cache_ttl=0,
        use_cache=True,
    )


def _cached_member_rows(config: RadarConfig, ts_code: str) -> list[dict[str, Any]] | None:
    return cache.get(
        config.market_database_path,
        "ths_member",
        {"ts_code": ts_code},
        fields=THS_MEMBER_FIELDS,
        ttl=THS_MEMBER_TTL_SECONDS,
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
