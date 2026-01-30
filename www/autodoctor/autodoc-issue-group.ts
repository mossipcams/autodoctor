import { LitElement, html, TemplateResult, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

import { autodocTokens, issueGroupStyles } from "./styles.js";
import type { AutomationGroup, IssueWithFix, ValidationIssue } from "./types.js";

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

  static styles = [autodocTokens, issueGroupStyles];

  protected render(): TemplateResult {
    const group = this.group;

    return html`
      <div class="automation-group ${group.has_error ? "has-error" : "has-warning"}">
        <div class="automation-header">
          <span class="automation-severity-icon" aria-hidden="true"
            >${group.has_error ? "\u2715" : "!"}</span
          >
          <span class="automation-name">${group.automation_name}</span>
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
    const isDismissed = this.dismissedKeys.has(this._getSuggestionKey(issue));

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
            \u2298
          </button>
        </div>
        ${fix && !isDismissed
          ? html`
              <div class="fix-suggestion">
                <span class="fix-icon" aria-hidden="true">\uD83D\uDCA1</span>
                <div class="fix-content">
                  <span class="fix-description">${fix.description}</span>
                  ${this._renderConfidencePill(fix.confidence)}
                </div>
                <button
                  class="dismiss-btn"
                  @click=${() => this._dispatchDismiss(issue)}
                  aria-label="Dismiss suggestion"
                >
                  \u2715
                </button>
              </div>
            `
          : nothing}
      </div>
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

  private _getSuggestionKey(issue: ValidationIssue): string {
    return `${issue.automation_id}:${issue.entity_id}:${issue.message}`;
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
}

declare global {
  interface HTMLElementTagNameMap {
    "autodoc-issue-group": AutodocIssueGroup;
  }
}
