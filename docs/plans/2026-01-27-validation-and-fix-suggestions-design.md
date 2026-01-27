# Autodoctor: Validation Improvements and Fix Suggestions

## Overview

Two new validation rules plus a Lovelace card that surfaces issues with actionable fix suggestions.

### New Validation Rules

1. **Entity Removal Detection** - When an automation references an entity that doesn't exist, check recorder history to determine if it existed before (removed/renamed vs. typo)

2. **Impossible Trigger→Condition Detection** - Surface existing simulator logic through the validation pipeline to catch automations where trigger and condition states are mutually exclusive

### Proactive Feature

3. **Autodoctor Card** - TypeScript Lovelace card showing automation issues with suggested fixes and deep links to the automation editor

## Entity Removal Detection

### Problem

Current validation catches "entity doesn't exist" but can't distinguish between:
- Typo in entity ID (never existed)
- Entity was removed or renamed (existed before)

### Solution

Query recorder history for entity IDs that existed in the past but don't exist now.

### Implementation

**knowledge_base.py** - Add method to query historical entity IDs:

```python
async def get_historical_entity_ids(self) -> set[str]:
    """Get entity IDs that have existed in recorder history."""
    # Query recorder for distinct entity_ids from states table
    # Return set of all entity_ids that have ever had state recorded
```

**validator.py** - Check entity history when entity not found:

```python
def _check_entity_history(self, entity_id: str) -> ValidationIssue | None:
    """Check if missing entity existed in history."""
    if entity_id in self.knowledge_base.get_historical_entity_ids():
        # Entity existed before - was removed or renamed
        similar = self._find_similar_entities(entity_id)
        return ValidationIssue(
            type=IssueType.ENTITY_REMOVED,
            severity=Severity.ERROR,
            entity_id=entity_id,
            message="Entity existed in history but is now missing",
            suggested_fix=f"Similar entity: {similar}" if similar else None,
        )
    return None
```

### Edge Cases

- Entity renamed multiple times: suggest the current/final name
- Entity deleted entirely (not renamed): indicate removal, no suggestion
- Integration not loaded: entity may return once integration loads (lower confidence)

## Impossible Trigger→Condition Detection

### Problem

Automations can have triggers and conditions that are mutually exclusive:

```yaml
trigger:
  - platform: state
    entity_id: person.matt
    to: "home"
condition:
  - condition: state
    entity_id: person.matt
    state: "not_home"  # Can never be true when trigger fires
```

### Solution

The simulator already detects this in `_verify_conditions()`. Surface these findings through the validation pipeline.

### Implementation

**analyzer.py** - Add cross-reference logic:

```python
def check_trigger_condition_compatibility(
    self, automation: dict
) -> list[ValidationIssue]:
    """Check if triggers and conditions are compatible."""
    triggers = automation.get("trigger", automation.get("triggers", []))
    conditions = automation.get("condition", [])

    issues = []
    trigger_states = self._extract_trigger_states(triggers)

    for condition in conditions:
        if condition.get("condition") == "state":
            entity_id = condition.get("entity_id")
            required_state = condition.get("state")

            if entity_id in trigger_states:
                trigger_to = trigger_states[entity_id]
                if not self._states_compatible(trigger_to, required_state):
                    issues.append(ValidationIssue(
                        type=IssueType.IMPOSSIBLE_CONDITION,
                        severity=Severity.ERROR,
                        entity_id=entity_id,
                        message=f"Condition requires '{required_state}' but trigger fires on '{trigger_to}'",
                        suggested_fix=f"Change condition state to '{trigger_to}'",
                    ))
    return issues
```

### Detection Rules

| Trigger | Condition | Verdict |
|---------|-----------|---------|
| `person.matt` → `home` | `person.matt` == `home` | OK |
| `person.matt` → `home` | `person.matt` == `not_home` | Impossible |
| `person.matt` → `home` | `person.matt` in [`home`, `away`] | OK |
| `light.kitchen` → `on` | `light.kitchen` == `off` | Impossible |

