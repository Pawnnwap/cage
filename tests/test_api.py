from __future__ import annotations

import asyncio

import httpx
import pytest

from app.evidence import EvidenceSigner
from app.llm import FakeLLM, LLMResponse, ToolCall
from app.main import create_app
from app.config import Settings


def _app(tmp_path, **overrides):
    values = dict(
        data_dir=tmp_path,
        workspace_root=tmp_path / "workspaces",
        sandbox_mode="local",
        llm_mode="fake",
        max_steps=4,
        command_timeout_s=10,
        task_timeout_s=30,
        probe_timeout_s=5,
        evidence_key_path=tmp_path / "evidence_key.pem",
    )
    values.update(overrides)
    settings = Settings(**values)
    script = [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="w1",
                    name="write_file",
                    arguments={"path": "a.txt", "content": "hello"},
                )
            ]
        ),
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="f1",
                    name="finish",
                    arguments={"summary": "done"},
                )
            ]
        ),
    ]
    return create_app(settings, llm=FakeLLM(script))


@pytest.mark.asyncio
async def test_health_config_and_task_lifecycle(tmp_path):
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["ok"] is True

        config = await client.get("/api/config")
        assert config.status_code == 200
        assert config.json()["sandbox_mode"] == "local"

        created = await client.post(
            "/api/tasks", json={"prompt": "write a file"}
        )
        assert created.status_code == 200
        task_id = created.json()["id"]

        status = None
        for _ in range(50):
            await asyncio.sleep(0.05)
            detail = await client.get(f"/api/tasks/{task_id}")
            status = detail.json()["task"]["status"]
            if status in {"completed", "failed", "cancelled"}:
                break
        assert status == "completed"

        evidence = await client.get(f"/api/tasks/{task_id}/evidence")
        assert evidence.status_code == 200
        body = evidence.json()
        assert body["task"]["id"] == task_id
        unsigned = {
            key: value
            for key, value in body.items()
            if key
            not in {
                "signature",
                "public_key",
                "signature_algorithm",
                "key_fingerprint",
            }
        }
        assert EvidenceSigner.verify(
            unsigned, body["signature"], body["public_key"]
        )

        public_key = await client.get("/api/evidence/public-key")
        assert public_key.status_code == 200
        assert public_key.json()["algorithm"] == "Ed25519"

        probe = await client.post(
            "/api/containment/probe", json={"probe": "rm_rf"}
        )
        assert probe.status_code == 400


@pytest.mark.asyncio
async def test_task_rate_limit(tmp_path):
    app = _app(
        tmp_path,
        rate_limit_per_minute=1,
        max_concurrent_tasks=0,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/tasks", json={"prompt": "one"})
        assert first.status_code == 200
        second = await client.post("/api/tasks", json={"prompt": "two"})
        assert second.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_uses_forwarded_ip(tmp_path):
    app = _app(
        tmp_path,
        rate_limit_per_minute=1,
        max_concurrent_tasks=0,
        trust_proxy=True,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a = {"X-Forwarded-For": "203.0.113.1"}
        headers_b = {"X-Forwarded-For": "203.0.113.2"}
        assert (
            await client.post(
                "/api/tasks", json={"prompt": "one"}, headers=headers_a
            )
        ).status_code == 200
        assert (
            await client.post(
                "/api/tasks", json={"prompt": "two"}, headers=headers_a
            )
        ).status_code == 429
        assert (
            await client.post(
                "/api/tasks", json={"prompt": "three"}, headers=headers_b
            )
        ).status_code == 200


@pytest.mark.asyncio
async def test_whitespace_prompt_is_rejected(tmp_path):
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/tasks", json={"prompt": "   \n"})
        assert response.status_code == 422
