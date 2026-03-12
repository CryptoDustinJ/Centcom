# Star Office UI - API Reference

## Base URL

`http://your-domain.com` (or `http://localhost:19000`)

All endpoints return JSON unless otherwise noted.

## Authentication

- **Session-based**: Asset editor and future admin endpoints use Flask sessions. Acquire session cookie via `/assets/auth` (POST with JSON `{"password": "..."}`).
- **Join Keys**: For agent connections, provide `joinKey` in the request body of `/join-agent` or `/agent-push`.

---

## Endpoints

### Core

#### `GET /`

Serve the main office UI (HTML page).

#### `GET /electron-standalone`

Serve standalone HTML for desktop pet mode.

#### `GET /join`

Display the agent join page (HTML).

#### `GET /invite`

Display invite instructions (HTML).

#### `GET /health`

Comprehensive health check.

**Response:**
```json
{
  "status": "healthy",
  "checks": {
    "state_file": "ok",
    "agents_file": "ok",
    "join_keys_file": "ok",
    "frontend_dir": "ok",
    "disk_free_mb": 1234,
    "disk": "ok",
    "redis": "connected",
    "gemini_env": "ready"
  },
  "timestamp": "2026-03-11T12:34:56Z",
  "service": "star-office-ui",
  "uptime": 3600
}
```
Status codes: `200` healthy, `200` degraded, `503` unhealthy.

#### `GET /metrics`

Prometheus-format metrics text (requires `prometheus-client`).

### State (Main Agent)

#### `GET /status`

Get current main agent state.

**Response:**
```json
{
  "state": "idle",
  "detail": "待命中",
  "progress": 0,
  "updated_at": "2026-03-11T12:34:56Z",
  "officeName": "Rook's Office" // optional, if IDENTITY.md present
}
```

#### `POST /set_state`

Update main agent state.

**Body:**
```json
{
  "state": "writing",
  "detail": "Writing some code"
}
```
- `state`: one of `idle`, `writing`, `researching`, `executing`, `syncing`, `error`
- `detail`: max 500 chars, HTML-escaped.

**Response:** `{"status": "ok"}` or `{"status": "error", "msg": "..."}`

#### `GET /yesterday-memo`

Retrieve yesterday's memo from `memory/*.md` files.

**Response:**
```json
{
  "date": "2026-03-10",
  "memo": "Yesterday I worked on..."
}
```

---

### Multi-Agent

#### `POST /join-agent`

Agent requests to join the office using a join key.

**Body:**
```json
{
  "name": "Ralph",
  "state": "idle",
  "detail": "Ready",
  "joinKey": "ocj_team_01"
}
```

**Response:** `{"ok": true, "agentId": "...", "authStatus": "approved"}`

Rate limit: 10 per 5 minutes per IP.

#### `POST /agent-push`

Remote agent pushes status updates (for OpenClaw integration).

**Body:**
```json
{
  "agentId": "abc123",
  "joinKey": "ocj_team_01",
  "state": "writing",
  "detail": "coding",
  "name": "Ralph" // optional
}
```

**Response:** `{"ok": true, "agent": { ... } }`

Rate limit: 60 per minute per IP.

#### `POST /leave-agent`

Agent notifies it is leaving.

**Body:**
```json
{
  "agentId": "abc123"
}
```

**Response:** `{"ok": true}`

#### `GET /agents`

List all agents with automatic stale cleanup.

**Response:** array of agent objects.

Rate limit: 60 per minute per IP.

#### `POST /agent-approve` *(admin)*

Approve a pending agent.

**Body:**
```json
{ "agentId": "abc123" }
```

**Response:** `{"ok": true}`

#### `POST /agent-reject` *(admin)*

Reject a pending agent.

**Body:**
```json
{ "agentId": "abc123" }
```

**Response:** `{"ok": true}`

#### `GET /agent-messages`

Retrieve pending dispatch messages (placeholder for future message queue).

**Response:** `{"messages": []}`

#### `POST /dispatch`

Receive dispatched messages from agents (OpenClaw integration).

**Response:** `{"ok": true, "msg": "dispatch received"}`

---

### Assets

#### `GET /assets/list`

List available custom asset files in `frontend/` directory.

**Response:**
```json
[
  {
    "path": "characters/star-working.webp",
    "size": 12345,
    "mtime": "2026-03-11T10:00:00"
  },
  ...
]
```

