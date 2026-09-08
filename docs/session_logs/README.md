# Session Logs

Archived, full-depth transcripts of the opencode sessions that produced this project
(protocol reverse-engineering + the cross-platform viewer). Kept so the thinking
process is auditable end-to-end.

## What's here
- `0000_session-index.md`   - overview table of every session.
- `NNN_YYYYMMDD_*.md`       - one file per session, full depth:
  - user and assistant text verbatim
  - assistant `thinking` blocks (collapsed `<details>` in markdown renderers)
  - every tool call (`[tool:name status] args` + `> result: …`)
  - `compaction` markers where older context was rolled up
- Main work session = the large `012_20260904_*` file (952+ messages, started 2026-09-03).

## Regenerate
```powershell
python tools/export_session.py            # all sessions
python tools/export_session.py --session ses_xxxx   # single session
python tools/export_session.py --out elsewhere
```

The exporter reads the local opencode store read-only (SQLite `opencode.db`,
`~/.local/share/opencode/` on all OSes) and writes Markdown here. Filenames are
numbered by chronological order, so a re-export is stable.

## Privacy
Export is applied to a redactor that blanks API-key/secret-looking tokens
(`sk-…`, `ghp_…`, JWT-like strings, long b64 blobs). Still review before sharing.