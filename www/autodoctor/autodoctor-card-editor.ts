import { LitElement, html, css, CSSResultGroup, TemplateResult } from "lit";
import { HomeAssistant } from "custom-card-helpers";

import type { AutodoctorCardConfig } from "./types.js";

export class AutodoctorCardEditor extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };

  public hass!: HomeAssistant;
  private _config!: AutodoctorCardConfig;

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
        <ha-textfield
          id="title"
          label="Title (optional)"
          .value=${this._config.title || ""}
          @change=${this._valueChanged}
          placeholder="Automation Health"
        ></ha-textfield>
      </div>
    `;
  }

  static get styles(): CSSResultGroup {
    return css`
      .card-config {
        padding: 16px;
      }
      ha-textfield {
        display: block;
      }
    `;
  }
}

if (!customElements.get("autodoctor-card-editor")) {
  customElements.define("autodoctor-card-editor", AutodoctorCardEditor);
}
