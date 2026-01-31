import { describe, it, expect, vi } from "vitest";
import { render } from "lit";
import { renderBadges } from "./badges.js";

function renderToContainer(
  counts: { errors: number; warnings: number; healthy: number; suppressed: number },
  onNavigate?: (view: "issues" | "suppressions") => void,
  activeView?: "issues" | "suppressions"
): HTMLDivElement {
  const container = document.createElement("div");
  render(renderBadges(counts, onNavigate, activeView), container);
  return container;
}

describe("renderBadges", () => {
  it("clicking healthy badge in suppressions view calls onNavigate with 'issues'", () => {
    const onNavigate = vi.fn();
    const counts = { errors: 0, warnings: 0, healthy: 5, suppressed: 3 };
    const el = renderToContainer(counts, onNavigate, "suppressions");
    const healthyBadge = el.querySelector(".badge-healthy") as HTMLElement;
    healthyBadge.click();
    expect(onNavigate).toHaveBeenCalledWith("issues");
  });

  it("clicking error badge in suppressions view navigates back to issues", () => {
    const onNavigate = vi.fn();
    const counts = { errors: 2, warnings: 0, healthy: 0, suppressed: 3 };
    const el = renderToContainer(counts, onNavigate, "suppressions");
    const errorBadge = el.querySelector(".badge-error") as HTMLElement;
    errorBadge.click();
    expect(onNavigate).toHaveBeenCalledWith("issues");
  });

  it("clicking suppressed badge in suppressions view toggles back to issues", () => {
    const onNavigate = vi.fn();
    const counts = { errors: 0, warnings: 0, healthy: 5, suppressed: 3 };
    const el = renderToContainer(counts, onNavigate, "suppressions");
    const suppBadge = el.querySelector(".badge-suppressed") as HTMLElement;
    suppBadge.click();
    expect(onNavigate).toHaveBeenCalledWith("issues");
  });

  it("issue badges have cursor pointer when in suppressions view", () => {
    const counts = { errors: 1, warnings: 1, healthy: 5, suppressed: 3 };
    const el = renderToContainer(counts, vi.fn(), "suppressions");
    const healthyBadge = el.querySelector(".badge-healthy") as HTMLElement;
    const errorBadge = el.querySelector(".badge-error") as HTMLElement;
    expect(healthyBadge.style.cursor).toBe("pointer");
    expect(errorBadge.style.cursor).toBe("pointer");
  });
});