### Edge Cases

- Trigger has no `to` state (fires on any change): skip check
- Condition uses `state_attr()` instead of state: skip (different check)
- Multiple triggers or conditions: check all combinations
- Template conditions: skip (too complex to analyze statically)

## Fix Suggestions

### Approach

Generate actionable fix suggestions with confidence scores.

### Fix Types

**Entity was removed/renamed:**
```
1. Query recorder for historical entity IDs
2. If missing entity existed in history → "Entity was removed or renamed"
3. Fuzzy match against current entities (Levenshtein distance)
4. Suggest closest match: "sensor.living_room_temp" → "sensor.lr_temperature"
```

**Impossible trigger→condition:**
```
1. Detect trigger "to" state conflicts with condition required state
2. Suggest changing condition to match trigger state
3. Use state frequency from recorder to guess user intent if ambiguous
```

**Invalid state value:**
```
1. State "away" not valid for person domain
2. Query knowledge base for valid states: ["home", "not_home"]
3. Fuzzy match: "away" → "not_home" (semantic similarity)
4. Suggest: "Did you mean 'not_home'?"
```

### Confidence Scoring

| Confidence | Threshold | Behavior |
|------------|-----------|----------|
| High | >90% | Show fix with high confidence indicator |
| Medium | 60-90% | Show suggestion, indicate uncertainty |
| Low | <60% | Show "Check manually" without specific suggestion |

### Implementation

**fix_engine.py** - New file:

```python
@dataclass
class FixSuggestion:
    """A suggested fix for a validation issue."""
    description: str
    confidence: float  # 0.0 - 1.0
    fix_value: str | None  # The corrected value
    field_path: str | None  # Where to apply the fix

class FixEngine:
    """Generates fix suggestions for validation issues."""

    def __init__(self, hass: HomeAssistant, knowledge_base: StateKnowledgeBase):
        self.hass = hass
        self.knowledge_base = knowledge_base

    def suggest_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Generate a fix suggestion for an issue."""
        if issue.type == IssueType.ENTITY_NOT_FOUND:
            return self._suggest_entity_fix(issue)
        elif issue.type == IssueType.ENTITY_REMOVED:
            return self._suggest_renamed_entity_fix(issue)
        elif issue.type == IssueType.INVALID_STATE:
            return self._suggest_state_fix(issue)
        elif issue.type == IssueType.IMPOSSIBLE_CONDITION:
            return self._suggest_condition_fix(issue)
        return None

    def _suggest_entity_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for missing entity (typo)."""
        similar = self._find_similar_entities(issue.entity_id)
        if similar:
            return FixSuggestion(
                description=f"Did you mean '{similar}'?",
                confidence=self._calculate_similarity(issue.entity_id, similar),
                fix_value=similar,
                field_path="entity_id",
            )
        return None

    def _find_similar_entities(self, entity_id: str) -> str | None:
        """Find similar entity IDs using fuzzy matching."""
        # Use Levenshtein distance against all current entity IDs
        # Return closest match above threshold
```

## Autodoctor Card

### Purpose

Lovelace card that surfaces validation issues with actionable fixes.

### User Interface

```
+---------------------------------------------+
| Automation Health                           |
+---------------------------------------------+
| 3 issues found                              |
+---------------------------------------------+
| X  Welcome Home                             |
|    Condition can never pass                 |
|    -> Trigger fires on "home" but           |
|       condition requires "not_home"         |
|    Suggested fix: Change condition to "home"|
|                                      [Edit] |
+---------------------------------------------+
| !  Temperature Alert                        |
|    Entity was removed                       |
|    -> sensor.living_room_temp not found     |
|    Similar entity: sensor.lr_temperature    |
|                                      [Edit] |
+---------------------------------------------+
| OK 47 automations healthy                   |
+---------------------------------------------+
```

