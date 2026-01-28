# Validation & Outcomes Tabs Design

## Overview

Add tabbed navigation to the Autodoctor card with separate views for Validation and Outcomes, each with a button to trigger the corresponding service call.

## Card Structure & Navigation

**Header with tabs:**
```
┌─────────────────────────────────────────────────┐
│ Autodoctor                                  ↻   │
├─────────────────────────────────────────────────┤
│  [Validation]  [Outcomes]                       │
│   ─────────                                     │
└─────────────────────────────────────────────────┘
```

- Two tabs below the title: "Validation" and "Outcomes"
- Active tab has underline indicator
- Tabs replace the current badge display in header (badges move into each view)
- Global refresh button (↻) remains in header - refreshes the currently active view

**State management:**
- `_activeTab: "validation" | "outcomes"` tracks which view is shown
- Each tab maintains its own data: `_validationData` and `_outcomesData`
- Switching tabs fetches data if not already loaded (lazy loading)
- Tab state persists during the session but not across page reloads
- Card opens to "Validation" tab by default

## Backend - New WebSocket Endpoints

| Endpoint | Returns | Purpose |
|----------|---------|---------|
| `autodoctor/validation` | Validation issues only | GET current results |
| `autodoctor/validation/run` | Runs validation, returns results | Trigger + GET |
| `autodoctor/outcomes` | Outcome issues only | GET current results |
| `autodoctor/outcomes/run` | Runs simulation, returns results | Trigger + GET |

**Response structure (same for both):**
```typescript
{
  issues: IssueWithFix[],
  healthy_count: number,
  last_run: string | null  // ISO timestamp of last run
}
```

**Data storage:**
- `hass.data[DOMAIN]["validation_issues"]` - validation results
- `hass.data[DOMAIN]["outcome_issues"]` - outcome results
- `hass.data[DOMAIN]["validation_last_run"]` - timestamp
- `hass.data[DOMAIN]["outcomes_last_run"]` - timestamp

**Backwards compatibility:**
- Keep existing `autodoctor/issues` and `autodoctor/refresh` endpoints
- They continue to return/trigger combined results

## OutcomeReport → ValidationIssue Conversion

The simulator returns `OutcomeReport` objects which need to be converted to `ValidationIssue` format for consistent card rendering.

```python
def outcome_report_to_issues(report: OutcomeReport) -> list[ValidationIssue]:
    if report.verdict == Verdict.ALL_REACHABLE:
        return []

    issues = []
    for path in report.unreachable_paths:
        issues.append(ValidationIssue(
            severity=Severity.WARNING,
            automation_id=report.automation_id,
            automation_name=report.automation_name,
            entity_id="",  # outcome issues are automation-level
            location=path,
            message=f"Unreachable: {path}",
            issue_type=IssueType.IMPOSSIBLE_CONDITION,
        ))
    return issues
```

**Why this approach:**
- Card stays simple - one issue format to render
- Fix engine already works with `ValidationIssue`
- No separate renderers or type switching
- Consistent UX across both tabs

## Card UI - Tab Content & Actions

**Each tab view contains:**

```
┌─────────────────────────────────────────────────┐
│ Autodoctor                                  ↻   │
├─────────────────────────────────────────────────┤
│  [Validation]  [Outcomes]                       │
│   ─────────                                     │
├─────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────┐   │
│  │ ✕ 2  ⚠ 1  ✓ 15                          │   │  ← badges for this view
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ▼ automation.living_room_lights               │
│    ✕ Invalid state "on" for binary_sensor...   │
│    💡 Use "off" instead (High confidence)      │
│    → Edit automation                           │
│                                                 │
├─────────────────────────────────────────────────┤
│  [▶ Run Validation]          Last run: 2m ago  │  ← action footer
└─────────────────────────────────────────────────┘
```

**Tab-specific footer:**
- "Run Validation" button on Validation tab
- "Run Outcomes" button on Outcomes tab
- Shows "Last run: X ago" timestamp (from `last_run` field)
- Button shows loading spinner while running

**Empty states:**
- No issues: "All automations passed validation" / "All outcomes reachable"
- Never run: "Run validation to check your automations" with prominent button

**Loading behavior:**
- First load of a tab: full loading spinner
- Subsequent refreshes: button spinner only, content stays visible

## Implementation Summary

**Backend changes (`custom_components/autodoctor/`):**

| File | Changes |
|------|---------|
| `models.py` | Add helper to convert `OutcomeReport` to `ValidationIssue` list |
| `websocket_api.py` | Add 4 new endpoints |
| `__init__.py` | Store results separately, add timestamps |
| `simulator.py` | Update to return issues in `ValidationIssue` format |

**Frontend changes (`www/autodoctor/`):**

| File | Changes |
|------|---------|
| `autodoctor-card.ts` | Add tab state, tab rendering, per-tab data fetching, run buttons, last-run display |
| `types.ts` | Add `last_run` to response type, add tab type |
