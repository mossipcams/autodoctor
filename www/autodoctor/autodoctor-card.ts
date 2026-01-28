import { LitElement, html, css, CSSResultGroup, TemplateResult, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import type { AutodoctorCardConfig, IssueWithFix, ValidationIssue, TabType, AutodoctorTabData, ConflictsTabData, Conflict } from "./types";

interface AutomationGroup {
  automation_id: string;
  automation_name: string;
  issues: IssueWithFix[];
  edit_url: string;
  has_error: boolean;
  error_count: number;
  warning_count: number;
}

@customElement("autodoctor-card")
export class AutodoctorCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config!: AutodoctorCardConfig;

  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _activeTab: TabType = "validation";
  @state() private _validationData: AutodoctorTabData | null = null;
  @state() private _outcomesData: AutodoctorTabData | null = null;
  @state() private _conflictsData: ConflictsTabData | null = null;
  @state() private _runningValidation = false;
  @state() private _runningOutcomes = false;
  @state() private _runningConflicts = false;
  @state() private _isRefreshing = false;
  @state() private _dismissedSuggestions = new Set<string>();

  public setConfig(config: AutodoctorCardConfig): void {
    this.config = config;
  }

  public static getStubConfig(): AutodoctorCardConfig {
    return {
      type: "custom:autodoctor-card",
    };
  }

  public static async getConfigElement(): Promise<HTMLElement> {
    await import("./autodoctor-card-editor");
    return document.createElement("autodoctor-card-editor");
  }

  protected async firstUpdated(): Promise<void> {
    await this._fetchValidation();
  }

  private _switchTab(tab: TabType): void {
    this._activeTab = tab;

    // Fetch data if not loaded
    if (tab === "validation" && !this._validationData) {
      this._fetchValidation();
    } else if (tab === "outcomes" && !this._outcomesData) {
      this._fetchOutcomes();
    } else if (tab === "conflicts" && !this._conflictsData) {
      this._fetchConflicts();
    }
  }

  private async _fetchValidation(): Promise<void> {
    this._loading = true;
    try {
      this._error = null;
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
      this._error = null;
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

  private async _fetchConflicts(): Promise<void> {
    this._loading = true;
    try {
      this._error = null;
      this._conflictsData = await this.hass.callWS<ConflictsTabData>({
        type: "autodoctor/conflicts",
      });
    } catch (err) {
      console.error("Failed to fetch conflicts data:", err);
      this._error = "Failed to load conflicts data";
    }
    this._loading = false;
  }

  private async _runConflicts(): Promise<void> {
    this._runningConflicts = true;
    try {
      this._conflictsData = await this.hass.callWS<ConflictsTabData>({
        type: "autodoctor/conflicts/run",
      });
    } catch (err) {
      console.error("Failed to run conflict detection:", err);
    }
    this._runningConflicts = false;
  }

  private async _refreshCurrentTab(): Promise<void> {
    this._isRefreshing = true;
    if (this._activeTab === "validation") {
      await this._fetchValidation();
    } else if (this._activeTab === "outcomes") {
      await this._fetchOutcomes();
    } else {
      await this._fetchConflicts();
    }
    this._isRefreshing = false;
  }

  private _groupIssuesByAutomation(issues: IssueWithFix[]): AutomationGroup[] {
    const groups = new Map<string, AutomationGroup>();

    for (const item of issues) {
      const { issue, edit_url } = item;
      const key = issue.automation_id;

      if (!groups.has(key)) {
        groups.set(key, {
          automation_id: issue.automation_id,
          automation_name: issue.automation_name,
          issues: [],
          edit_url,
          has_error: false,
          error_count: 0,
          warning_count: 0,
        });
      }

      const group = groups.get(key)!;
      group.issues.push(item);
      if (issue.severity === "error") {
        group.has_error = true;
        group.error_count++;
      } else {
        group.warning_count++;
      }
    }

    return Array.from(groups.values());
  }

  private _getCounts(data: AutodoctorTabData | null): { errors: number; warnings: number; healthy: number; suppressed: number } {
    if (!data) {
      return { errors: 0, warnings: 0, healthy: 0, suppressed: 0 };
    }

    let errors = 0;
    let warnings = 0;

    for (const item of data.issues) {
      if (item.issue.severity === "error") {
        errors++;
      } else {
        warnings++;
      }
    }

    return { errors, warnings, healthy: data.healthy_count, suppressed: data.suppressed_count || 0 };
  }

  protected render(): TemplateResult {
    const title = this.config.title || "Autodoctor";

    if (this._loading) {
      return this._renderLoading(title);
    }

    if (this._error) {
      return this._renderError(title);
    }

    // Handle conflicts tab separately since it has different data structure
    if (this._activeTab === "conflicts") {
      return this._renderConflictsTab(title);
    }

    const data = this._activeTab === "validation"
      ? this._validationData
      : this._outcomesData;

    if (!data) {
      return this._renderEmpty(title);
    }

    const groups = this._groupIssuesByAutomation(data.issues);
    const counts = this._getCounts(data);
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

  private _renderLoading(title: string): TemplateResult {
    return html`
      <ha-card>
        <div class="header">
          <h2 class="title">${title}</h2>
        </div>
        <div class="card-content loading-state">
          <div class="spinner" aria-label="Loading"></div>
          <span class="loading-text">Checking automations...</span>
        </div>
      </ha-card>
    `;
  }

  private _renderError(title: string): TemplateResult {
    return html`
      <ha-card>
        <div class="header">
          <h2 class="title">${title}</h2>
        </div>
        <div class="card-content error-state">
          <div class="error-icon" aria-hidden="true">⚠</div>
          <span class="error-text">${this._error}</span>
          <button class="retry-btn" @click=${this._refreshCurrentTab}>
            Try again
          </button>
        </div>
      </ha-card>
    `;
  }

  private _renderEmpty(title: string): TemplateResult {
    return html`
      <ha-card>
        ${this._renderHeader(title)}
        ${this._renderTabs()}
        <div class="card-content empty-state">
          <span class="empty-text">No data available</span>
        </div>
      </ha-card>
    `;
  }

  private _renderHeader(title: string): TemplateResult {
    return html`
      <div class="header">
        <h2 class="title">${title}</h2>
        <button
          class="refresh-btn ${this._isRefreshing ? 'refreshing' : ''}"
          @click=${this._refreshCurrentTab}
          ?disabled=${this._isRefreshing}
          aria-label="Refresh"
        >
          <span class="refresh-icon" aria-hidden="true">↻</span>
        </button>
      </div>
    `;
  }

  private _renderAllHealthy(healthyCount: number): TemplateResult {
    return html`
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">✓</div>
        <div class="healthy-message">
          <span class="healthy-title">All systems healthy</span>
          <span class="healthy-subtitle">${healthyCount} automation${healthyCount !== 1 ? 's' : ''} checked</span>
        </div>
      </div>
    `;
  }

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
        <button
          class="tab ${this._activeTab === 'conflicts' ? 'active' : ''}"
          @click=${() => this._switchTab('conflicts')}
        >
          Conflicts
        </button>
      </div>
    `;
  }

  private _renderBadges(counts: { errors: number; warnings: number; healthy: number; suppressed: number }): TemplateResult {
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
        ${counts.suppressed > 0
          ? html`<span class="badge badge-suppressed" title="${counts.suppressed} suppressed">
              <span class="badge-icon" aria-hidden="true">⊘</span>
              <span class="badge-count">${counts.suppressed}</span>
              <button
                class="clear-suppressions-btn"
                @click=${this._clearSuppressions}
                title="Clear all suppressions"
                aria-label="Clear all suppressions"
              >✕</button>
            </span>`
          : nothing}
      </div>
    `;
  }

  private _renderTabFooter(): TemplateResult {
    const isValidation = this._activeTab === "validation";
    const isOutcomes = this._activeTab === "outcomes";
    const isConflicts = this._activeTab === "conflicts";

    const isRunning = isValidation
      ? this._runningValidation
      : isOutcomes
        ? this._runningOutcomes
        : this._runningConflicts;

    const lastRun = isValidation
      ? this._validationData?.last_run
      : isOutcomes
        ? this._outcomesData?.last_run
        : this._conflictsData?.last_run;

    const buttonText = isValidation
      ? "Run Validation"
      : isOutcomes
        ? "Run Outcomes"
        : "Run Conflict Detection";

    const runHandler = () => {
      if (isValidation) {
        this._runValidation();
      } else if (isOutcomes) {
        this._runOutcomes();
      } else {
        this._runConflicts();
      }
    };

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

  private _getSuggestionKey(issue: ValidationIssue): string {
    return `${issue.automation_id}:${issue.entity_id}:${issue.message}`;
  }

  private _dismissSuggestion(issue: ValidationIssue): void {
    const key = this._getSuggestionKey(issue);
    this._dismissedSuggestions = new Set([...this._dismissedSuggestions, key]);
  }

  private async _suppressIssue(issue: ValidationIssue): Promise<void> {
    try {
      await this.hass.callWS({
        type: "autodoctor/suppress",
        automation_id: issue.automation_id,
        entity_id: issue.entity_id,
        issue_type: issue.issue_type || "unknown",
      });
      await this._refreshCurrentTab();
    } catch (err) {
      console.error("Failed to suppress issue:", err);
    }
  }

  private async _clearSuppressions(): Promise<void> {
    try {
      await this.hass.callWS({
        type: "autodoctor/clear_suppressions",
      });
      await this._refreshCurrentTab();
    } catch (err) {
      console.error("Failed to clear suppressions:", err);
    }
  }

  private _renderAutomationGroup(group: AutomationGroup): TemplateResult {
    return html`
      <div class="automation-group ${group.has_error ? 'has-error' : 'has-warning'}">
        <div class="automation-header">
          <span class="automation-severity-icon" aria-hidden="true">${group.has_error ? '✕' : '!'}</span>
          <span class="automation-name">${group.automation_name}</span>
          <span class="automation-badge">${group.issues.length}</span>
        </div>
        <div class="automation-issues">
          ${group.issues.map((item) => this._renderIssue(item))}
        </div>
        <a href="${group.edit_url}" class="edit-link" aria-label="Edit ${group.automation_name}">
          <span class="edit-text">Edit automation</span>
          <span class="edit-arrow" aria-hidden="true">→</span>
        </a>
      </div>
    `;
  }

  private _renderIssue(item: IssueWithFix): TemplateResult {
    const { issue, fix } = item;
    const isError = issue.severity === "error";
    const isDismissed = this._dismissedSuggestions.has(this._getSuggestionKey(issue));

    return html`
      <div class="issue ${isError ? 'error' : 'warning'}">
        <div class="issue-header">
          <span class="issue-icon" aria-hidden="true">${isError ? '✕' : '!'}</span>
          <span class="issue-message">${issue.message}</span>
          <button
            class="suppress-btn"
            @click=${() => this._suppressIssue(issue)}
            aria-label="Suppress this issue"
            title="Don't show this issue again"
          >⊘</button>
        </div>
        ${fix && !isDismissed
          ? html`
              <div class="fix-suggestion">
                <span class="fix-icon" aria-hidden="true">💡</span>
                <div class="fix-content">
                  <span class="fix-description">${fix.description}</span>
                  ${this._renderConfidencePill(fix.confidence)}
                </div>
                <button
                  class="dismiss-btn"
                  @click=${() => this._dismissSuggestion(issue)}
                  aria-label="Dismiss suggestion"
                >✕</button>
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
      <span class="confidence-pill ${isHigh ? 'high' : 'medium'}">
        ${isHigh ? 'High' : 'Medium'} confidence
      </span>
    `;
  }

  private _renderConflictsTab(title: string): TemplateResult {
    if (!this._conflictsData) {
      return this._renderEmpty(title);
    }

    const { conflicts, suppressed_count } = this._conflictsData;
    const hasConflicts = conflicts.length > 0;

    // Count by severity
    const errorCount = conflicts.filter(c => c.severity === "error").length;
    const warningCount = conflicts.filter(c => c.severity === "warning").length;

    return html`
      <ha-card>
        ${this._renderHeader(title)}
        ${this._renderTabs()}
        <div class="card-content">
          ${this._renderConflictsBadges(errorCount, warningCount, suppressed_count)}
          ${hasConflicts
            ? conflicts.map((conflict) => this._renderConflict(conflict))
            : this._renderNoConflicts()}
        </div>
        ${this._renderTabFooter()}
      </ha-card>
    `;
  }

  private _renderConflictsBadges(
    errors: number,
    warnings: number,
    suppressed: number
  ): TemplateResult {
    return html`
      <div class="badges-row">
        ${errors > 0
          ? html`<span class="badge badge-error" title="${errors} conflict${errors !== 1 ? 's' : ''}">
              <span class="badge-icon" aria-hidden="true">✕</span>
              <span class="badge-count">${errors}</span>
            </span>`
          : nothing}
        ${warnings > 0
          ? html`<span class="badge badge-warning" title="${warnings} warning${warnings !== 1 ? 's' : ''}">
              <span class="badge-icon" aria-hidden="true">!</span>
              <span class="badge-count">${warnings}</span>
            </span>`
          : nothing}
        ${errors === 0 && warnings === 0
          ? html`<span class="badge badge-healthy" title="No conflicts">
              <span class="badge-icon" aria-hidden="true">✓</span>
              <span class="badge-count">0</span>
            </span>`
          : nothing}
        ${suppressed > 0
          ? html`<span class="badge badge-suppressed" title="${suppressed} suppressed">
              <span class="badge-icon" aria-hidden="true">⊘</span>
              <span class="badge-count">${suppressed}</span>
            </span>`
          : nothing}
      </div>
    `;
  }

  private _renderNoConflicts(): TemplateResult {
    return html`
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">✓</div>
        <div class="healthy-message">
          <span class="healthy-title">No conflicts detected</span>
          <span class="healthy-subtitle">Your automations work harmoniously</span>
        </div>
      </div>
    `;
  }

  private _renderConflict(conflict: Conflict): TemplateResult {
    const isError = conflict.severity === "error";

    return html`
      <div class="conflict-card ${isError ? 'severity-error' : 'severity-warning'}">
        <div class="conflict-header">
          <span class="conflict-severity-icon" aria-hidden="true">${isError ? '✕' : '!'}</span>
          <span class="conflict-entity">${conflict.entity_id}</span>
        </div>
        <div class="conflict-automations">
          <div class="conflict-automation">
            <span class="conflict-automation-label">A:</span>
            <span class="conflict-automation-name">${conflict.automation_a}</span>
            <span class="conflict-action">${conflict.action_a}</span>
          </div>
          <div class="conflict-vs">vs</div>
          <div class="conflict-automation">
            <span class="conflict-automation-label">B:</span>
            <span class="conflict-automation-name">${conflict.automation_b}</span>
            <span class="conflict-action">${conflict.action_b}</span>
          </div>
        </div>
        <div class="conflict-explanation">${conflict.explanation}</div>
        <div class="conflict-scenario">
          <span class="conflict-scenario-label">Scenario:</span>
          ${conflict.scenario}
        </div>
      </div>
    `;
  }

  static get styles(): CSSResultGroup {
    return css`
      :host {
        /* Typography */
        --autodoc-font-family: 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', sans-serif;
        --autodoc-title-size: 1.1rem;
        --autodoc-name-size: 0.95rem;
        --autodoc-issue-size: 0.875rem;
        --autodoc-meta-size: 0.8rem;

        /* Colors */
        --autodoc-error: #d94848;
        --autodoc-warning: #c49008;
        --autodoc-success: #2e8b57;

        /* Spacing */
        --autodoc-spacing-xs: 4px;
        --autodoc-spacing-sm: 8px;
        --autodoc-spacing-md: 12px;
        --autodoc-spacing-lg: 16px;
        --autodoc-spacing-xl: 24px;

        /* Transitions */
        --autodoc-transition-fast: 150ms ease;
        --autodoc-transition-normal: 200ms ease;

        font-family: var(--autodoc-font-family);
      }

      @media (prefers-reduced-motion: reduce) {
        :host {
          --autodoc-transition-fast: 0ms;
          --autodoc-transition-normal: 0ms;
        }
      }

      :host {
        display: block;
        width: 100%;
        box-sizing: border-box;
      }

      ha-card {
        overflow: hidden;
        width: 100%;
        box-sizing: border-box;
      }

      /* Header */
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: var(--autodoc-spacing-lg);
        border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
      }

      .title {
        margin: 0;
        font-size: var(--autodoc-title-size);
        font-weight: 600;
        color: var(--primary-text-color);
      }

      /* Header refresh button */
      .header .refresh-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        padding: 0;
        background: transparent;
        color: var(--secondary-text-color);
        border: none;
        border-radius: 50%;
        cursor: pointer;
        transition: background var(--autodoc-transition-fast), color var(--autodoc-transition-fast);
      }

      .header .refresh-btn:hover:not(:disabled) {
        background: var(--divider-color, rgba(127, 127, 127, 0.2));
        color: var(--primary-color);
      }

      .header .refresh-btn:focus {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }

      .header .refresh-btn:disabled {
        cursor: not-allowed;
        opacity: 0.6;
      }

      .header .refresh-btn .refresh-icon {
        font-size: 1.1rem;
      }

      .header .refresh-btn.refreshing .refresh-icon {
        animation: rotate 1s linear infinite;
      }

      /* Tabs */
      .tabs {
        display: flex;
        flex-wrap: nowrap;
        width: 100%;
        box-sizing: border-box;
        border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
      }

      .tab {
        flex: 1 1 0%;
        min-width: 0;
        max-width: 100%;
        padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-xs);
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        color: var(--secondary-text-color);
        font-family: var(--autodoc-font-family);
        font-size: var(--autodoc-issue-size);
        font-weight: 500;
        cursor: pointer;
        transition: color var(--autodoc-transition-fast), border-color var(--autodoc-transition-fast);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        box-sizing: border-box;
      }

      .tab:hover {
        color: var(--primary-text-color);
      }

      .tab.active {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }

      .tab:focus {
        outline: none;
        background: var(--divider-color, rgba(127, 127, 127, 0.1));
      }

      /* Badges row (in content area) */
      .badges-row {
        display: flex;
        gap: var(--autodoc-spacing-sm);
        margin-bottom: var(--autodoc-spacing-md);
      }

      .badge {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: var(--autodoc-meta-size);
        font-weight: 600;
        transition: transform var(--autodoc-transition-fast);
        cursor: default;
      }

      .badge:hover {
        transform: scale(1.05);
      }

      .badge-icon {
        font-size: 0.7em;
      }

      .badge-error {
        background: rgba(217, 72, 72, 0.15);
        color: var(--autodoc-error);
      }

      .badge-warning {
        background: rgba(196, 144, 8, 0.15);
        color: var(--autodoc-warning);
      }

      .badge-healthy {
        background: rgba(46, 139, 87, 0.15);
        color: var(--autodoc-success);
      }

      .badge-suppressed {
        background: rgba(127, 127, 127, 0.15);
        color: var(--secondary-text-color);
      }

      .clear-suppressions-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 14px;
        height: 14px;
        margin-left: 2px;
        padding: 0;
        background: transparent;
        border: none;
        border-radius: 50%;
        color: inherit;
        font-size: 0.6em;
        cursor: pointer;
        opacity: 0.6;
        transition: opacity var(--autodoc-transition-fast), background var(--autodoc-transition-fast);
      }

      .clear-suppressions-btn:hover {
        opacity: 1;
        background: rgba(127, 127, 127, 0.3);
      }

      /* Card content */
      .card-content {
        padding: var(--autodoc-spacing-lg);
      }

      /* Loading state */
      .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: var(--autodoc-spacing-xl);
        gap: var(--autodoc-spacing-md);
      }

      .spinner {
        width: 24px;
        height: 24px;
        border: 3px solid var(--divider-color, rgba(127, 127, 127, 0.3));
        border-top-color: var(--primary-color);
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
      }

      @keyframes spin {
        to { transform: rotate(360deg); }
      }

      .loading-text {
        color: var(--secondary-text-color);
        font-size: var(--autodoc-issue-size);
      }

      /* Error state */
      .error-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: var(--autodoc-spacing-xl);
        gap: var(--autodoc-spacing-md);
        text-align: center;
      }

      .error-icon {
        font-size: 2rem;
        color: var(--autodoc-error);
      }

      .error-text {
        color: var(--autodoc-error);
        font-size: var(--autodoc-issue-size);
      }

      .retry-btn {
        margin-top: var(--autodoc-spacing-sm);
        padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-lg);
        background: transparent;
        color: var(--primary-color);
        border: 1px solid var(--primary-color);
        border-radius: 6px;
        font-size: var(--autodoc-issue-size);
        cursor: pointer;
        transition: background var(--autodoc-transition-fast), color var(--autodoc-transition-fast);
      }

      .retry-btn:hover {
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
      }

      /* Empty state */
      .empty-state {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--autodoc-spacing-xl);
      }

      .empty-text {
        color: var(--secondary-text-color);
        font-size: var(--autodoc-issue-size);
      }

      /* All healthy state */
      .all-healthy {
        display: flex;
        align-items: center;
        gap: var(--autodoc-spacing-md);
        padding: var(--autodoc-spacing-lg);
        background: rgba(46, 139, 87, 0.08);
        border-radius: 8px;
      }

      .healthy-icon {
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(46, 139, 87, 0.15);
        color: var(--autodoc-success);
        border-radius: 50%;
        font-size: 1.25rem;
        font-weight: bold;
      }

      .healthy-message {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .healthy-title {
        font-size: var(--autodoc-name-size);
        font-weight: 600;
        color: var(--autodoc-success);
      }

      .healthy-subtitle {
        font-size: var(--autodoc-meta-size);
        color: var(--secondary-text-color);
      }

      /* Automation groups */
      .automation-group {
        background: rgba(127, 127, 127, 0.06);
        border-left: 3px solid var(--autodoc-error);
        border-radius: 0 8px 8px 0;
        padding: var(--autodoc-spacing-md);
        margin-bottom: var(--autodoc-spacing-md);
      }

      .automation-group:last-child {
        margin-bottom: 0;
      }

      .automation-group.has-warning {
        border-left-color: var(--autodoc-warning);
      }

      .automation-header {
        display: flex;
        align-items: center;
        gap: var(--autodoc-spacing-sm);
      }

      .automation-severity-icon {
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(217, 72, 72, 0.15);
        color: var(--autodoc-error);
        border-radius: 50%;
        font-size: 0.7rem;
        font-weight: bold;
      }

      .automation-group.has-warning .automation-severity-icon {
        background: rgba(196, 144, 8, 0.15);
        color: var(--autodoc-warning);
      }

      .automation-name {
        flex: 1;
        font-size: var(--autodoc-name-size);
        font-weight: 600;
        color: var(--primary-text-color);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .automation-badge {
        background: var(--autodoc-error);
        color: #fff;
        font-size: var(--autodoc-meta-size);
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 10px;
        min-width: 18px;
        text-align: center;
      }

      .automation-group.has-warning .automation-badge {
        background: var(--autodoc-warning);
      }

      /* Issues */
      .automation-issues {
        margin-top: var(--autodoc-spacing-md);
        padding-left: 28px;
      }

      .issue {
        padding: var(--autodoc-spacing-sm) 0;
        border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.15));
      }

      .issue:last-child {
        border-bottom: none;
        padding-bottom: 0;
      }

      .issue-header {
        display: flex;
        align-items: flex-start;
        gap: var(--autodoc-spacing-sm);
      }

      .issue-icon {
        flex-shrink: 0;
        font-size: 0.65rem;
        font-weight: bold;
        margin-top: 3px;
      }

      .issue.error .issue-icon {
        color: var(--autodoc-error);
      }

      .issue.warning .issue-icon {
        color: var(--autodoc-warning);
      }

      .issue-message {
        flex: 1;
        font-size: var(--autodoc-issue-size);
        color: var(--secondary-text-color);
        line-height: 1.4;
      }

      .suppress-btn {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        padding: 0;
        background: transparent;
        border: none;
        border-radius: 50%;
        color: var(--secondary-text-color);
        font-size: 0.75rem;
        cursor: pointer;
        opacity: 0;
        transition: opacity var(--autodoc-transition-fast), background var(--autodoc-transition-fast);
      }

      .issue:hover .suppress-btn {
        opacity: 0.6;
      }

      .suppress-btn:hover {
        opacity: 1;
        background: var(--divider-color, rgba(127, 127, 127, 0.2));
      }

      .suppress-btn:focus {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
        opacity: 1;
      }

      /* Fix suggestions */
      .fix-suggestion {
        display: flex;
        align-items: flex-start;
        gap: var(--autodoc-spacing-sm);
        margin-top: var(--autodoc-spacing-sm);
        padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
        background: var(--primary-background-color, rgba(255, 255, 255, 0.5));
        border-radius: 6px;
      }

      .fix-icon {
        flex-shrink: 0;
        font-size: 0.875rem;
      }

      .fix-content {
        flex: 1;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--autodoc-spacing-sm);
      }

      .fix-description {
        font-size: var(--autodoc-issue-size);
        color: var(--primary-text-color);
        line-height: 1.4;
      }

      .confidence-pill {
        display: inline-block;
        font-size: var(--autodoc-meta-size);
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 10px;
      }

      .confidence-pill.high {
        background: rgba(46, 139, 87, 0.15);
        color: var(--autodoc-success);
      }

      .confidence-pill.medium {
        background: rgba(196, 144, 8, 0.15);
        color: var(--autodoc-warning);
      }

      .dismiss-btn {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        padding: 0;
        background: transparent;
        border: none;
        border-radius: 50%;
        color: var(--secondary-text-color);
        font-size: 0.7rem;
        cursor: pointer;
        opacity: 0.6;
        transition: opacity var(--autodoc-transition-fast), background var(--autodoc-transition-fast);
      }

      .dismiss-btn:hover {
        opacity: 1;
        background: var(--divider-color, rgba(127, 127, 127, 0.2));
      }

      .dismiss-btn:focus {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
        opacity: 1;
      }

      /* Edit link */
      .edit-link {
        display: inline-flex;
        align-items: center;
        gap: var(--autodoc-spacing-xs);
        margin-top: var(--autodoc-spacing-md);
        margin-left: 28px;
        color: var(--primary-color);
        text-decoration: none;
        font-size: var(--autodoc-issue-size);
        transition: gap var(--autodoc-transition-fast);
      }

      .edit-link:hover {
        text-decoration: underline;
        gap: var(--autodoc-spacing-sm);
      }

      .edit-link:focus {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
        border-radius: 2px;
      }

      .edit-arrow {
        transition: transform var(--autodoc-transition-fast);
      }

      .edit-link:hover .edit-arrow {
        transform: translateX(2px);
      }

      /* Footer */
      .footer {
        display: flex;
        align-items: center;
        gap: var(--autodoc-spacing-md);
        padding: var(--autodoc-spacing-md) var(--autodoc-spacing-lg);
        border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
      }

      .run-btn {
        display: inline-flex;
        align-items: center;
        gap: var(--autodoc-spacing-sm);
        padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
        border: none;
        border-radius: 6px;
        font-family: var(--autodoc-font-family);
        font-size: var(--autodoc-issue-size);
        font-weight: 500;
        cursor: pointer;
        transition: opacity var(--autodoc-transition-fast), transform var(--autodoc-transition-fast);
      }

      .run-btn:hover:not(:disabled) {
        opacity: 0.9;
        transform: translateY(-1px);
      }

      .run-btn:focus {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }

      .run-btn:disabled {
        cursor: not-allowed;
        opacity: 0.7;
      }

      .run-icon {
        font-size: 0.8rem;
      }

      .run-btn.running .run-icon {
        animation: rotate 1s linear infinite;
      }

      .run-text {
        font-family: var(--autodoc-font-family);
      }

      .last-run {
        color: var(--secondary-text-color);
        font-size: var(--autodoc-meta-size);
      }

      @keyframes rotate {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }

      /* Conflict cards */
      .conflict-card {
        background: rgba(127, 127, 127, 0.06);
        border-left: 3px solid var(--autodoc-error);
        border-radius: 0 8px 8px 0;
        padding: var(--autodoc-spacing-md);
        margin-bottom: var(--autodoc-spacing-md);
      }

      .conflict-card:last-child {
        margin-bottom: 0;
      }

      .conflict-card.severity-warning {
        border-left-color: var(--autodoc-warning);
      }

      .conflict-header {
        display: flex;
        align-items: center;
        gap: var(--autodoc-spacing-sm);
        margin-bottom: var(--autodoc-spacing-sm);
      }

      .conflict-severity-icon {
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(217, 72, 72, 0.15);
        color: var(--autodoc-error);
        border-radius: 50%;
        font-size: 0.7rem;
        font-weight: bold;
      }

      .conflict-card.severity-warning .conflict-severity-icon {
        background: rgba(196, 144, 8, 0.15);
        color: var(--autodoc-warning);
      }

      .conflict-entity {
        font-size: var(--autodoc-name-size);
        font-weight: 600;
        color: var(--primary-text-color);
        font-family: monospace;
      }

      .conflict-automations {
        display: flex;
        flex-direction: column;
        gap: var(--autodoc-spacing-xs);
        padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
        background: var(--primary-background-color, rgba(255, 255, 255, 0.5));
        border-radius: 6px;
        margin-bottom: var(--autodoc-spacing-sm);
      }

      .conflict-automation {
        display: flex;
        align-items: center;
        gap: var(--autodoc-spacing-sm);
        font-size: var(--autodoc-issue-size);
      }

      .conflict-automation-label {
        color: var(--secondary-text-color);
        font-weight: 600;
        min-width: 16px;
      }

      .conflict-automation-name {
        color: var(--primary-text-color);
        font-weight: 500;
      }

      .conflict-action {
        color: var(--secondary-text-color);
        font-style: italic;
      }

      .conflict-action::before {
        content: "→ ";
      }

      .conflict-vs {
        text-align: center;
        color: var(--secondary-text-color);
        font-size: var(--autodoc-meta-size);
        font-weight: 600;
        text-transform: uppercase;
      }

      .conflict-explanation {
        font-size: var(--autodoc-issue-size);
        color: var(--primary-text-color);
        line-height: 1.4;
        margin-bottom: var(--autodoc-spacing-sm);
      }

      .conflict-scenario {
        font-size: var(--autodoc-meta-size);
        color: var(--secondary-text-color);
        padding: var(--autodoc-spacing-sm);
        background: rgba(127, 127, 127, 0.08);
        border-radius: 4px;
      }

      .conflict-scenario-label {
        font-weight: 600;
        margin-right: var(--autodoc-spacing-xs);
      }
    `;
  }

  public getCardSize(): number {
    return 3;
  }

  public getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
      rows: "auto",
    };
  }
}

// Register card with HA
(window as any).customCards = (window as any).customCards || [];
(window as any).customCards.push({
  type: "autodoctor-card",
  name: "Autodoctor Card",
  description: "Shows automation health and validation issues",
  preview: false,
  documentationURL: "https://github.com/mossipcams/autodoctor",
});
