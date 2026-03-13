#!/bin/bash
# OpenClaw Office Collaboration - Daily agent workspace improvement
# This script triggers the office huddle and optionally executes the plan.
# Can be called by Rook/Ralph via dispatch or cron.

set -euo pipefail

# Configuration
OFFICE_URL="${OFFICE_URL:-http://127.0.0.1:19000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/daily_collaboration.py"
VENV_PYTHON="$SCRIPT_DIR/../.venv/bin/python3"
# Use venv python if available (has requests), else system python3
if [ -x "$VENV_PYTHON" ]; then
  PYTHON="$VENV_PYTHON"
else
  PYTHON="python3"
fi

# Colors for output (only if terminal supports)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  BLUE='\033[0;34m'
  YELLOW='\033[1;33m'
  RED='\033[0;31m'
  NC='\033[0m'
else
  GREEN=""
  BLUE=""
  YELLOW=""
  RED=""
  NC=""
fi

cmd="${1:-}"
shift 2>/dev/null || true

case "$cmd" in
  "huddle")
    # Just start a huddle (proposals only)
    echo -e "${BLUE}🤝 Starting office huddle...${NC}"
    echo "   Office URL: $OFFICE_URL"

    # Check office health
    if ! curl -sf "$OFFICE_URL/health" > /dev/null; then
      echo -e "${RED}❌ Office not responding at $OFFICE_URL${NC}"
      echo "   Is the backend running? Try:"
      echo "   cd $SCRIPT_DIR/../backend && python3 app.py"
      exit 1
    fi

    # Start huddle (dry-run to avoid auto-execute)
    "$PYTHON" "$PYTHON_SCRIPT" --propose-only
    ;;

  "execute")
    # Execute a specific huddle plan
    HUDDLE_ID="${1:-}"
    if [ -z "$HUDDLE_ID" ]; then
      echo "Usage: $0 execute <huddle_id>"
      echo "Tip: Get huddle_id from the huddle output or from /office/plans"
      exit 1
    fi
    echo -e "${BLUE}🔨 Executing huddle plan $HUDDLE_ID...${NC}"
    "$PYTHON" "$PYTHON_SCRIPT" --execute --huddle-id "$HUDDLE_ID"
    ;;

  "daily")
    # Full daily routine: huddle + execute
    echo -e "${BLUE}📅 Daily office collaboration${NC}"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"

    # Check office health
    if ! curl -sf "$OFFICE_URL/health" > /dev/null; then
      echo -e "${RED}❌ Office not responding at $OFFICE_URL${NC}"
      echo "   Is the backend running? Try:"
      echo "   cd $SCRIPT_DIR/../backend && python3 app.py"
      exit 1
    fi

    # Start huddle and auto-execute
    echo ""
    echo "Starting huddle and executing selected plan..."
    HUDDLE_OUTPUT=$("$PYTHON" "$PYTHON_SCRIPT" 2>&1) || true
    echo "$HUDDLE_OUTPUT"
    ;;

  "test")
    # Quick test connection
    echo "Testing office connectivity..."
    if curl -sf "$OFFICE_URL/health" > /dev/null; then
      echo -e "${GREEN}✅ Office reachable${NC}"
      echo "   URL: $OFFICE_URL"
      echo "   Status:"
      curl -s "$OFFICE_URL/office/status" | python3 -m json.tool 2>/dev/null || echo "   (could not fetch status)"
    else
      echo -e "${RED}❌ Office not reachable${NC}"
      exit 1
    fi
    ;;

  "list")
    # List previous huddles
    echo "Fetching collaboration history..."
    curl -s "$OFFICE_URL/office/plans" | python3 -m json.tool 2>/dev/null || echo "Cannot fetch plans"
    ;;

  *)
    echo "OpenClaw Office Collaboration Script"
    echo ""
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  huddle              Start a new huddle (proposals only, no execute)"
    echo "  execute <huddle_id> Execute a specific huddle plan"
    echo "  daily               Full daily routine (huddle + execute automatically)"
    echo "  test                Test office connectivity"
    echo "  list                List all huddle plans and their status"
    echo ""
    echo "Examples:"
    echo "  $0 huddle                           # Start proposals"
    echo "  $0 list                            # See past huddles"
    echo "  $0 execute huddle_20250312_0700    # Execute that plan"
    echo ""
    echo "Environment:"
    echo "  OFFICE_URL      Office backend URL (default: http://127.0.0.1:19000)"
    echo ""
    echo "Integration:"
    echo "  Add to Rook's dispatch (ralph-dispatch.sh):"
    echo "    office-collab)  \"$HOME/.openclaw/office-collaboration.sh\" daily ;;"
    echo ""
    echo "  Add to crontab (run daily at 7 AM):"
    echo "    0 7 * * * $HOME/.openclaw/office-collaboration.sh daily"
    exit 1
    ;;
esac
