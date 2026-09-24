import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/Toast";
import { ResultDetailPage } from "./ResultDetailPage";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ apiFetch: apiFetchMock }));

function makeDevices(substrateId: string, groupId: string) {
  return [
    {
      device_id: `device-${substrateId}-1`,
      label: `${substrateId}.Forward`,
      device_mark: null,
      substrate_id: substrateId,
      group_id: groupId,
      metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce: 10 }, reverse: null },
      traces: [
        { trace_id: "t1", label: `${substrateId}.Forward`, direction: "forward", measured_at: null, valid: true, error: null, metrics: { voc: 1, jsc: 20, ff: 0.5, pce: 10 }, points: [[0, -20], [1, 0]] },
      ],
    },
  ];
}

function makeDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 42,
    experiment_id: 7,
    fabrication_batch_id: 5,
    filename: "run-001.csv",
    content_type: "text/csv",
    size_bytes: 2048,
    sha256: "a".repeat(64),
    group_assignment: "",
    metrics: { pce: 10.2 },
    analysis_schema_version: 2,
    created_by_id: 2,
    created_at: "2026-08-14T08:00:00Z",
    groups: [
      { group_id: "control", batch_condition_id: 21, condition_code: "C", kind: "control", name: "Control" },
      { group_id: "target-1", batch_condition_id: 22, condition_code: "T1", kind: "target", name: "ADH" },
    ],
    assignments: [],
    analysis: {
      schema_version: 2,
      devices: [...makeDevices("sample-1", ""), ...makeDevices("sample-2", "")],
      substrates: [
        { substrate_id: "sample-1", device_ids: ["device-sample-1-1"], instrument_labels: ["sample-1.Forward"], group_id: "", batch_condition_id: undefined },
        { substrate_id: "sample-2", device_ids: ["device-sample-2-1"], instrument_labels: ["sample-2.Forward"], group_id: "", batch_condition_id: undefined },
      ],
      summary: { voc: 1, jsc: 20, ff: 0.5, pce: 10, trace_count: 2, valid_trace_count: 2, device_count: 2 },
      statistics: {},
    },
    ...overrides,
  } as unknown as Record<string, unknown>;
}

