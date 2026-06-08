from __future__ import annotations

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.llm import LlmToolSpec, RuntimeLlmProvider, chat, chat_json, resolve_provider
from radar.core.llm.anthropic_client import chat_anthropic
from radar.core.llm.anthropic_client import chat_anthropic_response
from radar.core.llm.openai_client import chat_openai
from radar.core.llm.openai_client import chat_openai_response


def test_resolve_provider_uses_task_routing_and_secret():
    config = _config()

    name, provider = resolve_provider(config, task="classify")

    assert name == "anthropic_main"
    assert provider.protocol == "anthropic"
    assert provider.base_url == "https://api.anthropic.com"
    assert provider.api_key == "anthropic-key"


def test_chat_dispatches_openai_provider(monkeypatch):
    config = _config()
    calls = []

    def fake_chat_openai_response(provider, messages, model, temperature, max_tokens, disable_thinking, tools):
        calls.append((provider, messages, model, temperature, max_tokens, disable_thinking, tools))
        from radar.core.llm import LlmChatResponse

        return LlmChatResponse(content=f"{provider.name}:{messages[0]['content']}", tool_calls=[])

    monkeypatch.setattr("radar.core.llm.openai_client.chat_openai_response", fake_chat_openai_response)

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

def test_chat_can_disable_anthropic_thinking(monkeypatch):
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
        _provider("anthropic", "https://api.example/anthropic"),
        [{"role": "user", "content": "hello"}],
        disable_thinking=True,
    )

    assert reply == "ok"
    assert captured["json"]["thinking"] == {"type": "disabled"}


def test_openai_client_parses_tool_calls(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "search_messages",
                                        "arguments": '{"query":"AI"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured.update({"json": json})
            return FakeResponse()

    monkeypatch.setattr("radar.core.llm.openai_client.httpx.Client", FakeClient)

    response = chat_openai_response(
        _provider("openai", "https://llm.example/v1"),
        [{"role": "user", "content": "hello"}],
        tools=[_tool_spec()],
    )

    assert captured["json"]["tools"][0]["function"]["name"] == "search_messages"
    assert response.content == ""
    assert response.tool_calls[0].name == "search_messages"
    assert response.tool_calls[0].arguments == {"query": "AI"}


def test_anthropic_client_parses_tool_use(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [
                    {"type": "text", "text": "我先查一下"},
                    {
                        "type": "tool_use",
                        "id": "toolu-1",
                        "name": "search_messages",
                        "input": {"query": "AI"},
                    },
                ]
            }

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            captured.update({"json": json})
            return FakeResponse()

    monkeypatch.setattr("radar.core.llm.anthropic_client.httpx.Client", FakeClient)

    response = chat_anthropic_response(
        _provider("anthropic", "https://api.anthropic.com"),
        [{"role": "user", "content": "hello"}],
        tools=[_tool_spec()],
    )

    assert captured["json"]["tools"][0]["name"] == "search_messages"
    assert response.content == "我先查一下"
    assert response.tool_calls[0].call_id == "toolu-1"
    assert response.tool_calls[0].arguments == {"query": "AI"}


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
        headers={},
    )


def _tool_spec() -> LlmToolSpec:
    return LlmToolSpec(
        name="search_messages",
        description="搜索本地消息",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
