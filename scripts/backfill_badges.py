#!/usr/bin/env python3
"""Backfill badges for all existing contributions."""

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
GROWTH_DIR = ROOT / "growth"
AGENTS_STATE_FILE = ROOT / "agents-state.json"

# Import the badge system
import sys
sys.path.insert(0, str(ROOT / "backend"))
from blueprints.growth_badges import _load_badges, _load_agent_badges, _save_agent_badges, award_badge

# Load contributions
print("Loading contributions...")
with open(GROWTH_DIR / "contributions.json") as f:
    data = json.load(f)
contributions = data.get("contributions", [])

# Load existing agent badges
agent_badges = _load_agent_badges()

# Group contributions by agent
by_agent = {}
for c in contributions:
    agent = c.get("agent")
    if agent:
        by_agent.setdefault(agent, []).append(c)

print(f"Found contributions for {len(by_agent)} agents")

# For each agent, re-evaluate all badge conditions
badges = _load_badges()
for agent, agent_contribs in by_agent.items():
    print(f"\nProcessing {agent}: {len(agent_contribs)} contributions")

    # Count contributions by type
    room_created = sum(1 for c in agent_contribs if c.get("type") == "room_created")
    dash_created = sum(1 for c in agent_contribs if c.get("type") in ["dashboard_created", "room_dashboard"])
    automation = sum(1 for c in agent_contribs if c.get("type") == "automation")
    creative = sum(1 for c in agent_contribs if c.get("type") in ["creative", "theming", "content"])
    huddles = sum(1 for c in agent_contribs if c.get("type") == "huddle_started")

    # For each badge, check if qualified
    for bid, badge in badges.items():
        # Skip if already awarded
        if any(b.get("id") == bid for b in agent_badges.get(agent, [])):
            continue

        condition = badge.get("condition", {})
        cond_type = condition.get("type")
        triggered = False
        reason = ""

        if cond_type == "first_contribution":
            # Always award first_contribution if they have any contributions and no badges yet?
            # Or just because they have contributions. Simpler: award if they have >=1 contributions
            if len(agent_contribs) >= 1:
                triggered = True
                reason = "Has contributions"

        elif cond_type == "room_created":
            if room_created >= condition.get("count", 1):
                triggered = True
                reason = f"Created {room_created} rooms"

        elif cond_type == "dashboard_created":
            if dash_created >= condition.get("count", 5):
                triggered = True
                reason = f"Created {dash_created} dashboards"

        elif cond_type == "automation_expert":
            if automation >= condition.get("count", 5):
                triggered = True
                reason = f"Created {automation} automations"

        elif cond_type == "creative_genius":
            if creative >= condition.get("count", 3):
                triggered = True
                reason = f"Created {creative} creative works"

        elif cond_type == "huddle_starter":
            if huddles >= condition.get("count", 10):
                triggered = True
                reason = f"Started {huddles} huddles"

        if triggered:
            award = award_badge(agent, bid, reason)
            if award:
                print(f"  Awarded {badge['name']} to {agent}")

print("\nBackfill complete!")
print(f"Total badges awarded: {sum(len(badges) for badges in agent_badges.values())}")
