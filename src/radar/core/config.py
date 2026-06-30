from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "radar"
DEFAULT_BRAVE_SEARCH_BASE_URL = "https://api.search.brave.com"
DEFAULT_BRAVE_SEARCH_TIMEOUT = 30.0
DEFAULT_BARK_BASE_URL = "https://api.day.app"
DEFAULT_BARK_TIMEOUT = 10.0
BUILTIN_CHAT_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class StorageConfig(BaseModel):
    data_dir: Path = Field(default_factory=lambda: DEFAULT_CONFIG_DIR / "data")
    database: Path | None = None
    reports_database: Path | None = None

    @model_validator(mode="after")
    def normalize_paths(self) -> "StorageConfig":
        self.data_dir = self.data_dir.expanduser()
        if self.database is not None:
            self.database = self.database.expanduser()
        if self.reports_database is not None:
            self.reports_database = self.reports_database.expanduser()
        if self.database is None:
            self.database = self.data_dir / "radar.sqlite3"
        if self.reports_database is None:
            self.reports_database = self.data_dir / "reports.sqlite3"
        return self


class WechatSourceConfig(BaseModel):
    name: Literal["个人消息", "个人群"]
    endpoint: str


class WechatConfig(BaseModel):
    timeout: float = 30.0
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    retry_max_backoff_seconds: float = Field(default=8.0, ge=0.0, le=120.0)
    sources: dict[str, WechatSourceConfig] = Field(
        default_factory=lambda: {
            "personal_message": WechatSourceConfig(name="个人消息", endpoint="wechat_main"),
            "group_message": WechatSourceConfig(name="个人群", endpoint="wechat_main"),
        }
    )


class WechatEndpointSecret(BaseModel):
    base_url: str


class WechatSecrets(BaseModel):
    endpoints: dict[str, WechatEndpointSecret] = Field(default_factory=dict)


class LlmProviderConfig(BaseModel):
    protocol: Literal["openai", "anthropic"]
    secret_ref: str
    model: str
    context_window_tokens: int = Field(default=256_000, ge=1)
    timeout: float = 120.0
    max_tokens: int | None = None
    temperature: float | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class LlmConfig(BaseModel):
    default_provider: str | None = None
    providers: dict[str, LlmProviderConfig] = Field(default_factory=dict)
    task_routing: dict[str, str] = Field(default_factory=dict)


class ChatSkillsConfig(BaseModel):
    enabled: bool = True
    paths: list[Path] = Field(default_factory=list)
    max_active: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def normalize_paths(self) -> "ChatSkillsConfig":
        self.paths = [path.expanduser() for path in self.paths]
        return self


class ChatShellConfig(BaseModel):
    enabled: bool = True
    shell_path: str = "/bin/zsh"
    default_cwd: Path | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_output_chars: int = Field(default=12000, ge=1000, le=100000)

    @model_validator(mode="after")
    def normalize_paths(self) -> "ChatShellConfig":
        if self.default_cwd is not None:
            self.default_cwd = self.default_cwd.expanduser()
        return self


class ChatConfig(BaseModel):
    skills: ChatSkillsConfig = Field(default_factory=ChatSkillsConfig)
    shell: ChatShellConfig = Field(default_factory=ChatShellConfig)


class WebAuthConfig(BaseModel):
    enabled: bool = False


class WebConfig(BaseModel):
    auth: WebAuthConfig = Field(default_factory=WebAuthConfig)


