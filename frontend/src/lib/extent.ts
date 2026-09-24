/**
 * Extremes of a numeric list, computed with a loop. Trace arrays from
 * measurement files are unbounded (a 10 MB upload can hold hundreds of
 * thousands of points), so `Math.max(...values)` spread calls risk a
 * RangeError; a loop never does.
 */
export function extentOf(
  ...valueLists: ReadonlyArray<Iterable<number>>
): { minimum: number; maximum: number } {
  let minimum = Infinity;
  let maximum = -Infinity;
  for (const values of valueLists) {
    for (const value of values) {
      if (value < minimum) minimum = value;
      if (value > maximum) maximum = value;
    }
  }
  return { minimum, maximum };
}
