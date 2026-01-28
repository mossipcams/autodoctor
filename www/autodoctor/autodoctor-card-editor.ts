import { LitElement, html, css, CSSResultGroup, TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import type { AutodoctorCardConfig } from "./types";

@customElement("autodoctor-card-editor")
export class AutodoctorCardEditor extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _config!: AutodoctorCardConfig;

  public setConfig(config: AutodoctorCardConfig): void {
    this._config = config;
  }

  private _valueChanged(ev: CustomEvent): void {
    if (!this._config || !this.hass) {
      return;
    }

    const target = ev.target as HTMLInputElement;
    const newConfig = {
      ...this._config,
      [target.id]: target.value || undefined,
    };

    // Remove undefined values
    Object.keys(newConfig).forEach((key) => {
      if (newConfig[key as keyof AutodoctorCardConfig] === undefined) {
        delete newConfig[key as keyof AutodoctorCardConfig];
      }
    });

    const event = new CustomEvent("config-changed", {
      detail: { config: newConfig },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  protected render(): TemplateResult {
    if (!this.hass || !this._config) {
      return html``;
    }

    return html`
      <div class="card-config">
        <div class="config-row">
          <label for="title">Title (optional)</label>
          <input
            id="title"
            type="text"
            .value=${this._config.title || ""}
            @input=${this._valueChanged}
            placeholder="Automation Health"
          />
        </div>
      </div>
    `;
  }

  static get styles(): CSSResultGroup {
    return css`
      .card-config {
        padding: 16px;
      }

      .config-row {
        display: flex;
        flex-direction: column;
        margin-bottom: 16px;
      }

      label {
        font-weight: 500;
        margin-bottom: 4px;
        color: var(--primary-text-color);
      }

      input {
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
      }

      input:focus {
        outline: none;
        border-color: var(--primary-color);
      }
    `;
  }
}
