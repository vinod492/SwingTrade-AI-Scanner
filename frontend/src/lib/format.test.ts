import { describe, expect, it } from "vitest";

import { fmtPct, fmtPrice, fmtVol, fmtX, scoreColor } from "./format";

describe("format", () => {
  it("formats prices", () => {
    expect(fmtPrice(123.456)).toBe("123.46");
    expect(fmtPrice(1234.5)).toBe("1,235");
    expect(fmtPrice(null)).toBe("—");
  });

  it("formats percentages with sign", () => {
    expect(fmtPct(3.2)).toBe("+3.20%");
    expect(fmtPct(-1.5)).toBe("-1.50%");
    expect(fmtPct(2.5, false)).toBe("2.50%");
    expect(fmtPct(undefined)).toBe("—");
  });

  it("abbreviates volume", () => {
    expect(fmtVol(1_234_567)).toBe("1.2M");
    expect(fmtVol(2_500_000_000)).toBe("2.50B");
    expect(fmtVol(999)).toBe("999");
    expect(fmtVol(45_000)).toBe("45K");
  });

  it("formats multiples", () => {
    expect(fmtX(2.34)).toBe("2.3x");
    expect(fmtX(null)).toBe("—");
  });

  it("maps score to heat colors", () => {
    expect(scoreColor(90)).toBe("var(--color-gain-500)");
    expect(scoreColor(55)).toBe("var(--color-amber-flag)");
    expect(scoreColor(10)).toBe("var(--color-ink-400)");
  });
});
