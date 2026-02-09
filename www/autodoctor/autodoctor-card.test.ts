import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
    expect(callWS).toHaveBeenCalledTimes(2);

    card.remove();
  });
});
