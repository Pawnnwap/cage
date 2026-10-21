# Deploy Cage on a Vultr VM

## Prerequisites

- Vultr account and a Vultr Serverless Inference API key.
- A Vultr Cloud Compute instance:
  - Ubuntu 24.04 LTS
  - 4 vCPU / 8 GB RAM recommended (2 vCPU / 4 GB works for a demo)
  - 80 GB disk
  - Open ports 22, 80, 443 in the Vultr firewall
- A public GitHub repo containing this project.

## 1. Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

## 2. Clone and configure

```bash
git clone <your-repo-url> cage
cd cage
cp .env.example .env
nano .env
```

Set at minimum:

```dotenv
LLM_MODE=vultr
VULTR_BASE_URL=https://api.vultrinference.com/v1
VULTR_API_KEY=<your-vultr-inference-key>
VULTR_MODEL=qwen3.8-27b
SANDBOXD_TOKEN=<a-long-random-shared-token>
DEMO_ENABLED=true
MAX_CONCURRENT_TASKS=2
RATE_LIMIT_PER_MINUTE=6
MAX_TASK_TOKENS=200000
WORKSPACE_LIMIT_MB=64
```

Other tool-capable Vultr models are listed at:

```bash
curl -s https://api.vultrinference.com/v1/models | head
```

`nemotron-3-nano-omni-30b-a3b-reasoning` is a good NVIDIA alternative; `qwen3.8-27b` is the default for coding.

## 3. Build the sandbox image, then start

The sandbox image is built as a separate pre-step so only `sandboxd` ever gets the Docker socket.

```bash
docker build -t cage-sandbox:latest sandbox_image
docker compose up -d --build
docker compose ps
```

Expected services:

- `sandboxd`: running on the internal network, owns `/var/run/docker.sock`.
- `app`: running on loopback port 8080.
- `caddy`: the public reverse proxy on ports 80/443, with an active `/healthz` health check (keeps the evidence viewer up even if sandboxd is down).

Check health:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/readyz
docker compose logs -f sandboxd
```

If `SANDBOXD_TOKEN` is unset, `sandboxd` rejects the sandbox API (fail closed). Set it in `.env` before starting.

`readyz` checks the real sandboxd/Docker/image path; `healthz` proves the app process and SQLite are alive. Caddy routes on `/healthz`, so a sandbox outage does not take down the evidence viewer; new tasks fail with a clear error until `/readyz` recovers.

Open `http://<vultr-ip>` through Caddy. The app port is bound to `127.0.0.1:8080`; use an SSH tunnel if you need direct access:

```bash
ssh -L 8080:127.0.0.1:8080 root@<vultr-ip>
```

## 4. Verify the sandbox boundary

In the UI, click **Containment drills**. In Docker mode each drill creates a fresh sandbox, runs the hostile command, and destroys it.

Expected:

- `rm -rf / --no-preserve-root`: `CONTAINED`, read-only root rejected the delete; the 64MB tmpfs workspace is disposable.
- `infinite loop`: `CONTAINED`, command killed by the sandbox timeout.
- `fork bomb`: `CONTAINED`, pids limit contained the fork storm.
- `secret probe`: `CONTAINED`, no secret-like environment variables.
- `network probe`: `CONTAINED`, no route from the sandbox.
- `host write`: `CONTAINED`, read-only root rejected the write.
- `read-only canary`: `CONTAINED`, the world-writable root file stayed unchanged (this fails if `read_only=False`).
- `cross-task`: `CONTAINED`, a second sandbox could not read the first sandbox's workspace.

If the app reports `Containment drills require SANDBOX_MODE=docker`, the app is still in local fallback. Check `.env` and restart:

```bash
docker compose restart app
```

## 5. Domain and HTTPS (optional)

Edit `caddy/Caddyfile`:

```caddyfile
cage.example.com {
    encode gzip
    reverse_proxy app:8080
}
```

Point the DNS A record at the Vultr IP, then:

```bash
docker compose restart caddy
```

Caddy obtains a certificate automatically. Without a domain, keep `:80` and use the VM IP.

## 6. Troubleshooting

**`sandbox image not found`**
```bash
docker build -t cage-sandbox:latest sandbox_image
docker compose restart sandboxd
```

**`sandboxd` rejects requests with 503**
Set `SANDBOXD_TOKEN` in `.env` and restart both services. The token is intentionally required; `SANDBOXD_ALLOW_INSECURE=1` is only for local development.

**`sandboxd` cannot reach Docker**
```bash
docker compose logs sandboxd
ls -l /var/run/docker.sock
```
The `sandboxd` service must mount `/var/run/docker.sock`. Do not run it rootless.

**`permission denied` when the agent writes `/workspace`**
Rebuild the sandbox image; `/workspace` must be owned by UID 1000:
```bash
docker compose build --no-cache sandbox-image
```

**Model 404**
List valid model IDs:
```bash
curl -s https://api.vultrinference.com/v1/models | python -m json.tool | grep '"id"'
```
Then set `VULTR_MODEL` to an exact ID and restart `app`.

**Port 80 already in use**
Stop the conflicting service or change the Caddy port mapping in `docker-compose.yml`.

**I want to inspect and verify evidence**
Open `GET /api/tasks/{id}/evidence` in the browser. The JSON includes every event, command, exit code, stdout/stderr, token usage, and containment probe result, plus an Ed25519 signature and public key. Fetch `GET /api/evidence/public-key` and verify the canonical JSON with `EvidenceSigner.verify()`; the signature covers the pack without the signature fields.

## 7. Security notes

- Use a dedicated VM. `sandboxd` has Docker socket authority; treat it as a privileged service.
- Do not expose port 8090 publicly. It is only reachable inside the Compose network.
- Keep `VULTR_API_KEY` in `.env`, never in the repo or the sandbox.
- The local fallback (`SANDBOX_MODE=local`) is for development only.
- For a public multi-user deployment, add authentication and per-user quotas in front of the app.
- The app and sandboxd share `SANDBOXD_TOKEN`; rotate it like any other secret.
- Back up `data/evidence_key.pem` (or mount it from a secret manager). If the key is regenerated, old packs will not match the published fingerprint.
- The app port is loopback-only in Compose; Caddy is the public surface.
- For a stronger isolation boundary than Docker, run rootless Docker, gVisor, or Firecracker. Cage states the container boundary honestly.

## 8. Teardown

```bash
docker compose down -v
```

Then delete the Vultr instance if it was only for the demo.
