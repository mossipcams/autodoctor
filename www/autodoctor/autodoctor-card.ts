import { LitElement, html, css, CSSResultGroup, TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import type { AutodoctorCardConfig, AutodoctorData, IssueWithFix } from "./types";

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

    return html`
      <ha-card header="${this.config.title || "Automation Health"}">
        <div class="card-content">
          ${this._data.issues.length > 0
            ? html`
                <div class="issue-count">
                  ${this._data.issues.length} issue${this._data.issues.length > 1 ? "s" : ""} found
                </div>
                ${this._data.issues.map((item) => this._renderIssue(item))}
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

  private _renderIssue(item: IssueWithFix): TemplateResult {
    const { issue, fix, edit_url } = item;
    const isError = issue.severity === "error";

    return html`
      <div class="issue ${isError ? "error" : "warning"}">
        <div class="issue-header">
          <span class="severity-icon">${isError ? "✕" : "!"}</span>
          <span class="automation-name">${issue.automation_name}</span>
        </div>
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
        <a href="${edit_url}" class="edit-link">Edit automation</a>
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

      .issue {
        border-left: 4px solid var(--error-color);
        padding: 12px;
        margin-bottom: 12px;
        background: var(--secondary-background-color);
        border-radius: 0 4px 4px 0;
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
        font-weight: bold;
      }

      .issue.warning .severity-icon {
        color: var(--warning-color);
      }

      .issue-message {
        margin: 8px 0;
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
});
