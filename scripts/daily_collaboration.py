#!/usr/bin/env python3
"""
Daily Office Collaboration - Autonomous Agent Workspace Improvement

This script coordinates a daily "huddle" where agents propose and execute
improvements to their shared office environment.

Usage:
  python3 daily_collaboration.py [--dry-run] [--execute] [--huddle-id <id>]

Options:
  --dry-run        Show what would be done without making changes
  --execute        Execute the selected plan (commits changes)
  --huddle-id ID   Execute a specific huddle plan by ID
  --propose-only   Only start a huddle, don't execute (for manual review)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import requests

# Configuration
OFFICE_URL = os.environ.get("OFFICE_URL", "http://127.0.0.1:19000")
HUDDLE_ENDPOINT = f"{OFFICE_URL}/office/huddle/start"
PLANS_ENDPOINT = f"{OFFICE_URL}/office/plans"
EXECUTE_ENDPOINT = f"{OFFICE_URL}/office/plans"

# OpenClaw workspace paths (to read agent states)
OPENCLAW_HOME = os.environ.get("OPENCLAW_HOME", os.path.expanduser("~/.openclaw"))
AGENTS_STATE_FILE = Path(OPENCLAW_HOME) / "workspace" / "AGENTS.md"

def start_huddle(dry_run=False):
    """Start a new collaboration huddle."""
    print(f"🤝 Starting office collaboration huddle...")
    print(f"   Office URL: {OFFICE_URL}")

    if dry_run:
        print("   [DRY RUN] Would POST to /office/huddle/start")
        return {"huddle_id": "dry_run_123", "agents": ["Rook", "Ralph", "Nova"], "selected_plan": {"agent": "Rook", "idea": "Add server room"}}

    try:
        resp = requests.post(HUDDLE_ENDPOINT, timeout=30)
        if resp.status_code != 200:
            print(f"❌ Failed to start huddle: {resp.status_code} {resp.text}")
            sys.exit(1)
        data = resp.json()
        if not data.get("ok"):
            print(f"❌ Huddle failed: {data.get('msg')}")
            sys.exit(1)

        huddle = data
        print(f"✅ Huddle started: {huddle['huddle_id']}")
        print(f"   Agents: {', '.join(huddle['agents'])}")
        print(f"   Proposals: {len(huddle['proposals'])}")
        for p in huddle["proposals"]:
            print(f"   - {p['agent']}: {p['idea']} (priority {p['priority']})")
        print(f"   Selected: {huddle['selected_plan']['agent']} → {huddle['selected_plan']['idea']}")
        return huddle
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def execute_plan(huddle_id, dry_run=False):
    """Execute the selected plan for a huddle."""
    print(f"\n🔨 Executing plan for huddle {huddle_id}...")

    if dry_run:
        print("   [DRY RUN] Would POST to /office/plans/{huddle_id}/execute")
        print("   Would commit changes to git")
        return

    try:
        url = f"{EXECUTE_ENDPOINT}/{huddle_id}/execute"
        resp = requests.post(url, timeout=60)
        if resp.status_code != 200:
            print(f"❌ Execution failed: {resp.status_code} {resp.text}")
            return False
        data = resp.json()
        if not data.get("ok"):
            print(f"❌ Execution error: {data.get('msg')}")
            return False

        result = data
        print(f"✅ Plan executed successfully!")
        print(f"   {result['msg']}")
        print("   Execution log:")
        for log in result.get("execution_log", []):
            print(f"   - {log}")
        return True
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Daily office collaboration coordinator")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--execute", action="store_true", help="Execute the selected plan")
    parser.add_argument("--huddle-id", help="Execute a specific huddle by ID")
    parser.add_argument("--propose-only", action="store_true", help="Only start huddle, don't execute")
    args = parser.parse_args()

    print("=" * 60)
    print("DAILY OFFICE COLLABORATION")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Check office health
    try:
        health = requests.get(f"{OFFICE_URL}/health", timeout=5)
        if health.status_code != 200:
            print(f"❌ Office not healthy (HTTP {health.status_code})")
            sys.exit(1)
    except requests.RequestException:
        print(f"❌ Cannot reach office at {OFFICE_URL}")
        print("   Is the backend running? Try: cd ~/openclaw-office/backend && python3 app.py")
        sys.exit(1)

    # Execute a specific huddle if requested
    if args.huddle_id:
        execute_plan(args.huddle_id, dry_run=args.dry_run)
        return

    # Start new huddle
    huddle = start_huddle(dry_run=args.dry_run)
    huddle_id = huddle["huddle_id"]

    # If propose-only, stop here
    if args.propose_only:
        print("\n💡 Proposal phase complete. Manually review and execute with:")
        print(f"   python3 {sys.argv[0]} --execute --huddle-id {huddle_id}")
        return

    # Small delay to simulate agents discussing (optional)
    if not args.dry_run:
        print("\n⏳ Waiting 5 seconds for agent discussion... (simulated)")
        time.sleep(5)

    # Execute the selected plan automatically
    if args.execute:
        execute_plan(huddle_id, dry_run=args.dry_run)
    else:
        print("\n💡 Plan ready for execution.")
        print("   Run with: python3 daily_collaboration.py --execute --huddle-id", huddle_id)

    print("\n" + "=" * 60)
    print("Collaboration session complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
