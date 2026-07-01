from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

CNINFO_BASE_URL = "http://www.cninfo.com.cn"
CNINFO_STOCK_URL = f"{CNINFO_BASE_URL}/new/data/szse_stock.json"
CNINFO_DISCLOSURE_QUERY_URL = f"{CNINFO_BASE_URL}/new/hisAnnouncement/query"
CNINFO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": f"{CNINFO_BASE_URL}/new/commonUrl/pageOfSearch?url=disclosure/list/search",
}
CNINFO_DISCLOSURE_CATEGORY_CODES = {
    "年报": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
    "业绩预告": "category_yjygjxz_szsh",
    "权益分派": "category_qyfpxzcs_szsh",
    "董事会": "category_dshgg_szsh",
    "监事会": "category_jshgg_szsh",
    "股东大会": "category_gddh_szsh",
    "日常经营": "category_rcjy_szsh",
    "公司治理": "category_gszl_szsh",
    "中介报告": "category_zj_szsh",
    "首发": "category_sf_szsh",
    "增发": "category_zf_szsh",
    "股权激励": "category_gqjl_szsh",
    "配股": "category_pg_szsh",
    "解禁": "category_jj_szsh",
    "公司债": "category_gszq_szsh",
    "可转债": "category_kzzq_szsh",
    "其他融资": "category_qtrz_szsh",
    "股权变动": "category_gqbd_szsh",
    "补充更正": "category_bcgz_szsh",
    "澄清致歉": "category_cqdq_szsh",
    "风险提示": "category_fxts_szsh",
    "特别处理和退市": "category_tbclts_szsh",
    "退市整理期": "category_tszlq_szsh",
}

_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?:\.(?:SH|SZ|BJ))?(?!\d)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class CninfoDisclosureError(RuntimeError):
    pass


def search_cninfo_disclosures(
    *,
    stock: str,
    ts_code: str | None = None,
    keywords: list[str] | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 5,
    timeout: float = 12.0,
) -> dict[str, Any]:
    code_hint = _stock_code(ts_code or stock)
    normalized_keywords = _clean_keywords(keywords or [])
    normalized_category = _normalize_category(category) or _infer_category(normalized_keywords)
    start, end = _date_window(start_date, end_date)
    capped_limit = max(1, min(int(limit), 30))

    with httpx.Client(
        timeout=timeout,
        headers=CNINFO_HEADERS,
        follow_redirects=True,
    ) as client:
        stock_row = _resolve_cninfo_stock(client, stock=stock, code_hint=code_hint)
        attempts = _query_attempts(
            keywords=normalized_keywords,
            category=normalized_category,
            narrow_date_window=(end - start).days <= 14,
        )
        items, attempt_records = _collect_disclosures(
            client,
            stock_row=stock_row,
            attempts=attempts,
            start=start,
            end=end,
            limit=capped_limit,
        )

    return {
        "source": "cninfo",
        "scope": "cninfo_disclosure_list",
        "stock": stock,
        "code": stock_row["code"],
        "name": stock_row["name"],
        "org_id": stock_row["org_id"],
        "category": normalized_category,
        "keywords": normalized_keywords,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "query_attempts": attempt_records,
        "item_count": len(items),
        "items": items,
    }


def _resolve_cninfo_stock(
    client: httpx.Client,
    *,
    stock: str,
    code_hint: str | None,
) -> dict[str, str]:
    raw = _get_json(client, CNINFO_STOCK_URL)
    stock_list = raw.get("stockList")
    if not isinstance(stock_list, list):
        raise CninfoDisclosureError("巨潮股票列表返回格式异常")

    rows = [_normalize_stock_row(row) for row in stock_list if isinstance(row, dict)]
    if code_hint:
        for row in rows:
            if row["code"] == code_hint:
                return row

    stock_name = stock.strip()
    exact = [row for row in rows if row["name"] == stock_name]
    if len(exact) == 1:
        return exact[0]

    fuzzy = [row for row in rows if stock_name and (stock_name in row["name"] or row["name"] in stock_name)]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if fuzzy:
        listed = ", ".join(f"{row['code']}({row['name']})" for row in fuzzy[:5])
        raise CninfoDisclosureError(f"股票 {stock!r} 匹配到多个巨潮标的，请用代码指定: {listed}")
    raise CninfoDisclosureError(f"巨潮股票列表找不到 {stock!r}")


