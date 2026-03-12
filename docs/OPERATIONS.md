# Star Office UI - Operator's Manual

This manual covers ongoing operations, maintenance, and troubleshooting for a production Star Office UI deployment.

## Daily Checks

1. **Service Health**
   - Visit `/health` endpoint in browser or use curl.
   - Expected: `"status": "healthy"`.
   - If degraded/unhealthy, investigate the failed checks.

2. **Log Review**
   - Check error count: `grep -c '"level":"ERROR"' logs/star-office.log | tail -1`
   - Look for repeated errors: `tail -100 logs/star-office.log | jq -r '.event // .message' | sort | uniq -c | sort -nr | head`
   - Rotate logs if file size > 10 MB (automatic rotation is configured).

3. **Agent Churn**
   - How many agents online? `curl -s http://localhost:19000/agents | jq length`
   - If ghost agents accumulate, verify cleanup thread is running (should be daemonized).

4. **Disk Space**
   - `df -h` on project partition. Ensure > 500 MB free.
   - Audit log growth: `du -sh audit.log`

## Weekly Tasks

- **Update Dependencies**: Check for outdated packages: `source .venv/bin/activate && pip list --outdated`. Upgrade cautiously in a maintenance window.
- **Review Audit Log**: Scan `audit.log` for unauthorized access or unexpected actions.
  ```bash
  tail -100 audit.log | jq -r '"\(.timestamp) \(.event) by \(.actor)"' | column -t
  ```
- **Asset Cleanup**: If custom assets are no longer needed, prune unused files from `frontend/` to avoid clutter.
- **Rate Limit Tuning**: If legitimate users are hitting limits, adjust the numbers in `backend/rate_limit.py`.

## Monthly Tasks

- **Security Audit**
  - Confirm `FLASK_SECRET_KEY` is strong (>=24 chars, not default).
  - Rotate `ASSET_DRAWER_PASS` if used.
  - Check system for exposed port 19000; ensure only localhost or through reverse proxy.
  - Review `join-keys.json` – revoke any keys that are no longer needed.

- **Backup Test**
  - Verify your backup restoration procedure works on a staging environment.
  - Ensure `audit.log` rotation and offsite copy.

- **Dependency Updates**
  - Review security advisories for Flask, Pillow, etc.
  - Update virtual environment in staging, test, then prod.

- **Metrics Review**
  - If using Prometheus, check dashboards for request rates, error spikes, agent count anomalies.
  - Set up alerts for `staroffice_http_requests_total{status=~"5.."}` and `staroffice_stale_agents_total > 0`.

## Monitoring Alerts (Recommended)

| Metric | Threshold | Action |
|--------|-----------|--------|
| `/health` status != `healthy` | immediate | Investigate failed check |
| `staroffice_stale_agents_total > 3` | warning | Investigate agent connectivity |
| `rate_limit_violations_total` (if instrumented) | > 10/min | Check for abuse |
| `staroffice_http_requests_total{status="503"}` rate > 1/min | warning | Backend overload or error |
| Disk free < 200 MB | critical | Clean up logs or expand storage |

## Logging Details

- **Application logs**: `logs/star-office.log` (JSON lines, rotate 10 MB, keep 10)
- **Access logs**: Handled by Nginx (or systemd if direct)
- **Audit log**: `audit.log` (root dir, append-only, immutable for compliance)
- **Error stack traces**: Include `exc_info=true` for full tracebacks.

To tail live:

```bash
# Application logs (colored)
tail -f logs/star-office.log | jq -c '. | select(.level=="ERROR" or .level=="WARNING")'

# Audit events
tail -f audit.log | jq -r '.timestamp .event .actor .target'
```

## Troubleshooting Scenarios

### Symptom: "pairing required" message when agents connect

**Cause**: Agents use join keys but the key is not approved or the agent hasn't been approved.

**Fix**:
```bash
# List pending agents
curl -s http://localhost:19000/agents | jq '.[] | select(.authStatus=="pending")'
# Approve via UI or POST /agent-approve with {"agentId": "..."}
```

### Symptom: High latency on UI

**Cause**: Large asset files, image processing blocking worker, or rate limiting kicks in.

**Investigation**:
- Check `staroffice_http_request_duration_seconds` histogram metrics.
- Look for long `json_write_duration_seconds` (indicates file lock contention).
- Monitor CPU and memory of gunicorn workers.

**Remediation**:
- Increase gunicorn workers (`--workers`).
- Offload Gemini generation to separate worker (future RQ implementation).
- Enable Redis caching for frequently accessed config.

### Symptom: Ghost agents remain on screen indefinitely

**Cause**: Cleanup thread may have crashed or `STALE_STATE_TTL_SECONDS` too high.

**Fix**:
- Verify cleanup thread is alive (should be daemon, auto-revived on restart).
- Manually trigger cleanup: `python3 -c "from app import _cleanup_stale_agents; _cleanup_stale_agents()"`
- Check `agents-state.json` for agents with very old `lastPushAt`.

### Symptom: Images not updating after custom asset upload

**Cause**: Browser cache serving old static assets.

**Fix**:
- The backend appends `?v=VERSION_TIMESTAMP` query param to encourage busting. Ensure the timestamp updates on restart (`_INDEX_HTML_CACHE`).
- Clear browser cache or use incognito.
- Verify asset file path in `frontend/` matches the `path` used in upload.

### Symptom: Gemini background generation fails

**Cause**: Missing script, wrong Python path, or no API key.

**Check**:
- Ensure `skills/gemini-image-generate/scripts/gemini_image_generate.py` exists.
- Ensure OpenClaw workspace path is correct (`OPENCLAW_WORKSPACE` env).
- Verify Gemini API key in `runtime-config.json` and file permissions 600.
- Check logs for `MISSING_API_KEY` or script errors.

## Maintenance Procedures

### Updating the Code

1. Pull new changes in a maintenance window.
2. Activate virtualenv and install new requirements: `pip install -r backend/requirements.txt --upgrade`.
3. Restart service: `systemctl --user restart star-office`.
4. Verify with `systemctl --user status star-office` and `/health`.

If database migration (SQLite) is involved in the update, run the provided migration script before restarting.

### Restarting Cleanly

```bash
systemctl --user restart star-office
# or if using run.sh manually:
./run.sh
```

### Zero-downtime Reload (Gunicorn)

Gunicorn supports graceful reload with `HUP` signal:

```bash
kill -HUP $(cat /tmp/star-office.pid)  # if PID file configured
# For systemd:
systemctl --user reload star-office
```

The `--preload` flag in the gunicorn command ensures application code is loaded before worker forks, reducing memory usage and enabling hot reload of code without dropping connections.

---

## Security Checklist

- [ ] `FLASK_SECRET_KEY` is 24+ random characters, not committed to repo.
- [ ] `ASSET_DRAWER_PASS` is strong; default `1234` never used in prod.
- [ ] `STAR_OFFICE_ENV=production` is set.
- [ ] TLS termination enabled (nginx or Cloudflare).
- [ ] `join-keys.json` contains only necessary keys; rotate periodically.
- [ ] File permissions: `state.json`, `agents-state.json`, `runtime-config.json` readable by service user only; `chmod 600` where appropriate.
- [ ] Nginx restricts `/assets/upload` and admin endpoints to authenticated users (via app-level auth) and possibly IP whitelisting.
- [ ] Firewall blocks port 19000 from public; only localhost or reverse proxy allowed.

---

## Support

For issues, consult:
- GitHub Issues: https://github.com/ringhyacinth/Star-Office-UI/issues
- Project README and SKILL.md for OpenClaw integration.
- Deployment guide for setup specifics.
