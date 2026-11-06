"""Provision (and later destroy) the Cage demo host through the Vultr API v2.

The API key is read from a file outside version control (default
`.secrets/vultr_api_key`). Instance facts are written to `.secrets/vm.json`.

    python deploy/vultr_provision.py check
    python deploy/vultr_provision.py create --region sgp --plan vc2-4c-8gb
    python deploy/vultr_provision.py status
    python deploy/vultr_provision.py inference
    python deploy/vultr_provision.py destroy
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.vultr.com/v2"
VM_FILE = ROOT / ".secrets" / "vm.json"
INFERENCE_KEY_FILE = ROOT / ".secrets" / "vultr_inference_key"
OS_NAME = "Ubuntu 24.04 LTS x64"


class Vultr:
    def __init__(self, key: str) -> None:
        self.key = key

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail}") from None
        return json.loads(raw) if raw else {}


def load_key(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"API key file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def cmd_check(api: Vultr, _args: argparse.Namespace) -> int:
    account = api.call("GET", "/account")["account"]
    print(json.dumps({k: account.get(k) for k in ("balance", "pending_charges", "acls")}, indent=1))
    return 0


def find_os_id(api: Vultr) -> int:
    for item in api.call("GET", "/os?per_page=500")["os"]:
        if item["name"] == OS_NAME:
            return item["id"]
    raise SystemExit(f"OS not found: {OS_NAME}")


def ensure_ssh_key(api: Vultr, pub_path: Path) -> str:
    pub = pub_path.read_text(encoding="utf-8").strip()
    for item in api.call("GET", "/ssh-keys?per_page=100")["ssh_keys"]:
        if item["ssh_key"].strip() == pub:
            return item["id"]
    return api.call("POST", "/ssh-keys", {"name": "cage-deploy", "ssh_key": pub})["ssh_key"]["id"]


def cmd_create(api: Vultr, args: argparse.Namespace) -> int:
    if VM_FILE.exists():
        raise SystemExit(f"{VM_FILE} exists; destroy the old instance first")
    available = api.call("GET", f"/regions/{args.region}/availability?type=vc2")["available_plans"]
    if args.plan not in available:
        raise SystemExit(f"plan {args.plan} not available in {args.region}: {available}")
    user_data = (ROOT / "deploy" / "cloud-init.yaml").read_bytes()
    body = {
        "region": args.region,
        "plan": args.plan,
        "os_id": find_os_id(api),
        "label": "cage-demo",
        "hostname": "cage-demo",
        "sshkey_id": [ensure_ssh_key(api, Path(args.pubkey))],
        "user_data": base64.b64encode(user_data).decode(),
        "backups": "disabled",
        "tags": ["cage", "agent-rush"],
    }
    inst = api.call("POST", "/instances", body)["instance"]
    facts = {"id": inst["id"], "region": args.region, "plan": args.plan, "created": inst.get("date_created")}
    VM_FILE.write_text(json.dumps(facts, indent=1), encoding="utf-8")
    print(f"created {inst['id']}; waiting for an IP...")
    return cmd_status(api, args)


def cmd_status(api: Vultr, args: argparse.Namespace) -> int:
    facts = json.loads(VM_FILE.read_text(encoding="utf-8"))
    deadline = time.time() + args.wait
    while True:
        inst = api.call("GET", f"/instances/{facts['id']}")["instance"]
        state = {k: inst.get(k) for k in ("status", "power_status", "server_status", "main_ip")}
        if inst.get("main_ip") not in (None, "", "0.0.0.0") and inst.get("status") == "active":
            break
        if time.time() > deadline:
            print(json.dumps(state))
            return 1
        time.sleep(10)
    facts.update(ip=inst["main_ip"], status=inst["status"], server_status=inst.get("server_status"))
    VM_FILE.write_text(json.dumps(facts, indent=1), encoding="utf-8")
    print(json.dumps(facts, indent=1))
    return 0


def cmd_destroy(api: Vultr, _args: argparse.Namespace) -> int:
    facts = json.loads(VM_FILE.read_text(encoding="utf-8"))
    api.call("DELETE", f"/instances/{facts['id']}")
    VM_FILE.rename(VM_FILE.with_suffix(".destroyed.json"))
    print(f"destroyed {facts['id']}")
    return 0


def cmd_inference(api: Vultr, args: argparse.Namespace) -> int:
    subs = api.call("GET", "/inference").get("subscriptions", [])
    sub = next((s for s in subs if s.get("label") == args.label), None)
    if sub is None:
        sub = api.call("POST", "/inference", {"label": args.label})["subscription"]
    INFERENCE_KEY_FILE.write_text(sub["api_key"].strip() + "\n", encoding="utf-8")
    print(json.dumps({k: sub.get(k) for k in ("id", "label", "date_created")}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key-file", default=str(ROOT / ".secrets" / "vultr_api_key"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    create = sub.add_parser("create")
    create.add_argument("--region", default="sgp")
    create.add_argument("--plan", default="vc2-4c-8gb")
    create.add_argument("--pubkey", default=str(ROOT / ".secrets" / "cage_vultr_ed25519.pub"))
    create.add_argument("--wait", type=int, default=600)
    status = sub.add_parser("status")
    status.add_argument("--wait", type=int, default=600)
    sub.add_parser("destroy")
    inference = sub.add_parser("inference")
    inference.add_argument("--label", default="cage-demo")
    args = parser.parse_args()

    api = Vultr(load_key(Path(args.key_file)))
    commands = {
        "check": cmd_check,
        "create": cmd_create,
        "status": cmd_status,
        "destroy": cmd_destroy,
        "inference": cmd_inference,
    }
    return commands[args.cmd](api, args)


if __name__ == "__main__":
    sys.exit(main())
