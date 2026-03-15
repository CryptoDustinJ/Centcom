# Agents

## Model Strategy (Cost-Optimized)

1. **Thinking/New Issues:** Use `google/gemini-3.1-flash-lite-preview`
2. **Routine Cron Tasks:** Use `google/gemini-1.5-flash-8b`
3. **Complex Refactoring:** Offload to the dedicated Claude Opus 4.6 terminal (via `/office/claude-code` API)
4. **Idle/Maintenance:** Use `google/gemini-1.5-flash-8b`
