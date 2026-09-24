import { FormField } from "../../components/FormField";
import type { DeviceLayout, Material } from "../../types/api";
import type { ExperimentDraft } from "./types";

interface SubstratePanelProps {
  draft: ExperimentDraft;
  materials: Material[];
  layouts: DeviceLayout[];
  onChange: (draft: ExperimentDraft) => void;
  onLayoutChange: (layout: DeviceLayout) => void;
}

export function SubstratePanel({ draft, materials, layouts, onChange, onLayoutChange }: SubstratePanelProps) {
  // Students may use their own still-pending proposals: /api/materials already
  // scopes pending records to their submitter, so pending entries shown here
  // (and flagged in the label) are always the current user's own.
  const usable = (status: string) => status === "active" || status === "pending";
  const substrateMaterials = materials.filter((material) => usable(material.status) && material.category === "substrate");
  const selectedMaterial = substrateMaterials.find((material) => material.name === draft.substrate.material) ?? null;
  const products = selectedMaterial?.products.filter((product) => usable(product.status)) ?? [];
  const productValue = products.find((product) => product.vendor === draft.substrate.vendor && product.catalog_number === draft.substrate.type_number)?.id ?? "";
  const currentLayout = draft.conditions[0]?.device_layout_code ?? "";

  return (
    <section className="builder-panel" aria-labelledby="builder-substrate-title">
      <div className="builder-panel__heading"><div><span className="builder-panel__eyebrow">Step 2</span><h2 id="builder-substrate-title">Substrate and device layout</h2></div></div>
      <p className="builder-help">Supplier products come from the reusable material directory. A layout controls substrate dimensions and expected device counts.</p>
      <div className="builder-fields builder-fields--three">
        <FormField label="Substrate material" htmlFor="builder-substrate-material" required>
          <select
            id="builder-substrate-material"
            className="text-input"
            value={draft.substrate.material}
            onChange={(event) => onChange({ ...draft, substrate: { ...draft.substrate, material: event.target.value, vendor: "", type_number: "" } })}
          >
            <option value="">Choose a material…</option>
            {substrateMaterials.map((material) => <option key={material.id} value={material.name}>{material.name}{material.status === "pending" ? " (pending review)" : ""}</option>)}
          </select>
        </FormField>
        <FormField label="Supplier product" htmlFor="builder-substrate-product" required>
          <select
            id="builder-substrate-product"
            className="text-input"
            disabled={!selectedMaterial}
            value={productValue}
            onChange={(event) => {
              const product = products.find((item) => String(item.id) === event.target.value);
              onChange({ ...draft, substrate: { ...draft.substrate, vendor: product?.vendor ?? "", type_number: product?.catalog_number ?? "" } });
            }}
          >
            <option value="">Choose a supplier product…</option>
            {products.map((product) => <option key={product.id} value={product.id}>{product.vendor} · {product.catalog_number}{product.status === "pending" ? " (pending review)" : ""}</option>)}
          </select>
        </FormField>
        <FormField label="Device layout" htmlFor="builder-layout" required>
          <select id="builder-layout" className="text-input" value={currentLayout} onChange={(event) => { const layout = layouts.find((item) => item.code === event.target.value); if (layout) onLayoutChange(layout); }}>
            <option value="">Choose a layout…</option>
            {layouts.map((layout) => <option key={layout.code} value={layout.code}>{layout.description} · {layout.substrate_width_mm} × {layout.substrate_length_mm} mm</option>)}
          </select>
        </FormField>
      </div>
      <dl className="builder-facts">
        <div><dt>Footprint</dt><dd>{draft.substrate.width_mm || "—"} × {draft.substrate.length_mm || "—"} mm</dd></div>
        <div><dt>Devices per substrate</dt><dd>{layouts.find((layout) => layout.code === currentLayout)?.devices_per_substrate ?? "—"}</dd></div>
        <div><dt>Catalog source</dt><dd>{draft.substrate.vendor && draft.substrate.type_number ? `${draft.substrate.vendor} · ${draft.substrate.type_number}` : "Not selected"}</dd></div>
      </dl>
    </section>
  );
}
