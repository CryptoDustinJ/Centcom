# OpenClaw Office - Great Improvement Plan

**Goal**: Transform the autonomous office from prototype to a living, learning, self-improving organism

**Strategy**: Delegate heavy lifting to CodeMaster while Rook coordinates and integrates

---

## 📋 MASTER CHECKLIST

### Phase 1: Smarter Decision-Making
- [ ] 1.1 Real Planning with Data Context
- [ ] 1.2 Assessment & Learning Loop

### Phase 2: Deeper Collaboration
- [ ] 2.1 Specialized Roles (Architect/Engineer/Artist/DevOps)
- [ ] 2.2 Cross-Room Dependencies
- [ ] 2.3 Joint Projects with Shared Ownership

### Phase 3: Smarter Office Environment
- [ ] 3.1 Dynamic Room Layout & Navigation
- [ ] 3.2 Environmental State Tied to Reality
- [ ] 3.3 Interactive Office Objects

### Phase 4: Growth Engine 2.0
- [ ] 4.1 Skill-Based Badges & Achievements
- [ ] 4.2 Career Progression System
- [ ] 4.3 Category Leaderboards
- [ ] 4.4 Betting/Prediction System

### Phase 5: Technical Capabilities
- [ ] 5.1 Multi-Agent Tool Orchestration
- [ ] 5.2 External API Integrations
- [ ] 5.3 Self-Modification & Self-Healing
- [ ] 5.4 Simulation & "What-If" Mode

### Phase 6: Game Mechanics
- [ ] 6.1 Seasons/Themes & Challenges
- [ ] 6.2 Random Events & Emergencies
- [ ] 6.3 Office Economy
- [ ] 6.4 Narrative & Lore

### Phase 7: Observability
- [ ] 7.1 Agent Conversation Transparency
- [ ] 7.2 Decision Audit Trail
- [ ] 7.3 Performance Profiling per Agent
- [ ] 7.4 A/B Testing Framework

### Phase 8: Scalability
- [ ] 8.1 Multi-Office Federation
- [ ] 8.2 Hierarchical Organizations
- [ ] 8.3 Complex Project Management
- [ ] 8.4 Resource Constraints & Budgeting

### Quick Wins (This Week)
- [ ] Q1: Add usage tracking to dashboards
- [ ] Q2: Enable multi-agent task assignment workflow
- [ ] Q3: Decision audit logging in plans.json
- [ ] Q4: Agent profile pages with badges
- [ ] Q5: Room connection graph for navigation
- [ ] Q6: Emergency huddle endpoint
- [ ] Q7: Office stats dashboard
- [ ] Q8: Agent birthday celebration

---

## 🎯 IMMEDIATE PRIORITIES (Start Here)

### Priority 1: Real Planning with Data Context (Phase 1.1)
**Assignee**: CodeMaster + Rook coordination
**Why**: Makes all future decisions smarter
**Impact**: HIGH

**Tasks**:
1. [ ] Create `/office/data/context.json` endpoint that aggregates:
   - Agent count, states, activity levels
   - Task backlog (open/completed/overdue counts)
   - Git status (recent commits, open PRs, branches)
   - System metrics (disk, memory, GPU)
   - Room utilization (which rooms have recent views)
   - Growth stats (recent contributions, leaderboard changes)

2. [ ] Modify `/office/huddle/start` to inject context into agent proposals:
   - Instead of hardcoded "Server room" → query agents with context
   - Use `sessions_send` to ask each agent: "Based on current state, what 1 improvement should we make?"

3. [ ] Add reasoning capture: Store agent's "why" in proposal details

**Acceptance Criteria**:
- Huddle proposals vary based on actual system state
- Proposals reference real data ("Disk at 85%, we need cleanup dashboard")
- At least 3 different proposal types emerge from different contexts

---

### Priority 2: Skill Badges & Achievements (Phase 4.1)
**Assignee**: CodeMaster (frontend + backend)
**Why**: Quick feedback, visible agent identity
**Impact**: MEDIUM-HIGH

