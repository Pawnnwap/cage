from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = "Cage"
    data_dir: Path = Path("./data")
    workspace_root: Path = Path("./data/workspaces")

    sandbox_mode: str = "local"  # local | docker
    sandboxd_url: str = "http://127.0.0.1:8090"
    sandboxd_token: str = ""
    sandbox_image: str = "cage-sandbox:latest"
    workspace_limit_mb: int = 64
    sandbox_memory_mb: int = 512
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 128
    max_sandboxes: int = 4

    llm_mode: str = "vultr"  # vultr | fake
    vultr_base_url: str = "https://api.vultrinference.com/v1"
    vultr_api_key: str = ""
    vultr_model: str = "qwen3.8-27b"
    max_task_tokens: int = 200_000

    max_steps: int = 24
    command_timeout_s: int = 30
    task_timeout_s: int = 600
    probe_timeout_s: int = 10

    max_concurrent_tasks: int = 2
    max_concurrent_probes: int = 1
    max_probe_reports: int = 200
    rate_limit_per_minute: int = 6
    trust_proxy: bool = False
    demo_enabled: bool = True
    max_daily_tokens: int = 2_000_000
    max_tasks_per_day: int = 100
    evidence_key_path: Path = Path("./data/evidence_key.pem")

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        return cls(
            data_dir=data_dir,
            workspace_root=Path(
                os.getenv("WORKSPACE_ROOT", str(data_dir / "workspaces"))
            ),
            sandbox_mode=os.getenv("SANDBOX_MODE", "local").lower(),
            sandboxd_url=os.getenv("SANDBOXD_URL", "http://127.0.0.1:8090"),
            sandboxd_token=os.getenv("SANDBOXD_TOKEN", ""),
            sandbox_image=os.getenv("SANDBOX_IMAGE", "cage-sandbox:latest"),
            workspace_limit_mb=_env_int("WORKSPACE_LIMIT_MB", 64),
            sandbox_memory_mb=_env_int("SANDBOX_MEMORY_MB", 512),
            sandbox_cpus=float(os.getenv("SANDBOX_CPUS", "1.0") or 1.0),
            sandbox_pids_limit=_env_int("SANDBOX_PIDS_LIMIT", 128),
            max_sandboxes=_env_int("MAX_SANDBOXES", 4),
            llm_mode=os.getenv("LLM_MODE", "vultr").lower(),
            vultr_base_url=os.getenv(
                "VULTR_BASE_URL", "https://api.vultrinference.com/v1"
            ),
            vultr_api_key=os.getenv("VULTR_API_KEY", ""),
            vultr_model=os.getenv("VULTR_MODEL", "qwen3.8-27b"),
            max_task_tokens=_env_int("MAX_TASK_TOKENS", 200_000),
            max_steps=_env_int("MAX_STEPS", 24),
            command_timeout_s=_env_int("COMMAND_TIMEOUT_S", 30),
            task_timeout_s=_env_int("TASK_TIMEOUT_S", 600),
            probe_timeout_s=_env_int("PROBE_TIMEOUT_S", 10),
            max_concurrent_tasks=_env_int("MAX_CONCURRENT_TASKS", 2),
            max_concurrent_probes=_env_int("MAX_CONCURRENT_PROBES", 1),
            max_probe_reports=_env_int("MAX_PROBE_REPORTS", 200),
            rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", 6),
            trust_proxy=_env_bool("TRUST_PROXY", False),
            demo_enabled=_env_bool("DEMO_ENABLED", True),
            max_daily_tokens=_env_int("MAX_DAILY_TOKENS", 2_000_000),
            max_tasks_per_day=_env_int("MAX_TASKS_PER_DAY", 100),
            evidence_key_path=Path(
                os.getenv("EVIDENCE_KEY_PATH", str(data_dir / "evidence_key.pem"))
            ),
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.evidence_key_path.parent.mkdir(parents=True, exist_ok=True)
