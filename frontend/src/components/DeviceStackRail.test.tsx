import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeviceStackRail } from "./DeviceStackRail";

describe("DeviceStackRail", () => {
  it("renders the substrate above the layers in order", () => {
    render(
      <DeviceStackRail
        substrate="ITO"
        layers={[
          { name: "NiOx", role: "htl", layerType: "niox" },
          { name: "Perovskite", role: "perovskite", layerType: "perovskite" },
          { name: "C60", role: "etl", layerType: "c60" },
          { name: "Ag", role: "top_electrode", layerType: "ag" },
        ]}
      />,
    );

    const rail = screen.getByRole("list", { name: "Device stack" });
    const items = rail.querySelectorAll("li");
    expect(items).toHaveLength(5);
    expect(items[0]).toHaveTextContent("ITO");
    expect(items[1]).toHaveTextContent("NiOx");
    expect(items[2]).toHaveTextContent("Perovskite");
    expect(items[3]).toHaveTextContent("C60");
    expect(items[4]).toHaveTextContent("Ag");
  });

  it("renders human-readable role labels", () => {
    render(
      <DeviceStackRail
        layers={[
          { name: "Perovskite", role: "perovskite", layerType: "perovskite" },
        ]}
      />,
    );
    expect(screen.getByText("perovskite", { selector: ".stack-rail__role" })).toBeInTheDocument();
  });
});