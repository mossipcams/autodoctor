# Validation & Outcomes Tabs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add tabbed navigation to the Autodoctor card with separate Validation and Outcomes views, each with a run button.

**Architecture:** Backend adds 4 new WebSocket endpoints (2 per tab: get + run). Frontend adds tab state and renders appropriate view with run button and last-run timestamp.

**Tech Stack:** Python (Home Assistant custom component), TypeScript/Lit (Lovelace card)

---

## Task 1: Add OutcomeReport to ValidationIssue Converter

**Files:**
- Modify: `custom_components/autodoctor/models.py`
- Test: `tests/test_models.py` (create if needed)

**Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Tests for models."""

import pytest
from custom_components.autodoctor.models import (
    OutcomeReport,
    ValidationIssue,
    Verdict,
    Severity,
    IssueType,
    outcome_report_to_issues,
)


def test_outcome_report_to_issues_all_reachable():
    """All reachable returns empty list."""
    report = OutcomeReport(
        automation_id="automation.test",
        automation_name="Test Automation",
        triggers_valid=True,
        conditions_reachable=True,
        outcomes=["action.call_service"],
        unreachable_paths=[],
        verdict=Verdict.ALL_REACHABLE,
    )
    issues = outcome_report_to_issues(report)
    assert issues == []


def test_outcome_report_to_issues_unreachable():
    """Unreachable paths become ValidationIssue objects."""
    report = OutcomeReport(
        automation_id="automation.test",
        automation_name="Test Automation",
        triggers_valid=True,
        conditions_reachable=False,
        outcomes=["action.call_service"],
        unreachable_paths=["condition[0]: state requires 'home' but trigger sets 'away'"],
        verdict=Verdict.UNREACHABLE,
    )
    issues = outcome_report_to_issues(report)

    assert len(issues) == 1
    assert issues[0].automation_id == "automation.test"
    assert issues[0].automation_name == "Test Automation"
    assert issues[0].severity == Severity.WARNING
    assert issues[0].issue_type == IssueType.IMPOSSIBLE_CONDITION
    assert "condition[0]" in issues[0].location
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with "cannot import name 'outcome_report_to_issues'"

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/models.py` after the `OutcomeReport` class:

```python
def outcome_report_to_issues(report: OutcomeReport) -> list[ValidationIssue]:
    """Convert an OutcomeReport to a list of ValidationIssue objects."""
    if report.verdict == Verdict.ALL_REACHABLE:
        return []

    issues = []
    for path in report.unreachable_paths:
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                automation_id=report.automation_id,
                automation_name=report.automation_name,
                entity_id="",
                location=path,
                message=f"Unreachable outcome: {path}",
                issue_type=IssueType.IMPOSSIBLE_CONDITION,
            )
        )
    return issues
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/models.py tests/test_models.py
git commit -m "feat(models): add outcome_report_to_issues converter"
```

---

## Task 2: Update __init__.py for Separate Data Storage

**Files:**
- Modify: `custom_components/autodoctor/__init__.py`

**Step 1: Update hass.data storage structure**

In `async_setup_entry`, update the data dict (around line 165):

```python
hass.data[DOMAIN] = {
    "knowledge_base": knowledge_base,
    "analyzer": analyzer,
    "validator": validator,
    "simulator": simulator,
    "reporter": reporter,
    "fix_engine": fix_engine,
    "issues": [],  # Keep for backwards compatibility
    "validation_issues": [],
    "outcome_issues": [],
    "validation_last_run": None,
    "outcomes_last_run": None,
    "entry": entry,
    "debounce_task": None,
}
```

**Step 2: Update async_validate_all to store separately**

At end of `async_validate_all` (around line 300-303), add:

```python
hass.data[DOMAIN]["issues"] = all_issues  # Keep for backwards compatibility
hass.data[DOMAIN]["validation_issues"] = all_issues
hass.data[DOMAIN]["validation_last_run"] = datetime.now(timezone.utc).isoformat()
return all_issues
```

Add import at top of file:
```python
from datetime import datetime, timezone
```

**Step 3: Update async_simulate_all to store issues**

Replace `async_simulate_all` function:

```python
async def async_simulate_all(hass: HomeAssistant) -> list:
    """Simulate all automations and return issues."""
    from .models import outcome_report_to_issues

    data = hass.data.get(DOMAIN, {})
    simulator = data.get("simulator")

    if not simulator:
        return []

    automations = _get_automation_configs(hass)
    all_issues = []
    for automation in automations:
        report = simulator.verify_outcomes(automation)
        issues = outcome_report_to_issues(report)
        all_issues.extend(issues)

    hass.data[DOMAIN]["outcome_issues"] = all_issues
    hass.data[DOMAIN]["outcomes_last_run"] = datetime.now(timezone.utc).isoformat()
    return all_issues
```

**Step 4: Run existing tests**

Run: `pytest tests/ -v`
Expected: All existing tests pass

**Step 5: Commit**

```bash
git add custom_components/autodoctor/__init__.py
git commit -m "feat(init): store validation and outcome issues separately"
```

---

## Task 3: Add New WebSocket Endpoints

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py`
- Test: `tests/test_websocket_api.py`

**Step 1: Write failing tests**

Add to `tests/test_websocket_api.py`:

```python
async def test_websocket_get_validation(hass, hass_ws_client):
    """Test getting validation issues only."""
    hass.data[DOMAIN] = {
        "validation_issues": [],
        "validation_last_run": "2026-01-27T12:00:00+00:00",
        "fix_engine": None,
    }

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "autodoctor/validation"})
    response = await client.receive_json()

    assert response["success"]
    assert response["result"]["issues"] == []
    assert response["result"]["last_run"] == "2026-01-27T12:00:00+00:00"


async def test_websocket_get_outcomes(hass, hass_ws_client):
    """Test getting outcome issues only."""
    hass.data[DOMAIN] = {
        "outcome_issues": [],
        "outcomes_last_run": "2026-01-27T12:00:00+00:00",
        "fix_engine": None,
    }

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "autodoctor/outcomes"})
    response = await client.receive_json()

    assert response["success"]
    assert response["result"]["issues"] == []
    assert response["result"]["last_run"] == "2026-01-27T12:00:00+00:00"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_websocket_api.py -v -k "validation or outcomes"`
Expected: FAIL

**Step 3: Implement the endpoints**

Add to `custom_components/autodoctor/websocket_api.py`:

```python
async def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Set up WebSocket API."""
    websocket_api.async_register_command(hass, websocket_get_issues)
    websocket_api.async_register_command(hass, websocket_refresh)
    websocket_api.async_register_command(hass, websocket_get_validation)
    websocket_api.async_register_command(hass, websocket_run_validation)
    websocket_api.async_register_command(hass, websocket_get_outcomes)
    websocket_api.async_register_command(hass, websocket_run_outcomes)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/validation",
    }
)
@websocket_api.async_response
async def websocket_get_validation(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get validation issues only."""
    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")
    issues: list = data.get("validation_issues", [])
    last_run = data.get("validation_last_run")

    issues_with_fixes = _format_issues_with_fixes(issues, fix_engine)
    healthy_count = _get_healthy_count(hass, issues)

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
            "last_run": last_run,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/validation/run",
    }
)
@websocket_api.async_response
async def websocket_run_validation(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run validation and return results."""
    from . import async_validate_all

    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")

    issues = await async_validate_all(hass)
    issues_with_fixes = _format_issues_with_fixes(issues, fix_engine)
    healthy_count = _get_healthy_count(hass, issues)
    last_run = hass.data[DOMAIN].get("validation_last_run")

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
            "last_run": last_run,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/outcomes",
    }
)
@websocket_api.async_response
async def websocket_get_outcomes(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get outcome issues only."""
    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")
    issues: list = data.get("outcome_issues", [])
    last_run = data.get("outcomes_last_run")

    issues_with_fixes = _format_issues_with_fixes(issues, fix_engine)
    healthy_count = _get_healthy_count(hass, issues)

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
            "last_run": last_run,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/outcomes/run",
    }
)
@websocket_api.async_response
async def websocket_run_outcomes(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run outcome simulation and return results."""
    from . import async_simulate_all

    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")

    issues = await async_simulate_all(hass)
    issues_with_fixes = _format_issues_with_fixes(issues, fix_engine)
    healthy_count = _get_healthy_count(hass, issues)
    last_run = hass.data[DOMAIN].get("outcomes_last_run")

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
            "last_run": last_run,
        },
    )


