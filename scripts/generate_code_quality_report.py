#!/usr/bin/env python3
"""
Code Quality Dashboard Generator
Analyzes the codebase and generates a metrics report for the Lab room.
"""

import json
import os
import re
import subprocess
import requests
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/dustin/openclaw-office")
REPORT_DIR = ROOT / "growth" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

def count_lines_and_code(root: Path):
    """Count total lines, code lines, comment lines, blank lines."""
    total_lines = 0
    code_lines = 0
    comment_lines = 0
    blank_lines = 0
    file_count = 0

    for file_path in root.rglob("*.py"):
        if "growth/reports" in str(file_path):
            continue
        file_count += 1
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                total_lines += len(lines)
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        blank_lines += 1
                    elif stripped.startswith('#'):
                        comment_lines += 1
                    else:
                        code_lines += 1
        except Exception:
            pass

    return {
        "total_lines": total_lines,
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "file_count": file_count
    }

def get_git_stats():
    """Get recent commit stats."""
    try:
        # Count commits in last 7 days
        since = (datetime.now().timestamp() - 7*86400)
        commits = subprocess.check_output(
            ["git", "log", f"--since={int(since)}", "--oneline"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip().split('\n') if subprocess.run(["git", "log", f"--since={int(since)}", "--oneline"], cwd=ROOT, capture_output=True).returncode == 0 else []
        commit_count = len([c for c in commits if c])

        # Get lines added/deleted in last 30 days
        stats = subprocess.check_output(
            ["git", "log", "--since=30 days ago", "--pretty=tformat:", "--numstat"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip().split('\n') if subprocess.run(["git", "log", "--since=30 days ago", "--pretty=tformat:", "--numstat"], cwd=ROOT, capture_output=True).returncode == 0 else []
        additions = 0
        deletions = 0
        for line in stats:
            parts = line.split('\t')
            if len(parts) >= 2:
                try:
                    additions += int(parts[0])
                    deletions += int(parts[1])
                except ValueError:
                    pass

        return {
            "commits_7d": commit_count,
            "lines_added_30d": additions,
            "lines_deleted_30d": deletions
        }
    except Exception as e:
        return {"commits_7d": 0, "lines_added_30d": 0, "lines_deleted_30d": 0, "error": str(e)}


def get_github_stats():
    """Fetch GitHub repository metrics (PRs, issues, reviews)."""
    repo = os.getenv('GITHUB_REPO', 'CryptoDustinJ/Centcom')
    token = os.getenv('GITHUB_TOKEN')
    headers = {'Authorization': f'token {token}'} if token else {}

    try:
        # Open PRs
        prs_resp = requests.get(
            f'https://api.github.com/repos/{repo}/pulls',
            headers=headers,
            params={'state': 'open', 'per_page': 100, 'sort': 'created', 'direction': 'desc'},
            timeout=10
        )
        prs = prs_resp.json() if prs_resp.status_code == 200 else []

        # Open issues (excluding PRs)
        issues_resp = requests.get(
            f'https://api.github.com/repos/{repo}/issues',
            headers=headers,
            params={'state': 'open', 'per_page': 100},
            timeout=10
        )
        issues = issues_resp.json() if issues_resp.status_code == 200 else []
        issues = [i for i in issues if 'pull_request' not in i]

        # Review coverage: count PRs with reviews
        review_coverage = 0
        if prs:
            sample_prs = prs[:10]
            for pr in sample_prs:
                rev_resp = requests.get(
                    f'https://api.github.com/repos/{repo}/pulls/{pr["number"]}/reviews',
                    headers=headers,
                    timeout=5
                )
                if rev_resp.status_code == 200 and len(rev_resp.json()) > 0:
                    review_coverage += 1

        return {
            "open_prs": len(prs),
            "open_issues": len(issues),
            "review_coverage_pct": round((review_coverage / min(10, len(prs))) * 100) if prs else 0,
            "recent_prs": [{"number": p["number"], "title": p["title"][:50], "user": p["user"]["login"]} for p in prs[:5]],
            "recent_issues": [{"number": i["number"], "title": i["title"][:50]} for i in issues[:5]],
            "rate_limited": prs_resp.status_code == 403 or issues_resp.status_code == 403
        }
    except Exception as e:
        return {"error": str(e), "open_prs": 0, "open_issues": 0}

def analyze_python_quality():
    """Basic Python code quality checks."""
    metrics = {
        "functions": 0,
        "classes": 0,
        "imports": 0,
        "todo_count": 0,
        "print_statements": 0,
    }

    for file_path in ROOT.rglob("*.py"):
        if "growth/reports" in str(file_path):
            continue
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith('def '):
                        metrics["functions"] += 1
                    elif stripped.startswith('class '):
                        metrics["classes"] += 1
                    elif stripped.startswith('import ') or stripped.startswith('from '):
                        metrics["imports"] += 1
                    if 'TODO' in line or 'FIXME' in line:
                        metrics["todo_count"] += 1
                    if re.match(r'^\s*print\s*\(', line):
                        metrics["print_statements"] += 1
        except Exception:
            pass

    return metrics

def generate_html_report(data: dict) -> str:
    """Generate an HTML dashboard page."""
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Code Quality Dashboard - Lab</title>
    <style>
        body {{ font-family: 'Courier New', monospace; background: #1e1e1e; color: #d4d4d4; padding: 20px; }}
        h1 {{ color: #4ec9b0; }}
        .metric {{ background: #2d2d2d; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007acc; }}
        .metric h3 {{ margin: 0 0 5px 0; color: #dcdcaa; }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #4ec9b0; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
        .footer {{ margin-top: 30px; color: #6a6a6a; font-size: 12px; }}
        .status-ok {{ border-left-color: #4ec9b0; }}
        .status-warn {{ border-left-color: #dcdcaa; }}
        .status-err {{ border-left-color: #f48771; }}
    </style>
</head>
<body>
    <h1>🖥️ Code Quality Dashboard</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

    <div class="grid">
        <div class="metric status-ok">
            <h3>📦 Files</h3>
            <div class="value">{data['file_count']}</div>
            <small>Python files analyzed</small>
        </div>
        <div class="metric status-ok">
            <h3>📝 Lines of Code</h3>
            <div class="value">{data['code_lines']:,}</div>
            <small>Total: {data['total_lines']:,} | Comments: {data['comment_lines']:,}</small>
        </div>
        <div class="metric status-ok">
            <h3>🔨 Functions</h3>
            <div class="value">{data['functions']}</div>
            <small>In codebase</small>
        </div>
        <div class="metric status-ok">
            <h3>🏛️ Classes</h3>
            <div class="value">{data['classes']}</div>
            <small>Object-oriented structures</small>
        </div>
        <div class="metric status-warn">
            <h3>📦 Imports</h3>
            <div class="value">{data['imports']}</div>
            <small>Dependencies count</small>
        </div>
        <div class="metric {'status-err' if data['todo_count'] > 0 else 'status-ok'}">
            <h3>✅ TODOs / FIXMEs</h3>
            <div class="value">{data['todo_count']}</div>
            <small>{'Needs attention' if data['todo_count'] > 0 else 'Clean!'}</small>
        </div>
    </div>

    <h2>📈 Git Activity (Last 30 Days)</h2>
    <div class="grid">
        <div class="metric status-ok">
            <h3>🔀 Commits (7d)</h3>
            <div class="value">{data['git_stats']['commits_7d']}</div>
            <small>Recent activity</small>
        </div>
        <div class="metric status-ok">
            <h3>📈 Lines Added</h3>
            <div class="value">+{data['git_stats']['lines_added_30d']:,}</div>
            <small>Growth metric</small>
        </div>
        <div class="metric status-ok">
            <h3>📉 Lines Deleted</h3>
            <div class="value">-{data['git_stats']['lines_deleted_30d']:,}</div>
            <small>Refactoring effort</small>
        </div>
    </div>

    <h2>🐙 GitHub Activity (OpenClaw Office)</h2>
    <div class="grid">
        <div class="metric status-ok">
            <h3>🔀 Open PRs</h3>
            <div class="value">{data['github_stats'].get('open_prs', 0)}</div>
            <small>Pending review</small>
        </div>
        <div class="metric status-ok">
            <h3>📝 Open Issues</h3>
            <div class="value">{data['github_stats'].get('open_issues', 0)}</div>
            <small>Bug reports & features</small>
        </div>
        <div class="metric status-{'status-warn' if data['github_stats'].get('rate_limited') else 'status-ok'}">
            <h3>📊 Review Coverage</h3>
            <div class="value">{data['github_stats'].get('review_coverage_pct', 0)}%</div>
            <small>{'Rate limited' if data['github_stats'].get('rate_limited') else 'PRs with reviews'}</small>
        </div>
    </div>

    {'<p style="color: #f48771;">⚠️ GitHub API rate limited. Set GITHUB_TOKEN for full data.</p>' if data['github_stats'].get('rate_limited') else ''}

    <div class="footer">
        Generated by CodeMaster's Dashboard Generator | OpenClaw Office Growth Engine
    </div>
</body>
</html>'''
    return html

def main():
    print("🔍 Analyzing codebase...")
    metrics = count_lines_and_code(ROOT)
    print(f"   Files: {metrics['file_count']}, Lines: {metrics['total_lines']}")

    git_stats = get_git_stats()
    print(f"   Git commits (7d): {git_stats['commits_7d']}")

    quality = analyze_python_quality()
    print(f"   Functions: {quality['functions']}, Classes: {quality['classes']}, TODOs: {quality['todo_count']}")

    # Combine data
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "generator": "CodeMaster",
        **metrics,
        "git_stats": git_stats,
        "github_stats": get_github_stats(),
        **quality
    }

    # Save JSON
    json_path = REPORT_DIR / "code_quality_latest.json"
    json_path.write_text(json.dumps(report_data, indent=2))
    print(f"✅ JSON report saved: {json_path}")

    # Generate and save HTML
    html = generate_html_report(report_data)
    html_path = REPORT_DIR / "dashboard_latest.html"
    html_path.write_text(html)
    print(f"✅ HTML report saved: {html_path}")

    # Also create a link/copy in the lab room static assets?
    lab_assets = ROOT / "frontend" / "rooms" / "lab"
    lab_assets.mkdir(parents=True, exist_ok=True)
    (lab_assets / "code_quality_dashboard.html").write_text(html)
    print(f"✅ Dashboard deployed to lab room: {lab_assets / 'code_quality_dashboard.html'}")

    print("\n📊 Report Summary:")
    print(f"   - Total Python files: {metrics['file_count']}")
    print(f"   - Lines of code: {metrics['code_lines']:,}")
    print(f"   - Functions: {quality['functions']}")
    print(f"   - Classes: {quality['classes']}")
    print(f"   - TODOs: {quality['todo_count']}")

    return 0

if __name__ == "__main__":
    exit(main())
