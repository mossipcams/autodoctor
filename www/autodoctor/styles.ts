import { css } from "lit";

/**
 * Design tokens and host styles shared by all autodoctor components.
 * Every component should include this in its styles array.
 */
export const autodocTokens = css`
  :host {
    /* Typography */
    --autodoc-title-size: 1.1rem;
    --autodoc-name-size: 0.95rem;
    --autodoc-issue-size: 0.875rem;
    --autodoc-meta-size: 0.8rem;

    /* Colors */
    --autodoc-error: #d94848;
    --autodoc-warning: #c49008;
    --autodoc-success: #2e8b57;

    /* Spacing */
    --autodoc-spacing-xs: 4px;
    --autodoc-spacing-sm: 8px;
    --autodoc-spacing-md: 12px;
    --autodoc-spacing-lg: 16px;
    --autodoc-spacing-xl: 24px;

    /* Transitions */
    --autodoc-transition-fast: 150ms ease;
    --autodoc-transition-normal: 200ms ease;
  }

  @media (prefers-reduced-motion: reduce) {
    :host {
      --autodoc-transition-fast: 0ms;
      --autodoc-transition-normal: 0ms;
    }
  }

  :host {
    display: block;
    width: 100%;
    box-sizing: border-box;
  }

  /* Mobile: larger text for readability */
  @media (max-width: 600px) {
    :host {
      --autodoc-title-size: 1.25rem;
      --autodoc-name-size: 1.05rem;
      --autodoc-issue-size: 1rem;
      --autodoc-meta-size: 0.9rem;
    }
  }
`;

/**
 * Badge row styles: error/warning/healthy/suppressed pills with counts.
 */
export const badgeStyles = css`
  /* Badges row (in content area) */
  .badges-row {
    display: flex;
    gap: var(--autodoc-spacing-sm);
    margin-bottom: var(--autodoc-spacing-md);
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: var(--autodoc-meta-size);
    font-weight: 600;
    transition: transform var(--autodoc-transition-fast);
    cursor: default;
  }

  .badge:hover {
    transform: scale(1.05);
  }

  .badge-icon {
    font-size: 0.7em;
  }

  .badge-error {
    background: rgba(217, 72, 72, 0.15);
    color: var(--autodoc-error);
  }

  .badge-warning {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }

  .badge-healthy {
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
  }

  .badge-suppressed {
    background: rgba(127, 127, 127, 0.15);
    color: var(--secondary-text-color);
    margin-left: auto;
  }

  .badge-active {
    outline: 2px solid var(--primary-color);
    outline-offset: 1px;
  }

  /* Mobile: larger tap targets for badges */
  @media (max-width: 600px) {
    .badge {
      padding: 6px 12px;
      font-size: var(--autodoc-issue-size);
      min-height: 36px;
    }

    .badge-icon {
      font-size: 1em;
    }

    .badges-row {
      flex-wrap: wrap;
    }
  }

`;

/**
 * Issue group styles: automation group container, issues, fix suggestions,
 * confidence pills, suppress/dismiss buttons, edit links.
 */