def _format_issues_with_fixes(issues: list, fix_engine) -> list[dict]:
    """Format issues with fix suggestions."""
    issues_with_fixes = []
    for issue in issues:
        fix = fix_engine.suggest_fix(issue) if fix_engine else None
        automation_id = issue.automation_id.replace("automation.", "") if issue.automation_id else ""
        issues_with_fixes.append({
            "issue": issue.to_dict(),
            "fix": {
                "description": fix.description,
                "confidence": fix.confidence,
                "fix_value": fix.fix_value,
            } if fix else None,
            "edit_url": f"/config/automation/edit/{automation_id}",
        })
    return issues_with_fixes


def _get_healthy_count(hass: HomeAssistant, issues: list) -> int:
    """Calculate healthy automation count."""
    automation_data = hass.data.get("automation")
    total_automations = 0
    if automation_data:
        if hasattr(automation_data, "entities"):
            total_automations = len(list(automation_data.entities))
        elif isinstance(automation_data, dict):
            total_automations = len(automation_data.get("config", []))

    automations_with_issues = len(set(i.automation_id for i in issues))
    return max(0, total_automations - automations_with_issues)
```

**Step 4: Run tests**

Run: `pytest tests/test_websocket_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py tests/test_websocket_api.py
git commit -m "feat(websocket): add validation and outcomes endpoints"
```

---

## Task 4: Update TypeScript Types

**Files:**
- Modify: `www/autodoctor/types.ts`

**Step 1: Read current types**

Check current `types.ts` for existing interfaces.

**Step 2: Update types**

Add/update in `www/autodoctor/types.ts`:

```typescript
export type TabType = "validation" | "outcomes";

