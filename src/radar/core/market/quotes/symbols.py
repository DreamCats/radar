from __future__ import annotations


def to_public_quote_code(ts_code: str) -> str:
    """把 Tushare 代码转成腾讯/新浪公开行情代码，例如 000811.SZ -> sz000811。"""

    raw = ts_code.strip()
    if not raw:
        raise ValueError("ts_code 不能为空")
    code, market = _split_ts_code(raw)
    return f"{market.lower()}{code}"


def from_public_quote_code(quote_code: str) -> str:
    raw = quote_code.strip().lower()
    if len(raw) < 3:
        raise ValueError(f"不支持的行情代码: {quote_code}")
    market = raw[:2]
    code = raw[2:]
    if not code.isdigit():
        raise ValueError(f"不支持的行情代码: {quote_code}")
    if market == "sz":
        return f"{code}.SZ"
    if market == "sh":
        return f"{code}.SH"
    if market == "bj":
        return f"{code}.BJ"
    raise ValueError(f"不支持的行情市场: {market}")


def _split_ts_code(value: str) -> tuple[str, str]:
    upper = value.upper()
    if "." in upper:
        code, market = upper.split(".", 1)
    else:
        code = upper
        market = _infer_market(code)
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"不支持的股票代码: {value}")
    if market not in {"SZ", "SH", "BJ"}:
        raise ValueError(f"不支持的股票市场: {market}")
    return code, market


def _infer_market(code: str) -> str:
    if code.startswith(("0", "2", "3")):
        return "SZ"
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    raise ValueError(f"无法从股票代码推断市场: {code}")
