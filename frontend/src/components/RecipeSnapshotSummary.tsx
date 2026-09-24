import type { ConditionDeviceConfiguration, PerovskiteDepositionProcess } from "../types/api";
import { DeviceStackRail } from "./DeviceStackRail";

interface RecipeSnapshotSummaryProps {
  // The condition-owned device configuration (also satisfied by a full
  // DeviceRecipe, e.g. a baseline revision).
  deviceRecipe: ConditionDeviceConfiguration;
  depositionProcess: PerovskiteDepositionProcess | null;
}

export function RecipeSnapshotSummary({
  deviceRecipe,
  depositionProcess,
}: RecipeSnapshotSummaryProps) {
  const substrate = deviceRecipe.substrate;
  return (
    <div className="recipe-summary">
      <DeviceStackRail
        substrate={`${substrate.material} · ${substrate.vendor} · ${substrate.type_number}`}
        layers={deviceRecipe.layers.map((layer) => ({
          name: layer.name,
          role: layer.role,
          layerType: layer.layer_type,
        }))}
      />
      <dl className="recipe-summary__metadata">
        <div><dt>Junction</dt><dd>{deviceRecipe.junction_type.replace(/_/g, " ")}</dd></div>
        <div><dt>Bandgap</dt><dd>{deviceRecipe.perovskite_bandgap?.replace(/_/g, " ") ?? "Not recorded"}</dd></div>
        <div><dt>Recipe schema</dt><dd>{deviceRecipe.schema_version}</dd></div>
        <div><dt>Perovskite process</dt><dd>{depositionProcess?.method.replace(/_/g, " ") ?? "Not recorded"}</dd></div>
      </dl>
    </div>
  );
}
