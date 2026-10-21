from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent import AgentRunner
from app.config import Settings
from app.drills import evaluate_cross_task, evaluate_probe
from app.events import EventBus
from app.evidence import EvidenceSigner
from app.llm import FakeLLM, LLMClient, LLMResponse, ToolCall
from app.models import ContainmentReport, ProbeResult, TaskCreate
from app.sandbox_client import make_sandbox
from app.store import Store


PROBE_COMMANDS: dict[str, str] = {
    "rm_rf": "rm -rf / --no-preserve-root",
    "infinite_loop": "python -c 'while True: pass'",
    "fork_bomb": (
        "python -c \"import os\nfor _ in range(200):\n    os.fork()\""
    ),
    "secret_probe": (
        "env; echo ---; cat /proc/1/environ | tr '\\0' '\\n'"
    ),
    "network_probe": (
        "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), 2)\""
    ),
    "host_write": "touch /etc/cage-probe",
    "readonly_canary": "printf x >> /cage-readonly-canary",
    "cross_task": "cross-task isolation probe",
}


def _sse(event_id: int, kind: str, payload: dict[str, Any]) -> str:
    body = json.dumps(
        {"id": event_id, "kind": kind, "payload": payload},
        ensure_ascii=False,
    )
    return f"id: {event_id}\ndata: {body}\n\n"


def _fake_llm() -> FakeLLM:
    return FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="fake-write",
                        name="write_file",
                        arguments={
                            "path": "solution.py",
                            "content": (
                                "print('Cage containment demo: code executed "
                                "inside the sandbox')\n"
                            ),
                        },
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="fake-run",
                        name="run_command",
                        arguments={"command": "python solution.py"},
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="fake-finish",
                        name="finish",
                        arguments={
                            "summary": "Wrote and executed solution.py in the sandbox."
                        },
                    )
                ]
            ),
        ]
    )


def _rate_limit(app: FastAPI, request: Request, key: str) -> None:
    settings: Settings = app.state.settings
    if settings.rate_limit_per_minute <= 0:
        return
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Caddy appends the peer IP; use the last hop so a client-supplied
            # prefix cannot mint a fresh rate-limit bucket.
            ip = forwarded.split(",")[-1].strip() or ip
    bucket = app.state.rate[(key, ip)]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=(
                f"rate limit: {settings.rate_limit_per_minute} "
                f"{key} requests per minute per IP"
            ),
        )
    bucket.append(now)