**Tasks**:
1. [ ] Define badge catalog in `growth/badges.json`:
```json
{
  "badges": [
    {
      "id": "first_room_creator",
      "name": "Pioneer",
      "description": "Created the first new room",
      "icon": "🏠",
      "condition": {"type": "room_created", "count": 1}
    },
    {
      "id": "dashboard_hero",
      "name": "Dashboard Hero",
      "description": "Created 5+ dashboards",
      "icon": "📊",
      "condition": {"type": "dashboard_created", "count": 5}
    },
    {
      "id": "collaborator",
      "name": "Team Player",
      "description": "Completed 3+ multi-agent tasks",
      "icon": "🤝",
      "condition": {"type": "multi_agent_tasks", "count": 3}
    }
  ]
}
```

2. [ ] Create badge awarding logic in `growth/contributions.py`:
   - Check conditions when contributions logged
   - Award badge if not already owned
   - Store in `growth/agent_badges.json`

3. [ ] Display badges on agent profile page (new endpoint: `/agents/<id>/profile`)
   - Show earned badges with icons
   - Show badge acquisition date

**Acceptance Criteria**:
- Badges appear in agent profile API
- Agents see their badges in UI (new badge display component)
- Badge history tracked (when earned)

---

### Priority 3: Usage Tracking & Impact Metrics (Quick Win Q1)
**Assignee**: CodeMaster + Nova (UI)
**Why**: Data-driven agent scoring
**Impact**: HIGH

**Tasks**:
1. [ ] Add page view tracking:
   - Instrument all room HTML files to call `/growth/track-view` on load
   - Track agent ID, room, timestamp, duration (heartbeat every 30s)

2. [ ] Add interaction tracking:
   - Clicks on dashboard controls
   - Filter changes, date range selections
   - Time spent on page

3. [ ] Create `/growth/room/<room_id>/stats` endpoint:
   - Total views this week/month
   - Unique visitors (agent IDs)
   - Average session duration
   - Peak usage times

4. [ ] Update scoring algorithm:
   - Base points × (1 + usage_ multiplier)
   - High-traffic dashboards → bonus points
   - Create `/growth/recalculate-scores` endpoint

**Acceptance Criteria**:
- Dashboard views tracked in DB/file
- Stats endpoint returns room popularity
- Agent scores adjust based on usage
- Existing dashboards retroactively tracked

---

## 🤝 DELEGATION TO CODEMASTER

The following tasks are ideal for CodeMaster (code generation/improvement):

### For CodeMaster (Auto-assign via tasks):

**Task CM-1**: Implement `/office/data/context.json` aggregator
- Files: `backend/blueprints/office.py` (new function)
- Query: agents_state, tasks.json, git status, disk metrics
- Return: comprehensive JSON snapshot

**Task CM-2**: Rewrite huddle agent query to use context
- Files: `backend/blueprints/office.py` → `start_huddle()`
- Use `sessions_send` to ask agents for proposals based on context
- Parse responses instead of hardcoded if-else

**Task CM-3**: Build badge system (growth/badges.py)
- New blueprint module: `backend/blueprints/growth_badges.py`
- Conditions engine: evaluate badge criteria
- Award tracking: `growth/agent_badges.json`

**Task CM-4**: Create agent profile page
- New endpoint: `GET /agents/<id>/profile`
- Returns: badges, stats, contribution history, skill matrix
- Frontend: `frontend/agent-profile.html` template

**Task CM-5**: Dashboard usage tracking
- Add JS snippet to all room dashboards (inject via shared template)
- `POST /growth/track-view` endpoint in growth.py
- Storage: `growth/usage.json` (room views by day)

**Task CM-6**: Room connection graph
- Extend `rooms.json` with `connections` array (adjacent rooms)
- Frontend: Click to navigate between rooms
- Visual: Show mini-map with room layout

**Task CM-7**: Office stats dashboard
- New room: "lobby" or "metrics" room
- Dashboard showing: total commits, agent activity heatmap, room popularity
- Real-time updates (WebSocket or polling)

**Task CM-8**: Decision audit trail
- Modify `collaboration/plans.json` to store full agent reasoning
- New file: `collaboration/decisions/<huddle_id>_reasoning.json`
- Include: agent context, raw response, vote weights

**Task CM-9**: Multi-agent task assignment workflow
- UI: Checkbox to select multiple agents for a task
- Backend: `POST /growth/tasks` accepts `assignees: []` array
- Credit splitting: Points divided equally among completers

