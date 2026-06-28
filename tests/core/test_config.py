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
filters:
  group_blacklist_patterns:
    - 小学
    - 寝室
chat:
  skills:
    paths:
      - skills
    max_active: 2
  shell:
    default_cwd: ~/Work/radar
    timeout_seconds: 10
    max_output_chars: 2000
channel:
  bark:
    enabled: true
    secret_ref: bark_main
    base_url: https://example.invalid/bark
    timeout: 8
    default_group: radar
    default_level: timeSensitive
cloud:
  aly:
    enabled: true
    secret_ref: aly_main
    host: 39.106.190.32
    user: root
    port: 22
    remote_dir: /usr/share/caddy/radar
    url_prefix: http://39.106.190.32/radar
    sshpass_path: /opt/homebrew/bin/sshpass
""",
        encoding="utf-8",
    )
    (config_dir / "secrets.yaml").write_text(
        """
wechat:
  endpoints:
    wechat_main:
      base_url: https://example.invalid/wechat
channel:
  bark:
    bark_main:
      device_key: bark-secret
      device_keys:
        - bark-secret-2
        - bark-secret-3
cloud:
  aly:
    aly_main:
      password: aly-secret
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)

    assert config.wechat.timeout == 10
    assert str(config.data_dir).endswith("data")
    assert "~" not in str(config.database_path)
    assert config.market_database_path == config.data_dir / "market.sqlite3"
    assert config.wechat_endpoint_url("group_message") == "https://example.invalid/wechat"
    assert config.filters.group_blacklist_patterns == ["小学", "寝室"]
    assert config.chat_skill_paths == [config_dir / "skills"]
    assert config.chat.skills.max_active == 2
    assert str(config.chat.shell.default_cwd).endswith("Work/radar")
    assert "~" not in str(config.chat.shell.default_cwd)
    assert config.chat.shell.timeout_seconds == 10
    assert config.chat.shell.max_output_chars == 2000
    assert config.channel.bark.enabled is True
    assert config.channel.bark.secret_ref == "bark_main"
    assert config.channel.bark.base_url == "https://example.invalid/bark"
    assert config.channel.bark.timeout == 8
    assert config.channel.bark.default_group == "radar"
    assert config.channel.bark.default_level == "timeSensitive"
    assert config.secrets.channel.bark["bark_main"].device_key == "bark-secret"
    assert config.secrets.channel.bark["bark_main"].device_keys == [
        "bark-secret-2",
        "bark-secret-3",
    ]
    assert config.cloud.aly.enabled is True
    assert config.cloud.aly.secret_ref == "aly_main"
    assert config.cloud.aly.host == "39.106.190.32"
    assert config.cloud.aly.user == "root"
    assert config.cloud.aly.port == 22
    assert config.cloud.aly.remote_dir == "/usr/share/caddy/radar"
    assert config.cloud.aly.url_prefix == "http://39.106.190.32/radar"
    assert config.cloud.aly.sshpass_path == "/opt/homebrew/bin/sshpass"
    assert config.secrets.cloud.aly["aly_main"].password == "aly-secret"


def test_env_overrides_wechat_base_url(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_WECHAT_BASE_URL", "https://example.invalid/env")

    config = load_config(config_dir)

    assert config.wechat_base_url == "https://example.invalid/env"


def test_env_overrides_tushare_token(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_TUSHARE_TOKEN", "token-from-env")
    monkeypatch.setenv("RADAR_TUSHARE_API_URL", "https://example.invalid/tushare")
    monkeypatch.setenv("RADAR_TUSHARE_REQUEST_DELAY_MS", "200")
    monkeypatch.setenv("RADAR_MARKET_DATABASE", "~/radar-market.sqlite3")

    config = load_config(config_dir)

    assert config.market.provider == "tushare"
    assert config.market.secret_ref == "tushare_main"
    assert config.market.api_url == "https://example.invalid/tushare"
    assert config.market.request_delay_ms == 200
    assert str(config.market_database_path).endswith("radar-market.sqlite3")
    assert "~" not in str(config.market_database_path)
    assert config.secrets.market["tushare_main"].token == "token-from-env"


def test_env_overrides_brave_search_key(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_BRAVE_SEARCH_API_KEY", "brave-key-from-env")
    monkeypatch.setenv("RADAR_BRAVE_SEARCH_BASE_URL", "https://example.invalid/brave")
    monkeypatch.setenv("RADAR_BRAVE_SEARCH_TIMEOUT", "12")

    config = load_config(config_dir)

    assert config.brave_search.provider == "brave"
    assert config.brave_search.secret_ref == "brave_search_main"
    assert config.brave_search.base_url == "https://example.invalid/brave"
    assert config.brave_search.timeout == 12
    assert config.secrets.brave_search["brave_search_main"].api_key == "brave-key-from-env"


def test_env_overrides_bark_channel(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_BARK_DEVICE_KEY", "bark-key-from-env")
    monkeypatch.setenv("RADAR_BARK_BASE_URL", "https://example.invalid/bark")
    monkeypatch.setenv("RADAR_BARK_TIMEOUT", "6")

    config = load_config(config_dir)

    assert config.channel.bark.enabled is True
    assert config.channel.bark.secret_ref == "bark_main"
    assert config.channel.bark.base_url == "https://example.invalid/bark"
    assert config.channel.bark.timeout == 6
    assert config.secrets.channel.bark["bark_main"].device_key == "bark-key-from-env"


def test_env_overrides_bark_device_keys(config_dir: Path, monkeypatch):
    monkeypatch.setenv("RADAR_BARK_DEVICE_KEYS", "bark-a, bark-b")

    config = load_config(config_dir)

    assert config.channel.bark.enabled is True
    assert config.channel.bark.secret_ref == "bark_main"
    assert config.secrets.channel.bark["bark_main"].device_keys == ["bark-a", "bark-b"]


def test_load_does_not_read_brave_search_cli_config(config_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cli_config = tmp_path / "Library" / "Application Support" / "brave-search" / "config.json"
    cli_config.parent.mkdir(parents=True)
    cli_config.write_text(
        """
{
  "api_key": "brave-key-from-cli",
  "base_url": "https://api.search.brave.software",
  "timeout": 7
}
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)

    assert config.brave_search.provider is None
    assert config.brave_search.secret_ref is None
    assert config.brave_search.base_url == "https://api.search.brave.com"
    assert config.brave_search.timeout == 30
    assert config.secrets.brave_search == {}


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
