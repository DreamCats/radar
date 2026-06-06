from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "radar"


class StorageConfig(BaseModel):
    data_dir: Path = Field(default_factory=lambda: DEFAULT_CONFIG_DIR / "data")
    database: Path | None = None

    @model_validator(mode="after")
    def normalize_paths(self) -> "StorageConfig":
        self.data_dir = self.data_dir.expanduser()
        if self.database is not None:
            self.database = self.database.expanduser()
        if self.database is None:
            self.database = self.data_dir / "radar.sqlite3"
        return self


class WechatSourceConfig(BaseModel):
    name: Literal["个人消息", "个人群"]
    endpoint: str


class WechatConfig(BaseModel):
    timeout: float = 30.0
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
    timeout: float = 120.0
    max_tokens: int | None = None
    temperature: float | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class LlmConfig(BaseModel):
    default_provider: str | None = None
    providers: dict[str, LlmProviderConfig] = Field(default_factory=dict)
    task_routing: dict[str, str] = Field(default_factory=dict)


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


class FeatureFlags(BaseModel):
    llm_classify: bool = False
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


class RadarConfig(BaseModel):
    """合并后的运行配置；CLI 和 Web 都只消费这一种模型。"""

    config_dir: Path = DEFAULT_CONFIG_DIR
    storage: StorageConfig = Field(default_factory=StorageConfig)
    wechat: WechatConfig = Field(default_factory=WechatConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
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
    return config
