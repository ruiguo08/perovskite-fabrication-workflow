# Result analysis

The result page keeps the uploaded J-V measurements, substrate assignments, and exclusion decisions together. Upload a CSV against a frozen fabrication batch, then assign every parsed substrate to a batch condition. J-V curves can be inspected before assignments are complete. Group statistics, distributions, and substrate uniformity require complete assignments.

## Metric provenance and scan selection

The parser retains every J-V trace and its sampling points. For each physical device and each scan direction, it uses the valid scan with the highest reported PCE as the representative for device-level analysis. Ties keep the first valid scan in file order. Forward and reverse values are never pooled into a single device metric.

Instrument-reported metrics take priority: the trailing per-scan summary table, then the in-block `[Statistic]` section or information rows when present. Recalculation from curve points is a fallback. Each trace records its metric source, so a reader can inspect how Voc, Jsc, FF, and PCE were obtained. The original CSV and every parsed scan remain available.

## Assignments and exclusions

Assignments map instrument substrate labels to the batch's frozen conditions. The page records device exclusions with a reason; exclusions do not delete measurements or remove J-V curves.

The automatic exclusion preset has one threshold per enabled metric, shared by forward and reverse scans. A direction fails if **any** enabled metric is below its threshold. A device is automatically excluded only when **both** directions fail. The failing metric can differ between directions. A missing direction is not automatically excluded and needs manual review. Manual exclusions remain possible and require a recorded reason.

Changing exclusions shows an **Unsaved analysis preview** until the selection is saved. The page offers Save and Discard controls. The filtered statistics and figures preview the current selection; exported filtered figures are disabled until that selection is saved.

## What each view counts

| View | Scope |
| --- | --- |
| J-V curves | All parsed devices and scans; the user can narrow the display to selected devices. Exclusions do not remove curves. |
| Directional group statistics | For each condition and scan direction, maximum, mean, and valid sample count for Voc, Jsc, FF, and PCE. Separate rows show all devices and devices after exclusions. |
| Metric distributions | Paired **All devices** and **Exclude flagged devices** figures. Forward and reverse scans are shown separately. |
| Substrate uniformity | Paired **All devices** and **Exclude flagged devices** figures for the selected metric and scan direction. Flagged cells remain visible as marked cells in the all-device view and are masked in the filtered view. Both figures share a color scale. |

The figure controls offer multiple palettes. Uniformity also accepts a minimum, maximum, and optional threshold for the color bar. Publication figures can be downloaded as SVG, PDF, or TIFF.

The all-device view is the stable reference for understanding a substrate's measured spatial pattern. The filtered view is useful for comparing the pattern after the recorded quality decision. Review both before drawing conclusions from a small or unevenly excluded group.