**Task CM-10**: Emergency huddle endpoint
- New endpoint: `POST /office/huddle/emergency`
- Bypasses normal scheduling → immediate huddle
- Useful for critical alerts (disk full, service down)

---

## 🎮 PHASE 3: IMMERSION & VISUALIZATION (Day 6-10)

*Added 2026-03-12 per Rook's request - transforming the office into a living, breathing organism*

### Task CM-11: Context Pressure Heatmaps
**Assignee**: Rook + Nova (frontend visualization)
**Why**: Visual feedback on agent cognitive load - helps manage context window usage
**Impact**: HIGH (prevvents context overflow issues)

**Tasks**:
1. [ ] Backend: Extend `/agents` endpoint to include `context_usage_pct` per agent (from OpenClaw agent state if available, or estimate based on recent activity)
2. [ ] Frontend: In `renderAgent()`, add a glow effect around the agent's desk/star icon based on `context_usage_pct`
   - 0-50%: no glow
   - 50-75%: soft blue glow
   - 75-90%: orange glow
   - 90%+: red pulsing glow (critical)
3. [ ] Use Phaser `setBlendMode(Phaser.BlendModes.ADD)` with radial gradient sprite for glow
4. [ ] Animate pulse for critical levels (scale oscillation)

**Acceptance Criteria**:
- Agent sprites visually indicate their context pressure
- Glow color/intensity correlates with usage percentage
- Critical threshold (90%) produces obvious pulsing alert

---

**Task CM-12**: Data "Conduits" Visualization
**Assignee**: Rook + Nova (visual effects)
**Why**: Make tool calls visible and understandable - show data flow to external systems
**Impact**: MEDIUM-HIGH

**Tasks**:
1. [ ] Define conduit zones: "Library" (RAG/database), "Mailroom" (email), "Cloud" (API), "Forge" (execution)
2. [ ] When agent executes a tool, spawn an animated pipe/beam from agent's desk to the appropriate zone
3. [ ] Use Phaser particle system or animated line with moving dots showing data flow
4. [ ] Conduit disappears when tool completes
5. [ ] Color-code by tool type: exec=orange, search=blue, email=green, etc.

**Acceptance Criteria**:
- Tool calls produce visible conduits in the office
- Conduits connect agent to appropriate themed zone
- Animation shows "data flowing" (moving particles or pulse)

---

**Task CM-13**: The "Water Cooler" (OOC Zone)
**Assignee**: Rook + CodeMaster (backend + frontend)
**Why**: Separate casual banter/logs from serious work output - cleaner context
**Impact**: MEDIUM

**Tasks**:
1. [ ] Create new area in office layout: `ooc_zone` (breakroom expansion or separate corner)
2. [ ] Backend: New endpoint `/office/ooc-messages` to store/retrieve casual messages (like old "vibe checks")
3. [ ] Frontend: Add scrolling ticker or small speech bubbles from the water cooler area showing recent OOC messages
4. [ ] Implement periodic "vibe check" auto-post (every 30min) from agents
5. [ ] Store OOC messages separately from main agent reasoning to reduce context noise

**Acceptance Criteria**:
- Dedicated water cooler visual element in office
- Ticker or bubbles show non-task messages
- OOC zone clearly separated from work areas

---

**Task CM-14**: Ghost Replays - Time Machine Mode
**Assignee**: Rook + Nova (advanced visualization)
**Why**: Replay complex collaboration sessions - invaluable for debugging and onboarding
**Impact**: HIGH (learning/analysis)

**Tasks**:
1. [ ] Backend: Capture full collaboration session data (huddle proposals, votes, execution steps with timestamps)
2. [ ] Store in `collaboration/replays/<date>/` as JSON with frame-by-frame agent states
3. [ ] Frontend: Add "Time Machine" UI panel (toggle)
4. [ ] Playback engine: scrub through timeline, render ghost agents (semi-transparent) re-enacting movements and state changes
5. [ ] Controls: play/pause, speed (0.5x, 1x, 2x), timeline scrubber
6. [ ] Ghost agents use ghost sprite (30% opacity, blue tint)

**Acceptance Criteria**:
- Complete huddle sessions can be replayed
- Timeline scrubber controls playback
- Ghost agents mimic original movements

---

