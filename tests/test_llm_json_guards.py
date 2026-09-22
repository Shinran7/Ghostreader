"""Tests for LLM response normalization and JSON contract guards."""

from __future__ import annotations

from typing import Any

import pytest

from ghostreader.llm import (
    extract_json_array,
    extract_json_object,
    message_text,
    probe_json_contract,
)


class TestMessageText:
    def test_list_shaped_gemini_parts(self) -> None:
        content = [{"type": "text", "text": '{"ok": true}'}]
        assert message_text(content) == '{"ok": true}'
        assert "type" in str(content)  # str(list) is the failure mode


class TestExtractJson:
    def test_object_with_fence_and_prose(self) -> None:
        raw = 'Sure.\n```json\n{"ok": true, "n": 1}\n```\nDone.'
        assert extract_json_object(raw) == {"ok": True, "n": 1}

    def test_array_embedded(self) -> None:
        raw = 'Findings:\n[{"dimension": "prose.repetition", "severity": "neutral"}]\n'
        data = extract_json_array(raw)
        assert isinstance(data, list)
        assert data[0]["dimension"] == "prose.repetition"

    def test_python_list_repr_fails(self) -> None:
        broken = str([{"type": "text", "text": '{"ok": true}'}])
        assert extract_json_object(broken) is None


class TestProbe:
    @pytest.mark.asyncio()
    async def test_stub_skips_ok(self) -> None:
        from ghostreader.llm import _stub_chat_model

        ok, detail = await probe_json_contract(_stub_chat_model())
        assert ok is True
        assert "stub" in detail.lower()

    @pytest.mark.asyncio()
    async def test_probe_recovers_after_list_shaped_then_ok(self) -> None:
        class _Flaky:
            _llm_type = "fake"

            def __init__(self) -> None:
                self.calls = 0

            async def ainvoke(self, messages: Any) -> Any:
                self.calls += 1

                class _Resp:
                    pass

                resp = _Resp()
                if self.calls == 1:
                    resp.content = [{"type": "text", "text": "not json"}]
                else:
                    resp.content = [{"type": "text", "text": '{"ok": true}'}]
                return resp

        ok, _ = await probe_json_contract(_Flaky())  # type: ignore[arg-type]
        assert ok is True