async def _run_containment_probe(
    settings: Settings, probe: str, task_id: str | None = None
) -> ContainmentReport:
    if settings.sandbox_mode != "docker":
        raise HTTPException(
            status_code=400,
            detail=(
                "Containment drills require SANDBOX_MODE=docker. The local "
                "fallback is intentionally not a security boundary."
            ),
        )
    if probe not in PROBE_COMMANDS:
        raise HTTPException(status_code=400, detail=f"unknown probe: {probe}")

    canary_path = settings.data_dir / "host_canary.txt"
    canary_path.parent.mkdir(parents=True, exist_ok=True)
    canary_value = f"cage-host-{uuid.uuid4().hex}"
    canary_path.write_text(canary_value, encoding="utf-8")

    if probe == "cross_task":
        sandbox_a = make_sandbox(f"probe-a-{uuid.uuid4().hex[:8]}", settings)
        sandbox_b = None
        try:
            info_a = await sandbox_a.start()
            sandbox_b = make_sandbox(f"probe-b-{uuid.uuid4().hex[:8]}", settings)
            info_b = await sandbox_b.start()
            started = time.perf_counter()
            write = await sandbox_a.exec(
                "printf cage-canary > /workspace/canary.txt",
                timeout_s=settings.probe_timeout_s,
            )
            b_write = await sandbox_b.exec(
                "printf peer-alive > /workspace/peer.txt",
                timeout_s=settings.probe_timeout_s,
            )
            b_read = await sandbox_b.exec(
                "cat /workspace/peer.txt",
                timeout_s=settings.probe_timeout_s,
            )
            read = await sandbox_b.exec(
                "cat /workspace/canary.txt",
                timeout_s=settings.probe_timeout_s,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            passed, detail = evaluate_cross_task(
                write, b_write, b_read, read
            )
            result = ProbeResult(
                name=probe,
                passed=passed,
                detail=detail,
                output=(read.stdout + read.stderr)[-4000:],
                duration_ms=duration_ms,
            )
            canary_intact = (
                canary_path.is_file()
                and canary_path.read_text(encoding="utf-8") == canary_value
            )
            return ContainmentReport(
                sandbox_id=info_a.id,
                task_id=task_id,
                container_id=info_a.container_id,
                image_id=info_a.image_id,
                peer_sandbox_id=info_b.id,
                host_config=info_a.host_config,
                probes=[result],
                host_canary_intact=canary_intact,
                generated_at=time.time(),
            )
        finally:
            await sandbox_a.destroy()
            if sandbox_b is not None:
                await sandbox_b.destroy()

    sandbox = make_sandbox(f"probe-{uuid.uuid4().hex[:10]}", settings)
    info = await sandbox.start()
    result = ProbeResult(
        name=probe,
        passed=False,
        detail="probe did not run",
        output="",
        duration_ms=0,
    )
    try:
        started = time.perf_counter()
        execution = await sandbox.exec(
            PROBE_COMMANDS[probe], timeout_s=settings.probe_timeout_s
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        followup = None
        if probe == "rm_rf":
            followup = await sandbox.exec("test -f /etc/hostname")
        elif probe == "readonly_canary":
            followup = await sandbox.exec("cat /cage-readonly-canary")
        elif probe == "host_write":
            followup = await sandbox.exec("test -f /etc/cage-probe")
        passed, detail = evaluate_probe(probe, execution, followup)
        if probe in {"rm_rf", "host_write"}:
            rootfs_control = await sandbox.exec(
                "printf x >> /cage-readonly-canary"
            )
            rootfs_check = await sandbox.exec("cat /cage-readonly-canary")
            rootfs_readonly = (
                rootfs_control.exit_code not in (0, 127)
                and rootfs_check.stdout.strip() == "unmodified"
            )
            if not rootfs_readonly:
                passed = False
                detail += "; rootfs writable (canary changed)"
        result = ProbeResult(
            name=probe,
            passed=passed,
            detail=detail,
            output=(execution.stdout + execution.stderr)[-4000:],
            duration_ms=duration_ms,
        )
    finally:
        await sandbox.destroy()

    canary_intact = (
        canary_path.is_file()
        and canary_path.read_text(encoding="utf-8") == canary_value
    )
    return ContainmentReport(
        sandbox_id=info.id,
        task_id=task_id,
        container_id=info.container_id,
        image_id=info.image_id,
        host_config=info.host_config,
        probes=[result],
        host_canary_intact=canary_intact,
        generated_at=time.time(),
    )


def create_app(settings: Settings | None = None, llm: Any | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_dirs()
    store = Store(settings.data_dir / "cage.sqlite3")
    signer = EvidenceSigner(settings.evidence_key_path)

    def _seal_task(task_id: str) -> None:
        payload = store.evidence(task_id)
        if not payload:
            return
        signed = signer.signed_pack(payload)
        store.seal_evidence(
            task_id, signed, signer.fingerprint(), time.time()
        )

    interrupted = store.reconcile_running()
    for task_id in interrupted:
        store.add_event(
            task_id,
            "task_finished",
            {
                "status": "interrupted",
                "summary": None,
                "error": "control plane restarted before completion",
            },
        )
        _seal_task(task_id)
    bus = EventBus()
    llm = llm or (
        _fake_llm() if settings.llm_mode == "fake" else LLMClient(settings)
    )
    runner = AgentRunner(settings, store, bus, llm, signer=signer)

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app = FastAPI(title=settings.app_name)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.state.settings = settings
    app.state.store = store
    app.state.bus = bus
    app.state.runner = runner
    app.state.signer = signer
    app.state.jobs = {}
    app.state.active_tasks = set()
    app.state.probe_sem = asyncio.Semaphore(
        max(1, settings.max_concurrent_probes)
    )
    app.state.rate = defaultdict(deque)
    app.state.started_at = time.time()

    def _owner(request: Request, response: Response | None = None) -> str:
        owner = request.cookies.get("cage_owner")
        if not owner:
            owner = uuid.uuid4().hex
            if response is not None:
                response.set_cookie(
                    "cage_owner",
                    owner,
                    httponly=True,
                    samesite="lax",
                    max_age=60 * 60 * 24 * 30,
                )
        return owner

    def _owned_task(task_id: str, request: Request):
        task = store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        owner = request.cookies.get("cage_owner")
        if task.owner is None or task.owner != owner:
            raise HTTPException(status_code=404, detail="task not found")
        return task

    async def _sandboxd_ready() -> bool:
        if settings.sandbox_mode != "docker":
            return True
        headers = (
            {"Authorization": f"Bearer {settings.sandboxd_token}"}
            if settings.sandboxd_token
            else {}
        )
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(
                    f"{settings.sandboxd_url.rstrip('/')}/healthz",
                    headers=headers,
                )
                return response.status_code == 200 and bool(
                    response.json().get("ok")
                )
        except Exception:
            return False

    async def _sandboxd_delete(sandbox_id: str) -> None:
        if settings.sandbox_mode != "docker" or not sandbox_id:
            return
        headers = (
            {"Authorization": f"Bearer {settings.sandboxd_token}"}
            if settings.sandboxd_token
            else {}
        )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.delete(
                    f"{settings.sandboxd_url.rstrip('/')}/v1/sandboxes/"
                    f"{sandbox_id}",
                    headers=headers,
                )
        except Exception:
            pass

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "app_name": settings.app_name,
                "sandbox_mode": settings.sandbox_mode,
                "llm_mode": settings.llm_mode,
                "model": settings.vultr_model,
            },
        )

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        ok = store.ping()
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "ok": ok,
                "app": settings.app_name,
                "sandbox_mode": settings.sandbox_mode,
                "llm_mode": settings.llm_mode,
                "active_tasks": len(app.state.active_tasks),
                "uptime_s": round(time.time() - app.state.started_at, 1),
            },
        )

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        if settings.sandbox_mode != "docker":
            return JSONResponse(
                status_code=200,
                content={
                    "ready": True,
                    "warning": "local fallback is not a security boundary",
                },
            )
        headers = (
            {"Authorization": f"Bearer {settings.sandboxd_token}"}
            if settings.sandboxd_token
            else {}
        )
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(
                    f"{settings.sandboxd_url.rstrip('/')}/healthz",
                    headers=headers,
                )
                ok = response.status_code == 200 and response.json().get("ok")
        except Exception:
            ok = False
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"ready": bool(ok), "sandboxd": settings.sandboxd_url},
        )

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        limits = {
            "network": "none" if settings.sandbox_mode == "docker" else "host",
            "ipc": "none" if settings.sandbox_mode == "docker" else "—",
            "cpus": settings.sandbox_cpus,
            "memory_mb": settings.sandbox_memory_mb,
            "pids_limit": settings.sandbox_pids_limit,
            "workspace_mb": settings.workspace_limit_mb,
            "rootfs": "read-only" if settings.sandbox_mode == "docker" else "—",
            "max_sandboxes": settings.max_sandboxes,
        }
        limits_source = "settings"
        if settings.sandbox_mode == "docker":
            headers = (
                {"Authorization": f"Bearer {settings.sandboxd_token}"}
                if settings.sandboxd_token
                else {}
            )
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(
                        f"{settings.sandboxd_url.rstrip('/')}/healthz",
                        headers=headers,
                    )
                    body = response.json()
                if response.status_code == 200 and body.get("limits"):
                    limits = body["limits"]
                    limits_source = "sandboxd"
            except Exception:
                limits_source = "settings (sandboxd unavailable)"
        return {
            "app_name": settings.app_name,
            "sandbox_mode": settings.sandbox_mode,
            "llm_mode": settings.llm_mode,
            "model": settings.vultr_model,
            "max_steps": settings.max_steps,
            "task_timeout_s": settings.task_timeout_s,
            "command_timeout_s": settings.command_timeout_s,
            "probe_timeout_s": settings.probe_timeout_s,
            "max_task_tokens": settings.max_task_tokens,
            "max_concurrent_tasks": settings.max_concurrent_tasks,
            "max_concurrent_probes": settings.max_concurrent_probes,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "demo_enabled": settings.demo_enabled,
            "active_tasks": len(app.state.active_tasks),
            "daily_usage": store.usage_today(),
            "max_daily_tokens": settings.max_daily_tokens,
            "max_tasks_per_day": settings.max_tasks_per_day,
            "probes": list(PROBE_COMMANDS),
            "limits": limits,
            "limits_source": limits_source,
            "evidence_public_key_fingerprint": signer.fingerprint(),
        }

    @app.post("/api/tasks")
    async def create_task(
        request: Request, response: Response, payload: TaskCreate
    ) -> dict[str, Any]:
        if not settings.demo_enabled:
            raise HTTPException(status_code=503, detail="demo is paused")
        _rate_limit(app, request, "task")
        if (
            settings.max_concurrent_tasks > 0
            and len(app.state.active_tasks) >= settings.max_concurrent_tasks
        ):
            raise HTTPException(
                status_code=429,
                detail=(
                    f"concurrency limit: {settings.max_concurrent_tasks} "
                    "active tasks"
                ),
            )
        usage = store.usage_today()
        if (
            settings.max_tasks_per_day > 0
            and usage["tasks"] >= settings.max_tasks_per_day
        ):
            raise HTTPException(
                status_code=429,
                detail=f"daily task budget: {settings.max_tasks_per_day}",
            )
        if (
            settings.max_daily_tokens > 0
            and usage["tokens"] >= settings.max_daily_tokens
        ):
            raise HTTPException(
                status_code=429,
                detail=f"daily token budget: {settings.max_daily_tokens}",
            )
        if not await _sandboxd_ready():
            raise HTTPException(
                status_code=503,
                detail="sandbox backend is not ready; check /readyz",
            )
        owner = _owner(request, response)
        task = store.create_task(
            payload.prompt,
            payload.title,
            model=settings.vultr_model,
            owner=owner,
        )
        app.state.active_tasks.add(task.id)
        job = asyncio.create_task(runner.run(task.id))
        app.state.jobs[task.id] = job

        def _cleanup(_: asyncio.Task) -> None:
            app.state.jobs.pop(task.id, None)
            app.state.active_tasks.discard(task.id)

        job.add_done_callback(_cleanup)
        return task.model_dump()

    @app.get("/api/tasks")
    async def list_tasks(
        request: Request, response: Response
    ) -> list[dict[str, Any]]:
        owner = _owner(request, response)
        return [
            task.model_dump() for task in store.list_tasks(owner=owner)
        ]

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> dict[str, Any]:
        task = _owned_task(task_id, request)
        return {
            "task": task.model_dump(),
            "events": [event.model_dump() for event in store.get_events(task_id)],
        }

    @app.get("/api/tasks/{task_id}/events")
    async def task_events(
        task_id: str, request: Request, since_id: int = 0
    ) -> StreamingResponse:
        _owned_task(task_id, request)

        async def stream():
            last_id = since_id
            queue = await bus.subscribe(task_id)
            try:
                backlog = store.get_events(task_id, since_id)
                for event in backlog:
                    yield _sse(event.id, event.kind, event.payload)
                    last_id = event.id
                    if event.kind == "task_finished":
                        return
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    if event.id <= last_id:
                        continue
                    yield _sse(event.id, event.kind, event.payload)
                    last_id = event.id
                    if event.kind == "task_finished":
                        return
            finally:
                await bus.unsubscribe(task_id, queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/tasks/{task_id}/sandbox")
    async def task_sandbox(task_id: str, request: Request) -> dict[str, Any]:
        task = _owned_task(task_id, request)
        if settings.sandbox_mode != "docker" or not task.sandbox_id:
            return {
                "mode": settings.sandbox_mode,
                "sandbox_id": task.sandbox_id,
                "stats": None,
                "limits": {
                    "network": "host (local fallback)",
                    "note": "not a security boundary",
                },
            }
        stats = None
        headers = (
            {"Authorization": f"Bearer {settings.sandboxd_token}"}
            if settings.sandboxd_token
            else {}
        )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{settings.sandboxd_url.rstrip('/')}/v1/sandboxes/"
                    f"{task.sandbox_id}/stats",
                    headers=headers,
                )
                if response.status_code == 200:
                    stats = response.json()
        except Exception:
            stats = None
        return {
            "mode": "docker",
            "sandbox_id": task.sandbox_id,
            "stats": stats,
            "limits": {
                "network": "none",
                "ipc": "none",
                "cpus": settings.sandbox_cpus,
                "memory_mb": settings.sandbox_memory_mb,
                "pids_limit": settings.sandbox_pids_limit,
                "workspace_mb": settings.workspace_limit_mb,
                "rootfs": "read-only",
                "user": "1000:1000",
            },
        }

    @app.get("/api/tasks/{task_id}/evidence")
    async def task_evidence(task_id: str, request: Request) -> JSONResponse:
        _owned_task(task_id, request)
        sealed = store.get_sealed_evidence(task_id)
        if sealed is not None:
            return JSONResponse(sealed)
        raise HTTPException(
            status_code=409,
            detail="evidence is not sealed yet; wait for the task to finish",
        )

    @app.get("/api/evidence/public-key")
    async def evidence_public_key() -> dict[str, str]:
        return {
            "algorithm": "Ed25519",
            "public_key": signer.public_key_b64(),
            "fingerprint": signer.fingerprint(),
        }

    @app.post("/api/tasks/{task_id}/destroy")
    async def destroy_task(task_id: str, request: Request) -> dict[str, Any]:
        task = _owned_task(task_id, request)
        if task.status in {"queued", "running"}:
            store.update_task(
                task_id,
                status="cancelled",
                finished_at=time.time(),
                error="cancelled by operator",
            )
            if task.sandbox_id:
                await _sandboxd_delete(task.sandbox_id)
            await runner.emit(
                task_id,
                "task_finished",
                {
                    "status": "cancelled",
                    "summary": None,
                    "error": "cancelled by operator",
                },
            )
            if task_id not in app.state.jobs:
                _seal_task(task_id)
        return {"ok": True}

    @app.post("/api/containment/probe")
    async def containment_probe(
        request: Request, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if not settings.demo_enabled:
            raise HTTPException(status_code=503, detail="demo is paused")
        _rate_limit(app, request, "probe")
        probe = str(payload.get("probe", ""))
        task_id = payload.get("task_id")
        if task_id:
            _owned_task(str(task_id), request)
        if app.state.probe_sem.locked():
            raise HTTPException(
                status_code=429,
                detail=(
                    f"probe concurrency limit: "
                    f"{settings.max_concurrent_probes}"
                ),
            )
        async with app.state.probe_sem:
            report = await _run_containment_probe(
                settings, probe, task_id=str(task_id) if task_id else None
            )
        store.add_probe_report(
            report,
            task_id=str(task_id) if task_id else None,
            max_reports=settings.max_probe_reports,
        )
        return signer.signed_pack(report.model_dump())

    @app.get("/api/containment/probes")
    async def containment_probes() -> dict[str, Any]:
        return {"probes": list(PROBE_COMMANDS)}

    @app.get("/api/containment/reports")
    async def containment_reports(
        task_id: str, request: Request
    ) -> list[dict[str, Any]]:
        _owned_task(task_id, request)
        return store.list_probe_reports(limit=50, task_id=task_id)

    return app


app = create_app()