**Task CM-15**: Boardroom Podium with TTS
**Assignee**: Rook + CodeMaster (audio integration)
**Why**: 7 AM Board Meeting delivery - immersive briefing experience
**Impact**: HIGH (Rook's daily ritual)

**Tasks**:
1. [ ] Add `podium` object to LAYOUT.furniture in layout.js
2. [ ] Create podium sprite asset or use existing rectangle with styling
3. [ ] Clicking podium triggers: `GET /office/latest-briefing` → returns TTS audio URL or text
4. [ ] Play TTS using Web Speech API or audio element
5. [ ] Backend: Generate daily briefing content (summary of yesterday's contributions, today's plan) via Gemini
6. [ ] Cache briefing in `growth/briefings/<date>.json`
7. [ ] Visual: podium glows when new briefing available

**Acceptance Criteria**:
- Clickable podium in office
- Plays latest TTS briefing
- Briefing auto-generated daily

---

**Task CM-16**: Skill "Supply Closet"
**Assignee**: Nova + CodeMaster (UI + permissions)
**Why**: Visual skill authorization management - drag & drop to grant skills
**Impact**: MEDIUM-HIGH

**Tasks**:
1. [ ] Backend: `GET /skills/list` endpoint reads `~/.openclaw/skills/` directory and returns skill definitions
2. [ ] Frontend: Add "Supply Closet" room or panel showing skill cards (icon + name + description)
3. [ ] Implement drag & drop: drag skill card onto agent sprite in office view
4. [ ] On drop: `POST /agents/<id>/skills` to add skill to agent's allowed list
5. [ ] Visual feedback: skill icon appears on agent's desk as "equipped"

**Acceptance Criteria**:
- Skills browsable in UI
- Drag & drop grants/revokes skill authorizations
- Visual indicator shows agent's current skills

---

**Task CM-17**: Incident Alarm System
**Assignee**: Rook + Ralph (monitoring integration)
**Why**: Immediate visual alert when tools fail or rate limits hit
**Impact**: HIGH (ops awareness)

**Tasks**1. [ ] Backend: Monitor tool execution failures (429, 500 errors) in audit.log
2. [ ] New endpoint `/office/incidents` returns current incident status (color: green/yellow/red)
3. [ ] Frontend: Poll `/office/incidents` every 10s
4. [ ] On red alert: office lighting shifts (tint overlay, siren animation optional)
5. [ ] Show incident count badge on alert icon
6. [ ] Click alert → shows incident details panel

**Acceptance Criteria**:
- Office visual changes when incidents detected
- Incident count visible
- Details accessible via click

---

**Task CM-18**: Desk Snapping for Sessions
**Assignee**: Rook + Nova (UX enhancement)
**Why**: Click agent's desk to "sit down" in their session - makes multi-threading tangible
**Impact**: HIGH (UX)

**Tasks**:
1. [ ] Frontend: Make agent star icons clickable (already partially there)
2. [ ] On click: open dedicated session view (`/session/<agent_id>`) in new panel or modal
3. [ ] Show agent's current conversation, tasks, and context in that view
4. [ ] Active session indicator: highlight current desk with border
5. [ ] Backend: `GET /agents/<id>/session` returns session data (messages, state memo)

**Acceptance Criteria**:
- Clicking agent opens their session view
- Active session visually highlighted
- Multiple sessions can be open simultaneously

---

**Task CM-19**: Sub-agent Nesting Visuals
**Assignee**: Nova + Rook (visual hierarchy)
**Why**: When agent spawns sub-agent, show them as smaller desk next to parent - visual parent-child relationship
**Impact**: MEDIUM

**Tasks**:
1. [ ] Backend: Store parent agent ID in sub-agent state (`parentAgentId`)
2. [ ] Frontend: In `renderAgent()`, check for agents with same room but different `parentAgentId`
3. [ ] Position sub-agents offset from parent desk (smaller scale, 75% size)
4. [ ] Draw subtle connecting line between parent and sub-agent
5. [ ] When parent moves, sub-agents follow (group movement)

**Acceptance Criteria**:
- Sub-agents appear as smaller desks near parent
- Visual connection shows hierarchy
- Parent movement includes sub-agents

---

**Task CM-20**: Resource Vitals Floor Tiles
**Assignee**: Rook + CodeMaster (system metrics display)
**Why**: System health visible in office background - don't need to leave 3D view
**Impact**: MEDIUM-HIGH

**Tasks**:
1. [ ] Backend: `GET /office/vitals` returns CPU%, RAM%, Disk%, Network% (cross-platform)
2. [ ] Frontend: Add floor tile pattern or wall screen in lobby that updates every 5s
3. [ ] Color-code vitals: green (healthy), yellow (warning), red (critical)
4. [ ] Animated bars or gauges in floor tiles
5. [ ] Optional: Click vitals panel to see detailed metrics

**Acceptance Criteria**:
- System resources displayed in office view
- Auto-refresh every 5 seconds
- Color coding indicates health status

---

## 🚀 IMPLEMENTATION SEQUENCE (Updated)

### Week 1: Foundation + Gamification (Days 1-5)
- Complete CM-1 through CM-8 (mostly done)
- Focus: CM-9 Decision Audit Trail completion

### Week 2: Collaboration Enhancements (Days 6-7)
- CM-10: Emergency huddle
- Multi-agent tasks (if not yet done)

### Week 3-4: Immersion & Visualization (Days 8-17) **NEW PRIORITY**
- CM-11: Context Pressure Heatmaps (quick win, high impact)
- CM-12: Data Conduits (fun visual)
- CM-13: Water Cooler OOC Zone
- CM-14: Ghost Replays (complex, may take longer)
- CM-15: Boardroom Podium with TTS
- CM-16: Skill Supply Closet
- CM-17: Incident Alarm System
- CM-18: Desk Snapping (quick, high UX impact)
- CM-19: Sub-agent Nesting
- CM-20: Resource Vitals Floor Tiles

### Week 5+: Advanced Phases
- Phase 4: Growth Engine 2.0 (skills-based badges, career progression)
- Phase 5: Technical Capabilities (multi-agent orchestration)
- Phase 6: Game Mechanics (seasons, themes, office economy)
- Phase 7: Observability improvements
- Phase 8: Scalability (multi-office federation)

**NOTE**: Immersion features are now HIGH PRIORITY per Rook's request. Begin CM-11 immediately after CM-9 completion.

---

## 🚀 IMPLEMENTATION SEQUENCE

### Day 1-2: Foundation
1. Create plan file (this document) ✓
2. Assign CodeMaster tasks via growth system
3. Set up tracking: `PLAN_STATUS.md` to check off boxes
4. Deploy context aggregator (CM-1)
5. Test huddle with real context (CM-2)

### Day 3-5: Gamification
6. Build badge system (CM-3)
7. Agent profiles (CM-4)
8. Usage tracking (CM-5)
9. Recalculate scores with usage data

### Day 6-7: UX Improvements
10. Room connections (CM-6)
11. Office stats dashboard (CM-7)
12. Audit trail (CM-8)

### Day 8-10: Collaboration Enhancements
13. Multi-agent tasks (CM-9)
14. Emergency huddles (CM-10)

### Week 2+: Advanced Features
15. Begin Phase 3 (environment)
16. Begin Phase 5 (external APIs)
17. Begin Phase 6 (game mechanics)

---

## 📊 SUCCESS METRICS

- **Engagement**: Number of huddles per day (target: 3+)
- **Productivity**: Tasks completed per agent per week (target: 2+)
- **Quality**: Room views per dashboard (target: 10+ views/week)
- **Collaboration**: Multi-agent tasks (target: 30% of all tasks)
- **Innovation**: New rooms per month (target: 1+)

---

## 🔄 RESTART PROTOCOL

If context limit reached or need to restart:

1. Read `PLAN_STATUS.md` to see completion status
2. Pick up at next unchecked item in sequence
3. All tasks are independent except:
   - Must do CM-1 before CM-2
   - Must do CM-3 before completing badge-related quick wins
   - Usage tracking (CM-5) should precede scoring recalculation

4. CodeMaster can work in parallel on independent tasks:
   - CM-3, CM-4, CM-6 can run concurrently
   - CM-5 needed before any usage-based scoring

---

## 🎯 STretch GOAL (After Core)

Once all checked, consider:
- Deploy second office instance → federation experiment
- Add Claude as 5th agent with "philosopher" role
- Implement self-modification: agents can edit plan file
- Add "predictive maintenance" where agents forecast issues

---

**Started**: 2026-03-12
**Status**: In Progress
**Coordinator**: Rook (with CodeMaster automation)
