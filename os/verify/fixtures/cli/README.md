# CLI event fixtures — SYNTHETIC

These JSONL files are **hand-written approximations** of what Claude Code (`claude -p --output-format
stream-json --verbose`) and Codex (`codex exec --json`) print, based on public documentation. They were
**not recorded from a real CLI run**. They exist to test the tolerant adapters without network access or cost.
Replace/add real recordings in step O6 and compare. Sentinel strings (`SENTINEL-…`) prove that message text is
never copied into stored events.
