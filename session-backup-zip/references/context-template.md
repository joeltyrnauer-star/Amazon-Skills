# Context files

Write CONTEXT.md with goal, decisions and reasons, inputs/outputs and their status, current state, unresolved issues, environment, and restore instructions. Do not repeat large source bodies.

Write checkpoint.yaml with these keys; omit empty fields:
```yaml
project:
goal:
done_when:
constraints:
approved_decisions:
proposals:
state:
validation:
blockers:
open_questions:
next_actions:
resume_reads:
references:
```
Preserve exact identifiers/formulas/commands when needed. Target about 800 tokens. Describe unavailable state explicitly.

Write sources.json as records mapping source ID/URL/path, original filename, version/capture time, export format, and staged/archive path. Preserve multiple versions and same-name files with unique paths.

Write coverage.json:
```json
{
  "scope": "current session and named project",
  "capture_cutoff_utc": "ISO timestamp",
  "user_timezone": "IANA timezone",
  "categories": {
    "transcript": {"status": "partial", "reason": "Only visible messages available"},
    "context": {"status": "complete", "evidence": "Context files staged"},
    "inputs": {"status": "missing", "reason": "Inventory pending"},
    "outputs": {"status": "missing", "reason": "Inventory pending"},
    "project_files": {"status": "missing", "reason": "Inventory pending"},
    "tool_logs": {"status": "partial", "reason": "Only accessible logs"}
  },
  "redactions": [],
  "inaccessible_sources": []
}
```
Use complete, partial, missing, or excluded. Replace example values with verified evidence. Record categories with no applicable items explicitly. Never certify complete using mere file presence. The script defaults to partial and also downgrades when any exclusions occur.
