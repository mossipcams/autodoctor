import { LitElement, html, css, CSSResultGroup, TemplateResult, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";
import { autodocTokens } from "./styles.js";
import type { SuppressionEntry, SuppressionsResponse } from "./types.js";

@customElement("autodoc-suppressions")
export class AutodocSuppressions extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _suppressions: SuppressionEntry[] = [];
  @state() private _loading = true;
  @state() private _error: string | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this._fetchSuppressions();
  }

  private async _fetchSuppressions(): Promise<void> {
    this._loading = true;
    this._error = null;
    try {
      const resp = await this.hass.callWS<SuppressionsResponse>({
        type: "autodoctor/list_suppressions",
      });
      this._suppressions = resp.suppressions;
    } catch (err) {
      console.error("Failed to fetch suppressions:", err);
      this._error = "Failed to load suppressions";
    }
    this._loading = false;
  }

  private async _unsuppress(key: string): Promise<void> {
    try {
      await this.hass.callWS({
        type: "autodoctor/unsuppress",
        key,
      });
      this._suppressions = this._suppressions.filter((s) => s.key !== key);
      this.dispatchEvent(
        new CustomEvent("suppressions-changed", {
          bubbles: true,
          composed: true,
        })
      );
    } catch (err) {
      console.error("Failed to unsuppress:", err);
    }
  }

  private async _clearAll(): Promise<void> {
    try {
      await this.hass.callWS({ type: "autodoctor/clear_suppressions" });
      this._suppressions = [];
      this.dispatchEvent(
        new CustomEvent("suppressions-changed", {
          bubbles: true,
          composed: true,
        })
      );
    } catch (err) {
      console.error("Failed to clear suppressions:", err);
    }
  }

  protected render(): TemplateResult {
    if (this._loading) {
      return html`<div class="loading">Loading suppressions...</div>`;
    }
    if (this._error) {
      return html`<div class="error">${this._error}</div>`;
    }
    if (this._suppressions.length === 0) {
      return html`<div class="empty">No suppressed issues</div>`;
    }

    return html`
      <div class="suppressions-list">
        <div class="suppressions-header">
          <span class="suppressions-title"
            >${this._suppressions.length} suppressed
            issue${this._suppressions.length !== 1 ? "s" : ""}</span
          >
          <button class="clear-all-btn" @click=${this._clearAll}>Clear all</button>
        </div>
        ${this._suppressions.map((s) => this._renderSuppression(s))}
      </div>
    `;
  }

  private _renderSuppression(entry: SuppressionEntry): TemplateResult {
    return html`
      <div class="suppression-item">
        <div class="suppression-info">
          <span class="suppression-automation"
            >${entry.automation_name || entry.automation_id}</span
          >
          <span class="suppression-detail"
            >${entry.entity_id}${entry.message ? ` \u2014 ${entry.message}` : ""}</span
          >
        </div>
        <button
          class="restore-btn"
          @click=${() => this._unsuppress(entry.key)}
          title="Restore this issue"
          aria-label="Restore suppressed issue"
        >
          <ha-icon icon="mdi:eye-outline" style="--mdc-icon-size: 18px;"></ha-icon>
        </button>
      </div>
    `;
  }

  static get styles(): CSSResultGroup {
    return [
      autodocTokens,
      css`
        :host {
          display: block;
        }

        .loading,
        .error,
        .empty {
          padding: var(--autodoc-spacing-lg);
          text-align: center;
          color: var(--secondary-text-color);
          font-size: var(--autodoc-issue-size);
        }

        .error {
          color: var(--autodoc-error);
        }

        .suppressions-list {
          display: flex;
          flex-direction: column;
          gap: var(--autodoc-spacing-sm);
        }

        .suppressions-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0 0 var(--autodoc-spacing-sm) 0;
        }

        .suppressions-title {
          font-size: var(--autodoc-name-size);
          font-weight: 600;
          color: var(--primary-text-color);
        }

        .clear-all-btn {
          background: transparent;
          border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
          border-radius: 6px;
          color: var(--primary-color);
          font-size: var(--autodoc-meta-size);
          padding: 4px 10px;
          cursor: pointer;
          transition: background var(--autodoc-transition-fast);
        }

        .clear-all-btn:hover {
          background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.08);
        }

        .suppression-item {
          display: flex;
          align-items: center;
          gap: var(--autodoc-spacing-sm);
          padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
          background: rgba(127, 127, 127, 0.06);
          border-radius: 8px;
          border-left: 3px solid var(--secondary-text-color);
        }

        .suppression-info {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 2px;
          overflow: hidden;
        }

        .suppression-automation {
          font-size: var(--autodoc-name-size);
          font-weight: 500;
          color: var(--primary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .suppression-detail {
          font-size: var(--autodoc-meta-size);
          color: var(--secondary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .restore-btn {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          padding: 0;
          background: transparent;
          border: none;
          border-radius: 50%;
          color: var(--secondary-text-color);
          cursor: pointer;
          transition:
            background var(--autodoc-transition-fast),
            color var(--autodoc-transition-fast);
        }

        .restore-btn:hover {
          background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.1);
          color: var(--primary-color);
        }
      `,
    ];
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "autodoc-suppressions": AutodocSuppressions;
  }
}