export const issueGroupStyles = css`
  /* Automation groups */
  .automation-group {
    background: rgba(127, 127, 127, 0.06);
    border-left: 3px solid var(--autodoc-error);
    border-radius: 0 8px 8px 0;
    padding: var(--autodoc-spacing-md);
    margin-bottom: var(--autodoc-spacing-md);
  }

  .automation-group:last-child {
    margin-bottom: 0;
  }

  .automation-group.has-warning {
    border-left-color: var(--autodoc-warning);
  }

  .automation-header {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
  }

  .automation-severity-icon {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(217, 72, 72, 0.15);
    color: var(--autodoc-error);
    border-radius: 50%;
    font-size: 0.7rem;
    font-weight: bold;
  }

  .automation-group.has-warning .automation-severity-icon {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }

  .automation-name {
    flex: 1;
    font-size: var(--autodoc-name-size);
    font-weight: 600;
    color: var(--primary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .automation-badge {
    background: var(--autodoc-error);
    color: #fff;
    font-size: var(--autodoc-meta-size);
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    min-width: 18px;
    text-align: center;
  }

  .automation-group.has-warning .automation-badge {
    background: var(--autodoc-warning);
  }

  /* Issues */
  .automation-issues {
    margin-top: var(--autodoc-spacing-md);
    padding-left: 28px;
  }

  .issue {
    padding: var(--autodoc-spacing-sm) 0;
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.15));
  }

  .issue:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .issue-header {
    display: flex;
    align-items: flex-start;
    gap: var(--autodoc-spacing-sm);
  }

  .issue-icon {
    flex-shrink: 0;
    font-size: 0.65rem;
    font-weight: bold;
    margin-top: 3px;
  }

  .issue.error .issue-icon {
    color: var(--autodoc-error);
  }

  .issue.warning .issue-icon {
    color: var(--autodoc-warning);
  }

  .issue-message {
    flex: 1;
    font-size: var(--autodoc-issue-size);
    color: var(--secondary-text-color);
    line-height: 1.4;
    word-break: break-word;
  }

  .suppress-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: var(--secondary-text-color);
    font-size: 0.75rem;
    cursor: pointer;
    opacity: 0.6;
    transition:
      opacity var(--autodoc-transition-fast),
      background var(--autodoc-transition-fast);
  }

  .suppress-btn:hover {
    opacity: 1;
    background: var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .suppress-btn:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 1px;
    opacity: 1;
  }

  /* Fix suggestions */
  .fix-suggestion {
    display: flex;
    align-items: flex-start;
    gap: var(--autodoc-spacing-sm);
    margin-top: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    background: var(--primary-background-color, rgba(255, 255, 255, 0.5));
    border-radius: 6px;
  }

  .fix-icon {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
  }

  .fix-content {
    flex: 1;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
  }

  .fix-description {
    font-size: var(--autodoc-issue-size);
    color: var(--primary-text-color);
    line-height: 1.4;
  }

  .confidence-pill {
    display: inline-block;
    font-size: var(--autodoc-meta-size);
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 10px;
  }

  .confidence-pill.high {
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
  }

  .confidence-pill.medium {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }

  .dismiss-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: var(--secondary-text-color);
    font-size: 0.7rem;
    cursor: pointer;
    opacity: 0.6;
    transition:
      opacity var(--autodoc-transition-fast),
      background var(--autodoc-transition-fast);
  }

  .dismiss-btn:hover {
    opacity: 1;
    background: var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .dismiss-btn:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 1px;
    opacity: 1;
  }

  /* Edit link */
  .edit-link {
    display: inline-flex;
    align-items: center;
    gap: var(--autodoc-spacing-xs);
    margin-top: var(--autodoc-spacing-md);
    margin-left: 28px;
    color: var(--primary-color);
    text-decoration: none;
    font-size: var(--autodoc-issue-size);
    transition: gap var(--autodoc-transition-fast);
  }

  .edit-link:hover {
    text-decoration: underline;
    gap: var(--autodoc-spacing-sm);
  }

  .edit-link:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
    border-radius: 2px;
  }

  .edit-arrow {
    transition: transform var(--autodoc-transition-fast);
  }

  .edit-link:hover .edit-arrow {
    transform: translateX(2px);
  }

  /* Mobile: suppress/dismiss label visibility */
  .suppress-label,
  .dismiss-label {
    display: none;
  }

  /* Mobile: touch-friendly issue groups */
  @media (max-width: 600px) {
    .automation-issues {
      padding-left: 16px;
    }

    .automation-severity-icon {
      width: 24px;
      height: 24px;
      font-size: 0.8rem;
    }

    /* Suppress button: show label, 44px touch target */
    .suppress-btn {
      width: auto;
      min-width: 44px;
      min-height: 44px;
      padding: 8px 10px;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 6px;
      opacity: 0.7;
    }

    .suppress-label {
      display: inline;
      font-size: var(--autodoc-meta-size);
    }

    /* Dismiss button: 44px touch target */
    .dismiss-btn {
      width: auto;
      min-width: 44px;
      min-height: 44px;
      padding: 8px 10px;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 6px;
    }

    .dismiss-label {
      display: inline;
      font-size: var(--autodoc-meta-size);
    }

    .issue-icon {
      font-size: 0.75rem;
    }

    .edit-link {
      margin-left: 16px;
      min-height: 44px;
      display: inline-flex;
      align-items: center;
    }

    .fix-suggestion {
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-sm);
    }
  }
`;

