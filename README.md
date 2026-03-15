# CentCom — OpenClaw Office

![CentCom Preview](docs/screenshots/office-preview-20260313.jpg)

**A pixel-art command center for your AI agent team.** Watch your agents work, roam, chat, and collaborate in a cyberpunk office — all in real time.

Built on [Star Office UI](https://github.com/ringhyacinth/Star-Office-UI) and deeply integrated with [OpenClaw](https://github.com/openclaw/openclaw).

---

## What Is This?

CentCom is a visual dashboard that turns your OpenClaw agent team into pixel-art characters working in a shared office. Each agent has their own desk, walks around checking things, visits teammates, and gathers at the coffee table for daily huddles.

**The Team:**
- **Rook** — Lead agent (Google Gemini). Coordinates the team, handles complex tasks.
- **Ralph** — Operator (Google Gemini). Runs system checks, dispatches tasks, executes scripts.
- **Nova** — Research specialist (OpenRouter). Continuous improvement, knowledge base research.
- **CodeMaster** — Code quality expert. Analyzes codebases, generates dashboards.

## Features

**Live Agent Visualization**
- Custom pixel-art sprites for each agent with idle and walk animations
- Agents independently roam the office — checking their desk, visiting shared areas, walking to teammates
- Chat bubbles show recent Discord messages above each agent's head

**Direct Agent Chat**
- Click any agent to open a chat box and talk to them directly
- Messages dispatch via OpenClaw — agents respond in real time
- Replies appear in the chat box and as speech bubbles

**Interactive Computers**
- Click specific computers in the office to open in-game dashboards
- Code Quality Dashboard (CodeMaster's station)
- Server Room Metrics (system health, GPU, disk)
- Syscheck Pipeline (Ralph's monitoring)

**Embedded Claude Code Terminal**
- Click a computer to open a fully functional Claude Code (Opus 4.6) terminal *inside* the pixel-art office
- Claude has full project context — it knows it's running inside CentCom and can modify the office code from within
- Session persistence: conversations carry across messages using `--resume`
- Runs with `--dangerously-skip-permissions` for uninterrupted autonomous coding
- **The office can literally rewrite itself** — a self-modifying application where the AI living inside the UI can change the UI

**Code Forge**
- Dedicated room for build artifacts and deployment status
- Live compiler status showing current git branch, last commit, and build state (idle/building/dirty)
- Deployment pipeline panel with target environment and service health
- Artifact shelf listing the 20 most recent build outputs with sizes
- System vitals (CPU/RAM/Disk) in the Build Tools card
- Auto-refreshes every 10 seconds via `/office/forge-status` API
- Proposed by CodeMaster during huddle `huddle_20260314_1225`

**Daily Huddle**
- Agents walk to the coffee table for a team standup (cron-scheduled)
- Collaborative planning with proposal voting and auto-execution

**Live Chat Feed**
- Scrollable panel showing all agent Discord messages
- Color-coded by agent with timestamps

**Hive-Mind Swarm Dashboard**
- Clickable in-game computer opens a live swarm status panel
- Shows all agent statuses (online/idle/error) with model info
- Displays recent Hive-Mind ledger events — syschecks, alerts, deploys, auto-heals
- Auto-refreshes every 15 seconds

**Swarm Domain-Agent Dispatcher**
- Background thread checks all agent sessions every 15 minutes
- Writes status snapshots to `swarm/swarm-status.json`
- Powers the Hive-Mind dashboard and swarm status API (`/office/swarm-status`)

**Hive-Mind Shared Memory Ledger**
- All agents log events (syschecks, alerts, fixes, research, deploys) to a shared ledger
- Events auto-archive after 24 hours
- API endpoints: `GET /office/get-hive-mind-context`, `POST /office/log-memory-packet`
- Agents use this for cross-team awareness without flooding Discord

**Task Queue System**
- Structured task queue with dependencies and chains
- Agents pick up, execute, and complete tasks autonomously
- Wake-dispatcher sends task context when waking idle agents
- Nightly consolidation auto-generates research tasks from a rotating backlog

**Auto-Heal System**
- Error interceptor service tails gateway/node logs and posts errors to the Hive-Mind ledger
- CodeMaster dispatches for known playbook matches with fallback to direct script fixes
- Escalates to Rook after repeated failures
- Regression detection within 30 minutes of a fix

**Windows Guardian Watchdog**
- PowerShell script runs silently on Windows, checks health every 2 minutes
- File-based architecture: WSL cron writes health status, Guardian reads it and writes repair requests
- Auto-recovers: WSL crashes, service failures, port issues, cron death, disk full
- Directly restarts WSL cron when it dies (no circular dependency)
- Escalates via Windows toast notifications after repeated failures
- Auto-launches from Windows Startup folder

**Wake-on-Demand**
- Agents sleep until needed — 5-minute dispatcher poll replaces constant heartbeats
- Heartbeats reduced to 6-hour safety nets
- Saves tokens and API costs while keeping agents responsive

**Command Center**
- Dispatch tasks: syscheck, fullcheck, self-heal, weather, wallpaper
- Knowledge base search and research triggers
- Storybook scraping and browsing

**Rooms**
- **Main Office** — Agent desks, coffee table for huddles, interactive computers
- **Server Room** — Live system metrics (CPU, RAM, disk, GPU, services)
- **Code Forge** — Build artifacts, deployment pipeline, compiler status
- **War Room** — Incident response and emergency coordination
- **Observatory** — API monitoring
- **Library** — Knowledge base browser
- **Archive** — Decision history and past huddles
- **Ops Center** — Live service dashboards
- **Comms Center** — Cross-agent messaging hub
- **Gallery** — Art gallery
- **Rooftop Garden** — Agent relaxation area

## Setup

**Requirements:** Python 3.10+, [OpenClaw](https://github.com/openclaw/openclaw) (for agent integration)

```bash
# Clone
git clone https://github.com/CryptoDustinJ/Centcom.git
cd Centcom

# Install dependencies
python3 -m pip install -r backend/requirements.txt

# Copy default state (first time)
cp state.sample.json state.json

# Start
cd backend
python3 app.py
```

Open **http://127.0.0.1:19000**

## Architecture

```
frontend/           Phaser 3 game + HTML overlays (single-page)
  index.html        Main UI (~7500 lines, inline Phaser game)
  sprites/          Agent spritesheets (idle, walk, talk)
  rooms/            Dashboard HTML files per room

backend/            Flask server (port 19000)
  app.py            Application factory, swarm dispatcher, cleanup threads
  config.py         Configuration with environment validation
  blueprints/
    core.py         Page serving, health checks, metrics
    agents.py       Agent state, messaging, dispatch to OpenClaw
    office/         Huddle system, collaboration, plans, Hive-Mind ledger

swarm/              Swarm status snapshots and domain agent dispatchers
collaboration/      Huddle decisions, plans, and team proposals
```

## Agent Configuration

Agents connect via reusable join keys defined in `join-keys.json`. The backend preserves agents with reusable keys across restarts — they reset to idle instead of being removed.

All agents dispatch through OpenClaw and communicate via Discord + agent-to-agent backchannel (`sessions_send`).

| Agent | Model | Role |
|---|---|---|
| Rook | `google/gemini-3.1-flash-lite-preview` | Team lead, strategy, coordination |
| Ralph | `google/gemini-2.5-flash-lite` | System monitoring, ops, dispatch |
| Nova | `openrouter/healer-alpha` | Research, knowledge base, analysis |
| CodeMaster | `openrouter/hunter-alpha` | Code audits, quality dashboards |

## Credits

- Original [Star Office UI](https://github.com/ringhyacinth/Star-Office-UI) by [Ring Hyacinth](https://x.com/ring_hyacinth) and [Simon Lee](https://x.com/simonxxoo)
- Customized and extended for OpenClaw multi-agent operations by [@CryptoDustinJ](https://github.com/CryptoDustinJ)
- Powered by [OpenClaw](https://github.com/openclaw/openclaw)
