from radar.core.tushare.stock_matcher import Stock, StockMatcher


ROBOT = Stock(ts_code="300024.SZ", symbol="300024", name="机器人")


def test_robot_stock_name_requires_explicit_code_in_strict_mode():
    matcher = StockMatcher([ROBOT])

    assert matcher.detect("#机器人：订单与客户验证加速") == []
    assert matcher.detect("【机器人】产业链产能继续释放") == []


def test_robot_stock_name_keeps_explicit_code_matches():
    matcher = StockMatcher([ROBOT])

    assert matcher.detect("300024 机器人：预计收入增长") == [ROBOT]
    assert matcher.detect("300024.SZ 预计收入增长") == [ROBOT]
