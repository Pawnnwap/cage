from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Any

from docker.errors import NotFound
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from sandboxd.manager import SandboxManager


class SandboxCreate(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)


class ExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=8000)
    timeout_s: int = Field(default=30, ge=1, le=120)


class FileWrite(BaseModel):
    path: str
    content: str


_manager_instance: SandboxManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> SandboxManager:
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = SandboxManager(
                image=os.getenv("SANDBOX_IMAGE", "cage-sandbox:latest"),
                ttl_seconds=int(os.getenv("TTL_SECONDS", "7200")),
                max_sandboxes=int(os.getenv("MAX_SANDBOXES", "4")),
                workspace_limit_mb=int(os.getenv("WORKSPACE_LIMIT_MB", "64")),
                memory_mb=int(os.getenv("SANDBOX_MEMORY_MB", "512")),
                cpus=float(os.getenv("SANDBOX_CPUS", "1.0")),
                pids_limit=int(os.getenv("SANDBOX_PIDS_LIMIT", "128")),
            )
    return _manager_instance


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("SANDBOXD_TOKEN", "")
    if not expected:
        if os.getenv("SANDBOXD_ALLOW_INSECURE") == "1":
            return
        raise HTTPException(
            status_code=503,
            detail="SANDBOXD_TOKEN is required; set it or set SANDBOXD_ALLOW_INSECURE=1 for local dev",
        )
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid sandboxd token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("SANDBOXD_TOKEN") and os.getenv(
        "SANDBOXD_ALLOW_INSECURE"
    ) != "1":
        logging.warning(
            "SANDBOXD_TOKEN is not set; the sandbox API will reject requests "
            "until it is configured."
        )

    async def reaper() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                manager = await asyncio.to_thread(get_manager)
                await asyncio.to_thread(manager.reap_once)
            except Exception:
                pass

    task = asyncio.create_task(reaper())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Cage sandboxd", lifespan=lifespan)


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=429, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    manager = await asyncio.to_thread(get_manager)
    try:
        await asyncio.to_thread(manager.client.ping)
        docker_ok = True
    except Exception:
        docker_ok = False
    try:
        await asyncio.to_thread(manager.client.images.get, manager.image)
        image_ok = True
    except Exception:
        image_ok = False
    return {
        "ok": docker_ok and image_ok,
        "docker_ok": docker_ok,
        "image_ok": image_ok,
        "image": manager.image,
        "sandboxes": manager.count(),
        "max_sandboxes": manager.max_sandboxes,
        "limits": {
            "network": "none",
            "ipc": "none",
            "cpus": manager.cpus,
            "memory_mb": manager.memory_mb,
            "pids_limit": manager.pids_limit,
            "workspace_mb": manager.workspace_limit_mb,
            "rootfs": "read-only",
            "user": "1000:1000",
            "max_sandboxes": manager.max_sandboxes,
        },
    }


@app.post("/v1/sandboxes", dependencies=[Depends(require_token)])
async def create_sandbox(payload: SandboxCreate) -> dict[str, Any]:
    try:
        manager = await asyncio.to_thread(get_manager)
        return await asyncio.to_thread(manager.create, payload.task_id)
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc


@app.post("/v1/sandboxes/{sandbox_id}/exec", dependencies=[Depends(require_token)])
async def exec_command(sandbox_id: str, payload: ExecRequest) -> dict[str, Any]:
    try:
        manager = await asyncio.to_thread(get_manager)
        return await asyncio.to_thread(
            manager.exec, sandbox_id, payload.command, payload.timeout_s
        )
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc


@app.get("/v1/sandboxes/{sandbox_id}/files", dependencies=[Depends(require_token)])
async def read_file(sandbox_id: str, path: str) -> dict[str, str]:
    try:
        manager = await asyncio.to_thread(get_manager)
        return {
            "content": await asyncio.to_thread(
                manager.read_file, sandbox_id, path
            )
        }
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc


@app.put("/v1/sandboxes/{sandbox_id}/files", dependencies=[Depends(require_token)])
async def write_file(sandbox_id: str, payload: FileWrite) -> dict[str, bool]:
    try:
        manager = await asyncio.to_thread(get_manager)
        await asyncio.to_thread(
            manager.write_file, sandbox_id, payload.path, payload.content
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc


@app.get(
    "/v1/sandboxes/{sandbox_id}/files/list",
    dependencies=[Depends(require_token)],
)
async def list_files(sandbox_id: str, path: str = ".") -> dict[str, list[str]]:
    try:
        manager = await asyncio.to_thread(get_manager)
        return {
            "files": await asyncio.to_thread(
                manager.list_files, sandbox_id, path
            )
        }
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc


@app.get(
    "/v1/sandboxes/{sandbox_id}/stats",
    dependencies=[Depends(require_token)],
)
async def sandbox_stats(sandbox_id: str) -> dict[str, Any]:
    try:
        manager = await asyncio.to_thread(get_manager)
        return await asyncio.to_thread(manager.stats, sandbox_id)
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc


@app.delete(
    "/v1/sandboxes/{sandbox_id}",
    dependencies=[Depends(require_token)],
)
async def destroy_sandbox(sandbox_id: str) -> dict[str, bool]:
    try:
        manager = await asyncio.to_thread(get_manager)
        await asyncio.to_thread(manager.destroy, sandbox_id)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        raise _handle(exc) from exc
