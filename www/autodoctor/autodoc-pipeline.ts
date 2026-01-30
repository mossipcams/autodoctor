import { LitElement, html, CSSResultGroup, TemplateResult, nothing, PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { autodocTokens, pipelineStyles } from "./styles.js";
import type { ValidationGroup } from "./types.js";

/** How long the accent highlight stays on each group (ms). */
const ACTIVE_DURATION_MS = 300;

/** Gap between one group resolving and the next group highlighting (ms). */
const INTER_GROUP_DELAY_MS = 100;

@customElement("autodoc-pipeline")
export class AutodocPipeline extends LitElement {
  @property({ attribute: false }) groups: ValidationGroup[] = [];
  @property({ type: Boolean }) running = false;

  /** Per-group display state: "neutral", "active", "pass", "warning", or "fail". */
  @state() private _displayStates: string[] = [];

  /** Controls summary rollup visibility. */
  @state() private _showSummary = false;

  /** Monotonically increasing ID for abort guard. */
  private _staggerRunId = 0;

  static styles: CSSResultGroup = [autodocTokens, pipelineStyles];

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    // Cancel any pending stagger by invalidating the current run ID
    this._staggerRunId++;
  }

  protected override updated(changedProps: PropertyValues): void {
    super.updated(changedProps);

    if (changedProps.has("running")) {
      const prevRunning = changedProps.get("running") as boolean | undefined;

      if (this.running) {
        // Validation just started: reset to neutral, hide summary
        this._displayStates = this.groups.map(() => "neutral");
        this._showSummary = false;
      } else if (prevRunning === true && !this.running && this.groups.length > 0) {
        // Validation just finished: start stagger sequence
        this._startStagger();
      }
    }
  }

  private async _startStagger(): Promise<void> {
    const runId = ++this._staggerRunId;

    // Reduced motion: skip animation entirely, show all results at once
    if (this._prefersReducedMotion()) {
      this._displayStates = this.groups.map((g) => g.status);
      this._showSummary = true;
      return;
    }

    // Initialize all groups to neutral
    this._displayStates = this.groups.map(() => "neutral");
    this._showSummary = false;

    for (let i = 0; i < this.groups.length; i++) {
      // Abort guard: another stagger started or component disconnected
      if (this._staggerRunId !== runId) return;

      // Highlight current group
      this._displayStates = [...this._displayStates];
      this._displayStates[i] = "active";
      this.requestUpdate();

      await this._delay(ACTIVE_DURATION_MS);

      // Abort guard after delay
      if (this._staggerRunId !== runId) return;

      // Resolve current group to its final status
      this._displayStates = [...this._displayStates];
      this._displayStates[i] = this.groups[i].status;

      // Show summary simultaneously with last group resolving
      if (i === this.groups.length - 1) {
        this._showSummary = true;
      }

      this.requestUpdate();

      // Inter-group delay (skip after last group)
      if (i < this.groups.length - 1) {
        await this._delay(INTER_GROUP_DELAY_MS);
      }
    }
  }

  private _delay(ms: number): Promise<void> {
    return new Promise<void>((resolve) => setTimeout(resolve, ms));
  }

  private _prefersReducedMotion(): boolean {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  protected render(): TemplateResult {
    return html`
      <div class="pipeline" role="region" aria-label="Validation pipeline">
        ${this.groups.map((group, i) => this._renderGroup(group, i))}
        ${this._showSummary
          ? this._renderSummary()
          : nothing}
      </div>
    `;
  }

  private _renderGroup(group: ValidationGroup, index: number): TemplateResult {
    const displayState = this._displayStates[index] ?? group.status;
    const isResult = displayState !== "neutral" && displayState !== "active";

    return html`
      <div class="pipeline-group ${displayState}">
        <div class="group-header">
          <div class="group-status-icon" aria-hidden="true">
            ${displayState === "active"
              ? html`<span class="active-dot"></span>`
              : isResult
                ? this._statusIcon(displayState)
                : nothing}
          </div>
          <span class="group-label">${group.label}</span>
          ${isResult ? this._renderCounts(group) : nothing}
        </div>
      </div>
    `;
  }

  private _statusIcon(status: string): TemplateResult {
    const icons: Record<string, string> = {
      pass: "\u2713",
      warning: "!",
      fail: "\u2715",
    };
    return html`<span>${icons[status] || "?"}</span>`;
  }

  private _renderCounts(group: ValidationGroup): TemplateResult {
    if (group.issue_count === 0) {
      return html`<span class="group-count pass-text">No issues</span>`;
    }
    const parts: string[] = [];
    if (group.error_count > 0) {
      parts.push(`${group.error_count} error${group.error_count !== 1 ? "s" : ""}`);
    }
    if (group.warning_count > 0) {
      parts.push(`${group.warning_count} warning${group.warning_count !== 1 ? "s" : ""}`);
    }
    return html`<span class="group-count ${group.status}-text">${parts.join(", ")}</span>`;
  }

  private _getOverallStatus(): "pass" | "warning" | "fail" {
    if (this.groups.some((g) => g.status === "fail")) return "fail";
    if (this.groups.some((g) => g.status === "warning")) return "warning";
    return "pass";
  }

  private _renderSummary(): TemplateResult {
    const status = this._getOverallStatus();
    const totalErrors = this.groups.reduce((sum, g) => sum + g.error_count, 0);
    const totalWarnings = this.groups.reduce((sum, g) => sum + g.warning_count, 0);

    const messages: Record<string, string> = {
      pass: "All checks passed",
      warning: `${totalWarnings} warning${totalWarnings !== 1 ? "s" : ""} found`,
      fail: `${totalErrors} error${totalErrors !== 1 ? "s" : ""}${totalWarnings > 0 ? `, ${totalWarnings} warning${totalWarnings !== 1 ? "s" : ""}` : ""} found`,
    };

    return html`
      <div
        class="pipeline-summary ${status}"
        role="status"
      >
        <span class="summary-icon" aria-hidden="true">${this._statusIcon(status)}</span>
        <span class="summary-text">${messages[status]}</span>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "autodoc-pipeline": AutodocPipeline;
  }
}
