from __future__ import annotations

from pathlib import Path

from radar.core.config import load_config


def test_load_split_config(config_dir: Path):
    (config_dir / "config.yaml").write_text(
        """
storage:
  data_dir: ./data
wechat:
  timeout: 10
  sources:
    personal_message:
      name: 个人消息
      endpoint: wechat_main
    group_message:
      name: 个人群
      endpoint: wechat_main
features:
  llm_classify: false
filters:
  group_blacklist_patterns:
    - 小学
    - 寝室
""",
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text(
        """
wechat:
  endpoints:
    wechat_main:
      base_url: https://example.invalid/wechat
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)

    assert config.wechat.timeout == 10
    assert str(config.data_dir).endswith("data")
    assert "~" not in str(config.database_path)
    assert config.market_database_path == config.data_dir / "market.sqlite3"
    assert config.wechat_endpoint_url("group_message") == "https://example.invalid/wechat"
    assert config.features.llm_classify is False
    assert config.filters.group_blacklist_patterns == ["小学", "寝室"]


def test_env_overrides_wechat_base_url(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_WECHAT_BASE_URL", "https://example.invalid/env")

    config = load_config(config_dir)

    assert config.wechat_base_url == "https://example.invalid/env"


def test_env_overrides_tushare_token(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_TUSHARE_TOKEN", "token-from-env")
    monkeypatch.setenv("RADAR_TUSHARE_API_URL", "https://example.invalid/tushare")
    monkeypatch.setenv("RADAR_MARKET_DATABASE", "~/radar-market.sqlite3")

    config = load_config(config_dir)

    assert config.market.provider == "tushare"
    assert config.market.secret_ref == "tushare_main"
    assert config.market.api_url == "https://example.invalid/tushare"
    assert str(config.market_database_path).endswith("radar-market.sqlite3")
    assert "~" not in str(config.market_database_path)
    assert config.secrets.market["tushare_main"].token == "token-from-env"


def test_load_accepts_legacy_tushare_api_url(config_dir: Path):
    (config_dir / "config.yaml").write_text(
        """
market:
  provider: tushare
  secret_ref: tushare_main
  tushare_api_url: https://example.invalid/proxy
""",
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text(
        """
market:
  tushare_main:
    token: secret-token
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)

    assert config.market.api_url == "https://example.invalid/proxy"


def test_load_accepts_market_database(config_dir: Path):
    (config_dir / "config.yaml").write_text(
        """
storage:
  data_dir: ./data
market:
  database: ~/custom-market.sqlite3
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)

    assert str(config.market_database_path).endswith("custom-market.sqlite3")
    assert "~" not in str(config.market_database_path)