/**
 * Card layout styles: ha-card shell, header, tabs, content area,
 * loading/error/empty/healthy states, footer with run button.
 */
export const cardLayoutStyles = css`
  ha-card {
    overflow: hidden;
    width: 100%;
    box-sizing: border-box;
    position: relative;
  }

  /* Header */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--autodoc-spacing-lg);
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .title {
    margin: 0;
    font-size: var(--autodoc-title-size);
    font-weight: 600;
    color: var(--primary-text-color);
  }

  /* Card content */
  .card-content {
    padding: var(--autodoc-spacing-lg);
  }

  /* Loading state */
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--autodoc-spacing-xl);
    gap: var(--autodoc-spacing-md);
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--divider-color, rgba(127, 127, 127, 0.3));
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .loading-text {
    color: var(--secondary-text-color);
    font-size: var(--autodoc-issue-size);
  }

  /* Error state */
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--autodoc-spacing-xl);
    gap: var(--autodoc-spacing-md);
    text-align: center;
  }

  .error-icon {
    font-size: 2rem;
    color: var(--autodoc-error);
  }

  .error-text {
    color: var(--autodoc-error);
    font-size: var(--autodoc-issue-size);
  }

  .retry-btn {
    margin-top: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-lg);
    background: transparent;
    color: var(--primary-color);
    border: 1px solid var(--primary-color);
    border-radius: 6px;
    font-size: var(--autodoc-issue-size);
    cursor: pointer;
    transition:
      background var(--autodoc-transition-fast),
      color var(--autodoc-transition-fast);
  }

  .retry-btn:hover {
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
  }

  /* Empty state */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--autodoc-spacing-xl);
  }

  .empty-text {
    color: var(--secondary-text-color);
    font-size: var(--autodoc-issue-size);
  }

  /* All healthy state */
  .all-healthy {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-md);
    padding: var(--autodoc-spacing-lg);
    background: rgba(46, 139, 87, 0.08);
    border-radius: 8px;
  }

  .healthy-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
    border-radius: 50%;
    font-size: 1.25rem;
    font-weight: bold;
  }

  .healthy-message {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .healthy-title {
    font-size: var(--autodoc-name-size);
    font-weight: 600;
    color: var(--autodoc-success);
  }

  .healthy-subtitle {
    font-size: var(--autodoc-meta-size);
    color: var(--secondary-text-color);
  }

  /* Footer */
  .footer {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-md);
    padding: var(--autodoc-spacing-md) var(--autodoc-spacing-lg);
    border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .run-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
    border: none;
    border-radius: 6px;
    font-size: var(--autodoc-issue-size);
    font-weight: 500;
    cursor: pointer;
    transition:
      opacity var(--autodoc-transition-fast),
      transform var(--autodoc-transition-fast);
  }

  .run-btn:hover:not(:disabled) {
    opacity: 0.9;
    transform: translateY(-1px);
  }

  .run-btn:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .run-btn:disabled {
    cursor: not-allowed;
    opacity: 0.7;
  }

  .run-icon {
    font-size: 0.8rem;
  }

  .run-btn.running .run-icon {
    animation: spin 1s linear infinite;
  }

  .last-run {
    color: var(--secondary-text-color);
    font-size: var(--autodoc-meta-size);
  }

  /* Mobile responsive */
  @media (max-width: 600px) {
    .card-content {
      padding: var(--autodoc-spacing-md);
    }

    .header {
      padding: var(--autodoc-spacing-md);
    }

    .footer {
      padding: var(--autodoc-spacing-md);
      flex-wrap: wrap;
    }

    .run-btn {
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-lg);
      font-size: var(--autodoc-name-size);
      min-height: 44px;
    }

    .run-icon {
      font-size: 0.9rem;
    }

    .retry-btn {
      min-height: 44px;
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-xl);
      font-size: var(--autodoc-name-size);
    }
  }

  /* Toast notification */
  .toast {
    position: absolute;
    bottom: 60px;
    left: 50%;
    transform: translateX(-50%) translateY(8px);
    background: var(--primary-text-color);
    color: var(--card-background-color, #fff);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: var(--autodoc-meta-size);
    font-weight: 500;
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--autodoc-transition-normal), transform var(--autodoc-transition-normal);
    z-index: 10;
    white-space: nowrap;
  }

  .toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }

`;

