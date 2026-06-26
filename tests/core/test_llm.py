from __future__ import annotations

from radar.core.config import RadarConfig, RadarSecrets
from radar.core.llm import (
    LlmChatDelta,
    LlmChatDone,
    LlmReasoningDelta,
    LlmToolCallDelta,
    LlmToolCallDone,
    LlmToolCallStarted,
    LlmToolSpec,
    RuntimeLlmProvider,
    chat,
    chat_json,
    resolve_provider,
)
from radar.core.llm.anthropic_client import chat_anthropic
from radar.core.llm.anthropic_client import chat_anthropic_response
from radar.core.llm.anthropic_client import stream_chat_anthropic_response
from radar.core.llm.openai_client import chat_openai
from radar.core.llm.openai_client import chat_openai_response
from radar.core.llm.openai_client import stream_chat_openai_response


def test_resolve_provider_uses_task_routing_and_secret():
    config = _config()

    name, provider = resolve_provider(config, task="chat")

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


def test_openai_client_streams_text_and_parses_tool_calls(monkeypatch):
    captured = {}

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    'data: {"choices":[{"delta":{"content":"先"}}]}',
                    'data: {"choices":[{"delta":{"content":"看"}}]}',
                    (
                        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
                        '"function":{"name":"search_","arguments":"{\\"query\\""}}]}}]}'
                    ),
                    (
                        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                        '"function":{"name":"messages","arguments":":\\"AI\\"}"}}]}}]}'
                    ),
                    "data: [DONE]",
                ]
            )

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def stream(self, method, url, headers, json):
            captured.update({"method": method, "url": url, "headers": headers, "json": json})
            return FakeStreamResponse()

    monkeypatch.setattr("radar.core.llm.openai_client.httpx.Client", FakeClient)

    events = list(
        stream_chat_openai_response(
            _provider("openai", "https://llm.example/v1"),
            [{"role": "user", "content": "hello"}],
            tools=[_tool_spec()],
        )
    )

    assert captured["json"]["stream"] is True
    assert [event.content for event in events if isinstance(event, LlmChatDelta)] == ["先", "看"]
    started = [event for event in events if isinstance(event, LlmToolCallStarted)]
    assert [(event.index, event.call_id) for event in started] == [(0, "call-1")]
    assert [event.arguments_delta for event in events if isinstance(event, LlmToolCallDelta)] == ['{"query"', ':"AI"}']
    completed = [event for event in events if isinstance(event, LlmToolCallDone)]
    assert [(event.index, event.tool_call.name) for event in completed] == [(0, "search_messages")]
    done = [event for event in events if isinstance(event, LlmChatDone)][0]
    assert done.response.content == "先看"
    assert done.response.tool_calls[0].name == "search_messages"
    assert done.response.tool_calls[0].arguments == {"query": "AI"}


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


def test_anthropic_client_streams_text_and_parses_tool_calls(monkeypatch):
    captured = {}

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    'event: message_start',
                    'data: {"type":"message_start","message":{"id":"msg-1"}}',
                    'event: content_block_delta',
                    (
                        'data: {"type":"content_block_delta","index":0,'
                        '"delta":{"type":"thinking_delta","thinking":"先判断是否需要工具。"}}'
                    ),
                    'event: content_block_delta',
                    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"先"}}',
                    'event: content_block_delta',
                    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"看"}}',
                    'event: content_block_start',
                    (
                        'data: {"type":"content_block_start","index":1,'
                        '"content_block":{"type":"tool_use","id":"toolu-1","name":"search_messages","input":{}}}'
                    ),
                    'event: content_block_delta',
                    (
                        'data: {"type":"content_block_delta","index":1,'
                        '"delta":{"type":"input_json_delta","partial_json":"{\\"query\\":\\"AI\\"}"}}'
                    ),
                    'event: message_stop',
                    'data: {"type":"message_stop"}',
                ]
            )

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def stream(self, method, url, headers, json):
            captured.update({"method": method, "url": url, "headers": headers, "json": json})
            return FakeStreamResponse()

    monkeypatch.setattr("radar.core.llm.anthropic_client.httpx.Client", FakeClient)

    events = list(
        stream_chat_anthropic_response(
            _provider("anthropic", "https://api.anthropic.com"),
            [{"role": "user", "content": "hello"}],
            tools=[_tool_spec()],
            enable_thinking=True,
        )
    )

    assert captured["json"]["stream"] is True
    assert captured["json"]["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert captured["json"]["temperature"] == 1
    assert [event.content for event in events if isinstance(event, LlmReasoningDelta)] == ["先判断是否需要工具。"]
    assert [event.content for event in events if isinstance(event, LlmChatDelta)] == ["先", "看"]
    started = [event for event in events if isinstance(event, LlmToolCallStarted)]
    assert [(event.index, event.call_id, event.name) for event in started] == [(1, "toolu-1", "search_messages")]
    assert [event.arguments_delta for event in events if isinstance(event, LlmToolCallDelta)] == ['{"query":"AI"}']
    completed = [event for event in events if isinstance(event, LlmToolCallDone)]
    assert [(event.index, event.tool_call.name) for event in completed] == [(1, "search_messages")]
    done = [event for event in events if isinstance(event, LlmChatDone)][0]
    assert done.response.content == "先看"
    assert done.response.tool_calls[0].call_id == "toolu-1"
    assert done.response.tool_calls[0].arguments == {"query": "AI"}


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
            "task_routing": {"chat": "anthropic_main"},
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