export interface AutodoctorTabData {
  issues: IssueWithFix[];
  healthy_count: number;
  last_run: string | null;
}
```

**Step 3: Commit**

```bash
git add www/autodoctor/types.ts
git commit -m "feat(types): add TabType and AutodoctorTabData interfaces"
```

---

## Task 5: Add Tab State and Navigation to Card

**Files:**
- Modify: `www/autodoctor/autodoctor-card.ts`

**Step 1: Add tab state properties**

Add after existing `@state()` declarations (around line 25):

```typescript
@state() private _activeTab: TabType = "validation";
@state() private _validationData: AutodoctorTabData | null = null;
@state() private _outcomesData: AutodoctorTabData | null = null;
@state() private _runningValidation = false;
@state() private _runningOutcomes = false;
```

Update imports at top:

```typescript
import type { AutodoctorCardConfig, IssueWithFix, ValidationIssue, TabType, AutodoctorTabData } from "./types";
```

**Step 2: Add tab switching method**

```typescript
private _switchTab(tab: TabType): void {
  this._activeTab = tab;

  // Fetch data if not loaded
  if (tab === "validation" && !this._validationData) {
    this._fetchValidation();
  } else if (tab === "outcomes" && !this._outcomesData) {
    this._fetchOutcomes();
  }
}
```

**Step 3: Add fetch methods for each tab**

```typescript
private async _fetchValidation(): Promise<void> {
  this._loading = true;
  try {
    this._validationData = await this.hass.callWS<AutodoctorTabData>({
      type: "autodoctor/validation",
    });
  } catch (err) {
    console.error("Failed to fetch validation data:", err);
    this._error = "Failed to load validation data";
  }
  this._loading = false;
}

private async _fetchOutcomes(): Promise<void> {
  this._loading = true;
  try {
    this._outcomesData = await this.hass.callWS<AutodoctorTabData>({
      type: "autodoctor/outcomes",
    });
  } catch (err) {
    console.error("Failed to fetch outcomes data:", err);
    this._error = "Failed to load outcomes data";
  }
  this._loading = false;
}

private async _runValidation(): Promise<void> {
  this._runningValidation = true;
  try {
    this._validationData = await this.hass.callWS<AutodoctorTabData>({
      type: "autodoctor/validation/run",
    });
  } catch (err) {
    console.error("Failed to run validation:", err);
  }
  this._runningValidation = false;
}