/**
 * Pipeline styles: validation group panels with neutral/active/result states,
 * JS-driven stagger transitions, summary rollup bar, and
 * three-state (pass/warning/fail) visual treatment.
 */
export const pipelineStyles = css`
  .pipeline {
    display: flex;
    flex-direction: column;
    gap: var(--autodoc-spacing-sm);
    margin-bottom: var(--autodoc-spacing-lg);
  }

  /* Individual group panel -- JS controls visibility via state classes */
  .pipeline-group {
    display: flex;
    align-items: center;
    padding: var(--autodoc-spacing-md);
    border-radius: 8px;
    background: rgba(127, 127, 127, 0.06);
    border-left: 3px solid transparent;
    opacity: 1;
    transition: opacity 200ms ease, border-color 200ms ease, background-color 200ms ease, box-shadow 200ms ease;
  }

  /* Neutral: dimmed "waiting" state before this group is checked */
  .pipeline-group.neutral {
    opacity: 0.45;
    border-left-color: transparent;
    background: rgba(127, 127, 127, 0.04);
  }

  /* Active: highlighted state -- the primary running indicator */
  .pipeline-group.active {
    opacity: 1;
    border-left: 3px solid var(--primary-color);
    background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.08);
    box-shadow: 0 0 0 1px rgba(var(--rgb-primary-color, 66, 133, 244), 0.15);
  }

  /* Status-specific left border (result states) */
  .pipeline-group.pass {
    border-left: 3px solid var(--autodoc-success);
  }
  .pipeline-group.warning {
    border-left: 3px solid var(--autodoc-warning);
  }
  .pipeline-group.fail {
    border-left: 3px solid var(--autodoc-error);
  }

  .group-header {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-md);
    width: 100%;
  }

  /* Status icon circle */
  .group-status-icon {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 0.85rem;
    font-weight: bold;
    flex-shrink: 0;
  }

  .pipeline-group.active .group-status-icon {
    background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.15);
    color: var(--primary-color);
  }

  .pipeline-group.pass .group-status-icon {
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
  }
  .pipeline-group.warning .group-status-icon {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }
  .pipeline-group.fail .group-status-icon {
    background: rgba(217, 72, 72, 0.15);
    color: var(--autodoc-error);
  }

  /* Active dot indicator (replaces spinner) */
  .active-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary-color);
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.75); }
  }

  .group-label {
    flex: 1;
    font-size: var(--autodoc-name-size);
    font-weight: 600;
    color: var(--primary-text-color);
  }

  .group-count {
    font-size: var(--autodoc-meta-size);
    font-weight: 500;
  }
  .group-count.pass-text { color: var(--autodoc-success); }
  .group-count.warning-text { color: var(--autodoc-warning); }
  .group-count.fail-text { color: var(--autodoc-error); }

  /* Summary rollup bar -- visibility controlled by JS _showSummary */
  .pipeline-summary {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    border-radius: 6px;
    font-size: var(--autodoc-issue-size);
    font-weight: 500;
    opacity: 1;
    transition: opacity 200ms ease;
  }

  .pipeline-summary.pass {
    background: rgba(46, 139, 87, 0.08);
    color: var(--autodoc-success);
  }
  .pipeline-summary.warning {
    background: rgba(196, 144, 8, 0.08);
    color: var(--autodoc-warning);
  }
  .pipeline-summary.fail {
    background: rgba(217, 72, 72, 0.08);
    color: var(--autodoc-error);
  }

  /* Respect reduced motion -- CSS layer (JS layer skips stagger loop separately) */
  @media (prefers-reduced-motion: reduce) {
    .pipeline-group,
    .pipeline-summary {
      transition: none;
    }
    .active-dot {
      animation: none;
    }
  }
`;
