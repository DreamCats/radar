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
    assert config.wechat_endpoint_url("group_message") == "https://example.invalid/wechat"
    assert config.features.llm_classify is False
    assert config.filters.group_blacklist_patterns == ["小学", "寝室"]


def test_env_overrides_wechat_base_url(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_WECHAT_BASE_URL", "https://example.invalid/env")

    config = load_config(config_dir)

    assert config.wechat_base_url == "https://example.invalid/env"