private async _runOutcomes(): Promise<void> {
  this._runningOutcomes = true;
  try {
    this._outcomesData = await this.hass.callWS<AutodoctorTabData>({
      type: "autodoctor/outcomes/run",
    });
  } catch (err) {
    console.error("Failed to run outcomes:", err);
  }
  this._runningOutcomes = false;
}
```

**Step 4: Update firstUpdated to fetch validation tab**

```typescript
protected async firstUpdated(): Promise<void> {
  await this._fetchValidation();
}
```

**Step 5: Commit**

```bash
git add www/autodoctor/autodoctor-card.ts
git commit -m "feat(card): add tab state and data fetching methods"
```

---

## Task 6: Add Tab Rendering to Card

**Files:**
- Modify: `www/autodoctor/autodoctor-card.ts`

**Step 1: Add tab bar rendering method**

```typescript
private _renderTabs(): TemplateResult {
  return html`
    <div class="tabs">
      <button
        class="tab ${this._activeTab === 'validation' ? 'active' : ''}"
        @click=${() => this._switchTab('validation')}
      >
        Validation
      </button>
      <button
        class="tab ${this._activeTab === 'outcomes' ? 'active' : ''}"
        @click=${() => this._switchTab('outcomes')}
      >
        Outcomes
      </button>
    </div>
  `;
}
```

**Step 2: Add tab-specific footer rendering**

```typescript
private _renderTabFooter(): TemplateResult {
  const isValidation = this._activeTab === "validation";
  const isRunning = isValidation ? this._runningValidation : this._runningOutcomes;
  const lastRun = isValidation
    ? this._validationData?.last_run
    : this._outcomesData?.last_run;

  const runHandler = isValidation ? this._runValidation : this._runOutcomes;
  const buttonText = isValidation ? "Run Validation" : "Run Outcomes";

  return html`
    <div class="footer">
      <button
        class="run-btn ${isRunning ? 'running' : ''}"
        @click=${runHandler}
        ?disabled=${isRunning}
      >
        <span class="run-icon" aria-hidden="true">${isRunning ? '↻' : '▶'}</span>
        <span class="run-text">${isRunning ? 'Running...' : buttonText}</span>
      </button>
      ${lastRun ? html`
        <span class="last-run">Last run: ${this._formatLastRun(lastRun)}</span>
      ` : nothing}
    </div>
  `;
}

private _formatLastRun(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}
```

**Step 3: Update main render method**

Update the `render()` method to use tabs:

```typescript
protected render(): TemplateResult {
  const title = this.config.title || "Autodoctor";

  if (this._loading) {
    return this._renderLoading(title);
  }

  if (this._error) {
    return this._renderError(title);
  }

  const data = this._activeTab === "validation"
    ? this._validationData
    : this._outcomesData;

  if (!data) {
    return this._renderEmpty(title);
  }

  const groups = this._groupIssuesByAutomation(data.issues);
  const counts = this._getCountsFromData(data);
  const hasIssues = data.issues.length > 0;

  return html`
    <ha-card>
      ${this._renderHeader(title)}
      ${this._renderTabs()}
      <div class="card-content">
        ${this._renderBadges(counts)}
        ${hasIssues
          ? groups.map((group) => this._renderAutomationGroup(group))
          : this._renderAllHealthy(counts.healthy)}
      </div>
      ${this._renderTabFooter()}
    </ha-card>
  `;
}

private _getCountsFromData(data: AutodoctorTabData): { errors: number; warnings: number; healthy: number } {
  let errors = 0;
  let warnings = 0;

  for (const item of data.issues) {
    if (item.issue.severity === "error") {
      errors++;
    } else {
      warnings++;
    }
  }

  return { errors, warnings, healthy: data.healthy_count };
}

private _renderBadges(counts: { errors: number; warnings: number; healthy: number }): TemplateResult {
  return html`
    <div class="badges-row">
      ${counts.errors > 0
        ? html`<span class="badge badge-error" title="${counts.errors} error${counts.errors !== 1 ? 's' : ''}">
            <span class="badge-icon" aria-hidden="true">✕</span>
            <span class="badge-count">${counts.errors}</span>
          </span>`
        : nothing}
      ${counts.warnings > 0
        ? html`<span class="badge badge-warning" title="${counts.warnings} warning${counts.warnings !== 1 ? 's' : ''}">
            <span class="badge-icon" aria-hidden="true">!</span>
            <span class="badge-count">${counts.warnings}</span>
          </span>`
        : nothing}
      <span class="badge badge-healthy" title="${counts.healthy} healthy">
        <span class="badge-icon" aria-hidden="true">✓</span>
        <span class="badge-count">${counts.healthy}</span>
      </span>
    </div>
  `;
}
```

**Step 4: Update header to remove badges (moved to content area)**

```typescript
private _renderHeader(title: string): TemplateResult {
  return html`
    <div class="header">
      <h2 class="title">${title}</h2>
      <button
        class="refresh-btn ${this._refreshing ? 'refreshing' : ''}"
        @click=${this._refreshCurrentTab}
        ?disabled=${this._refreshing}
        aria-label="Refresh"
      >
        <span class="refresh-icon" aria-hidden="true">↻</span>
      </button>
    </div>
  `;
}

