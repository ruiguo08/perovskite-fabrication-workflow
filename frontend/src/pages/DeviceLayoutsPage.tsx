import { useCallback, useState, type FormEvent } from "react";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { useSession } from "../auth/session";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { useApiResource } from "../lib/useApiResource";
import type { DeviceLayout } from "../types/api";

const COLUMNS: Column<DeviceLayout>[] = [
  {
    key: "code",
    header: "Layout",
    render: (row) => <code>{row.code}</code>,
  },
  {
    key: "dimensions",
    header: "Substrate",
    render: (row) => `${row.substrate_width_mm} × ${row.substrate_length_mm} mm`,
  },
  {
    key: "devices_per_substrate",
    header: "Devices",
    className: "numeric-cell",
  },
  {
    key: "device_active_area_cm2",
    header: "Area / device",
    className: "numeric-cell",
    render: (row) => `${row.device_active_area_cm2} cm²`,
  },
  {
    key: "total_active_area_cm2",
    header: "Total active area",
    className: "numeric-cell",
    render: (row) => `${row.total_active_area_cm2} cm²`,
  },
  {
    key: "version",
    header: "Version",
    render: (row) => <span className="version-mark">v{row.version}</span>,
  },
];

interface LayoutFormState {
  code: string;
  version: string;
  substrate_width_mm: string;
  substrate_length_mm: string;
  devices_per_substrate: string;
  device_active_area_cm2: string;
  total_active_area_cm2: string;
  description: string;
}

const EMPTY_FORM: LayoutFormState = {
  code: "",
  version: "1",
  substrate_width_mm: "",
  substrate_length_mm: "",
  devices_per_substrate: "1",
  device_active_area_cm2: "",
  total_active_area_cm2: "",
  description: "",
};

export function DeviceLayoutsPage() {
  const { user } = useSession();
  const { show } = useToast();
  const isAdmin = user?.role === "administrator";
  const loadLayouts = useCallback(
    () => apiFetch<DeviceLayout[]>("/api/device-layouts"),
    [],
  );
  const resource = useApiResource(loadLayouts);
  const [form, setForm] = useState<LayoutFormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const rows = resource.data ?? [];

  async function createLayout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiFetch<DeviceLayout>("/api/device-layouts", {
        method: "POST",
        body: {
          code: form.code.trim(),
          version: Number(form.version),
          substrate_width_mm: form.substrate_width_mm,
          substrate_length_mm: form.substrate_length_mm,
          devices_per_substrate: Number(form.devices_per_substrate),
          device_active_area_cm2: form.device_active_area_cm2,
          total_active_area_cm2: form.total_active_area_cm2,
          description: form.description.trim(),
        },
      });
      show(`Device layout ${created.code} v${created.version} created.`, "success");
      setForm(EMPTY_FORM);
      await resource.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create the device layout.");
    } finally {
      setSubmitting(false);
    }
  }

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading device layouts…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState message={resource.error ?? "Unable to load device layouts."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }

  return (
    <>
      <PageHeader
        title="Device layouts"
        description="Versioned substrate geometry used to calculate physical devices and active area. Students cannot plan experiments until at least one layout exists."
        meta={isAdmin ? "Administrator-managed catalog" : "Read-only reference catalog"}
      />
      {isAdmin ? (
        <section className="panel panel--accent" aria-labelledby="create-layout-title">
          <h2 className="panel__title" id="create-layout-title">Create a device layout</h2>
          <p className="builder-help">
            Layout rows are immutable. To change a geometry, create a new row with the same code and a bumped
            version — historical conditions keep their original layout. Students see every code at its latest version.
          </p>
          <form
            className="preset-create-grid"
            onSubmit={(event) => void createLayout(event)}
          >
            <FormField label="Code" htmlFor="layout-code" required hint="Short stable identifier, e.g. 15x15_dual_005.">
              <input id="layout-code" className="text-input" required maxLength={40} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} />
            </FormField>
            <FormField label="Version" htmlFor="layout-version" required>
              <input id="layout-version" className="text-input" required type="number" min="1" step="1" value={form.version} onChange={(event) => setForm({ ...form, version: event.target.value })} />
            </FormField>
            <FormField label="Substrate width (mm)" htmlFor="layout-width" required>
              <input id="layout-width" className="text-input" required type="number" min="0" step="any" value={form.substrate_width_mm} onChange={(event) => setForm({ ...form, substrate_width_mm: event.target.value })} />
            </FormField>
            <FormField label="Substrate length (mm)" htmlFor="layout-length" required>
              <input id="layout-length" className="text-input" required type="number" min="0" step="any" value={form.substrate_length_mm} onChange={(event) => setForm({ ...form, substrate_length_mm: event.target.value })} />
            </FormField>
            <FormField label="Devices per substrate" htmlFor="layout-devices" required>
              <input id="layout-devices" className="text-input" required type="number" min="1" step="1" value={form.devices_per_substrate} onChange={(event) => setForm({ ...form, devices_per_substrate: event.target.value })} />
            </FormField>
            <FormField label="Active area per device (cm²)" htmlFor="layout-area" required>
              <input id="layout-area" className="text-input" required type="number" min="0" step="any" value={form.device_active_area_cm2} onChange={(event) => setForm({ ...form, device_active_area_cm2: event.target.value })} />
            </FormField>
            <FormField label="Total active area (cm²)" htmlFor="layout-total" required>
              <input id="layout-total" className="text-input" required type="number" min="0" step="any" value={form.total_active_area_cm2} onChange={(event) => setForm({ ...form, total_active_area_cm2: event.target.value })} />
            </FormField>
            <FormField label="Description" htmlFor="layout-description" required>
              <input id="layout-description" className="text-input" required maxLength={500} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
            </FormField>
            <div className="form-grid__action">
              <button className="button button--primary" type="submit" disabled={submitting}>
                {submitting ? "Creating…" : "Create layout"}
              </button>
            </div>
          </form>
          <InlineFormError message={error} />
        </section>
      ) : null}
      <section className="panel panel--catalog">
        <DataTable
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => `${row.code}:${row.version}`}
          ariaLabel="Device layout directory"
          loading={resource.status === "loading"}
          empty={isAdmin
            ? <EmptyState title="No device layouts exist yet." description="Students cannot plan experiments until you create the first layout above." />
            : <EmptyState title="No device layouts are available." description="Ask your administrator to create the device layouts." />}
        />
      </section>
    </>
  );
}
