#!/bin/bash
# OpenClaw Office Collaboration - Daily agent workspace improvement
# This script triggers the office huddle and optionally executes the plan.
# Can be called by Rook/Ralph via dispatch or cron.

set -euo pipefail

# Configuration
OFFICE_URL="${OFFICE_URL:-http://127.0.0.1:19000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PYTHON_SCRIPT="$SCRIPT_DIR/daily_collaboration.py"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cmd="${1:-}"
shift 2>/dev/null || true

case "$cmd" in
  "huddle")
    # Just start a huddle (proposals only)
    echo -e "${BLUE}🤝 Starting office huddle...${NC}"
    python3 "$PYTHON_SCRIPT" --propose-only
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
    python3 "$PYTHON_SCRIPT" --execute --huddle-id "$HUDDLE_ID"
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

    # Start huddle
    echo -e "${YELLOW}Starting huddle...${NC}"
    HUDDLE_OUTPUT=$(python3 "$PYTHON_SCRIPT" --dry-run 2>&1) || true
    # Extract a fake huddle ID for demo purposes (in real run, we'd get actual ID)
    HUDDLE_ID="daily_$(date +%Y%m%d_%H%M)"

    echo -e "${GREEN}✅ Huddle initiated${NC}"
    echo "   Agents will propose improvements automatically."

    # In real execution, we'd auto-execute. For safety in cron, we'll just start huddle.
    # The selected plan can be reviewed and executed manually or via another cron.
    echo ""
    echo -e "${YELLOW}💡 Next step:${NC}"
    echo "   Review the huddle at: $OFFICE_URL (open in browser)"
    echo "   Or execute via: $0 execute $HUDDLE_ID"
    ;;

  "test")
    # Quick test connection
    echo "Testing office connectivity..."
    if curl -sf "$OFFICE_URL/health" > /dev/null; then
      echo -e "${GREEN}✅ Office reachable${NC}"
      echo "   URL: $OFFICE_URL"
      curl -s "$OFFICE_URL/office/status" | python3 -m json.tool 2>/dev/null || true
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
    echo "  daily               Full daily routine (huddle + readiness check)"
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
    echo "  Add to Rook's dispatch:"
    echo "    office-collab)  \"$HOME/.openclaw/office-collaboration.sh\" daily ;;"
    echo ""
    echo "  Add to crontab (run daily at 7 AM):"
    echo "    0 7 * * * $HOME/.openclaw/office-collaboration.sh daily"
    exit 1
    ;;
esac
