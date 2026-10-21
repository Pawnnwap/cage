# Demo runbook

## If the public demo is being abused

1. Pause new tasks and probes:
   ```bash
   sed -i 's/^DEMO_ENABLED=.*/DEMO_ENABLED=false/' .env
   docker compose up -d --no-deps --force-recreate app
   ```
2. Kill every sandbox container immediately:
   ```bash
   docker ps -q --filter label=cage.sandbox=1 | xargs -r docker rm -f
   ```
3. Confirm nothing is left:
   ```bash
   docker ps -a --filter label=cage.sandbox=1
   ```
4. Check the app and sandboxd:
   ```bash
   curl -s http://127.0.0.1:8080/healthz
   curl -s http://127.0.0.1:8080/readyz
   docker compose logs --tail=100 app sandboxd
   ```
5. Rotate `SANDBOXD_TOKEN` and `VULTR_API_KEY` if you suspect either leaked. Restart `app` and `sandboxd` after rotation.
6. Back up the evidence key out-of-band if it is not already in a secret manager:
   ```bash
   cp data/evidence_key.pem /secure/backup/cage-evidence-key-$(date +%F).pem
   ```
7. Re-enable only after the incident is understood:
   ```bash
   sed -i 's/^DEMO_ENABLED=.*/DEMO_ENABLED=true/' .env
   docker compose up -d --no-deps --force-recreate app
   ```

## If the app is up but tasks fail

- Check `/readyz`; if it returns 503, sandboxd or Docker is not ready.
- `docker compose logs -f sandboxd` for Docker errors.
- `docker images | grep cage-sandbox`; rebuild if missing:
  ```bash
  docker build -t cage-sandbox:latest sandbox_image
  docker compose restart sandboxd
  ```
- If the model returns 404, check the Vultr model ID:
  ```bash
  curl -s https://api.vultrinference.com/v1/models | head
  ```
  Update `VULTR_MODEL` and restart `app`.

## If a task is cancelled

- The container is deleted directly by `/api/tasks/{id}/destroy`.
- The runner records the tokens spent before cancellation and does not overwrite the `cancelled` status.
- Confirm:
  ```bash
  docker ps -a --filter label=cage.task=<task-id>
  curl -s http://127.0.0.1:8080/api/tasks/<task-id>/evidence
  ```

## If the control plane restarts

- Startup reconciliation marks `running` tasks `interrupted` and emits a `task_finished` event.
- Orphan sandboxes are removed by sandboxd's TTL reaper; for an immediate cleanup use the kill command above.

## If evidence needs verification

```bash
curl -s http://127.0.0.1:8080/api/tasks/<task-id>/evidence > evidence.json
python scripts/verify_evidence.py evidence.json
```

The public key is also at `GET /api/evidence/public-key`; pin its fingerprint in the submission description. If you rotate the key, publish the new fingerprint and keep the old public key available so previously sealed packs still verify.
