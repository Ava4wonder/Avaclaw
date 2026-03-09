import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.plugins.registry import PluginRegistry, Tool
from app.services.agent_runtime import AgentRuntime
from app.services.llm_executor import LlmResponse
from app.skills.registry import SkillRegistry


class DummyStore:
    def update_task(self, *_args, **_kwargs):
        return None


class DummyQueue:
    def enqueue(self, *_args, **_kwargs):
        return None

    def depth(self):
        return 0

    def dequeue(self):
        return None

    def mark_running(self, *_args, **_kwargs):
        return None

    def mark_complete(self, *_args, **_kwargs):
        return None


class RecordingLogger:
    def __init__(self):
        self.spans = []
        self.steps = []

    def log_span(self, payload):
        self.spans.append(payload)
        return payload

    def log_step(self, payload):
        self.steps.append(payload)
        return payload


class FakeLlmExecutor:
    def __init__(self):
        self.calls = 0

    async def chat(self, _model, _messages, tools=None, tool_choice=None):
        self.calls += 1
        if self.calls == 1:
            return LlmResponse(
                content="",
                raw={},
                tokens_used=1,
                tool_calls=[
                    {
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{\"value\":\"trace\"}"}
                    }
                ]
            )
        return LlmResponse(content="done", raw={}, tokens_used=1, tool_calls=None)


@pytest.mark.asyncio
async def test_trace_spans_have_consistent_parent_and_trace():
    registry = PluginRegistry()
    registry.register_tool(
        Tool(
            id="echo",
            name="Echo",
            description="Echo",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False
            },
            handler=lambda payload: payload.get("value")
        ),
        origin="test"
    )

    logger = RecordingLogger()
    runtime = AgentRuntime(
        store=DummyStore(),
        agent_manager=None,
        execution_logger=logger,
        plugin_registry=registry,
        skill_registry=SkillRegistry(),
        task_queue=DummyQueue(),
        llm_executor=FakeLlmExecutor()
    )

    agent = SimpleNamespace(system_prompt="Test.", tools=["echo"], skills=[], model="test")
    task = SimpleNamespace(id="task-2", input="trace")
    await runtime._execute(agent, task, trace_id="trace-1", parent_span_id="root-span")

    assert logger.spans
    for span in logger.spans:
        assert span["trace_id"] == "trace-1"
        assert span["parent_span_id"] == "root-span"