private async _refreshCurrentTab(): Promise<void> {
  this._refreshing = true;
  if (this._activeTab === "validation") {
    await this._fetchValidation();
  } else {
    await this._fetchOutcomes();
  }
  this._refreshing = false;
}
```

**Step 5: Commit**

```bash
git add www/autodoctor/autodoctor-card.ts
git commit -m "feat(card): add tab rendering and navigation UI"
```

---

## Task 7: Add Tab Styles

**Files:**
- Modify: `www/autodoctor/autodoctor-card.ts` (styles section)

**Step 1: Add tab styles to the static styles**

Add to the `styles` getter:

```css
/* Tabs */
.tabs {
  display: flex;
  gap: 0;
  padding: 0 var(--autodoc-spacing-lg);
  border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
}

.tab {
  padding: var(--autodoc-spacing-md) var(--autodoc-spacing-lg);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--secondary-text-color);
  font-size: var(--autodoc-issue-size);
  font-family: var(--autodoc-font-family);
  cursor: pointer;
  transition: color var(--autodoc-transition-fast), border-color var(--autodoc-transition-fast);
}

.tab:hover {
  color: var(--primary-text-color);
}

.tab.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}

/* Badges row (in content area) */
.badges-row {
  display: flex;
  gap: var(--autodoc-spacing-sm);
  margin-bottom: var(--autodoc-spacing-md);
}

/* Run button */
.run-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--autodoc-spacing-sm);
  padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
  background: var(--primary-color);
  color: var(--text-primary-color, #fff);
  border: none;
  border-radius: 6px;
  font-size: var(--autodoc-issue-size);
  font-family: var(--autodoc-font-family);
  cursor: pointer;
  transition: opacity var(--autodoc-transition-fast);
}

.run-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.run-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.run-btn.running .run-icon {
  animation: rotate 1s linear infinite;
}

.run-icon {
  font-size: 0.9rem;
}

/* Last run timestamp */
.last-run {
  color: var(--secondary-text-color);
  font-size: var(--autodoc-meta-size);
  margin-left: auto;
}

/* Footer layout update */
.footer {
  display: flex;
  align-items: center;
  padding: var(--autodoc-spacing-md) var(--autodoc-spacing-lg);
  border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
}
```

**Step 2: Commit**

```bash
git add www/autodoctor/autodoctor-card.ts
git commit -m "feat(card): add tab and run button styles"
```

---

## Task 8: Build and Test Card

**Files:**
- Build: `www/autodoctor/autodoctor-card.js`

**Step 1: Build TypeScript**

Run: `cd www/autodoctor && npx tsc` (or project-specific build command)

**Step 2: Test in browser**

1. Copy built JS to Home Assistant
2. Hard refresh browser
3. Verify:
   - Tabs appear and switch correctly
   - Validation tab shows validation issues
   - Outcomes tab shows outcome issues
   - Run buttons trigger services
   - Last run timestamps update

**Step 3: Commit built files**

```bash
git add www/autodoctor/autodoctor-card.js
git commit -m "build: compile card with tab support"
```

---

## Task 9: Update Version and Final Testing

**Files:**
- Modify: `custom_components/autodoctor/const.py`

**Step 1: Bump version**

Update VERSION in `const.py`:

```python
VERSION = "1.1.0"
```

**Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 3: Final commit**

```bash
git add custom_components/autodoctor/const.py
git commit -m "chore: bump version to 1.1.0"
```

---

## Execution Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | OutcomeReport converter | models.py, test_models.py |
| 2 | Separate data storage | __init__.py |
| 3 | WebSocket endpoints | websocket_api.py, test_websocket_api.py |
| 4 | TypeScript types | types.ts |
| 5 | Tab state & fetching | autodoctor-card.ts |
| 6 | Tab rendering | autodoctor-card.ts |
| 7 | Tab styles | autodoctor-card.ts |
| 8 | Build & test | autodoctor-card.js |
| 9 | Version bump | const.py |
