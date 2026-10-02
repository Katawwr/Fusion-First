"""Provider adapters: request shaping and response mapping, exercised offline with fake SDKs."""

from __future__ import annotations

import pytest

from fusion_first.model.client import ModelRequest, ModelRole
from fusion_first.model.providers._common import strictify_schema
from fusion_first.model.providers.anthropic import AnthropicModelClient
from fusion_first.model.providers.openai import OpenAIModelClient

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "violated": {"type": "boolean"}},
                "required": ["id", "violated"],
            },
        },
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["criteria", "rationale", "confidence"],
}


# --------------------------- fake Anthropic SDK ---------------------------


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class _Msg:
    def __init__(self, text="{}", model="m", stop_reason="end_turn"):
        self.content = [_Block(text)] if text is not None else []
        self.model = model
        self.stop_reason = stop_reason
        self.usage = _Usage(11, 22)


class _FakeBadRequest(Exception):
    status_code = 400


class _FakeAnthropicMessages:
    def __init__(self, response, fail_schema_once=False):
        self.calls: list[dict] = []
        self._response = response
        self._fail_schema_once = fail_schema_once

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail_schema_once and "output_config" in kwargs:
            self._fail_schema_once = False
            raise _FakeBadRequest("output_config schema invalid")
        return self._response


class _FakeAnthropic:
    def __init__(self, response, fail_schema_once=False):
        self.messages = _FakeAnthropicMessages(response, fail_schema_once)


@pytest.mark.unit
async def test_anthropic_omits_temperature_and_disables_thinking_for_sonnet5():
    fake = _FakeAnthropic(_Msg(text='{"ok": true}'))
    client = AnthropicModelClient(client=fake)
    await client.complete(ModelRequest(role=ModelRole.JUDGE))  # resolves to claude-sonnet-5
    call = fake.messages.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert "temperature" not in call
    assert call["thinking"] == {"type": "disabled"}


@pytest.mark.unit
async def test_anthropic_passes_temperature_for_haiku():
    fake = _FakeAnthropic(_Msg())
    client = AnthropicModelClient(client=fake)
    await client.complete(ModelRequest(role=ModelRole.PREFILTER))  # claude-haiku-4-5
    call = fake.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["temperature"] == 0.0
    assert "thinking" not in call


@pytest.mark.unit
async def test_anthropic_strictifies_schema_and_maps_usage():
    fake = _FakeAnthropic(_Msg(text='{"criteria": []}'))
    client = AnthropicModelClient(client=fake)
    resp = await client.complete(ModelRequest(role=ModelRole.JUDGE, response_schema=JUDGE_SCHEMA))
    schema = fake.messages.calls[0]["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["criteria"]["items"]["additionalProperties"] is False
    assert resp.input_tokens == 11 and resp.output_tokens == 22


@pytest.mark.unit
async def test_anthropic_falls_back_to_plain_json_on_schema_400():
    fake = _FakeAnthropic(_Msg(text='{"criteria": []}'), fail_schema_once=True)
    client = AnthropicModelClient(client=fake)
    resp = await client.complete(ModelRequest(role=ModelRole.JUDGE, response_schema=JUDGE_SCHEMA))
    assert len(fake.messages.calls) == 2  # first with output_config, retry without
    assert "output_config" not in fake.messages.calls[1]
    assert resp.text == '{"criteria": []}'


@pytest.mark.unit
async def test_anthropic_refusal_fails_closed_with_empty_text():
    fake = _FakeAnthropic(_Msg(text=None, stop_reason="refusal"))
    client = AnthropicModelClient(client=fake)
    resp = await client.complete(ModelRequest(role=ModelRole.JUDGE))
    assert resp.text == ""
    assert resp.stop_reason == "refusal"


@pytest.mark.unit
async def test_target_role_requires_explicit_model_id():
    fake = _FakeAnthropic(_Msg())
    client = AnthropicModelClient(client=fake)
    with pytest.raises(ValueError):
        await client.complete(ModelRequest(role=ModelRole.TARGET))


@pytest.mark.unit
async def test_explicit_model_id_must_be_allowlisted():
    fake = _FakeAnthropic(_Msg())
    client = AnthropicModelClient(client=fake)
    with pytest.raises(ValueError):
        await client.complete(ModelRequest(role=ModelRole.TARGET, model_id="gpt-9-ultra"))


# --------------------------- fake OpenAI SDK ---------------------------


class _OAIMessage:
    def __init__(self, content):
        self.content = content


class _OAIChoice:
    def __init__(self, content, finish="stop"):
        self.message = _OAIMessage(content)
        self.finish_reason = finish


class _OAIUsage:
    def __init__(self):
        self.prompt_tokens = 7
        self.completion_tokens = 9


class _OAIResp:
    def __init__(self, content="{}", finish="stop", model="gpt-4o"):
        self.choices = [_OAIChoice(content, finish)]
        self.usage = _OAIUsage()
        self.model = model


class _FakeCompletions:
    def __init__(self, response):
        self.calls: list[dict] = []
        self._response = response

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeOpenAI:
    def __init__(self, response):
        self.chat = _FakeChat(response)


@pytest.mark.unit
async def test_openai_judge_prepends_system_and_uses_json_schema():
    fake = _FakeOpenAI(_OAIResp(content='{"criteria": []}'))
    client = OpenAIModelClient(client=fake)
    resp = await client.complete(
        ModelRequest(role=ModelRole.JUDGE, system="be strict", response_schema=JUDGE_SCHEMA)
    )
    call = fake.chat.completions.calls[0]
    assert call["model"] == "gpt-4o"  # cross-family judge
    assert call["messages"][0] == {"role": "system", "content": "be strict"}
    assert call["response_format"]["json_schema"]["strict"] is True
    assert resp.input_tokens == 7 and resp.output_tokens == 9


@pytest.mark.unit
async def test_openai_content_filter_fails_closed():
    fake = _FakeOpenAI(_OAIResp(content="partial", finish="content_filter"))
    client = OpenAIModelClient(client=fake)
    resp = await client.complete(ModelRequest(role=ModelRole.JUDGE))
    assert resp.text == ""


@pytest.mark.unit
def test_strictify_is_idempotent_and_recursive():
    once = strictify_schema(JUDGE_SCHEMA)
    twice = strictify_schema(once)
    assert once == twice
    assert once["additionalProperties"] is False
