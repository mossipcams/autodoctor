import { html, nothing, TemplateResult } from "lit";

/**
 * Render the badge row for the validation tab.
 * Shows error, warning, healthy, and suppressed counts.
 *
 * @param counts - Issue/status counts to display
 * @param onNavigate - Optional callback for navigation (e.g. to suppressions view)
 * @param activeView - Current active view ("issues" or "suppressions")
 */
export function renderBadges(
  counts: { errors: number; warnings: number; healthy: number; suppressed: number },
  onNavigate?: (view: "issues" | "suppressions") => void,
  activeView?: "issues" | "suppressions"
): TemplateResult {
  return html`
    <div class="badges-row">
      ${counts.errors > 0
        ? html`<span
            class="badge badge-error"
            title="${counts.errors} error${counts.errors !== 1 ? "s" : ""}"
          >
            <span class="badge-icon" aria-hidden="true">\u2715</span>
            <span class="badge-count">${counts.errors}</span>
          </span>`
        : nothing}
      ${counts.warnings > 0
        ? html`<span
            class="badge badge-warning"
            title="${counts.warnings} warning${counts.warnings !== 1 ? "s" : ""}"
          >
            <span class="badge-icon" aria-hidden="true">!</span>
            <span class="badge-count">${counts.warnings}</span>
          </span>`
        : nothing}
      ${counts.healthy > 0
        ? html`<span class="badge badge-healthy" title="${counts.healthy} healthy">
            <span class="badge-icon" aria-hidden="true">\u2713</span>
            <span class="badge-count">${counts.healthy}</span>
          </span>`
        : nothing}
      ${counts.suppressed > 0
        ? html`<span
            class="badge badge-suppressed ${activeView === "suppressions" ? "badge-active" : ""}"
            title="${counts.suppressed} suppressed"
            role="button"
            tabindex="0"
            @click=${() => onNavigate?.("suppressions")}
            @keydown=${(e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onNavigate?.("suppressions");
              }
            }}
            style="cursor: pointer;"
          >
            <span class="badge-icon" aria-hidden="true">\u2298</span>
            <span class="badge-count">${counts.suppressed}</span>
          </span>`
        : nothing}
    </div>
  `;
}
