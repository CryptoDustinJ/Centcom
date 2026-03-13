#!/bin/bash
# Command Center: List recent emails
himalaya envelope list --max-width 100 2>/dev/null || echo "Email check unavailable"
