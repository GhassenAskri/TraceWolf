#!/bin/bash
# Put the THROWAWAY database back to the 40 seeded conversations (never touches the dev database).
docker exec aicontrol-ui-check psql -U aicontrol -d aicontrol -qc "TRUNCATE llm_calls, volumes RESTART IDENTITY CASCADE" && \
cd /Users/g.askri/Desktop/AIControl/api && PYTHONPATH=. uv run python /Users/g.askri/Desktop/AIControl/.claude/features/monitoring-sidebar/spike/seed_ui_check.py 2>&1 | grep -v UV_NATIVE
