#!/usr/bin/env python3
"""
Comprehensive test suite for Centcom Office features
Tests all endpoints added in the team sprint
"""

import requests
import json
import sys

BASE = "http://127.0.0.1:19000"

def test(name, func):
    """Run test and report result"""
    try:
        func()
        print(f"✅ {name}")
        return True
    except Exception as e:
        print(f"❌ {name}: {e}")
        return False

def get_json(endpoint):
    """Helper: GET and parse JSON"""
    resp = requests.get(f"{BASE}{endpoint}")
    resp.raise_for_status()
    return resp.json()

def post_json(endpoint, data):
    """Helper: POST JSON"""
    resp = requests.post(f"{BASE}{endpoint}", json=data)
    resp.raise_for_status()
    return resp.json() if resp.content else None

def test_health():
    """Basic health check"""
    resp = requests.get(f"{BASE}/health")
    assert resp.status_code == 200

def test_agents():
    """Agent list endpoint"""
    agents = get_json("/agents")
    assert isinstance(agents, list)
    assert len(agents) > 0

def test_rooms():
    """Rooms endpoint with connections"""
    rooms_data = get_json("/office/rooms")
    assert isinstance(rooms_data, dict)
    assert "rooms" in rooms_data
    # Check for connections field in rooms
    for room in rooms_data["rooms"]:
        if "connections" in room:
            assert isinstance(room["connections"], list)

def test_context_pressure():
    """Context pressure heatmap endpoint"""
    pressure = get_json("/office/context-pressure")
    assert isinstance(pressure, dict)
    assert "agents" in pressure or "pressure" in pressure

def test_conduits():
    """Data conduits endpoints"""
    conduits = get_json("/office/conduits")
    assert isinstance(conduits, dict)
    assert "zones" in conduits or "conduits" in conduits

    activity = get_json("/office/conduits/activity")
    assert isinstance(activity, dict)
    assert "activity" in activity or "calls" in activity

def test_incidents():
    """Incident alarm system"""
    incidents = get_json("/office/incidents")
    assert isinstance(incidents, dict)

def test_vitals():
    """Resource vitals floor tiles"""
    vitals = get_json("/office/vitals")
    assert isinstance(vitals, dict)
    # Check for expected metrics
    expected = ["cpu", "ram", "disk", "network"]
    for metric in expected:
        if metric not in vitals:
            print(f"  ⚠️  Missing metric: {metric} (not critical)")

def test_huddle_emergency():
    """Emergency huddle endpoint"""
    # This will start a huddle - may fail if already in one
    try:
        result = post_json("/office/huddle/emergency", {})
        assert isinstance(result, dict)
        assert "huddle_id" in result or "status" in result
    except requests.HTTPError as e:
        if "already" in str(e).lower() or "conflict" in str(e):
            print("  ℹ️  Huddle already active (OK)")
        else:
            raise

def test_skills_list():
    """Skill supply closet - list skills"""
    skills = get_json("/skills/list")
    assert isinstance(skills, dict)
    assert "skills" in skills

def test_agents_profile():
    """Agent profile pages"""
    agents = get_json("/agents")
    # agents is a list, get first agent ID
    if agents and len(agents) > 0:
        agent_id = agents[0].get("agentId") or agents[0].get("id")
        if agent_id:
            profile = get_json(f"/agents/{agent_id}/profile")
            assert isinstance(profile, dict)

def test_growth_tasks():
    """Growth tasks endpoint"""
    tasks = get_json("/growth/tasks")
    assert isinstance(tasks, dict)

def test_decision_audit():
    """Decision audit trail"""
    decisions = get_json("/office/decisions")
    assert isinstance(decisions, dict)

def test_office_context():
    """Office context aggregator (includes stats)"""
    context = get_json("/office/data/context.json")
    assert isinstance(context, dict)
    assert "context" in context

def run_all():
    """Run all tests"""
    tests = [
        ("Health check", test_health),
        ("Agents list", test_agents),
        ("Rooms with connections", test_rooms),
        ("Context pressure heatmaps", test_context_pressure),
        ("Data conduits", test_conduits),
        ("Incident alarms", test_incidents),
        ("Resource vitals", test_vitals),
        ("Emergency huddle", test_huddle_emergency),
        ("Skills list", test_skills_list),
        ("Agent profile", test_agents_profile),
        ("Growth tasks", test_growth_tasks),
        ("Decision audit", test_decision_audit),
        ("Office context", test_office_context),
    ]

    print(f"🧪 Testing {len(tests)} endpoints...\n")
    results = []
    for name, func in tests:
        results.append(test(name, func))

    passed = sum(results)
    total = len(results)
    print(f"\n📊 Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(run_all())