### Architecture

```
+----------------------+     +---------------------+
|  Lovelace Card       |---->|  autodoctor API     |
|  (TypeScript)        |<----|  (WebSocket)        |
+----------------------+     +---------------------+
                                      |
                              +-------v-------+
                              | Validation +   |
                              | Fix Engine     |
                              +---------------+
```

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `autodoctor-card.ts` | `www/autodoctor/` | Lovelace card frontend |
| `types.ts` | `www/autodoctor/` | TypeScript interfaces |
| `styles.ts` | `www/autodoctor/` | Card styling |
| `websocket_api.py` | `custom_components/autodoctor/` | Expose issues/fixes via WebSocket |
| `fix_engine.py` | `custom_components/autodoctor/` | Generate fix suggestions |

### WebSocket API

**websocket_api.py:**

```python
from homeassistant.components import websocket_api

async def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Set up WebSocket API."""
    websocket_api.async_register_command(hass, websocket_get_issues)

@websocket_api.websocket_command({
    vol.Required("type"): "autodoctor/issues",
})
@websocket_api.async_response
async def websocket_get_issues(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get current issues with fix suggestions."""
    data = hass.data.get(DOMAIN, {})
    validator = data.get("validator")
    fix_engine = data.get("fix_engine")

    issues = await get_all_issues(hass)
    issues_with_fixes = [
        {
            "issue": issue.to_dict(),
            "fix": fix_engine.suggest_fix(issue),
            "edit_url": f"/config/automation/edit/{issue.automation_id}",
        }
        for issue in issues
    ]

    connection.send_result(msg["id"], {
        "issues": issues_with_fixes,
        "healthy_count": get_healthy_automation_count(hass),
    })
```

### Card Implementation

**autodoctor-card.ts:**

```typescript
import { LitElement, html, css, PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

interface ValidationIssue {
  type: string;
  severity: string;
  entity_id: string;
  message: string;
  automation_id: string;
  automation_name: string;
}

interface FixSuggestion {
  description: string;
  confidence: number;
  fix_value: string | null;
}

interface IssueWithFix {
  issue: ValidationIssue;
  fix: FixSuggestion | null;
  edit_url: string;
}

interface AutodoctorData {
  issues: IssueWithFix[];
  healthy_count: number;
}

@customElement("autodoctor-card")
export class AutodoctorCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _data: AutodoctorData | null = null;
  @state() private _loading = true;

  protected async firstUpdated(): Promise<void> {
    await this._fetchData();
  }

  private async _fetchData(): Promise<void> {
    this._loading = true;
    try {
      this._data = await this.hass.callWS({ type: "autodoctor/issues" });
    } catch (err) {
      console.error("Failed to fetch autodoctor data:", err);
    }
    this._loading = false;
  }

  protected render() {
    if (this._loading) {
      return html`<ha-card><div class="loading">Loading...</div></ha-card>`;
    }

    if (!this._data) {
      return html`<ha-card><div class="error">Failed to load</div></ha-card>`;
    }

    return html`
      <ha-card header="Automation Health">
        <div class="card-content">
          ${this._data.issues.length > 0
            ? html`
                <div class="issue-count">
                  ${this._data.issues.length} issue${this._data.issues.length > 1 ? "s" : ""} found
                </div>
                ${this._data.issues.map((item) => this._renderIssue(item))}
              `
            : ""}
          <div class="healthy">
            ${this._data.healthy_count} automation${this._data.healthy_count !== 1 ? "s" : ""} healthy
          </div>
        </div>
      </ha-card>
    `;
  }

  private _renderIssue(item: IssueWithFix) {
    const { issue, fix, edit_url } = item;
    return html`
      <div class="issue ${issue.severity.toLowerCase()}">
        <div class="issue-header">
          <span class="severity-icon">${issue.severity === "ERROR" ? "X" : "!"}</span>
          <span class="automation-name">${issue.automation_name}</span>
        </div>
        <div class="issue-message">${issue.message}</div>
        ${fix
          ? html`
              <div class="fix-suggestion">
                Suggested fix: ${fix.description}
                ${fix.confidence > 0.9 ? html`<span class="confidence high">High confidence</span>` : ""}
              </div>
            `
          : ""}
        <a href="${edit_url}" class="edit-link">Edit</a>
      </div>
    `;
  }

  static styles = css`
    .card-content {
      padding: 16px;
    }
    .issue-count {
      font-weight: bold;
      margin-bottom: 16px;
    }
    .issue {
      border-left: 4px solid var(--error-color);
      padding: 12px;
      margin-bottom: 12px;
      background: var(--secondary-background-color);
    }
    .issue.warning {
      border-left-color: var(--warning-color);
    }
    .issue-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: bold;
    }
    .severity-icon {
      color: var(--error-color);
    }
    .issue.warning .severity-icon {
      color: var(--warning-color);
    }
    .issue-message {
      margin: 8px 0;
      color: var(--secondary-text-color);
    }
    .fix-suggestion {
      margin: 8px 0;
      padding: 8px;
      background: var(--primary-background-color);
      border-radius: 4px;
    }
    .confidence.high {
      color: var(--success-color);
      font-size: 0.9em;
    }
    .edit-link {
      display: inline-block;
      margin-top: 8px;
      color: var(--primary-color);
    }
    .healthy {
      color: var(--success-color);
      margin-top: 16px;
    }
    .loading, .error {
      padding: 16px;
      text-align: center;
    }
  `;
}
```

