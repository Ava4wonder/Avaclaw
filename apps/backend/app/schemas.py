from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    model: str
    enabled: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: Optional[list[str]] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None


class AgentOut(AgentBase):
    id: str


TaskStatus = Literal["queued", "running", "completed", "failed"]


class TaskOut(BaseModel):
    id: str
    agent_id: str
    input: str
    status: TaskStatus
    result: Optional[str]
    error: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


class TaskCreate(BaseModel):
    agent_id: str
    input: str


class ExecutionStepOut(BaseModel):
    id: str
    task_id: str
    step_index: int
    type: Literal["llm", "tool"]
    input: str
    output: str
    tokens_used: int
    timestamp: str


class ExecutionSpanOut(BaseModel):
    id: str
    task_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    name: str
    span_type: Literal["task", "llm", "tool"]
    start_time: str
    end_time: str
    duration_ms: int
    status: Literal["ok", "error"]
    error: Optional[str] = None
    model: Optional[str] = None
    tokens_total: Optional[int] = None
    tool_args: Any = None
    tool_result: Any = None


class SkillSummary(BaseModel):
    id: str
    name: str
    description: str
    origin: Optional[str] = None


class EnableRequest(BaseModel):
    enabled: bool
