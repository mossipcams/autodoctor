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

function makeGroupWithoutEditUrl(): AutomationGroup {
  return {
    ...makeGroup(),
    edit_url: null,
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

  it("renders dismiss button for runtime overactive issues", async () => {
    const group = makeGroup();
    group.issues[0].issue.issue_type = "runtime_automation_overactive";
    const el = new AutodocIssueGroup();
    el.group = group;
    document.body.appendChild(el);
    await el.updateComplete;

    const btn = el.shadowRoot?.querySelector(".dismiss-runtime-btn") as HTMLButtonElement;
    expect(btn).not.toBeNull();

    const events: CustomEvent[] = [];
    el.addEventListener("dismiss-runtime-issue", (e) => events.push(e as CustomEvent));
    btn.click();
    expect(events).toHaveLength(1);
    expect(events[0].detail.issue.issue_type).toBe("runtime_automation_overactive");

    el.remove();
  });

  it("does not render dismiss button for non-runtime issues", async () => {
    const el = new AutodocIssueGroup();
    el.group = makeGroup(); // issue_type is "case_mismatch"
    document.body.appendChild(el);
    await el.updateComplete;

    const btn = el.shadowRoot?.querySelector(".dismiss-runtime-btn");
    expect(btn).toBeNull();

    el.remove();
  });

  it("dismiss-runtime-btn has styles defined", () => {
    const sheets = (AutodocIssueGroup as any).styles as import("lit").CSSResult[];
    const css = sheets.map((s: any) => s.cssText).join("");
    expect(css).toContain(".dismiss-runtime-btn");
  });

  it("does not render edit link when edit_url is missing", async () => {
    const el = new AutodocIssueGroup();
    el.group = makeGroupWithoutEditUrl();
    document.body.appendChild(el);
    await el.updateComplete;

    const link = el.shadowRoot?.querySelector(".edit-link");
    expect(link).toBeNull();
    el.remove();
  });
});
