#!/usr/bin/env python3
"""
Team Sprint Coordinator - Assigns implementation tasks to CodeMaster
Run this to create implementation tasks for the current sprint.
"""

import requests
import json
from datetime import datetime

OFFICE_URL = "http://127.0.0.1:19000"

# Sprint tasks - each maps to a feature we need to build
SPRINT_TASKS = [
    {
        "title": "Render rooms from rooms.json on office canvas",
        "description": "Modify frontend/game.js to load /rooms endpoint and draw each room as a colored zone on the canvas. Add room labels and walls. Make agent sprites move between rooms based on their current area state.",
        "room": "workspace",
        "type": "frontend",
        "points": 50,
        "created_by": "Rook",
        "tags": ["frontend", "rendering", "rooms"]
    },
    {
        "title": "Auto-create tasks from daily huddle proposals",
        "description": "Update /office/huddle/start endpoint to automatically create tasks in /growth/tasks for each proposal with priority > 2. Assign tasks to the proposing agent. This makes the huddle actively generate work for the team.",
        "room": "workspace",
        "type": "backend",
        "points": 45,
        "created_by": "Rook",
        "tags": ["automation", "huddle", "tasks"]
    },
    {
        "title": "Build Story Corner display component",
        "description": "Create frontend/rooms/breakroom/story_corner.html that shows latest sci-fi stories. Pull from ~/.openclaw/knowledge/storybooks.db latest entries. Add furniture sprite (bookshelf, comfy chair) to breakroom JSON.",
        "room": "breakroom",
        "type": "creative",
        "points": 40,
        "created_by": "Nova",
        "tags": ["creative", "frontend", "content"]
    },
    {
        "title": "Syscheck Pipeline Dashboard",
        "description": "Build frontend/rooms/workspace/syscheck_dashboard.html that reads ~/.openclaw/workspace/reports/syscheck-latest.json and displays charts. Add chart visualization using Chart.js or similar. Show trends, alerts, system health.",
        "room": "workspace",
        "type": "automation",
        "points": 45,
        "created_by": "Ralph",
        "tags": ["automation", "dashboard", "metrics"]
    },
    {
        "title": "Server Room Live Metrics Panel",
        "description": "Create frontend/rooms/serverroom/metrics.html with live system stats: openclaw status (gateway/node), GPU usage (nvidia-smi), disk space, memory. Use polling or WebSocket if available.",
        "room": "serverroom",
        "type": "new_room",
        "points": 50,
        "created_by": "Rook",
        "tags": ["server", "metrics", "real-time"]
    },
    {
        "title": "GitHub API integration for PR/issue stats",
        "description": "Add to code_quality_report.py: fetch from GitHub API (octokit or requests) to get open PRs, recent issues, review coverage. Display in lab dashboard. Cache results to avoid rate limits.",
        "room": "lab",
        "type": "code_quality",
        "points": 40,
        "created_by": "CodeMaster",
        "tags": ["github", "api", "metrics"]
    },
    {
        "title": "Furniture upgrade system in UI",
        "description": "Implement room upgrade UI so agents can add furniture via API. Create frontend modal for asset drawer to place furniture sprites. Connect to /growth/room/upgrade endpoint.",
        "room": "workspace",
        "type": "frontend",
        "points": 35,
        "created_by": "CodeMaster",
        "tags": ["frontend", "ui", "assets"]
    },
]

def main():
    print("=" * 60)
    print("TEAM SPRINT COORDINATOR")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Check office health
    try:
        health = requests.get(f"{OFFICE_URL}/health", timeout=5)
        if health.status_code != 200:
            print(f"❌ Office unhealthy")
            return 1
    except requests.RequestException:
        print(f"❌ Cannot reach office at {OFFICE_URL}")
        return 1

    print(f"✅ Office reachable: {OFFICE_URL}")

    # Get current tasks to avoid duplicates
    existing = requests.get(f"{OFFICE_URL}/growth/tasks?limit=50").json()
    existing_titles = {t['title'] for t in existing.get('tasks', [])}

    # Create tasks
    created = 0
    for task in SPRINT_TASKS:
        if task['title'] in existing_titles:
            print(f"⏭️  Skipping: {task['title']} (already exists)")
            continue

        resp = requests.post(
            f"{OFFICE_URL}/growth/tasks",
            json=task,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            task_id = data['task']['id']
            print(f"✅ Created: {task['title']} (ID: {task_id})")
            created += 1
        else:
            print(f"❌ Failed: {task['title']} - {resp.text}")

    print(f"\n📊 Sprint tasks created: {created}")
    print("\nNext steps:")
    print("1. Review tasks: curl -s 'http://127.0.0.1:19000/growth/tasks?status=open' | python3 -m json.tool")
    print("2. Assign tasks to agents")
    print("3. Agents work on their tasks")
    print("4. Record contributions when complete")

    return 0

if __name__ == "__main__":
    exit(main())