#### `POST /assets/upload`

Upload a custom asset (requires asset editor auth via session).

**Form fields:**
- `path`: relative path in `frontend/` (e.g., `backgrounds/custom-bg.webp`)
- `backup`: `1` to keep backup (default `1`)
- `auto_spritesheet`: `1` to convert animated GIF/WebP to spritesheet
- `frame_w`, `frame_h`, `pixel_art`, `preserve_original`, `cols`, `rows`: conversion hints
- `file`: the image file

**Response:** `{"ok": true, "path": "...", "size": 12345, "msg": "上传成功"}`

Rate limit: 30 per minute per IP.

#### `POST /assets/generate-rpg-background`

Start AI-generated background (asynchronous).

**Body:**
```json
{
  "style_hint": "8-bit cyberpunk tavern",
  "speed_mode": "fast" // or "quality"
}
```

**Response:** `{"ok": true, "task_id": "uuid"}`

#### `GET /assets/generate-rpg-background/poll?task_id=...`

Check generation task status.

**Response:**
```json
{
  "ok": true,
  "task": {
    "status": "pending|running|done|error",
    "result": {...},
    "error": "..."
  }
}
```

#### `POST /assets/restore-reference-background`

Restore the original reference background (package default).

#### `POST /assets/restore-last-generated-background`

Restore the most recently AI-generated background.

#### `POST /assets/restore-default`

Restore default asset for a specific file (from `.default` snapshot).

**Body:** `{ "path": "background-home.webp" }`

#### `POST /assets/restore-prev`

Restore previous version (from `.bak` backup).

**Body:** `{ "path": "background-home.webp" }`

#### `GET /assets/home-favorites/list`

List user-saved favorite backgrounds from `assets/home-favorites/`.

#### `GET /assets/home-favorites/file/<filename>`

Serve a favorite asset file.

#### `POST /assets/home-favorites/save-current`

Save a current frontend asset to favorites.

**Body:** `{ "path": "background-home.webp" }`

#### `POST /assets/home-favorites/delete`

Remove a favorite.

**Body:** `{ "filename": "myfav.webp" }`

#### `POST /assets/home-favorites/apply`

Apply a favorite as the current `background-home.webp`.

**Body:** `{ "filename": "myfav.webp" }`

#### `GET|POST /assets/positions`

Get or set asset position overrides (JSON map).

#### `GET|POST /assets/defaults`

Get or set asset default selections (JSON map).

#### `POST /assets/auth`

Authenticate to asset editor.

**Body:** `{ "password": "your_password" }`

Sets `session["asset_editor_authed"] = true` on success.

#### `GET /assets/auth/status`

Check asset editor auth status.

**Response:** `{ "authed": true }`

---

### Configuration

#### `GET /config/gemini`

Get Gemini configuration (API key masked).

**Response:**
```json
{
  "gemini_api_key": "abcd****",
  "gemini_model": "nanobanana-pro"
}
```

#### `POST /config/gemini`

Set Gemini configuration (requires asset editor auth).

**Body:**
```json
{
  "gemini_api_key": "your-key",
  "gemini_model": "nanobanana-pro"
}
```

**Response:** `{"ok": true, "msg": "Gemini 配置已保存"}`

---

## Error Responses

Standard error format:

```json
{
  "ok": false,
  "msg": "Human-readable error message"
}
```

HTTP status codes:
- `400` – Bad request (validation error)
- `403` – Forbidden (invalid join key, auth required)
- `404` – Not found
- `429` – Rate limit exceeded
- `500` – Internal server error

## Rate Limits

- `/join-agent`: 10 per 5 minutes per IP
- `/agent-push`: 60 per minute per IP
- `/assets/upload`: 30 per minute per IP
- `/set_state`: 120 per minute per IP
- `/agents`: 60 per minute per IP
- Global default: 100 per minute per IP (applies to all other endpoints)

Rate limit response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (seconds until reset).

---

## Notes

- All timestamps are ISO 8601 format (UTC if with Z, otherwise local server time but usually UTC).
- File uploads are limited to 10 MB by default.
- The service uses Flask sessions; cookie is `Secure` in production (HTTPS only).
- Audit events are written to `audit.log` (not part of API).

---

End of API Reference.
