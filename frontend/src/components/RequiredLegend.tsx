/** Explains the required/optional markers used across the builder forms so
 * students can tell which fields block saving and which can keep defaults. */
export function RequiredLegend() {
  return (
    <p className="builder-legend">
      Fields marked <span aria-hidden="true">*</span> or{" "}
      <span className="field-marker field-marker--required">required</span> must be filled in
      before saving. Groups marked <span className="field-marker">optional</span> can be left
      empty or keep their defaults.
    </p>
  );
}
