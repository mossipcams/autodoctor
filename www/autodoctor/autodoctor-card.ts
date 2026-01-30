import { LitElement, html, CSSResultGroup, TemplateResult, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import type {
  AutodoctorCardConfig,
  AutomationGroup,
  IssueWithFix,
  ValidationIssue,
  TabType,
  AutodoctorTabData,
  ConflictsTabData,
  Conflict,
} from "./types";

import { autodocTokens, badgeStyles, conflictStyles, cardLayoutStyles } from "./styles.js";
import { renderBadges, renderConflictsBadges } from "./badges.js";
import "./autodoc-issue-group.js";

const CARD_VERSION = "2.1.0";

console.info(
  `%c AUTODOCTOR-CARD %c ${CARD_VERSION} `,
  "color: white; background: #3498db; font-weight: bold;",
  "color: #3498db; background: white; font-weight: bold;"
);

@customElement("autodoctor-card")
export class AutodoctorCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config!: AutodoctorCardConfig;

  @state() private _loadingValidation = true;
  @state() private _loadingConflicts = false;
  @state() private _error: string | null = null;
  @state() private _activeTab: TabType = "validation";
  @state() private _validationData: AutodoctorTabData | null = null;
  @state() private _conflictsData: ConflictsTabData | null = null;
  @state() private _runningValidation = false;
  @state() private _runningConflicts = false;
  @state() private _dismissedSuggestions = new Set<string>();

  // Request tracking to prevent race conditions
  private _validationRequestId = 0;
  private _conflictsRequestId = 0;
  private _suppressionInProgress = false;

  // Cooldown tracking to prevent rapid button clicks
  private _lastValidationClick = 0;
  private _lastConflictsClick = 0;
  private static readonly CLICK_COOLDOWN_MS = 2000; // 2 second minimum between clicks

  private _isInCooldown(isValidation: boolean): boolean {
    const lastClick = isValidation ? this._lastValidationClick : this._lastConflictsClick;
    return Date.now() - lastClick < AutodoctorCard.CLICK_COOLDOWN_MS;
  }

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

    // Fetch data if not loaded and not already fetching
    if (tab === "validation" && !this._validationData && !this._loadingValidation) {
      this._fetchValidation();
    } else if (tab === "conflicts" && !this._conflictsData && !this._loadingConflicts) {
      this._fetchConflicts();
    }
  }

  private async _fetchValidation(): Promise<void> {
    // Increment request ID to track this specific request
    const requestId = ++this._validationRequestId;
    this._loadingValidation = true;

    try {
      this._error = null;
      const data = await this.hass.callWS<AutodoctorTabData>({
        type: "autodoctor/validation",
      });

      // Only update state if this is still the latest request
      if (requestId === this._validationRequestId) {
        this._validationData = data;
      }
    } catch (err) {
      // Only set error if this is still the latest request
      if (requestId === this._validationRequestId) {
        console.error("Failed to fetch validation data:", err);
        this._error = "Failed to load validation data";
      }
    }

    // Only clear loading if this is still the latest request
    if (requestId === this._validationRequestId) {
      this._loadingValidation = false;
    }
  }

  private async _runValidation(): Promise<void> {
    // Prevent concurrent runs and enforce cooldown
    const now = Date.now();
    if (
      this._runningValidation ||
      now - this._lastValidationClick < AutodoctorCard.CLICK_COOLDOWN_MS
    ) {
      return;
    }
    this._lastValidationClick = now;

    const requestId = ++this._validationRequestId;
    this._runningValidation = true;

    try {
      const data = await this.hass.callWS<AutodoctorTabData>({
        type: "autodoctor/validation/run",
      });

      // Only update state if this is still the latest request
      if (requestId === this._validationRequestId) {
        this._validationData = data;
      }
    } catch (err) {
      if (requestId === this._validationRequestId) {
        console.error("Failed to run validation:", err);
      }
    }

    // Only clear running flag if this is still the latest request
    if (requestId === this._validationRequestId) {
      this._runningValidation = false;
    }
  }

  private async _fetchConflicts(): Promise<void> {
    // Increment request ID to track this specific request
    const requestId = ++this._conflictsRequestId;
    this._loadingConflicts = true;

    try {
      this._error = null;
      const data = await this.hass.callWS<ConflictsTabData>({
        type: "autodoctor/conflicts",
      });

      // Only update state if this is still the latest request
      if (requestId === this._conflictsRequestId) {
        this._conflictsData = data;
      }
    } catch (err) {
      // Only set error if this is still the latest request
      if (requestId === this._conflictsRequestId) {
        console.error("Failed to fetch conflicts data:", err);
        this._error = "Failed to load conflicts data";
      }
    }

    // Only clear loading if this is still the latest request
    if (requestId === this._conflictsRequestId) {
      this._loadingConflicts = false;
    }
  }

  private async _runConflicts(): Promise<void> {
    // Prevent concurrent runs and enforce cooldown
    const now = Date.now();
    if (
      this._runningConflicts ||
      now - this._lastConflictsClick < AutodoctorCard.CLICK_COOLDOWN_MS
    ) {
      return;
    }
    this._lastConflictsClick = now;

    const requestId = ++this._conflictsRequestId;
    this._runningConflicts = true;

    try {
      const data = await this.hass.callWS<ConflictsTabData>({
        type: "autodoctor/conflicts/run",
      });

      // Only update state if this is still the latest request
      if (requestId === this._conflictsRequestId) {
        this._conflictsData = data;
      }
    } catch (err) {
      if (requestId === this._conflictsRequestId) {
        console.error("Failed to run conflict detection:", err);
      }
    }

    // Only clear running flag if this is still the latest request
    if (requestId === this._conflictsRequestId) {
      this._runningConflicts = false;
    }
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

  private _getCounts(data: AutodoctorTabData | null): {
    errors: number;
    warnings: number;
    healthy: number;
    suppressed: number;
  } {
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

    return {
      errors,
      warnings,
      healthy: data.healthy_count,
      suppressed: data.suppressed_count || 0,
    };
  }

  private get _loading(): boolean {
    // Return loading state for the current tab
    return this._activeTab === "validation" ? this._loadingValidation : this._loadingConflicts;
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

    const data = this._validationData;

    if (!data) {
      return this._renderEmpty(title);
    }

    const groups = this._groupIssuesByAutomation(data.issues);
    const counts = this._getCounts(data);
    const hasIssues = data.issues.length > 0;

    return html`
      <ha-card>
        ${this._renderHeader(title)} ${this._renderTabs()}
        <div class="card-content">
          ${this._renderBadges(counts)}
          ${hasIssues
            ? groups.map(
                (group) => html`
                  <autodoc-issue-group
                    .group=${group}
                    .dismissedKeys=${this._dismissedSuggestions}
                    @suppress-issue=${(e: CustomEvent<{ issue: ValidationIssue }>) =>
                      this._suppressIssue(e.detail.issue)}
                    @dismiss-suggestion=${(e: CustomEvent<{ issue: ValidationIssue }>) =>
                      this._dismissSuggestion(e.detail.issue)}
                  ></autodoc-issue-group>
                `
              )
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
          <div class="error-icon" aria-hidden="true">\u26A0</div>
          <span class="error-text">${this._error}</span>
          <button
            class="retry-btn"
            @click=${() =>
              this._activeTab === "validation" ? this._fetchValidation() : this._fetchConflicts()}
          >
            Try again
          </button>
        </div>
      </ha-card>
    `;
  }

  private _renderEmpty(title: string): TemplateResult {
    return html`
      <ha-card>
        ${this._renderHeader(title)} ${this._renderTabs()}
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
      </div>
    `;
  }

  private _renderAllHealthy(healthyCount: number): TemplateResult {
    return html`
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">\u2713</div>
        <div class="healthy-message">
          <span class="healthy-title">All systems healthy</span>
          <span class="healthy-subtitle"
            >${healthyCount} automation${healthyCount !== 1 ? "s" : ""} checked</span
          >
        </div>
      </div>
    `;
  }

  private _renderTabs(): TemplateResult {
    return html`
      <div class="tabs">
        <button
          class="tab ${this._activeTab === "validation" ? "active" : ""}"
          @click=${() => this._switchTab("validation")}
        >
          Validation
        </button>
        <button
          class="tab ${this._activeTab === "conflicts" ? "active" : ""}"
          @click=${() => this._switchTab("conflicts")}
        >
          Conflicts
        </button>
      </div>
    `;
  }

  private _renderBadges(counts: {
    errors: number;
    warnings: number;
    healthy: number;
    suppressed: number;
  }): TemplateResult {
    return renderBadges(counts, () => this._clearSuppressions());
  }

  private _renderTabFooter(): TemplateResult {
    const isValidation = this._activeTab === "validation";

    const isRunning = isValidation ? this._runningValidation : this._runningConflicts;

    const isLoading = isValidation ? this._loadingValidation : this._loadingConflicts;

    // Disable button during any async operation or cooldown period
    const isDisabled = isRunning || isLoading || this._isInCooldown(isValidation);

    const lastRun = isValidation ? this._validationData?.last_run : this._conflictsData?.last_run;

    const buttonText = isValidation ? "Run Validation" : "Run Conflict Detection";

    const runHandler = () => {
      if (isValidation) {
        this._runValidation();
      } else {
        this._runConflicts();
      }
    };

    // Show running state for any async operation
    const showRunning = isRunning || isLoading;

    return html`
      <div class="footer">
        <button
          class="run-btn ${showRunning ? "running" : ""}"
          @click=${runHandler}
          ?disabled=${isDisabled}
        >
          <span class="run-icon" aria-hidden="true">${showRunning ? "\u21BB" : "\u25B6"}</span>
          <span class="run-text">${showRunning ? "Running..." : buttonText}</span>
        </button>
        ${lastRun
          ? html` <span class="last-run">Last run: ${this._formatLastRun(lastRun)}</span> `
          : nothing}
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
    // Prevent concurrent suppression operations
    if (this._suppressionInProgress) {
      return;
    }

    this._suppressionInProgress = true;
    try {
      await this.hass.callWS({
        type: "autodoctor/suppress",
        automation_id: issue.automation_id,
        entity_id: issue.entity_id,
        issue_type: issue.issue_type || "unknown",
      });
      if (this._activeTab === "validation") {
        await this._fetchValidation();
      } else {
        await this._fetchConflicts();
      }
    } catch (err) {
      console.error("Failed to suppress issue:", err);
    } finally {
      this._suppressionInProgress = false;
    }
  }

  private async _clearSuppressions(): Promise<void> {
    // Prevent concurrent suppression operations
    if (this._suppressionInProgress) {
      return;
    }

    this._suppressionInProgress = true;
    try {
      await this.hass.callWS({
        type: "autodoctor/clear_suppressions",
      });
      if (this._activeTab === "validation") {
        await this._fetchValidation();
      } else {
        await this._fetchConflicts();
      }
    } catch (err) {
      console.error("Failed to clear suppressions:", err);
    } finally {
      this._suppressionInProgress = false;
    }
  }

  private _renderConflictsTab(title: string): TemplateResult {
    if (!this._conflictsData) {
      return this._renderEmpty(title);
    }

    const { conflicts, suppressed_count } = this._conflictsData;
    const hasConflicts = conflicts.length > 0;

    // Count by severity
    const errorCount = conflicts.filter((c) => c.severity === "error").length;
    const warningCount = conflicts.filter((c) => c.severity === "warning").length;

    return html`
      <ha-card>
        ${this._renderHeader(title)} ${this._renderTabs()}
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
    return renderConflictsBadges(errors, warnings, suppressed);
  }

  private _renderNoConflicts(): TemplateResult {
    return html`
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">\u2713</div>
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
      <div class="conflict-card ${isError ? "severity-error" : "severity-warning"}">
        <div class="conflict-header">
          <span class="conflict-severity-icon" aria-hidden="true">${isError ? "\u2715" : "!"}</span>
          <span class="conflict-entity">${conflict.entity_id}</span>
        </div>
        <div class="conflict-automations">
          <div class="conflict-automation">
            <span class="conflict-automation-label">A:</span>
            <span class="conflict-automation-name">${conflict.automation_a_name}</span>
            <span class="conflict-action">${conflict.action_a}</span>
          </div>
          <div class="conflict-vs">vs</div>
          <div class="conflict-automation">
            <span class="conflict-automation-label">B:</span>
            <span class="conflict-automation-name">${conflict.automation_b_name}</span>
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
    return [autodocTokens, badgeStyles, conflictStyles, cardLayoutStyles];
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
