import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JsonObjectField } from "./JsonObjectField";

describe("JsonObjectField", () => {
  it("emits parsed objects when the JSON is valid", () => {
    const onTextChange = vi.fn();
    const onValidChange = vi.fn();
    const onValidityChange = vi.fn();
    render(
      <JsonObjectField
        id="specification"
        label="Specification"
        value="{}"
        onTextChange={onTextChange}
        onValidChange={onValidChange}
        onValidityChange={onValidityChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("Specification"), {
      target: { value: '{"purity":"99.99%"}' },
    });

    expect(onTextChange).toHaveBeenCalledWith('{"purity":"99.99%"}');
    expect(onValidChange).toHaveBeenCalledWith({ purity: "99.99%" });
    expect(onValidityChange).toHaveBeenLastCalledWith(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    ["an array", "[]", "Specification must be a JSON object."],
    ["a scalar", '"electronic grade"', "Specification must be a JSON object."],
    ["invalid JSON", "{purity}", "Specification must be valid JSON."],
  ])("rejects %s", (_caseName, value, message) => {
    const onValidChange = vi.fn();
    const onValidityChange = vi.fn();
    render(
      <JsonObjectField
        id="specification"
        label="Specification"
        value="{}"
        onTextChange={() => undefined}
        onValidChange={onValidChange}
        onValidityChange={onValidityChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("Specification"), {
      target: { value },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(onValidChange).not.toHaveBeenCalled();
    expect(onValidityChange).toHaveBeenLastCalledWith(false);
  });
});
