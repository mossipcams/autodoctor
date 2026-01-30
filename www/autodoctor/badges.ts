import { html, nothing, TemplateResult } from "lit";

/**
 * Render the badge row for the validation tab.
 * Shows error, warning, healthy, and suppressed counts.
 *
 * @param counts - Issue/status counts to display
 * @param onClearSuppressions - Optional callback for the "clear suppressions" button
 */
export function renderBadges(
  counts: { errors: number; warnings: number; healthy: number; suppressed: number },
  onClearSuppressions?: () => void
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
      <span class="badge badge-healthy" title="${counts.healthy} healthy">
        <span class="badge-icon" aria-hidden="true">\u2713</span>
        <span class="badge-count">${counts.healthy}</span>
      </span>
      ${counts.suppressed > 0
        ? html`<span class="badge badge-suppressed" title="${counts.suppressed} suppressed">
            <span class="badge-icon" aria-hidden="true">\u2298</span>
            <span class="badge-count">${counts.suppressed}</span>
            <button
              class="clear-suppressions-btn"
              @click=${onClearSuppressions}
              title="Clear all suppressions"
              aria-label="Clear all suppressions"
            >
              \u2715
            </button>
          </span>`
        : nothing}
    </div>
  `;
}

/**
 * Render the badge row for the conflicts tab.
 * Shows error count, warning count, and suppressed count.
 * If no errors and no warnings, shows a "0 conflicts" healthy badge.
 */
export function renderConflictsBadges(
  errors: number,
  warnings: number,
  suppressed: number
): TemplateResult {
  return html`
    <div class="badges-row">
      ${errors > 0
        ? html`<span
            class="badge badge-error"
            title="${errors} conflict${errors !== 1 ? "s" : ""}"
          >
            <span class="badge-icon" aria-hidden="true">\u2715</span>
            <span class="badge-count">${errors}</span>
          </span>`
        : nothing}
      ${warnings > 0
        ? html`<span
            class="badge badge-warning"
            title="${warnings} warning${warnings !== 1 ? "s" : ""}"
          >
            <span class="badge-icon" aria-hidden="true">!</span>
            <span class="badge-count">${warnings}</span>
          </span>`
        : nothing}
      ${errors === 0 && warnings === 0
        ? html`<span class="badge badge-healthy" title="No conflicts">
            <span class="badge-icon" aria-hidden="true">\u2713</span>
            <span class="badge-count">0</span>
          </span>`
        : nothing}
      ${suppressed > 0
        ? html`<span class="badge badge-suppressed" title="${suppressed} suppressed">
            <span class="badge-icon" aria-hidden="true">\u2298</span>
            <span class="badge-count">${suppressed}</span>
          </span>`
        : nothing}
    </div>
  `;
}