function renderPage(resultId = "42") {
  return render(
    <MemoryRouter initialEntries={[`/results/${resultId}`]}>
      <ToastProvider>
        <Routes>
          <Route path="/results/:resultId" element={<ResultDetailPage />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

async function renderReadyDetail() {
  renderPage();
  await screen.findByText("run-001.csv");
  // Drain pending passive-effect flushes (assignment/exclusion prefill) so a
  // late prefill cannot wipe user edits made by the very next interaction.
  // Under parallel-worker load findByText's act scope can return between the
  // detail commit and its passive effects, which made the exclusion test
  // flaky: the prefill's empty Maps overwrote the just-toggled checkbox.
  await act(async () => {});
}

function openSection(name: string) {
  fireEvent.click(within(screen.getByRole("navigation", { name: "Result sections" })).getByRole("button", { name: new RegExp(name, "i") }));
}

function openFigure(name: string) {
  fireEvent.click(within(screen.getByRole("navigation", { name: "Figure types" })).getByRole("button", { name: new RegExp(name, "i") }));
}

function openExclusions() {
  fireEvent.click(screen.getByText(/Device exclusions/, { selector: "summary" }));
}

function openDetails(name: string) {
  fireEvent.click(screen.getByText(new RegExp(name, "i"), { selector: "summary" }));
}

describe("ResultDetailPage", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if ((options?.method ?? "GET") === "GET" && path === "/api/results/42") {
        return makeDetail();
      }
      if ((options?.method ?? "GET") === "GET" && path === "/api/results/42/assignments") {
        return [];
      }
      return undefined;
    });
  });

  it("shows the header with integrity metadata and provenance", async () => {
    await renderReadyDetail();
    expect(screen.getByText("run-001.csv")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Experiment" })).toHaveAttribute("href", "/experiments/7");
    openSection("Data & provenance");
    expect(screen.getByText(/a{16}/)).toBeInTheDocument(); // sha256 preview
    expect(screen.getByText("2048 bytes")).toBeInTheDocument();
    expect(screen.getByText("Schema v2")).toBeInTheDocument();
    expect(within(screen.getByRole("heading", { name: /Integrity & provenance/i }).closest("section")!).getByText("2")).toBeInTheDocument(); // created_by_id
  });

  it("shows an unavailable provenance value when created_by_id is null", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") return makeDetail({ created_by_id: null });
      if (path === "/api/results/42/assignments") return [];
      return undefined;
    });
    await renderReadyDetail();
    openSection("Data & provenance");
    expect(screen.getByText(/unavailable|not available|unknown/i)).toBeInTheDocument();
  });

  it("preselects the batch condition only from analysis.substrates", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown[]>).substrates = [
          { substrate_id: "sample-1", device_ids: ["device-sample-1-1"], instrument_labels: ["sample-1.Forward"], group_id: "control", batch_condition_id: 21 },
          { substrate_id: "sample-2", device_ids: ["device-sample-2-1"], instrument_labels: ["sample-2.Forward"], group_id: "target-1", batch_condition_id: 22 },
        ];
        return detail;
      }
      if (path === "/api/results/42/assignments") return [];
      return undefined;
    });
    await renderReadyDetail();
    const select1 = (await screen.findByLabelText(/Assign sample-1 to/)) as HTMLSelectElement;
    const select2 = screen.getByLabelText(/Assign sample-2 to/) as HTMLSelectElement;
    await waitFor(() => expect(select1.value).toBe("21"), { timeout: 5000 });
    expect(select2.value).toBe("22");
  });

  it("disables submit until every substrate has a batch condition", async () => {
    await renderReadyDetail();
    expect(screen.getByRole("button", { name: /Save assignments/i })).toBeDisabled();
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    expect(screen.getByRole("button", { name: /Save assignments/i })).toBeEnabled();
  });

  it("shows one result section and one figure type at a time", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    expect(within(screen.getByRole("navigation", { name: "Result sections" })).getAllByRole("button").map((button) => button.textContent?.trim())).toEqual([
      "Assignments0/2", "Statistics", "Figures", "Data & provenance",
    ]);
    expect(within(screen.getByRole("navigation", { name: "Result sections" })).getByRole("button", { name: /Assignments/i }))
      .toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("heading", { name: "Publication substrate uniformity" })).not.toBeInTheDocument();
    openSection("Figures");
    expect(screen.getByRole("heading", { name: "Publication J–V curves" })).toBeInTheDocument();
    openFigure("Uniformity");
    expect(screen.getByRole("heading", { name: "Publication substrate uniformity" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Publication J–V curves" })).not.toBeInTheDocument();
    openSection("Data & provenance");
    expect(screen.getByRole("heading", { name: /Integrity & provenance/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Publication substrate uniformity" })).not.toBeInTheDocument();
  });

  it("keeps the J–V device selection when switching figure types", async () => {
    await renderReadyDetail();
    openSection("Figures");
    fireEvent.click(screen.getByText("Choose devices (0 selected)"));
    fireEvent.click(screen.getByLabelText("Choose device device-sample-1-1"));
    expect(screen.getByText("Choose devices (1 selected)")).toBeInTheDocument();
    openFigure("Uniformity");
    openFigure("J–V curves");
    expect(screen.getByText("Choose devices (1 selected)")).toBeInTheDocument();
  });

  it("keeps the J–V device selection when visiting another result section", async () => {
    await renderReadyDetail();
    openSection("Figures");
    fireEvent.click(screen.getByText("Choose devices (0 selected)"));
    fireEvent.click(screen.getByLabelText("Choose device device-sample-1-1"));
    openSection("Data & provenance");
    openSection("Figures");
    expect(screen.getByText("Choose devices (1 selected)")).toBeInTheDocument();
  });

  it("opens saved results on figures without loading every publication image", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    expect(within(screen.getByRole("navigation", { name: "Result sections" })).getByRole("button", { name: /Assignments/i }))
      .toHaveAttribute("aria-pressed", "true");
    openSection("Figures");
    expect(screen.getByRole("heading", { name: "Publication J–V curves" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /publication box plot/i })).not.toBeInTheDocument();
    openFigure("Distributions");
    expect(screen.getAllByRole("img", { name: /publication box plot/i })).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Metric"), { target: { value: "ff" } });
    for (const figure of screen.getAllByRole("img", { name: /FF .*publication box plot/i })) {
      expect(figure).toHaveAttribute("src", expect.stringContaining("metric=ff"));
    }
  });

  it("requires manual conditions for instrument-named substrates", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown[]>).substrates = [
          { substrate_id: "Control-1", device_ids: [], instrument_labels: [], group_id: "" },
          { substrate_id: "T1-6", device_ids: [], instrument_labels: [], group_id: "" },
        ];
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    const controlNamed = screen.getByLabelText("Assign Control-1 to") as HTMLSelectElement;
    const targetNamed = screen.getByLabelText("Assign T1-6 to") as HTMLSelectElement;
    expect(controlNamed.value).toBe("");
    expect(targetNamed.value).toBe("");
    fireEvent.change(controlNamed, { target: { value: "22" } });
    fireEvent.change(targetNamed, { target: { value: "21" } });
    expect(controlNamed.value).toBe("22");
    expect(targetNamed.value).toBe("21");
    expect(screen.getByRole("button", { name: /Save assignments/i })).toBeEnabled();
  });

  it("posts the exact assignment payload with complete substrate IDs", async () => {
    await renderReadyDetail();
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: /Save assignments/i }));
    await waitFor(
      () => {
        const call = apiFetchMock.mock.calls.find(
          (c) => c[0] === "/api/results/42/assignments" && c[1]?.method === "POST",
        );
        expect(call?.[1]?.body).toEqual({
          assignments: [
            { analysis_substrate_id: "sample-1", batch_condition_id: 21 },
            { analysis_substrate_id: "sample-2", batch_condition_id: 22 },
          ],
          exclusions: [],
        });
      },
      { timeout: 5000 },
    );
  });

  it("selects one scan direction for substrate uniformity and updates downloads", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Figures");
    openFigure("Uniformity");
    const section = screen.getByRole("heading", { name: "Publication substrate uniformity" }).closest("section")!;
    expect(within(section).getAllByRole("img")).toHaveLength(2);
    for (const figure of within(section).getAllByRole("img")) {
      expect(figure).toHaveAttribute("src", expect.stringContaining("direction=forward"));
    }
    fireEvent.change(within(section).getByLabelText("Scan direction"), { target: { value: "reverse" } });
    for (const figure of within(section).getAllByRole("img")) {
      expect(figure).toHaveAttribute("src", expect.stringContaining("direction=reverse"));
    }
    for (const link of within(section).getAllByRole("link", { name: "SVG" })) {
      expect(link).toHaveAttribute("href", expect.stringContaining("direction=reverse"));
    }
    fireEvent.change(within(section).getByLabelText("Color palette"), { target: { value: "rainbow" } });
    for (const figure of within(section).getAllByRole("img")) {
      expect(figure).toHaveAttribute("src", expect.stringContaining("palette=rainbow"));
    }
    for (const link of within(section).getAllByRole("link", { name: "SVG" })) {
      expect(link).toHaveAttribute("href", expect.stringContaining("palette=rainbow"));
    }
  });

  it("applies a categorical palette to both distribution scopes and downloads", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Figures");
    openFigure("Distributions");
    const section = screen.getByRole("heading", { name: "Metric distributions" }).closest("section")!;
    fireEvent.change(within(section).getByLabelText("Color palette"), { target: { value: "science-tol" } });
    for (const figure of within(section).getAllByRole("img")) {
      expect(figure).toHaveAttribute("src", expect.stringContaining("palette=science-tol"));
    }
    for (const link of within(section).getAllByRole("link", { name: "PDF" })) {
      expect(link).toHaveAttribute("href", expect.stringContaining("palette=science-tol"));
    }
  });

  it("applies a manual uniformity range and problem threshold to both scopes and downloads", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Figures");
    openFigure("Uniformity");
    const section = screen.getByRole("heading", { name: "Publication substrate uniformity" }).closest("section")!;
    fireEvent.change(within(section).getByLabelText("Metric"), { target: { value: "voc" } });
    fireEvent.change(within(section).getByLabelText("Color bar minimum"), { target: { value: "1.15" } });
    fireEvent.change(within(section).getByLabelText("Color bar maximum"), { target: { value: "1.0" } });
    fireEvent.click(within(section).getByRole("button", { name: "Apply color range" }));
    expect(within(section).getByRole("alert")).toHaveTextContent("minimum must be lower");
    expect(within(section).getAllByRole("img")[0].getAttribute("src")).not.toContain("scale_min=");
    fireEvent.change(within(section).getByLabelText("Color bar minimum"), { target: { value: "1.0" } });
    fireEvent.change(within(section).getByLabelText("Color bar maximum"), { target: { value: "1.15" } });
    fireEvent.change(within(section).getByLabelText("Problem threshold"), { target: { value: "1.10" } });
    fireEvent.click(within(section).getByRole("button", { name: "Apply color range" }));
    for (const figure of within(section).getAllByRole("img")) {
      expect(figure.getAttribute("src")).toContain("scale_min=1");
      expect(figure.getAttribute("src")).toContain("scale_max=1.15");
      expect(figure.getAttribute("src")).toContain("threshold=1.1");
    }
    for (const link of within(section).getAllByRole("link", { name: "PDF" })) {
      expect(link.getAttribute("href")).toContain("threshold=1.1");
    }
    fireEvent.click(within(section).getByRole("button", { name: "Reset color range" }));
    for (const figure of within(section).getAllByRole("img")) {
      expect(figure.getAttribute("src")).not.toContain("scale_min=");
      expect(figure.getAttribute("src")).not.toContain("threshold=");
    }
  });

  it("requires saved assignments before opening statistical figures", async () => {
    await renderReadyDetail();
    openSection("Figures");
    expect(screen.getByRole("button", { name: "Uniformity" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Distributions" })).toBeDisabled();
  });

  it("shows both uniformity scopes with separate figure downloads", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        const rows = (detail.analysis as { devices: Array<{ excluded?: boolean }> }).devices;
        rows[0].excluded = true;
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Figures");
    openFigure("Uniformity");
    const all = screen.getByRole("group", { name: "All devices" });
    const filtered = screen.getByRole("group", { name: /Exclude flagged devices \(1\)/i });
    expect(within(all).getByRole("img")).toHaveAttribute("src", expect.stringContaining("preview_exclusions=true"));
    expect(within(all).getByRole("img")).not.toHaveAttribute("src", expect.stringContaining("excluded_device_id="));
    expect(within(filtered).getByRole("img")).toHaveAttribute("src", expect.stringContaining("excluded_device_id=device-sample-1-1"));
    expect(within(all).getByRole("link", { name: "SVG" })).not.toHaveAttribute("href", expect.stringContaining("excluded_device_id="));
    expect(within(filtered).getByRole("link", { name: "SVG" })).toHaveAttribute("href", expect.stringContaining("excluded_device_id=device-sample-1-1"));
  });

  it("collapses device assignment after a successful save and can reopen it", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      if (path === "/api/results/42/assignments" && options?.method === "POST") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Figures");
    openFigure("Uniformity");
    const uniformityBefore = within(screen.getByRole("group", { name: "All devices" })).getByRole("img").getAttribute("src");
    openSection("Assignments");
    fireEvent.click(screen.getByRole("button", { name: /Edit assignments/i }));
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: /Save assignments/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Statistics/i })).toHaveAttribute("aria-pressed", "true"));
    openSection("Figures");
    expect(within(screen.getByRole("group", { name: "All devices" })).getByRole("img").getAttribute("src")).not.toBe(uniformityBefore);
    openSection("Assignments");
    const edit = await screen.findByRole("button", { name: /Edit assignments/i });
    expect(screen.queryByLabelText(/Assign sample-1 to/i)).not.toBeInTheDocument();
    fireEvent.click(edit);
    expect(screen.getByLabelText(/Assign sample-1 to/i)).toBeInTheDocument();
  });

  it("posts device exclusions with reasons alongside the assignments", async () => {
    await renderReadyDetail();
    openExclusions();
    fireEvent.click(screen.getByRole("checkbox", { name: "Exclude device-sample-1-1" }));
    fireEvent.change(screen.getByLabelText("Exclusion reason for device-sample-1-1"), {
      target: { value: "Voc < 0.7 V" },
    });
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: "Save condition and exclusion changes" }));
    await waitFor(
      () => {
        const call = apiFetchMock.mock.calls.find(
          (c) => c[0] === "/api/results/42/assignments" && c[1]?.method === "POST",
        );
        expect(call?.[1]?.body.exclusions).toEqual([
          { analysis_device_id: "device-sample-1-1", reason: "Voc < 0.7 V" },
        ]);
      },
      { timeout: 5000 },
    );
  });

  it("offers a save action when exclusions change after analysis was saved", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = { groups: [], comparisons: [] };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Assignments");
    openExclusions();
    expect(screen.queryByRole("button", { name: "Save condition and exclusion changes" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Exclude device-sample-1-1" }));
    expect(screen.getByRole("button", { name: "Save condition and exclusion changes" })).toBeInTheDocument();
  });

  it("updates publication box plots from the pending exclusion selection", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = {
          groups: [{
            group_id: "control", name: "Control", kind: "control",
            device_count: 2, valid_device_count: 2,
            metrics: { pce: { n: 2, mean: 10, median: 10, sd: 0, minimum: 10, q1: 10, q3: 10, maximum: 10 } },
          }],
          comparisons: [],
        };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    openSection("Figures");
    openFigure("Distributions");
    const boxplot = within(screen.getByRole("group", { name: "All devices" })).getByRole("img", { name: /PCE .*publication box plot/i });
    expect(boxplot).toHaveAttribute("src", expect.stringContaining("preview_exclusions=true"));
    openSection("Assignments");
    openExclusions();
    fireEvent.click(screen.getByRole("checkbox", { name: "Exclude device-sample-1-1" }));
    openSection("Figures");
    await waitFor(() => {
      expect(within(screen.getByRole("group", { name: /Exclude flagged devices \(1\)/i })).getByRole("img", { name: /PCE .*publication box plot/i })).toHaveAttribute(
        "src",
        expect.stringContaining("excluded_device_id=device-sample-1-1"),
      );
    });
    expect(within(screen.getByRole("group", { name: "All devices" })).getByRole("img")).not.toHaveAttribute(
      "src", expect.stringContaining("excluded_device_id="),
    );
    openFigure("Uniformity");
    expect(within(screen.getByRole("group", { name: /Exclude flagged devices \(1\)/i })).getByRole("img", { name: /Publication substrate uniformity/i })).toHaveAttribute(
      "src",
      expect.stringContaining("excluded_device_id=device-sample-1-1"),
    );
  });

  it("preserves complete long substrate IDs without truncation", async () => {
    const longId = "instrument-extended-identification-" + "z".repeat(90);
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).substrates = [{ substrate_id: longId, device_ids: [], instrument_labels: [], group_id: "" }];
        (detail.analysis as Record<string, unknown[]>).devices = [];
        return detail;
      }
      if (path === "/api/results/42/assignments") return [];
      return undefined;
    });
    await renderReadyDetail();
    fireEvent.change(screen.getByLabelText(/Assign .* to/i), { target: { value: "21" } });
    fireEvent.click(screen.getByRole("button", { name: /Save assignments/i }));
    // Slow CI runners need more than waitFor's 1s default for the POST round
    // trip through the React state update.
    await waitFor(
      () => {
        const call = apiFetchMock.mock.calls.find(
          (c) => c[0] === "/api/results/42/assignments" && c[1]?.method === "POST",
        );
        expect(call?.[1]?.body.assignments[0].analysis_substrate_id).toBe(longId);
      },
      { timeout: 5000 },
    );
  });

  it("shows an inconsistency notice when device rows disagree with each other", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        return { ...makeDetail(), assignments: [
          { id: 1, result_file_id: 42, analysis_device_id: "device-sample-1-1", analysis_substrate_id: "sample-1", instrument_label: "sample-1.Forward", fabrication_device_id: null, device_code: null, device_mark: null, substrate_id: null, substrate_code: null, substrate_mark: null, batch_condition_id: 21, source_condition_id: 11, condition_code: "C", condition_name: "Control", created_at: "2026-08-14T08:00:00Z" },
          { id: 2, result_file_id: 42, analysis_device_id: "device-sample-1-1", analysis_substrate_id: "sample-1", instrument_label: "sample-1.Forward", fabrication_device_id: null, device_code: null, device_mark: null, substrate_id: null, substrate_code: null, substrate_mark: null, batch_condition_id: 22, source_condition_id: 12, condition_code: "T1", condition_name: "ADH", created_at: "2026-08-14T08:00:00Z" },
        ] };
      }
      return undefined;
    });
    await renderReadyDetail();
    expect(await screen.findByText(/inconsisten/i)).toBeInTheDocument();
  });

  it("shows an inconsistency notice when device rows disagree with the substrate assignment", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/results/42") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown[]>).substrates = [
          { substrate_id: "sample-1", device_ids: ["device-sample-1-1"], instrument_labels: ["sample-1.Forward"], group_id: "control", batch_condition_id: 21 },
          { substrate_id: "sample-2", device_ids: ["device-sample-2-1"], instrument_labels: ["sample-2.Forward"], group_id: "", batch_condition_id: undefined },
        ];
        (detail as Record<string, unknown>).assignments = [
          { id: 1, result_file_id: 42, analysis_device_id: "device-sample-1-1", analysis_substrate_id: "sample-1", instrument_label: "sample-1.Forward", fabrication_device_id: null, device_code: null, device_mark: null, substrate_id: null, substrate_code: null, substrate_mark: null, batch_condition_id: 22, source_condition_id: 12, condition_code: "T1", condition_name: "ADH", created_at: "2026-08-14T08:00:00Z" },
        ];
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    expect(await screen.findByText(/inconsisten/i)).toBeInTheDocument();
  });

  it("replaces local state with the full POST response including statistics", async () => {
    let posted = false;
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") {
        if (posted) {
          const detail = makeDetail();
          (detail.analysis as Record<string, unknown>).statistics = {
            groups: [{ group_id: "control", name: "Control", kind: "control", device_count: 1, valid_device_count: 1, metrics: { pce: { n: 1, mean: 10, median: 10, sd: 0, minimum: 10, q1: 10, q3: 10, maximum: 10 } } }],
            comparisons: [],
          };
          return detail;
        }
        return makeDetail();
      }
      if (path === "/api/results/42/assignments" && (options?.method ?? "GET") === "GET") return [];
      if (path === "/api/results/42/assignments" && options?.method === "POST") {
        posted = true;
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = {
          groups: [{ group_id: "control", name: "Control", kind: "control", device_count: 1, valid_device_count: 1, metrics: { pce: { n: 1, mean: 10, median: 10, sd: 0, minimum: 10, q1: 10, q3: 10, maximum: 10 } } }],
          comparisons: [],
        };
        return detail;
      }
      return undefined;
    });
    await renderReadyDetail();
    expect(screen.queryByText(/Group statistics/i)).not.toBeInTheDocument();
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: /Save assignments/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Statistics" })).toBeEnabled());
    openSection("Statistics");
    expect(await screen.findByText(/Group statistics/i)).toBeInTheDocument();
  });

  it("shows a 404 state when the result is not found", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("result file not found"));
    renderPage();
    expect(await screen.findByText(/not found|could not be loaded/i)).toBeInTheDocument();
  });

  it("shows an API error with retry on a load failure", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("results unavailable"));
    renderPage();
    expect(await screen.findByText("Unable to load result")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("ignores an old-route assignment response after navigation", async () => {
    let resolveAssign!: (value: unknown) => void;
    const deferred = new Promise((resolve) => { resolveAssign = resolve; });
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") return makeDetail();
      if (path === "/api/results/42/assignments" && (options?.method ?? "GET") === "GET") return [];
      if (path === "/api/results/42/assignments" && options?.method === "POST") return deferred;
      return undefined;
    });
    function Nav() {
      const navigate = useNavigate();
      return <button type="button" onClick={() => navigate("/results/99")}>nav</button>;
    }
    render(
      <MemoryRouter initialEntries={["/results/42"]}>
        <ToastProvider>
          <Nav />
          <Routes>
            <Route path="/results/:resultId" element={<ResultDetailPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );
    await screen.findByText("run-001.csv");
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: /Save assignments/i }));
    fireEvent.click(screen.getByRole("button", { name: "nav" }));
    await act(async () => { resolveAssign(makeDetail()); await deferred; });
    // No success toast from the old route.
    expect(screen.queryByText(/Assignments saved|updated/i)).not.toBeInTheDocument();
  });

  it("shows directional best and mean metrics for all and included devices", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = {
          groups: [{
            group_id: "control", name: "Control", kind: "control",
            device_count: 2, valid_device_count: 2,
            metrics: {
              ff: { n: 2, mean: 0.5, median: 0.5, sd: 0.1, minimum: 0.45, q1: 0.45, q3: 0.55, maximum: 0.55 },
            },
          }],
          comparisons: [],
        };
        const rows = (detail.analysis as { devices: Array<{ group_id: string; metrics: unknown; excluded?: boolean }> }).devices;
        rows[0].group_id = "control";
        rows[0].metrics = { forward: { voc: 1, jsc: 20, ff: 0.5, pce: 10 }, reverse: { voc: 1.1, jsc: 22, ff: 0.6, pce: 14.52 } };
        rows[1].group_id = "control";
        rows[1].metrics = { forward: { voc: 0.8, jsc: 10, ff: 0.4, pce: 3.2 }, reverse: { voc: 0.9, jsc: 12, ff: 0.5, pce: 5.4 } };
        rows[1].excluded = true;
        return detail;
      }
      if (path === "/api/results/42/assignments") return [];
      return undefined;
    });
    await renderReadyDetail();
    openSection("Statistics");
    const rows = within(screen.getByRole("table", { name: "Directional group statistics" })).getAllByRole("row");
    expect(rows).toHaveLength(9);
    expect(rows[1]).toHaveTextContent("All devices");
    expect(rows[1]).toHaveTextContent("Forward");
    expect(rows[1]).toHaveTextContent("50.00");
    expect(rows[1]).toHaveTextContent("45.00");
    expect(rows[2]).toHaveTextContent("Reverse");
    expect(rows[3]).toHaveTextContent("After exclusions");
    expect(rows[3]).toHaveTextContent("50.00");
    expect(rows[3]).not.toHaveTextContent("45.00");
  });

  it("does not present direction-mixed comparison statistics", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") {
        const detail = makeDetail();
        (detail.analysis as Record<string, unknown>).statistics = {
          groups: [
            { group_id: "control", name: "Control", kind: "control", device_count: 2, valid_device_count: 2, metrics: { pce: { n: 2, mean: 10, median: 10, sd: 1, minimum: 9, q1: 9.5, q3: 10.5, maximum: 11 } } },
          ],
          comparisons: [{
            target_group_id: "target-1", target_name: "ADH", control_name: "Control",
            metrics: {
              pce: { mean_difference: 2.0, percent_difference: 20.0, effect_size: 0.5, p_value: 0.04, adjusted_p_value: 0.04, test_method: "exact permutation" },
              ff: null,
            },
          }],
        };
        return detail;
      }
      if (path === "/api/results/42/assignments") return [];
      return undefined;
    });
    await renderReadyDetail();
    openSection("Statistics");
    expect(screen.queryByText("Comparisons")).not.toBeInTheDocument();
    expect(screen.queryByText("Best scan per direction")).not.toBeInTheDocument();
  });

  it("renders saved assignment provenance rows", async () => {
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") {
        return { ...makeDetail(), assignments: [
          { id: 1, result_file_id: 42, analysis_device_id: "device-001", analysis_substrate_id: "sample-1", instrument_label: "sample-1.Forward", fabrication_device_id: 41, device_code: "B01-C-S01-D01", device_mark: "C011", substrate_id: 31, substrate_code: "B01-C-S01", substrate_mark: "C01", batch_condition_id: 21, source_condition_id: 11, condition_code: "C", condition_name: "Control", created_at: "2026-08-14T08:00:00Z" },
        ] };
      }
      if (path === "/api/results/42/assignments") return [];
      return undefined;
    });
    await renderReadyDetail();
    openSection("Data & provenance");
    openDetails("Saved assignment provenance");
    expect(screen.getByRole("heading", { name: "Saved assignment provenance" })).toBeInTheDocument();
    expect(screen.getByText("device-001")).toBeInTheDocument();
    expect(screen.getByText("sample-1.Forward")).toBeInTheDocument();
    expect(screen.getByText("B01-C-S01-D01")).toBeInTheDocument();
    expect(screen.getByText("C (Control)")).toBeInTheDocument();
  });

  it("renders the parsed-device inspection table before assignments are complete", async () => {
    await renderReadyDetail();
    openSection("Data & provenance");
    openDetails("Parsed devices");
    const inspection = screen.getByRole("heading", { name: "Parsed devices" }).closest("section")!;
    // The device id also appears in the device-exclusions panel table.
    expect(within(inspection).getAllByText("device-sample-1-1").length).toBeGreaterThan(0);
  });

  it("does not show a stale toast when an assignment POST resolves after unmount", async () => {
    let resolveAssign!: (value: unknown) => void;
    const deferred = new Promise((resolve) => { resolveAssign = resolve; });
    apiFetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/results/42" && (options?.method ?? "GET") === "GET") return makeDetail();
      if (path === "/api/results/42/assignments" && (options?.method ?? "GET") === "GET") return [];
      if (path === "/api/results/42/assignments" && options?.method === "POST") return deferred;
      return undefined;
    });
    const { unmount } = render(
      <MemoryRouter initialEntries={["/results/42"]}>
        <ToastProvider>
          <Routes>
            <Route path="/results/:resultId" element={<ResultDetailPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    );
    await screen.findByText("run-001.csv");
    const selects = screen.getAllByLabelText(/Assign .* to/i);
    fireEvent.change(selects[0], { target: { value: "21" } });
    fireEvent.change(selects[1], { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: /Save assignments/i }));
    unmount();
    await act(async () => { resolveAssign(makeDetail()); await deferred.catch(() => undefined); });
    // No stale toast rendered after unmount.
    expect(screen.queryByText(/Assignments saved|updated/i)).not.toBeInTheDocument();
  });

  it("renders an unavailable-data state instead of white-screening when analysis is malformed", async () => {
    apiFetchMock.mockResolvedValue(
      makeDetail({ analysis: { schema_version: 2, devices: "not-a-list", substrates: null, summary: {} } }),
    );
    renderPage();

    await screen.findByText("run-001.csv");
    expect(
      screen.getByText(/characterization analysis for this result is not available/i),
    ).toBeInTheDocument();
    // No crash from iterating a non-array.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders an unavailable-data state when device traces or substrate fields are malformed", async () => {
    // Device missing traces array.
    apiFetchMock.mockResolvedValueOnce(
      makeDetail({
        analysis: {
          schema_version: 3,
          devices: [{ device_id: "d1", substrate_id: "A001", group_id: "" }],
          substrates: [{ substrate_id: "A001", device_ids: ["d1"], instrument_labels: [] }],
          summary: {},
        },
      }),
    );
    renderPage();
    await screen.findByText("run-001.csv");
    expect(
      screen.getByText(/characterization analysis for this result is not available/i),
    ).toBeInTheDocument();
  });

  it("renders an unavailable-data state when substrate device_ids is missing", async () => {
    // Substrate missing device_ids array.
    apiFetchMock.mockResolvedValueOnce(
      makeDetail({
        analysis: {
          schema_version: 3,
          devices: [{ device_id: "d1", substrate_id: "A001", traces: [], group_id: "" }],
          substrates: [{ substrate_id: "A001", instrument_labels: [] }],
          summary: {},
        },
      }),
    );
    renderPage();
    await screen.findByText("run-001.csv");
    expect(
      screen.getByText(/characterization analysis for this result is not available/i),
    ).toBeInTheDocument();
  });
});
