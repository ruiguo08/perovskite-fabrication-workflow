import { describe, expect, it } from "vitest";
import { descriptiveStatistics } from "./stats";

describe("descriptiveStatistics", () => {
  it("mirrors the server's quartile and sample-sd conventions", () => {
    const stats = descriptiveStatistics([4, 1, 3, 2]);

    expect(stats.n).toBe(4);
    expect(stats.mean).toBeCloseTo(2.5, 12);
    expect(stats.median).toBeCloseTo(2.5, 12);
    // Linear-interpolation quartiles: positions 0.75 and 2.25 in the order.
    expect(stats.q1).toBeCloseTo(1.75, 12);
    expect(stats.q3).toBeCloseTo(3.25, 12);
    expect(stats.minimum).toBe(1);
    expect(stats.maximum).toBe(4);
    // Sample standard deviation (n-1 denominator).
    expect(stats.sd).toBeCloseTo(1.2909944487358056, 12);
  });

  it("returns sd 0 and the value itself for a single sample", () => {
    const stats = descriptiveStatistics([7.5]);

    expect(stats.n).toBe(1);
    expect(stats.mean).toBe(7.5);
    expect(stats.median).toBe(7.5);
    expect(stats.sd).toBe(0);
    expect(stats.minimum).toBe(7.5);
    expect(stats.maximum).toBe(7.5);
  });

  it("returns null statistics for an empty sample", () => {
    const stats = descriptiveStatistics([]);

    expect(stats.n).toBe(0);
    expect(stats.mean).toBeNull();
    expect(stats.median).toBeNull();
    expect(stats.sd).toBeNull();
    expect(stats.q1).toBeNull();
    expect(stats.q3).toBeNull();
  });
});