class SchedulerConfig(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = Field(default=30, ge=5, le=3600)


class LlmProviderSecret(BaseModel):
    base_url: str
    api_key: str


class MarketConfig(BaseModel):
    provider: Literal["tushare"] | None = None
    secret_ref: str | None = None
    api_url: str = "http://api.tushare.pro"
    timeout: float = 30.0
    request_delay_ms: int = Field(default=150, ge=0)
    database: Path | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_tushare_api_url(cls, data: object) -> object:
        """兼容 stock-news 的 market.tushare_api_url 配置名。"""

        if not isinstance(data, dict):
            return data
        if data.get("tushare_api_url") and not data.get("api_url"):
            data = dict(data)
            data["api_url"] = data["tushare_api_url"]
        return data

    @model_validator(mode="after")
    def normalize_paths(self) -> "MarketConfig":
        if self.database is not None:
            self.database = self.database.expanduser()
        return self


class MarketSecret(BaseModel):
    token: str | None = None


class BraveSearchConfig(BaseModel):
    provider: Literal["brave"] | None = None
    secret_ref: str | None = None
    base_url: str = DEFAULT_BRAVE_SEARCH_BASE_URL
    timeout: float = DEFAULT_BRAVE_SEARCH_TIMEOUT


class BraveSearchSecret(BaseModel):
    api_key: str | None = None


class BarkChannelConfig(BaseModel):
    enabled: bool = False
    secret_ref: str | None = None
    base_url: str = DEFAULT_BARK_BASE_URL
    timeout: float = DEFAULT_BARK_TIMEOUT
    default_group: str | None = None
    default_level: (
        Literal["critical", "active", "timeSensitive", "passive"] | None
    ) = None


class ChannelConfig(BaseModel):
    bark: BarkChannelConfig = Field(default_factory=BarkChannelConfig)


class BarkChannelSecret(BaseModel):
    device_key: str | None = None
    device_keys: list[str] = Field(default_factory=list)


class ChannelSecrets(BaseModel):
    bark: dict[str, BarkChannelSecret] = Field(default_factory=dict)


class AlyCloudConfig(BaseModel):
    enabled: bool = False
    secret_ref: str | None = None
    host: str = ""
    user: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    remote_dir: str = ""
    url_prefix: str = ""
    sshpass_path: str = "sshpass"


class CloudConfig(BaseModel):
    aly: AlyCloudConfig = Field(default_factory=AlyCloudConfig)


class AlyCloudSecret(BaseModel):
    password: str | None = None


class CloudSecrets(BaseModel):
    aly: dict[str, AlyCloudSecret] = Field(default_factory=dict)


class WebAuthSecret(BaseModel):
    token: str | None = None


class WebSecrets(BaseModel):
    auth: WebAuthSecret = Field(default_factory=WebAuthSecret)


class FeatureFlags(BaseModel):
    signal_radar: bool = False
    tushare_market: bool = False
    delivery: bool = False


class FiltersConfig(BaseModel):
    """阶段一只做硬过滤：按群名黑名单过滤明显非投研群。"""

    group_blacklist_patterns: list[str] = Field(default_factory=list)


class RadarSecrets(BaseModel):
    """敏感配置单独建模，避免把 token 混进普通运行配置。"""

    wechat: WechatSecrets = Field(default_factory=WechatSecrets)
    llm: dict[str, LlmProviderSecret] = Field(default_factory=dict)
    market: dict[str, MarketSecret] = Field(default_factory=dict)
    brave_search: dict[str, BraveSearchSecret] = Field(default_factory=dict)
    channel: ChannelSecrets = Field(default_factory=ChannelSecrets)
    cloud: CloudSecrets = Field(default_factory=CloudSecrets)
    web: WebSecrets = Field(default_factory=WebSecrets)


class RadarConfig(BaseModel):
    """合并后的运行配置；CLI 和 Web 都只消费这一种模型。"""

    config_dir: Path = DEFAULT_CONFIG_DIR
    storage: StorageConfig = Field(default_factory=StorageConfig)
    wechat: WechatConfig = Field(default_factory=WechatConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    channel: ChannelConfig = Field(default_factory=ChannelConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    brave_search: BraveSearchConfig = Field(default_factory=BraveSearchConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    secrets: RadarSecrets = Field(default_factory=RadarSecrets)

    @property
    def data_dir(self) -> Path:
        return self.storage.data_dir

    @property
    def database_path(self) -> Path:
        return self.storage.database or self.storage.data_dir / "radar.sqlite3"

    @property
    def market_database_path(self) -> Path:
        return self.market.database or self.storage.data_dir / "market.sqlite3"

    @property
    def reports_database_path(self) -> Path:
        return self.storage.reports_database or self.storage.data_dir / "reports.sqlite3"

    @property
    def chat_skill_paths(self) -> list[Path]:
        paths = self.chat.skills.paths or [Path("skills")]
        resolved_paths = [path if path.is_absolute() else self.config_dir / path for path in paths]
        return [BUILTIN_CHAT_SKILLS_DIR, *resolved_paths]

    @property
    def wechat_base_url(self) -> str | None:
        source = self.wechat.sources.get("group_message") or next(iter(self.wechat.sources.values()), None)
        if source is None:
            return None
        endpoint = self.secrets.wechat.endpoints.get(source.endpoint)
        return endpoint.base_url if endpoint else None

    def wechat_endpoint_url(self, source_key: str) -> str:
        source = self.wechat.sources[source_key]
        endpoint = self.secrets.wechat.endpoints.get(source.endpoint)
        if endpoint is None:
            raise KeyError(f"未配置微信 endpoint: {source.endpoint}")
        return endpoint.base_url


def load_config(config_dir: Path | None = None) -> RadarConfig:
    """读取 config.yaml 和 secrets.yaml，并允许环境变量做最小覆盖。"""

    resolved_dir = _config_dir(config_dir)
    config_data = _read_yaml(resolved_dir / "config.yaml")
    secrets_data = _read_yaml(resolved_dir / "secrets.yaml")
    config = RadarConfig(config_dir=resolved_dir, **config_data, secrets=RadarSecrets(**secrets_data))
    return _apply_env_overrides(config)


def _config_dir(config_dir: Path | None) -> Path:
    if config_dir is not None:
        return config_dir.expanduser()
    return Path(os.getenv("RADAR_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))).expanduser()


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    # 配置文件只允许 YAML mapping，避免误把 list/string 当成配置根节点。
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件根节点必须是 mapping: {path}")
    return data


def _apply_env_overrides(config: RadarConfig) -> RadarConfig:
    data_dir = os.getenv("RADAR_DATA_DIR")
    if data_dir:
        config.storage.data_dir = Path(data_dir).expanduser()
        config.storage.database = config.storage.data_dir / "radar.sqlite3"
        config.storage.reports_database = config.storage.data_dir / "reports.sqlite3"
        if config.market.database is None:
            config.market.database = config.storage.data_dir / "market.sqlite3"

    base_url = os.getenv("RADAR_WECHAT_BASE_URL")
    if base_url:
        config.secrets.wechat.endpoints["wechat_main"] = WechatEndpointSecret(base_url=base_url)

    tushare_token = os.getenv("RADAR_TUSHARE_TOKEN")
    if tushare_token:
        secret_ref = config.market.secret_ref or "tushare_main"
        config.market.provider = "tushare"
        config.market.secret_ref = secret_ref
        config.secrets.market[secret_ref] = MarketSecret(token=tushare_token)

    tushare_api_url = os.getenv("RADAR_TUSHARE_API_URL")
    if tushare_api_url:
        config.market.api_url = tushare_api_url

    request_delay_ms = os.getenv("RADAR_TUSHARE_REQUEST_DELAY_MS")
    if request_delay_ms:
        config.market.request_delay_ms = int(request_delay_ms)

    market_database = os.getenv("RADAR_MARKET_DATABASE")
    if market_database:
        config.market.database = Path(market_database).expanduser()

    reports_database = os.getenv("RADAR_REPORTS_DATABASE")
    if reports_database:
        config.storage.reports_database = Path(reports_database).expanduser()

    _apply_channel_overrides(config)
    _apply_brave_search_overrides(config)
    _apply_web_auth_overrides(config)
    return config


def _apply_channel_overrides(config: RadarConfig) -> None:
    bark_device_key = os.getenv("RADAR_BARK_DEVICE_KEY") or os.getenv("BARK_DEVICE_KEY")
    bark_device_keys = os.getenv("RADAR_BARK_DEVICE_KEYS") or os.getenv("BARK_DEVICE_KEYS")
    if bark_device_key:
        secret_ref = config.channel.bark.secret_ref or "bark_main"
        config.channel.bark.enabled = True
        config.channel.bark.secret_ref = secret_ref
        config.secrets.channel.bark[secret_ref] = BarkChannelSecret(device_key=bark_device_key)
    if bark_device_keys:
        secret_ref = config.channel.bark.secret_ref or "bark_main"
        config.channel.bark.enabled = True
        config.channel.bark.secret_ref = secret_ref
        config.secrets.channel.bark[secret_ref] = BarkChannelSecret(
            device_keys=_split_env_list(bark_device_keys)
        )

    bark_base_url = os.getenv("RADAR_BARK_BASE_URL") or os.getenv("BARK_BASE_URL")
    if bark_base_url:
        config.channel.bark.base_url = bark_base_url

    bark_timeout = os.getenv("RADAR_BARK_TIMEOUT")
    if bark_timeout:
        config.channel.bark.timeout = float(bark_timeout)


def _apply_brave_search_overrides(config: RadarConfig) -> None:
    brave_search_api_key = _brave_search_env_key()
    if brave_search_api_key and not _has_brave_search_secret(config):
        _set_brave_search_secret(config, brave_search_api_key)

    brave_search_base_url = os.getenv("RADAR_BRAVE_SEARCH_BASE_URL") or os.getenv(
        "BRAVE_SEARCH_BASE_URL"
    )
    if brave_search_base_url:
        config.brave_search.base_url = brave_search_base_url

    timeout = os.getenv("RADAR_BRAVE_SEARCH_TIMEOUT")
    if timeout:
        config.brave_search.timeout = float(timeout)


def _split_env_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _brave_search_env_key() -> str | None:
    return (
        os.getenv("RADAR_BRAVE_SEARCH_API_KEY")
        or os.getenv("BRAVE_SEARCH_API_KEY")
        or os.getenv("BRAVE_API_KEY")
    )


def _has_brave_search_secret(config: RadarConfig) -> bool:
    secret_ref = config.brave_search.secret_ref
    if not secret_ref:
        return False
    secret = config.secrets.brave_search.get(secret_ref)
    return bool(secret and secret.api_key)


def _set_brave_search_secret(config: RadarConfig, api_key: str) -> None:
    secret_ref = config.brave_search.secret_ref or "brave_search_main"
    config.brave_search.provider = "brave"
    config.brave_search.secret_ref = secret_ref
    config.secrets.brave_search[secret_ref] = BraveSearchSecret(api_key=api_key)


def _apply_web_auth_overrides(config: RadarConfig) -> None:
    enabled = os.getenv("RADAR_WEB_AUTH_ENABLED")
    if enabled is not None:
        config.web.auth.enabled = enabled.lower() in {"1", "true", "yes", "on"}

    token = os.getenv("RADAR_WEB_AUTH_TOKEN") or os.getenv("RADAR_API_TOKEN")
    if token:
        config.secrets.web.auth.token = token
    if token and enabled is None:
        config.web.auth.enabled = True
