import { LitElement, html, css, CSSResultGroup, TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import type { AutodoctorCardConfig, AutodoctorData, IssueWithFix, ValidationIssue } from "./types";

interface AutomationGroup {
  automation_id: string;
  automation_name: string;
  issues: IssueWithFix[];
  edit_url: string;
  has_error: boolean;
}

@customElement("autodoctor-card")
export class AutodoctorCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config!: AutodoctorCardConfig;

  @state() private _data: AutodoctorData | null = null;
  @state() private _loading = true;
  @state() private _error: string | null = null;

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
    await this._fetchData();
  }

  private async _fetchData(): Promise<void> {
    this._loading = true;
    this._error = null;

    try {
      this._data = await this.hass.callWS<AutodoctorData>({
        type: "autodoctor/issues",
      });
    } catch (err) {
      console.error("Failed to fetch autodoctor data:", err);
      this._error = "Failed to load automation health data";
    }

    this._loading = false;
  }

  private async _refresh(): Promise<void> {
    await this.hass.callWS({ type: "autodoctor/refresh" });
    await this._fetchData();
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
        });
      }

      const group = groups.get(key)!;
      group.issues.push(item);
      if (issue.severity === "error") {
        group.has_error = true;
      }
    }

    return Array.from(groups.values());
  }

  protected render(): TemplateResult {
    if (this._loading) {
      return html`
        <ha-card header="${this.config.title || "Automation Health"}">
          <div class="card-content loading">Loading...</div>
        </ha-card>
      `;
    }

    if (this._error) {
      return html`
        <ha-card header="${this.config.title || "Automation Health"}">
          <div class="card-content error">${this._error}</div>
        </ha-card>
      `;
    }

    if (!this._data) {
      return html`
        <ha-card header="${this.config.title || "Automation Health"}">
          <div class="card-content">No data available</div>
        </ha-card>
      `;
    }

    const groups = this._groupIssuesByAutomation(this._data.issues);
    const totalIssues = this._data.issues.length;

    return html`
      <ha-card header="${this.config.title || "Automation Health"}">
        <div class="card-content">
          ${totalIssues > 0
            ? html`
                <div class="issue-count">
                  ${totalIssues} issue${totalIssues > 1 ? "s" : ""} in ${groups.length} automation${groups.length > 1 ? "s" : ""}
                </div>
                ${groups.map((group) => this._renderAutomationGroup(group))}
              `
            : html`<div class="no-issues">No issues detected</div>`}
          <div class="healthy">
            ${this._data.healthy_count} automation${this._data.healthy_count !== 1 ? "s" : ""} healthy
          </div>
          <button class="refresh-btn" @click=${this._refresh}>Refresh</button>
        </div>
      </ha-card>
    `;
  }

  private _renderAutomationGroup(group: AutomationGroup): TemplateResult {
    return html`
      <div class="automation-group ${group.has_error ? "has-error" : "has-warning"}">
        <div class="automation-header">
          <span class="severity-icon">${group.has_error ? "✕" : "!"}</span>
          <span class="automation-name">${group.automation_name}</span>
          <span class="issue-badge">${group.issues.length}</span>
        </div>
        <div class="automation-issues">
          ${group.issues.map((item) => this._renderIssue(item))}
        </div>
        <a href="${group.edit_url}" class="edit-link">Edit automation</a>
      </div>
    `;
  }

  private _renderIssue(item: IssueWithFix): TemplateResult {
    const { issue, fix } = item;
    const isError = issue.severity === "error";

    return html`
      <div class="issue ${isError ? "error" : "warning"}">
        <div class="issue-message">${issue.message}</div>
        ${fix
          ? html`
              <div class="fix-suggestion">
                <span class="fix-label">Suggested fix:</span> ${fix.description}
                ${fix.confidence > 0.9
                  ? html`<span class="confidence high">High confidence</span>`
                  : fix.confidence > 0.6
                  ? html`<span class="confidence medium">Medium confidence</span>`
                  : ""}
              </div>
            `
          : ""}
      </div>
    `;
  }

  static get styles(): CSSResultGroup {
    return css`
      .card-content {
        padding: 16px;
      }

      .loading,
      .error {
        text-align: center;
        padding: 32px 16px;
      }

      .error {
        color: var(--error-color);
      }

      .issue-count {
        font-weight: bold;
        margin-bottom: 16px;
        color: var(--error-color);
      }

      .no-issues {
        color: var(--success-color);
        margin-bottom: 16px;
      }

      .automation-group {
        border-left: 4px solid var(--error-color);
        padding: 12px;
        margin-bottom: 12px;
        background: var(--secondary-background-color);
        border-radius: 0 4px 4px 0;
      }

      .automation-group.has-warning {
        border-left-color: var(--warning-color);
      }

      .automation-header {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: bold;
      }

      .severity-icon {
        color: var(--error-color);
        font-weight: bold;
      }

      .automation-group.has-warning .severity-icon {
        color: var(--warning-color);
      }

      .issue-badge {
        background: var(--error-color);
        color: white;
        font-size: 0.75em;
        padding: 2px 6px;
        border-radius: 10px;
        margin-left: auto;
      }

      .automation-group.has-warning .issue-badge {
        background: var(--warning-color);
      }

      .automation-issues {
        margin-top: 8px;
        padding-left: 24px;
      }

      .issue {
        padding: 8px 0;
        border-bottom: 1px solid var(--divider-color);
      }

      .issue:last-child {
        border-bottom: none;
      }

      .issue.error .issue-message::before {
        content: "✕ ";
        color: var(--error-color);
      }

      .issue.warning .issue-message::before {
        content: "! ";
        color: var(--warning-color);
      }

      .issue-message {
        color: var(--secondary-text-color);
        font-size: 0.9em;
      }

      .fix-suggestion {
        margin: 8px 0;
        padding: 8px;
        background: var(--primary-background-color);
        border-radius: 4px;
        font-size: 0.9em;
      }

      .fix-label {
        font-weight: 500;
      }

      .confidence {
        margin-left: 8px;
        font-size: 0.8em;
        padding: 2px 6px;
        border-radius: 4px;
      }

      .confidence.high {
        background: var(--success-color);
        color: white;
      }

      .confidence.medium {
        background: var(--warning-color);
        color: white;
      }

      .edit-link {
        display: inline-block;
        margin-top: 8px;
        color: var(--primary-color);
        text-decoration: none;
        font-size: 0.9em;
      }

      .edit-link:hover {
        text-decoration: underline;
      }

      .healthy {
        color: var(--success-color);
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid var(--divider-color);
      }

      .refresh-btn {
        margin-top: 16px;
        padding: 8px 16px;
        background: var(--primary-color);
        color: var(--text-primary-color);
        border: none;
        border-radius: 4px;
        cursor: pointer;
      }

      .refresh-btn:hover {
        opacity: 0.9;
      }
    `;
  }

  public getCardSize(): number {
    return 3;
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
