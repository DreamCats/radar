from __future__ import annotations

from radar.core.chat.cninfo_disclosures import search_cninfo_disclosures


def test_cninfo_disclosure_search_falls_back_from_keyword_to_category(monkeypatch):
    posts = []

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, *, timeout, headers, follow_redirects):
            self.timeout = timeout
            self.headers = headers
            self.follow_redirects = follow_redirects

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            return FakeResponse(
                {
                    "stockList": [
                        {
                            "code": "600233",
                            "zwjc": "圆通速递",
                            "orgId": "gssh0600233",
                        }
                    ]
                }
            )

        def post(self, url, data):
            posts.append(dict(data))
            if data["searchkey"]:
                return FakeResponse(
                    {
                        "totalAnnouncement": 0,
                        "announcements": None,
                    }
                )
            return FakeResponse(
                {
                    "totalAnnouncement": 1,
                    "announcements": [
                        {
                            "secCode": "600233",
                            "secName": "圆通速递",
                            "announcementTitle": (
                                "圆通速递股份有限公司关于2026年半年度"
                                "<em>业绩</em>预增的公告"
                            ),
                            "announcementTime": 1782835200000,
                            "announcementId": "1225399544",
                            "orgId": "gssh0600233",
                        }
                    ],
                }
            )

    monkeypatch.setattr("radar.core.chat.cninfo_disclosures.httpx.Client", FakeClient)

    result = search_cninfo_disclosures(
        stock="圆通速递",
        ts_code="600233.SH",
        keywords=["业绩预告", "净利润"],
        category=None,
        start_date="2026-07-01",
        end_date="2026-07-01",
        limit=5,
    )

    assert posts[0]["category"] == "category_yjygjxz_szsh"
    assert posts[0]["searchkey"] == "业绩预告"
    assert posts[1]["category"] == "category_yjygjxz_szsh"
    assert posts[1]["searchkey"] == ""
    assert result["source"] == "cninfo"
    assert result["code"] == "600233"
    assert result["category"] == "业绩预告"
    assert result["item_count"] == 1
    assert result["items"][0]["title"] == "圆通速递股份有限公司关于2026年半年度业绩预增的公告"
    assert result["items"][0]["announcement_time"] == "2026-07-01 00:00:00"
    assert "announcementId=1225399544" in result["items"][0]["url"]
