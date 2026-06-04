from __future__ import annotations

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.llm import RuntimeLlmProvider, chat, chat_json, resolve_provider
from radar.core.llm.anthropic_client import chat_anthropic
from radar.core.llm.openai_client import chat_openai


def test_resolve_provider_uses_task_routing_and_secret():
    config = _config()

    name, provider = resolve_provider(config, task="classify")

    assert name == "anthropic_main"
    assert provider.protocol == "anthropic"
    assert provider.base_url == "https://api.anthropic.com"
    assert provider.api_key == "anthropic-key"
    assert provider.disable_thinking is True


def test_chat_dispatches_openai_provider(monkeypatch):
    config = _config()
    calls = []

    def fake_chat_openai(provider, messages, model, temperature, max_tokens):
        calls.append((provider, messages, model, temperature, max_tokens))
        return f"{provider.name}:{messages[0]['content']}"

    monkeypatch.setattr("radar.core.llm.client.chat_openai", fake_chat_openai)

    reply = chat(config, [{"role": "user", "content": "ping"}], provider_name="openai_main")

    assert reply == "openai_main:ping"
    assert calls[0][0].api_key == "openai-key"


def test_chat_json_retries_invalid_json(monkeypatch):
    config = _config()
    replies = iter(["不是 json", '```json\n{"ok": true}\n```'])
    seen_messages = []

    def fake_chat(config, messages, **kwargs):
        seen_messages.append(messages)
        return next(replies)

    monkeypatch.setattr("radar.core.llm.client.chat", fake_chat)

    parsed = chat_json(config, [{"role": "user", "content": "return json"}])

    assert parsed == {"ok": True}
    assert seen_messages[1][-1]["content"].startswith("返回格式不是合法 JSON 对象")


def test_openai_client_builds_chat_completions_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("radar.core.llm.openai_client.httpx.Client", FakeClient)

    reply = chat_openai(
        _provider("openai", "https://llm.example/v1"),
        [{"role": "user", "content": "hello"}],
    )

    assert reply == "ok"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer key"
    assert captured["json"]["model"] == "test-model"


def test_anthropic_client_builds_messages_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"content": [{"type": "text", "text": "ok"}]}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("radar.core.llm.anthropic_client.httpx.Client", FakeClient)

    reply = chat_anthropic(
        _provider("anthropic", "https://api.anthropic.com/v1"),
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ],
    )

    assert reply == "ok"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["X-Api-Key"] == "key"
    assert captured["json"]["system"] == "sys"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hello"}]


def test_anthropic_client_can_disable_thinking(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"content": [{"type": "text", "text": "ok"}]}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("radar.core.llm.anthropic_client.httpx.Client", FakeClient)

    reply = chat_anthropic(
        _provider("anthropic", "https://api.example/anthropic", disable_thinking=True),
        [{"role": "user", "content": "hello"}],
    )

    assert reply == "ok"
    assert captured["json"]["thinking"] == {"type": "disabled"}


def _config() -> RadarConfig:
    return RadarConfig(
        llm={
            "default_provider": "openai_main",
            "providers": {
                "openai_main": {
                    "protocol": "openai",
                    "secret_ref": "openai_secret",
                    "model": "gpt-test",
                },
                "anthropic_main": {
                    "protocol": "anthropic",
                    "secret_ref": "anthropic_secret",
                    "model": "claude-test",
                    "disable_thinking": True,
                },
            },
            "task_routing": {"classify": "anthropic_main"},
        },
        secrets=RadarSecrets(
            llm={
                "openai_secret": {
                    "base_url": "https://openai.example/v1",
                    "api_key": "openai-key",
                },
                "anthropic_secret": {
                    "base_url": "https://api.anthropic.com",
                    "api_key": "anthropic-key",
                },
            }
        ),
    )


def _provider(
    protocol: str,
    base_url: str,
    *,
    disable_thinking: bool = False,
) -> RuntimeLlmProvider:
    return RuntimeLlmProvider(
        name="test",
        protocol=protocol,
        base_url=base_url,
        api_key="key",
        model="test-model",
        timeout=10,
        max_tokens=None,
        temperature=None,
        disable_thinking=disable_thinking,
        headers={},
    )
