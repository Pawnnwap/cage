from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    title: str | None = Field(default=None, max_length=120)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class Task(BaseModel):
    id: str
    title: str
    prompt: str
    status: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    summary: str | None = None
    error: str | None = None
    sandbox_id: str | None = None
    model: str | None = None
    tokens: int = 0
    owner: str | None = None


class Event(BaseModel):
    id: int
    task_id: str
    ts: float
    kind: str
    payload: dict[str, Any]


class SandboxInfo(BaseModel):
    id: str
    task_id: str
    container_id: str
    status: str
    image_id: str | None = None
    limits: dict[str, Any] = Field(default_factory=dict)
    host_config: dict[str, Any] = Field(default_factory=dict)


class ExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    oom_killed: bool = False


class ProbeResult(BaseModel):
    name: str
    passed: bool
    detail: str
    output: str = ""
    duration_ms: int = 0


class ContainmentReport(BaseModel):
    sandbox_id: str
    task_id: str | None = None
    container_id: str | None = None
    image_id: str | None = None
    peer_sandbox_id: str | None = None
    host_config: dict[str, Any] = Field(default_factory=dict)
    probes: list[ProbeResult]
    host_canary_intact: bool
    generated_at: float
