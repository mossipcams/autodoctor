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
}

export interface IssueWithFix {
  issue: ValidationIssue;
  fix: FixSuggestion | null;
  edit_url: string;
}

export interface AutodoctorData {
  issues: IssueWithFix[];
  healthy_count: number;
}

export interface AutodoctorCardConfig {
  type: string;
  title?: string;
}

export type TabType = "validation" | "conflicts";

export interface AutodoctorTabData {
  issues: IssueWithFix[];
  healthy_count: number;
  last_run: string | null;
  suppressed_count: number;
}

export interface Conflict {
  entity_id: string;
  automation_a: string;
  automation_b: string;
  action_a: string;
  action_b: string;
  severity: string;
  explanation: string;
  scenario: string;
}

export interface ConflictsTabData {
  conflicts: Conflict[];
  last_run: string | null;
  suppressed_count: number;
}
