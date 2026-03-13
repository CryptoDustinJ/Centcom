#!/usr/bin/env python3
"""
Auto-join OpenClaw agents to the Star Office.
Uses join keys from join-keys.json to register each agent.
Then runs push loop to keep status updated.
"""

import json
import os
import sys
import time
import requests

OFFICE_URL = "http://localhost:19000"
JOIN_KEYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "join-keys.json")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "office-agents-state.json")

# Agent name to join key mapping (from join-keys.json)
AGENT_KEYS = {
    "Rook": "ocj_rook_001",
    "Ralph": "ocj_ralph_002",
    "Nova": "ocj_nova_003",
    "CodeMaster": "ocj_codemaster_005"
}

def load_join_keys():
    with open(JOIN_KEYS_FILE) as f:
        data = json.load(f)
    return {k['key']: k for k in data.get('keys', [])}

def join_agent(agent_name, join_key):
    """Join an agent to the office."""
    resp = requests.post(f"{OFFICE_URL}/join-agent", json={
        "name": agent_name,
        "joinKey": join_key,
        "detail": f"Auto-joined via script"
    })
    if resp.status_code == 200:
        data = resp.json()
        if data.get('ok'):
            agent_id = data['agent']['agentId']
            print(f"✅ {agent_name} joined successfully (agentId: {agent_id})")
            return agent_id
        else:
            print(f"❌ {agent_name} join failed: {data.get('msg', 'unknown')}")
    else:
        print(f"❌ {agent_name} join error: HTTP {resp.status_code}")
    return None

def push_agent_status(agent_id, name, state='idle', detail='Auto-push active'):
    """Push agent status update."""
    resp = requests.post(f"{OFFICE_URL}/agent-push", json={
        "agentId": agent_id,
        "name": name,
        "state": state,
        "detail": detail
    })
    if resp.status_code == 200:
        data = resp.json()
        if data.get('ok'):
            return True
    return False

def main():
    print("🔄 Connecting OpenClaw agents to Star Office...")

    # Load existing state if any
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            saved_state = json.load(f)
    else:
        saved_state = {}

    join_keys = load_join_keys()

    for agent_name, key in AGENT_KEYS.items():
        if key not in join_keys:
            print(f"⚠️  {agent_name}: key not found in join-keys.json")
            continue

        key_info = join_keys[key]

        # Check if already joined and recent
        if agent_name in saved_state:
            last_push = saved_state[agent_name].get('last_push', 0)
            if time.time() - last_push < 300:  # less than 5 min
                print(f"✓ {agent_name} already joined, skipping")
                continue

        # Attempt to join
        agent_id = join_agent(agent_name, key)
        if agent_id:
            saved_state[agent_name] = {
                'agentId': agent_id,
                'name': agent_name,
                'last_join': time.time()
            }

    # Save state
    with open(STATE_FILE, 'w') as f:
        json.dump(saved_state, f, indent=2)

    print("\n📋 Agent IDs:")
    for agent_name, info in saved_state.items():
        print(f"  {agent_name}: {info['agentId']}")

    print("\n✅ All agents joined! They should now appear in the office.")
    print("   (Note: This script only performs initial join. For continuous status updates,")
    print("   you need to run the individual office-agent-push.py scripts for each agent.)")

if __name__ == "__main__":
    main()
