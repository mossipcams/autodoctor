import { LitElement, html, CSSResultGroup, TemplateResult, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import { autodocTokens, issueGroupStyles } from "./styles.js";
import {
  getSuggestionKey,
  type AutomationGroup,
  type FixSuggestion,
  type IssueWithFix,
  type ValidationIssue,
} from "./types.js";

/**
 * Renders a single automation group with its issues, fix suggestions,
 * confidence pills, and action buttons (suppress/dismiss).
 *
 * Data flows DOWN via properties; actions flow UP via CustomEvents.
 */
@customElement("autodoc-issue-group")
export class AutodocIssueGroup extends LitElement {
  @property({ attribute: false }) group!: AutomationGroup;
  @property({ attribute: false }) dismissedKeys: Set<string> = new Set();

  static styles: CSSResultGroup = [autodocTokens, issueGroupStyles];

  protected render(): TemplateResult {
    const group = this.group;

    return html`
      <div class="automation-group ${group.has_error ? "has-error" : "has-warning"}">
        <div class="automation-header">
          <span class="automation-severity-icon" aria-hidden="true"
            >${group.has_error ? "\u2715" : "!"}</span
          >
          <span class="automation-name" title="${group.automation_name}">${group.automation_name}</span>
          <span class="automation-badge">${group.issues.length}</span>
        </div>
        <div class="automation-issues">
          ${group.issues.map((item) => this._renderIssue(item))}
        </div>
        <a href="${group.edit_url}" class="edit-link" aria-label="Edit ${group.automation_name}">
          <span class="edit-text">Edit automation</span>
          <span class="edit-arrow" aria-hidden="true">\u2192</span>
        </a>
      </div>
    `;
  }

  private _renderIssue(item: IssueWithFix): TemplateResult {
    const { issue, fix } = item;
    const isError = issue.severity === "error";
    const isDismissed = this.dismissedKeys.has(getSuggestionKey(issue));

    return html`
      <div class="issue ${isError ? "error" : "warning"}">
        <div class="issue-header">
          <span class="issue-icon" aria-hidden="true">${isError ? "\u2715" : "!"}</span>
          <span class="issue-message">${issue.message}</span>
          <button
            class="suppress-btn"
            @click=${() => this._dispatchSuppress(issue)}
            aria-label="Suppress this issue"
            title="Don't show this issue again"
          >
            <span aria-hidden="true">\u2298</span><span class="suppress-label">Suppress</span>
          </button>
        </div>
        ${fix && !isDismissed
          ? html`
              <div class="fix-suggestion">
                <ha-icon class="fix-icon" icon="mdi:lightbulb-on-outline" style="--mdc-icon-size: 16px; color: var(--primary-color);" aria-hidden="true"></ha-icon>
                <div class="fix-content">
                  <span class="fix-description">${fix.description}</span>
                  ${this._renderFixReplacement(fix)}
                  ${fix.reason ? html`<span class="fix-reason">${fix.reason}</span>` : nothing}
                  ${this._renderConfidencePill(fix.confidence)}
                </div>
                <div class="fix-actions">
                  ${fix.suggested_value || fix.fix_value
                    ? html`
                        <button
                          class="copy-fix-btn"
                          @click=${() => this._copyFixValue(fix)}
                          aria-label="Copy suggested value"
                        >
                          Copy
                        </button>
                      `
                    : nothing}
                  ${this._canApplyFix(issue, fix)
                    ? html`
                        <button
                          class="apply-fix-btn"
                          @click=${() => this._dispatchApply(issue, fix)}
                          aria-label="Apply suggestion"
                        >
                          Apply
                        </button>
                      `
                    : nothing}
                </div>
                <button
                  class="dismiss-btn"
                  @click=${() => this._dispatchDismiss(issue)}
                  aria-label="Dismiss suggestion"
                >
                  <span aria-hidden="true">\u2715</span><span class="dismiss-label">Dismiss</span>
                </button>
              </div>
            `
          : nothing}
      </div>
    `;
  }

  private _renderFixReplacement(fix: FixSuggestion): TemplateResult | typeof nothing {
    if (
      fix.fix_type !== "replace_value" ||
      !fix.current_value ||
      !(fix.suggested_value || fix.fix_value)
    ) {
      return nothing;
    }

    const suggested = fix.suggested_value || fix.fix_value || "";
    return html`
      <span class="fix-replacement">
        <code class="fix-before">${fix.current_value}</code>
        <span class="fix-arrow" aria-hidden="true">\u2192</span>
        <code class="fix-after">${suggested}</code>
      </span>
    `;
  }

  private _renderConfidencePill(confidence: number): TemplateResult | typeof nothing {
    if (confidence <= 0.6) {
      return nothing;
    }

    const isHigh = confidence > 0.9;
    return html`
      <span class="confidence-pill ${isHigh ? "high" : "medium"}">
        ${isHigh ? "High" : "Medium"} confidence
      </span>
    `;
  }

  private _dispatchSuppress(issue: ValidationIssue): void {
    this.dispatchEvent(
      new CustomEvent("suppress-issue", {
        detail: { issue },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _dispatchDismiss(issue: ValidationIssue): void {
    this.dispatchEvent(
      new CustomEvent("dismiss-suggestion", {
        detail: { issue },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _canApplyFix(issue: ValidationIssue, fix: FixSuggestion): boolean {
    return (
      fix.fix_type === "replace_value" &&
      !!fix.suggested_value &&
      !!issue.location &&
      confidenceAtLeast(fix.confidence, 0.8)
    );
  }

  private async _copyFixValue(fix: FixSuggestion): Promise<void> {
    const value = fix.suggested_value || fix.fix_value;
    if (!value || !navigator.clipboard?.writeText) {
      return;
    }
    await navigator.clipboard.writeText(value);
    this.dispatchEvent(
      new CustomEvent("fix-copied", {
        detail: { value },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _dispatchApply(issue: ValidationIssue, fix: FixSuggestion): void {
    this.dispatchEvent(
      new CustomEvent("apply-fix", {
        detail: { issue, fix },
        bubbles: true,
        composed: true,
      })
    );
  }
}

function confidenceAtLeast(actual: number, min: number): boolean {
  return typeof actual === "number" && actual >= min;
}

declare global {
  interface HTMLElementTagNameMap {
    "autodoc-issue-group": AutodocIssueGroup;
  }
}