def _collect_disclosures(
    client: httpx.Client,
    *,
    stock_row: dict[str, str],
    attempts: list[dict[str, str]],
    start: dt.date,
    end: dt.date,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempt_records: list[dict[str, Any]] = []
    for attempt in attempts:
        rows, total = _query_disclosure_rows(
            client,
            stock_row=stock_row,
            keyword=attempt["keyword"],
            category=attempt["category"],
            start=start,
            end=end,
            limit=limit,
        )
        attempt_records.append({**attempt, "total": total, "returned": len(rows)})
        for row in rows:
            item = _disclosure_item(row, stock_row=stock_row, keyword=attempt["keyword"])
            item_id = item["announcement_id"] or item["url"]
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(item)
            if len(items) >= limit:
                return items, attempt_records
        if items:
            return items, attempt_records
    return items, attempt_records


def _query_disclosure_rows(
    client: httpx.Client,
    *,
    stock_row: dict[str, str],
    keyword: str,
    category: str,
    start: dt.date,
    end: dt.date,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    page_size = min(max(limit, 10), 30)
    payload = _query_payload(
        stock_row=stock_row,
        keyword=keyword,
        category=category,
        start=start,
        end=end,
        page_num=1,
        page_size=page_size,
    )
    first = _post_json(client, CNINFO_DISCLOSURE_QUERY_URL, payload)
    total = _safe_int(first.get("totalAnnouncement"))
    rows = _announcement_rows(first)
    page_count = min((total + page_size - 1) // page_size, (limit + page_size - 1) // page_size)

    for page_num in range(2, page_count + 1):
        payload["pageNum"] = str(page_num)
        data = _post_json(client, CNINFO_DISCLOSURE_QUERY_URL, payload)
        rows.extend(_announcement_rows(data))
        if len(rows) >= limit:
            break
    return rows[:limit], total


def _query_payload(
    *,
    stock_row: dict[str, str],
    keyword: str,
    category: str,
    start: dt.date,
    end: dt.date,
    page_num: int,
    page_size: int,
) -> dict[str, str]:
    category_code = CNINFO_DISCLOSURE_CATEGORY_CODES.get(category, "")
    return {
        "pageNum": str(page_num),
        "pageSize": str(page_size),
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{stock_row['code']},{stock_row['org_id']}",
        "searchkey": keyword,
        "secid": "",
        "category": category_code,
        "trade": "",
        "seDate": f"{start.isoformat()}~{end.isoformat()}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }


def _query_attempts(
    *,
    keywords: list[str],
    category: str | None,
    narrow_date_window: bool,
) -> list[dict[str, str]]:
    attempts: list[dict[str, str]] = []
    keyword_candidates = keywords[:3]
    if category:
        for keyword in keyword_candidates[:1]:
            attempts.append({"category": category, "keyword": keyword})
        attempts.append({"category": category, "keyword": ""})
    for keyword in keyword_candidates:
        attempts.append({"category": "", "keyword": keyword})
    if narrow_date_window or not attempts:
        attempts.append({"category": "", "keyword": ""})
    return _dedupe_attempts(attempts)


def _dedupe_attempts(attempts: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for attempt in attempts:
        key = (attempt["category"], attempt["keyword"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(attempt)
    return deduped


def _disclosure_item(
    row: dict[str, Any],
    *,
    stock_row: dict[str, str],
    keyword: str,
) -> dict[str, Any]:
    title = _strip_tags(str(row.get("announcementTitle") or ""))
    announcement_id = str(row.get("announcementId") or "")
    org_id = str(row.get("orgId") or stock_row["org_id"])
    timestamp_ms = _safe_int(row.get("announcementTime"))
    announcement_time = _format_cninfo_time(timestamp_ms)
    url = _announcement_url(
        code=str(row.get("secCode") or stock_row["code"]),
        announcement_id=announcement_id,
        org_id=org_id,
        announcement_time=announcement_time,
    )
    return {
        "code": str(row.get("secCode") or stock_row["code"]),
        "name": str(row.get("secName") or stock_row["name"]),
        "title": title,
        "announcement_time": announcement_time,
        "announcement_time_ms": timestamp_ms or None,
        "announcement_id": announcement_id,
        "org_id": org_id,
        "url": url,
        "matched_keywords": _matched_keywords(title, keyword),
    }


def _announcement_url(
    *,
    code: str,
    announcement_id: str,
    org_id: str,
    announcement_time: str | None,
) -> str:
    params = {
        "stockCode": code,
        "announcementId": announcement_id,
        "orgId": org_id,
    }
    if announcement_time:
        params["announcementTime"] = announcement_time
    return f"{CNINFO_BASE_URL}/new/disclosure/detail?{urlencode(params)}"


def _normalize_stock_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "code": str(row.get("code") or "").strip(),
        "name": str(row.get("zwjc") or "").strip(),
        "org_id": str(row.get("orgId") or "").strip(),
    }


def _get_json(client: httpx.Client, url: str) -> dict[str, Any]:
    try:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise CninfoDisclosureError(f"请求巨潮接口失败: {url}") from exc
    except ValueError as exc:
        raise CninfoDisclosureError(f"巨潮接口返回不是 JSON: {url}") from exc
    if not isinstance(data, dict):
        raise CninfoDisclosureError(f"巨潮接口返回格式异常: {url}")
    return data


def _post_json(client: httpx.Client, url: str, payload: dict[str, str]) -> dict[str, Any]:
    try:
        response = client.post(url, data=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise CninfoDisclosureError(f"请求巨潮公告接口失败: {url}") from exc
    except ValueError as exc:
        raise CninfoDisclosureError(f"巨潮公告接口返回不是 JSON: {url}") from exc
    if not isinstance(data, dict):
        raise CninfoDisclosureError(f"巨潮公告接口返回格式异常: {url}")
    return data


def _announcement_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("announcements")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _date_window(start_date: str | None, end_date: str | None) -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    end = _parse_date(end_date) if end_date else today
    start = _parse_date(start_date) if start_date else end - dt.timedelta(days=180)
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")
    return start, end


def _parse_date(value: str) -> dt.date:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("日期必须是 YYYY-MM-DD 或 YYYYMMDD")


def _stock_code(value: str | None) -> str | None:
    if not value:
        return None
    match = _CODE_RE.search(value.strip())
    return match.group(1) if match else None


def _clean_keywords(keywords: list[str]) -> list[str]:
    cleaned: list[str] = []
    for keyword in keywords:
        text = str(keyword).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:8]


def _normalize_category(category: str | None) -> str | None:
    if not category:
        return None
    text = category.strip()
    if text in CNINFO_DISCLOSURE_CATEGORY_CODES:
        return text
    for known in CNINFO_DISCLOSURE_CATEGORY_CODES:
        if known in text or text in known:
            return known
    if any(token in text for token in ("预增", "预减", "扭亏", "净利润", "业绩")):
        return "业绩预告"
    return None


def _infer_category(keywords: list[str]) -> str | None:
    joined = " ".join(keywords)
    if any(token in joined for token in ("业绩预告", "业绩预增", "预增", "预减", "扭亏", "净利润")):
        return "业绩预告"
    if "股权激励" in joined or "激励" in joined:
        return "股权激励"
    if "权益变动" in joined or "持股变动" in joined:
        return "股权变动"
    if "风险" in joined or "退市" in joined:
        return "风险提示"
    return None


def _matched_keywords(title: str, keyword: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[\s,，/]+", keyword) if part.strip()]
    return [part for part in parts if part in title]


def _strip_tags(value: str) -> str:
    return _TAG_RE.sub("", value).strip()


def _format_cninfo_time(timestamp_ms: int) -> str | None:
    if timestamp_ms <= 0:
        return None
    return (
        dt.datetime.fromtimestamp(timestamp_ms / 1000, tz=dt.timezone.utc)
        .astimezone(_SHANGHAI_TZ)
        .strftime("%Y-%m-%d %H:%M:%S")
    )


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
