import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { AutodoctorCard } from "./autodoctor-card.ts";
import type { StepsResponse } from "./types.js";

function makeResponse(): StepsResponse {
  return {
    groups: [],
    issues: [],
    healthy_count: 0,
    last_run: null,
    suppressed_count: 0,
  };
}

function makeCard() {
  const card = new AutodoctorCard() as any;
  card.config = { type: "custom:autodoctor-card" };
  card.hass = {
    callWS: vi.fn().mockResolvedValue(makeResponse()),
  };
  return card;
}

describe("AutodoctorCard cooldown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("blocks rapid clicks and re-enables the rendered button after cooldown", async () => {
    const card = makeCard();
    const callWS = card.hass.callWS as ReturnType<typeof vi.fn>;
    card._loading = false;
    card._validationData = makeResponse();

    document.body.appendChild(card);
    await card.updateComplete;
    callWS.mockClear();

    await card._runValidation();
    await card._runValidation();
    expect(callWS).toHaveBeenCalledTimes(1);

    await card.updateComplete;
    let runBtn = card.shadowRoot?.querySelector(".run-btn") as HTMLButtonElement;
    expect(runBtn.disabled).toBe(true);

    vi.advanceTimersByTime((AutodoctorCard as any).CLICK_COOLDOWN_MS + 1);
    await vi.runOnlyPendingTimersAsync();
    expect(card._cooldownUntil).toBe(0);
    await card.updateComplete;
    runBtn = card.shadowRoot?.querySelector(".run-btn") as HTMLButtonElement;
    expect(runBtn.disabled).toBe(false);

    await card._runValidation();
    const runStepCalls = callWS.mock.calls.filter(
      (call: any[]) => call[0]?.type === "autodoctor/validation/run_steps"
    );
    expect(runStepCalls).toHaveLength(2);

    card.remove();
  });
});

describe("AutodoctorCard undo fix", () => {
  it("shows undo button and calls websocket undo action", async () => {
    const card = new AutodoctorCard() as any;
    card.config = { type: "custom:autodoctor-card" };
    const callWS = vi.fn().mockImplementation((msg: { type: string }) => {
      if (msg.type === "autodoctor/fix_undo") {
        return Promise.resolve({ undone: true });
      }
      return Promise.resolve(makeResponse());
    });
    card.hass = { callWS };
    card._loading = false;
    card._validationData = makeResponse();
    card._canUndoLastFix = true;

    document.body.appendChild(card);
    await card.updateComplete;

    const undoBtn = card.shadowRoot?.querySelector(".undo-btn") as HTMLButtonElement;
    expect(undoBtn).toBeTruthy();
    undoBtn.click();
    await Promise.resolve();
    await card.updateComplete;

    expect(callWS).toHaveBeenCalledWith({ type: "autodoctor/fix_undo" });
    expect(card._canUndoLastFix).toBe(false);
    card.remove();
  });
});

describe("AutodoctorCard runtime health telemetry", () => {
  it("uses analyzed_automations in all-healthy subtitle", async () => {
    const card = makeCard();
    card._loading = false;
    card._validationData = {
      ...makeResponse(),
      healthy_count: 47,
      analyzed_automations: 0,
      last_run: "2026-02-12T10:00:00+00:00",
    };

    document.body.appendChild(card);
    await card.updateComplete;

    const subtitle = card.shadowRoot?.querySelector(".healthy-subtitle");
    expect(subtitle?.textContent).toContain("0 automations analyzed");
    card.remove();
  });
});

describe("AutodoctorCard build parity", () => {
  it("compiled_card_version_matches_package_version", () => {
    const packageJson = JSON.parse(
      readFileSync(resolve(process.cwd(), "package.json"), "utf-8"),
    ) as { version: string };
    const compiledCard = readFileSync(
      resolve(
        process.cwd(),
        "../../custom_components/autodoctor/www/autodoctor-card.js",
      ),
      "utf-8",
    );

    expect(compiledCard).toContain(
      `const CARD_VERSION = "${packageJson.version}";`,
    );
  });
});
