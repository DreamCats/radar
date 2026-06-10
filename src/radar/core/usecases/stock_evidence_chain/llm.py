from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.llm import chat
from radar.core.usecases.stock_evidence_chain.models import PROMPT_VERSION, STAGES, EvidencePack, Judgement

STAGE_LABELS = {
    "lead": "线索期",
    "seed": "种子期",
    "formed": "论证期",
    "spreading": "扩散期",
    "pricing": "定价期",
    "crowded": "拥挤期",
}
STAGE_RE = re.compile(r"\b(lead|seed|formed|spreading|pricing|crowded)\b", re.IGNORECASE)


def judge_pack(
    config: RadarConfig,
    pack: EvidencePack,
    *,
    provider_name: str | None,
    model: str | None,
    max_tokens: int,
    temperature: float,
) -> Judgement:
    text = chat(
        config,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(pack)},
        ],
        provider_name=provider_name,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        disable_thinking=True,
    )
    result = _parse_result(text)
    stage = _extract_stage(result, text)
    confidence = _extract_confidence(result)
    return Judgement(
        stage=stage,
        confidence=confidence,
        summary=_short_summary(result, text),
        raw_text=text,
        result=result,
        provider=provider_name,
        model=model,
    )


def save_judgement(
    conn: sqlite3.Connection,
    *,
    as_of: datetime,
    window_start: datetime,
    evidence_start: datetime,
    pack: EvidencePack,
    judgement: Judgement,
) -> None:
    candidate = pack.candidate
    now = datetime.now().isoformat()
    evidence_refs = [
        {
            "message_id": item.message.message_id,
            "message_time": item.message.message_time.isoformat(),
            "sender": item.message.sender,
            "group_name": item.message.group_name,
            "families": list(item.evidence_families),
        }
        for item in pack.evidence
    ]
    payload = dict(judgement.result)
    payload["summary"] = judgement.summary
    payload["raw_text"] = judgement.raw_text
    if pack.market is not None:
        payload["market_evidence"] = _market_payload(pack)
    conn.execute(
        """
        INSERT INTO stock_lifecycle_judgements (
            judgement_id, as_of_time, window_start_time, evidence_start_time, ts_code,
            stock_name, stage, confidence, trigger_count, unique_trigger_count,
            sender_count, conversation_count, evidence_count, channels_json,
            evidence_refs_json, llm_provider, model, prompt_version,
            result_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(as_of_time, ts_code, prompt_version) DO UPDATE SET
            stage = excluded.stage,
            confidence = excluded.confidence,
            trigger_count = excluded.trigger_count,
            unique_trigger_count = excluded.unique_trigger_count,
            sender_count = excluded.sender_count,
            conversation_count = excluded.conversation_count,
            evidence_count = excluded.evidence_count,
            channels_json = excluded.channels_json,
            evidence_refs_json = excluded.evidence_refs_json,
            llm_provider = excluded.llm_provider,
            model = excluded.model,
            result_json = excluded.result_json,
            updated_at = excluded.updated_at
        """,
        (
            uuid.uuid4().hex,
            as_of.isoformat(),
            window_start.isoformat(),
            evidence_start.isoformat(),
            candidate.stock.ts_code,
            candidate.stock.name,
            judgement.stage,
            judgement.confidence,
            candidate.trigger_count,
            candidate.unique_trigger_count,
            candidate.sender_count,
            candidate.conversation_count,
            len(pack.evidence),
            json.dumps(sorted(candidate.channels), ensure_ascii=False),
            json.dumps(evidence_refs, ensure_ascii=False),
            judgement.provider,
            judgement.model,
            PROMPT_VERSION,
            json.dumps(payload, ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()


def _system_prompt() -> str:
    return (
        "你是个人投资者的投研证据链助手。只能基于给定消息证据和市场证据判断阶段，"
        "不编造外部信息，不给买卖建议。输出必须是严格 JSON object，不能有 Markdown。"
    )


def _user_prompt(pack: EvidencePack) -> str:
    candidate = pack.candidate
    lines = [
        f"股票：{candidate.stock.name} {candidate.stock.ts_code}",
        f"触发：原始 {candidate.trigger_count} 条，去重 {candidate.unique_trigger_count} 条，发送人 {candidate.sender_count}，会话 {candidate.conversation_count}",
        f"召回通道：{', '.join(sorted(candidate.channels))}",
        f"强证据分：{candidate.evidence_score}，强证据类型：{candidate.family_counts}",
        "",
        "阶段只能选一个，并必须输出英文阶段码：",
        ", ".join(f"{key}({value})" for key, value in STAGE_LABELS.items()),
        "",
        "阶段判断口径：",
        "- lead 线索期：只有少量早期消息，逻辑还没被充分解释，主要价值是进入观察池。",
        "- seed 种子期：出现报告、调研、订单、涨价、供需等明确证据，但扩散范围还小。",
        "- formed 论证期：逻辑链条已经完整，能说明为什么、催化是什么、对应哪些股票。",
        "- spreading 扩散期：多发送人/多会话/多机构重复传播，路演、强推、纪要开始密集。",
        "- pricing 定价期：证据链与股价/成交/强 call 同时出现，市场正在快速反映。",
        "- crowded 拥挤期：群里高频争论、观点趋同、强烈追高或一致预期明显，性价比变差。",
        "",
        "只输出这个 JSON schema，字段必须齐全：",
        "{",
        '  "stage_code": "lead|seed|formed|spreading|pricing|crowded",',
        '  "stage_label": "中文阶段名",',
        '  "confidence": 0.0,',
        '  "one_line": "一句话结论，说明为什么是这个阶段",',
        '  "why": ["最多4条，说明阶段判断依据"],',
        '  "evidence_chain": [',
        '    {"time": "YYYY-MM-DD HH:MM", "type": "调研|报告|路演|催化|扩散|价格|其他", "evidence": "证据摘要", "message_id": "原消息ID"}',
        "  ],",
        '  "incremental": {"valid": true, "points": ["增量成立或不成立的关键点"]},',
        '  "pricing_risk": "定价风险，没有证据就写证据不足",',
        '  "crowding_risk": "拥挤风险，没有证据就写证据不足",',
        '  "watch_next": ["接下来要验证的事项"]',
        "}",
        "",
        "要求：",
        "- confidence 用 0 到 1 的数字，不要百分号，不能固定填 0.85。",
        "- confidence 口径：0.55 以下=证据薄弱；0.60-0.70=阶段可疑但有线索；0.70-0.80=证据链基本成立但有关键缺口；0.80-0.90=证据链清楚且多源验证；0.90 以上=阶段非常明确且几乎没有关键缺口。",
        "- 如果缺少股价/成交/定价证据，不要因为讨论热度高就判 pricing。",
        "- 如果缺少多会话/多发送人扩散证据，不要判 spreading。",
        "- pricing 必须结合市场证据：明显上涨、涨停、成交额/成交量放大、突破或连续大涨，不能只看消息热度。",
        "- crowded 必须结合市场证据和讨论证据：高位大涨后继续密集强推/争论/观点趋同，不能只看上涨。",
        "- evidence_chain 只选最关键的 5-8 条，必须来自下面证据时间线，不要编造。",
        "- 没有足够证据时要降阶段、降 confidence，并说明缺什么。",
        "",
        "证据时间线：",
    ]
    for item in pack.evidence[:80]:
        row = item.message
        snippet = " ".join(row.raw_content.split())[:220]
        lines.append(
            f"- message_id={row.message_id} | {row.message_time.isoformat()} | {row.sender} | {row.group_name or row.source} | "
            f"{row.category or '-'} | {','.join(item.evidence_families) or '-'} | {snippet}"
        )
    if pack.market is not None:
        lines.extend(["", "市场证据（本地 tushare daily 缓存，只用于判断定价/拥挤风险）："])
        lines.append(f"- 摘要：{pack.market.summary}")
        for point in pack.market.points:
            amount_yi = point.amount / 100000 if point.amount is not None else None
            amount_text = f"{amount_yi:.2f}亿" if amount_yi is not None else "-"
            ratio_text = f"{point.amount_ratio_5d:.2f}x" if point.amount_ratio_5d is not None else "-"
            pct_text = f"{point.pct_chg:.2f}%" if point.pct_chg is not None else "-"
            lines.append(
                f"- {point.trade_date} | {point.tag} | close={point.close} | pct_chg={pct_text} | "
                f"amount={amount_text} | amount_vs_prev5={ratio_text}"
            )
    return "\n".join(lines)


def _market_payload(pack: EvidencePack) -> dict[str, object]:
    if pack.market is None:
        return {}
    return {
        "summary": pack.market.summary,
        "points": [
            {
                "trade_date": point.trade_date,
                "close": point.close,
                "pct_chg": point.pct_chg,
                "amount": point.amount,
                "amount_ratio_5d": point.amount_ratio_5d,
                "tag": point.tag,
            }
            for point in pack.market.points
        ],
    }


def _parse_result(text: str) -> dict[str, object]:
    raw = _strip_json_fence(text.strip())
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_stage(result: dict[str, object], text: str) -> str:
    value = str(result.get("stage_code") or result.get("stage") or "")
    if value:
        value = value.strip().lower()
        if value in STAGES:
            return value
    match = STAGE_RE.search(text)
    if not match:
        return "formed"
    stage = match.group(1).lower()
    return stage if stage in STAGES else "formed"


def _extract_confidence(result: dict[str, object]) -> float | None:
    value = result.get("confidence")
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence > 1:
        confidence = confidence / 100
    return max(0.0, min(confidence, 1.0))


def _short_summary(result: dict[str, object], text: str) -> str:
    one_line = str(result.get("one_line") or "").strip()
    if one_line:
        return one_line[:240]
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first[:240]
