import { useState } from "react";
import type { AnalysisDevice } from "../types/api";

export function DeviceMultiSelect({ devices, selected, onChange }: {
  devices: AnalysisDevice[];
  selected: Set<string>;
  onChange: (ids: Set<string>) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = devices.filter((device) =>
    `${device.device_id} ${device.device_mark ?? ""} ${device.substrate_id} ${device.label}`.toLowerCase().includes(query.toLowerCase()),
  );
  return <details className="device-picker" onKeyDown={(event) => {
    if (event.key === "Escape") {
      event.currentTarget.open = false;
      event.currentTarget.querySelector("summary")?.focus();
    }
  }}>
    <summary>Choose devices ({selected.size} selected)</summary>
    <div className="device-picker__menu">
      <input className="text-input" aria-label="Search devices" placeholder="Device / substrate…"
        value={query} onChange={(event) => setQuery(event.target.value)} />
      <div className="device-picker__options">
        {visible.map((device) => <label key={device.device_id}>
          <input type="checkbox" aria-label={`Choose device ${device.device_id}`} checked={selected.has(device.device_id)}
            onChange={(event) => {
              const next = new Set(selected);
              if (event.target.checked) next.add(device.device_id); else next.delete(device.device_id);
              onChange(next);
            }} />
          {device.device_id} · {device.label}
          {device.excluded ? " (excluded from statistics)" : ""}
        </label>)}
        {!visible.length && <p>No matching devices.</p>}
      </div>
    </div>
  </details>;
}
