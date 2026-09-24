export interface StackLayer {
  name: string;
  role: string;
  layerType: string;
}

const ROLE_TONE: Record<string, string> = {
  htl: "stack-rail__item--htl",
  buried_interface_modifier: "stack-rail__item--interface",
  perovskite: "stack-rail__item--perovskite",
  top_passivation: "stack-rail__item--passivation",
  etl: "stack-rail__item--etl",
  top_electrode: "stack-rail__item--electrode",
};

function roleLabel(role: string, layerType: string): string {
  if (role) {
    return role.replace(/_/g, " ");
  }
  return layerType.replace(/_/g, " ");
}

interface DeviceStackRailProps {
  substrate?: string;
  layers: StackLayer[];
}

/**
 * Signature compact vertical representation of a device stack: substrate on
 * top, then transport, absorber, electrode, and encapsulation layers in
 * functional order.
 */
export function DeviceStackRail({ substrate, layers }: DeviceStackRailProps) {
  return (
    <ol className="stack-rail" aria-label="Device stack">
      <li className="stack-rail__item stack-rail__item--substrate">
        <span className="stack-rail__name">{substrate ?? "Substrate"}</span>
        <span className="stack-rail__role">substrate</span>
      </li>
      {layers.map((layer, index) => (
        <li
          key={`${layer.layerType}-${index}`}
          className={`stack-rail__item ${ROLE_TONE[layer.role] ?? ""}`.trim()}
        >
          <span className="stack-rail__name">{layer.name}</span>
          <span className="stack-rail__role">
            {roleLabel(layer.role, layer.layerType)}
          </span>
        </li>
      ))}
    </ol>
  );
}