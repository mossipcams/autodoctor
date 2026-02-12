export interface ValidationIssue {
  issue_type: string | null;
  severity: string;
  automation_id: string;
  automation_name: string;
  entity_id: string;
  location: string;
  message: string;
  suggestion: string | null;
  valid_states: string[];
}

export interface FixSuggestion {
  description: string;
  confidence: number;
  fix_value: string | null;
  fix_type?: "replace_value" | "reference";
  current_value?: string | null;
  suggested_value?: string | null;
  reason?: string;
}

export interface IssueWithFix {
  issue: ValidationIssue;
  fix: FixSuggestion | null;
  edit_url: string;
}

export interface AutodoctorCardConfig {
  type: string;
  title?: string;
}

export interface AutomationGroup {
  automation_id: string;
  automation_name: string;
  issues: IssueWithFix[];
  edit_url: string;
  has_error: boolean;
  error_count: number;
  warning_count: number;
}

export interface ValidationGroup {
  id: string;
  label: string;
  status: "pass" | "warning" | "fail";
  error_count: number;
  warning_count: number;
  issue_count: number;
  issues: IssueWithFix[];
  duration_ms: number;
}

export interface StepsResponse {
  groups: ValidationGroup[];
  issues: IssueWithFix[];
  healthy_count: number;
  last_run: string | null;
  suppressed_count: number;
  analyzed_automations?: number;
  failed_automations?: number;
  skip_reasons?: Record<string, Record<string, number>>;
}

export interface SuppressionEntry {
  key: string;
  automation_id: string;
  automation_name: string;
  entity_id: string;
  issue_type: string;
  message: string;
}

export interface SuppressionsResponse {
  suppressions: SuppressionEntry[];
}

export function getSuggestionKey(issue: ValidationIssue): string {
  return `${issue.automation_id}:${issue.entity_id}:${issue.message}`;
}
