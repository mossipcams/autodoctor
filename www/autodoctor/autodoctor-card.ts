import { LitElement, html, CSSResultGroup, TemplateResult, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import {
  getSuggestionKey,
  type AutodoctorCardConfig,
  type AutomationGroup,
  type IssueWithFix,
  type ValidationIssue,
  type StepsResponse,
} from "./types.js";

import { autodocTokens, badgeStyles, cardLayoutStyles } from "./styles.js";
import { renderBadges } from "./badges.js";
import "./autodoc-issue-group.js";
import "./autodoc-pipeline.js";

declare const __CARD_VERSION__: string;
const CARD_VERSION = __CARD_VERSION__;

console.info(
  `%c AUTODOCTOR-CARD %c ${CARD_VERSION} `,
  "color: white; background: #3498db; font-weight: bold;",
  "color: #3498db; background: white; font-weight: bold;"
);

@customElement("autodoctor-card")
export class AutodoctorCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config!: AutodoctorCardConfig;

  @state() private _loading = true;
  @state() private _error: string | null = null;
  @state() private _validationData: StepsResponse | null = null;
  @state() private _runningValidation = false;
  @state() private _dismissedSuggestions = new Set<string>();

  // Request tracking to prevent race conditions
  private _validationRequestId = 0;
  private _suppressionInProgress = false;

  // Cooldown tracking to prevent rapid button clicks
  private _lastValidationClick = 0;
  private static readonly CLICK_COOLDOWN_MS = 2000; // 2 second minimum between clicks

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

  private async _fetchValidation(): Promise<void> {
    // Increment request ID to track this specific request
    const requestId = ++this._validationRequestId;
    this._loading = true;

    try {
      this._error = null;
      const data = await this.hass.callWS<StepsResponse>({
        type: "autodoctor/validation/steps",
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
      this._loading = false;
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
      const data = await this.hass.callWS<StepsResponse>({
        type: "autodoctor/validation/run_steps",
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

  private _getCounts(data: StepsResponse | null): {
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

  protected render(): TemplateResult {
    const title = this.config.title || "Autodoctor";

    if (this._loading) {
      return this._renderLoading(title);
    }

    if (this._error) {
      return this._renderError(title);
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
        ${this._renderHeader(title)}
        <div class="card-content">
          ${this._renderBadges(counts)}
          ${data.last_run
            ? html`<autodoc-pipeline
                .groups=${data.groups || []}
                ?running=${this._runningValidation}
              ></autodoc-pipeline>`
            : nothing}
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
            : data.last_run
              ? nothing
              : this._renderAllHealthy(counts.healthy)}
        </div>
        ${this._renderFooter()}
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
          <button class="retry-btn" @click=${() => this._fetchValidation()}>Try again</button>
        </div>
      </ha-card>
    `;
  }

  private _renderEmpty(title: string): TemplateResult {
    return html`
      <ha-card>
        ${this._renderHeader(title)}
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

  private _renderBadges(counts: {
    errors: number;
    warnings: number;
    healthy: number;
    suppressed: number;
  }): TemplateResult {
    return renderBadges(counts, () => this._clearSuppressions());
  }

  private _renderFooter(): TemplateResult {
    // Disable button during any async operation or cooldown period
    const isRunning = this._runningValidation || this._loading;
    const isDisabled =
      isRunning || Date.now() - this._lastValidationClick < AutodoctorCard.CLICK_COOLDOWN_MS;

    return html`
      <div class="footer">
        <button
          class="run-btn ${isRunning ? "running" : ""}"
          @click=${() => this._runValidation()}
          ?disabled=${isDisabled}
        >
          <span class="run-icon" aria-hidden="true">${isRunning ? "\u21BB" : "\u25B6"}</span>
          <span class="run-text">${isRunning ? "Running..." : "Run Validation"}</span>
        </button>
        ${this._validationData?.last_run
          ? html` <span class="last-run"
              >Last run: ${this._formatLastRun(this._validationData.last_run)}</span
            >`
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

  private _dismissSuggestion(issue: ValidationIssue): void {
    const key = getSuggestionKey(issue);
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
      await this._fetchValidation();
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
      await this._fetchValidation();
    } catch (err) {
      console.error("Failed to clear suppressions:", err);
    } finally {
      this._suppressionInProgress = false;
    }
  }

  static get styles(): CSSResultGroup {
    return [autodocTokens, badgeStyles, cardLayoutStyles];
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
