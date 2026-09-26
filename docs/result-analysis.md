# Result analysis

The result page keeps the uploaded J-V measurements, substrate assignments, and exclusion decisions together. Upload a CSV against a frozen fabrication batch, then assign every parsed substrate to a batch condition. J-V curves can be inspected before assignments are complete. Group statistics, distributions, and substrate uniformity require complete assignments.

## Metric provenance and scan selection

The parser retains every J-V trace and its sampling points. For each physical device and each scan direction, it uses the valid scan with the highest reported PCE as the representative for device-level analysis. Ties keep the first valid scan in file order. Forward and reverse values are never pooled into a single device metric.

Instrument-reported metrics take priority: the trailing per-scan summary table, then the in-block `[Statistic]` section or information rows when present. Recalculation from curve points is a fallback. Each trace records its metric source, so a reader can inspect how Voc, Jsc, FF, and PCE were obtained. The original CSV and every parsed scan remain available.

## Assignments and exclusions

Assignments map instrument substrate labels to the batch's frozen conditions. The first save writes the complete mapping. A later change requires a correction reason and records the old and new condition in the audit log. A laser mark can be rebound to a substrate in the corrected condition only if no other result file uses its old physical device binding. Assignment edits and manual exclusion edits have separate Save controls. Manual exclusions and their reasons are stored in the analysis and audit log; no exclusion deletes measurements or removes J-V curves.

The automatic threshold filter has one threshold per enabled metric, shared by forward and reverse scans. A direction fails if **any** enabled metric is below its threshold. A device matches the filter only when **both** directions fail. The failing metric can differ between directions. A missing direction does not match and needs manual review. Thresholds and automatic matches exist only in the current browser analysis view; they are never saved as device exclusions. A manual reason takes priority when the same device also matches a threshold.

Changing manual exclusions shows an **Unsaved analysis preview** until saved. The filtered statistics and figures preview the current selection; filtered figure downloads stay disabled while manual edits are pending. Applied thresholds change the current filtered view without a save and can be cleared independently. Figure downloads reflect the active list of filtered device IDs; record the thresholds separately when using exported images in a publication.

## What each view counts

| View | Scope |
| --- | --- |
| J-V curves | All parsed devices and scans; the user can narrow the display to selected devices. Exclusions do not remove curves. |
| Directional group statistics | For each condition and scan direction, maximum, mean, and valid sample count for Voc, Jsc, FF, and PCE. Separate rows show all devices and devices after exclusions. |
| Metric distributions | Paired **All devices** and **Exclude flagged devices** figures. Forward and reverse scans are shown separately. |
| Substrate uniformity | Paired **All devices** and **Exclude flagged devices** figures for the selected metric and scan direction. Flagged cells remain visible as marked cells in the all-device view and are masked in the filtered view. Both figures share a color scale. |

The figure controls offer multiple palettes. Uniformity also accepts a minimum, maximum, and optional threshold for the color bar. Publication figures can be downloaded as SVG, PDF, or TIFF.

The all-device view is the stable reference for understanding a substrate's measured spatial pattern. The filtered view is useful for comparing the pattern after the recorded quality decision. Review both before drawing conclusions from a small or unevenly excluded group.

## Deferred data export work

The legacy flat `result_files.metrics` cache and training-data export still pool scan directions and may repeat a physical device across uploads. They are retained for compatibility in this change and must not be used for direction-specific scientific statistics. Before training-data export is used, replace the pooled record with explicit forward/reverse fields and deduplicate physical devices across files. No real CSV has been uploaded to the deployed database, so this release does not include a historical-data backfill.