### Deep Linking

The [Edit] button links to HA's automation editor:

```
/config/automation/edit/{automation_id}
```

URL structure needs validation during implementation. The automation ID may be:
- The entity ID suffix (e.g., `welcome_home` from `automation.welcome_home`)
- An internal UUID

## File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `custom_components/autodoctor/fix_engine.py` | Generate fix suggestions with confidence |
| `custom_components/autodoctor/websocket_api.py` | Expose issues/fixes to frontend |
| `www/autodoctor/autodoctor-card.ts` | Lovelace card (TypeScript) |
| `www/autodoctor/types.ts` | TypeScript interfaces |
| `www/autodoctor/styles.ts` | Card styling (if separated) |

### Modified Files

| File | Changes |
|------|---------|
| `custom_components/autodoctor/__init__.py` | Register WebSocket API, initialize FixEngine |
| `custom_components/autodoctor/models.py` | Add `suggested_fix`, `confidence` to ValidationIssue; add new IssueTypes |
| `custom_components/autodoctor/validator.py` | Add entity history check |
| `custom_components/autodoctor/analyzer.py` | Add trigger/condition compatibility check |
| `custom_components/autodoctor/knowledge_base.py` | Add `get_historical_entity_ids()` |

## Models

### Updated ValidationIssue

```python
@dataclass
class ValidationIssue:
    type: IssueType
    severity: Severity
    entity_id: str
    message: str
    automation_id: str | None = None
    automation_name: str | None = None
    suggested_fix: str | None = None
    fix_confidence: float | None = None
    context: dict[str, Any] | None = None
```

### New IssueTypes

```python
class IssueType(Enum):
    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_REMOVED = "entity_removed"  # NEW: existed in history
    INVALID_STATE = "invalid_state"
    IMPOSSIBLE_CONDITION = "impossible_condition"  # NEW
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"
```

## v1 Scope

### Included

- Entity removal detection via recorder history
- Impossible trigger→condition detection
- Fix suggestions with confidence scores
- Autodoctor card with issue display
- Deep links to automation editor
- User applies fixes manually in HA UI

### Excluded (Future)

- Auto-apply fixes (modify automation storage directly)
- Scenario builder (test multiple state changes)
- Unused automation detection
- Integration with HA repairs system for one-click fixes
