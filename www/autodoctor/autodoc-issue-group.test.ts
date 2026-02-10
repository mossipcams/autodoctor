import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { AutodocIssueGroup } from "./autodoc-issue-group";
import type { AutomationGroup } from "./types";

function makeGroup(): AutomationGroup {
  return {
    automation_id: "automation.test",
    automation_name: "Test automation",
    edit_url: "/config/automation/edit/test",
    has_error: true,
    error_count: 1,
    warning_count: 0,
    issues: [
      {
        issue: {
          issue_type: "case_mismatch",
          severity: "warning",
          automation_id: "automation.test",
          automation_name: "Test automation",
          entity_id: "light.Living_Room",
          location: "trigger[0].entity_id",
          message: "Case mismatch",
          suggestion: "light.living_room",
          valid_states: [],
        },
        fix: {
          description: "Did you mean 'light.living_room'?",
          confidence: 0.9,
          fix_value: "light.living_room",
          fix_type: "replace_value",
          current_value: "light.Living_Room",
          suggested_value: "light.living_room",
          reason: "Case mismatch detected.",
        },
        edit_url: "/config/automation/edit/test",
      },
    ],
  };
}

describe("AutodocIssueGroup", () => {
  const originalClipboard = navigator.clipboard;
  const writeText = vi.fn();

  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
  });

  afterEach(() => {
    writeText.mockReset();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: originalClipboard,
    });
  });

  it("renders concrete before/after replacement details", async () => {
    const el = new AutodocIssueGroup();
    el.group = makeGroup();
    document.body.appendChild(el);
    await el.updateComplete;

    const content = el.shadowRoot?.textContent || "";
    expect(content).toContain("light.Living_Room");
    expect(content).toContain("light.living_room");

    el.remove();
  });

  it("copies suggested value to clipboard", async () => {
    writeText.mockResolvedValue(undefined);
    const el = new AutodocIssueGroup();
    el.group = makeGroup();
    document.body.appendChild(el);
    await el.updateComplete;

    const btn = el.shadowRoot?.querySelector(".copy-fix-btn") as HTMLButtonElement;
    btn.click();

    expect(writeText).toHaveBeenCalledWith("light.living_room");
    el.remove();
  });
});
