import { LitElement, html, CSSResultGroup, TemplateResult, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { autodocTokens, pipelineStyles } from "./styles.js";
import type { ValidationGroup } from "./types.js";

@customElement("autodoc-pipeline")
export class AutodocPipeline extends LitElement {
  @property({ attribute: false }) groups: ValidationGroup[] = [];
  @property({ type: Boolean }) running = false;

  static styles: CSSResultGroup = [autodocTokens, pipelineStyles];

  protected render(): TemplateResult {
    return html`
      <div class="pipeline" role="region" aria-label="Validation pipeline">
        ${this.groups.map((group, i) => this._renderGroup(group, i))}
        ${!this.running && this.groups.length > 0
          ? this._renderSummary()
          : nothing}
      </div>
    `;
  }

  private _renderGroup(group: ValidationGroup, index: number): TemplateResult {
    const staggerMs = this.running ? 0 : index * 150;
    return html`
      <div
        class="pipeline-group ${this.running ? "running" : group.status}"
        style="animation-delay: ${staggerMs}ms"
      >
        <div class="group-header">
          <div class="group-status-icon" aria-hidden="true">
            ${this.running
              ? html`<div class="group-spinner" role="status" aria-label="Validating ${group.label}"></div>`
              : this._statusIcon(group.status)}
          </div>
          <span class="group-label">${group.label}</span>
          ${!this.running ? this._renderCounts(group) : nothing}
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
        style="animation-delay: ${this.groups.length * 150}ms"
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
