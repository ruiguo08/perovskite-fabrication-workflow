import type { ReactNode } from "react";
import { fieldMeta } from "../lib/fields";
import { formatNumber, scaleMetric } from "../lib/format";

interface QuantityRowProps {
  /** Registry key (provides label/unit/digits/scale). */
  name: string;
  value: number | null | undefined;
  /** Override the display label. */
  label?: string;
  /** Override the display precision. */
  digits?: number;
}

/** A read-only label · value · unit row, driven by the field registry. */
export function QuantityRow({ name, value, label, digits }: QuantityRowProps) {
  const meta = fieldMeta(name);
  const text = formatNumber(scaleMetric(name, value), digits ?? meta.digits ?? 2);
  const labelText = label ?? meta.label ?? name;
  return (
    <div className="quantity-row">
      <span className="quantity-row__label">{labelText}</span>
      <span className="quantity-row__value numeric-cell">{text}</span>
      {meta.unit ? <span className="quantity-row__unit">{meta.unit}</span> : null}
    </div>
  );
}

interface QuantityListProps {
  title?: string;
  children: ReactNode;
}

/** A grouped set of read-only quantity rows. */
export function QuantityList({ title, children }: QuantityListProps) {
  return (
    <div className="quantity-list">
      {title ? <h4 className="quantity-list__title">{title}</h4> : null}
      {children}
    </div>
  );
}
