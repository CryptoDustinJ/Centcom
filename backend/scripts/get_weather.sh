#!/bin/bash
# Command Center: Get weather summary
curl -sf "wttr.in/?format=3" 2>/dev/null || echo "Weather unavailable"
