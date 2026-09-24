import { useCallback, useMemo, useState, type FormEvent } from "react";
import { useSession } from "../auth/session";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { InlineFormError } from "../components/InlineFormError";
import { JsonObjectField } from "../components/JsonObjectField";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { formatDateTime, titleCase } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { Material, MaterialProduct } from "../types/api";

const CATEGORIES = ["substrate", "chemical", "solvent", "gas", "other"] as const;
const STATUSES = ["pending", "active", "inactive"] as const;
const CATEGORY_LABELS: Record<string, string> = {
  substrate: "Substrates",
  chemical: "Chemicals and reagents",
  solvent: "Solvents",
  gas: "Gases",
  other: "Other materials",
};

function jsonText(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

function upsertMaterial(rows: Material[], replacement: Material): Material[] {
  const existing = rows.some((row) => row.id === replacement.id);
  const next = existing
    ? rows.map((row) => (row.id === replacement.id ? replacement : row))
    : [...rows, replacement];
  return next.sort((left, right) =>
    `${left.category}:${left.name}`.localeCompare(`${right.category}:${right.name}`),
  );
}

export function MaterialsPage() {
  const { user } = useSession();
  const { show } = useToast();
  const canManage = user?.role === "instructor" || user?.role === "administrator";
  const loadMaterials = useCallback(() => apiFetch<Material[]>("/api/materials"), []);
  const resource = useApiResource(loadMaterials);
  const [materials, setMaterials] = useState<Material[] | null>(null);
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("substrate");
  const [name, setName] = useState("");
  const [formula, setFormula] = useState("");
  const [casNumber, setCasNumber] = useState("");
  const [specificationText, setSpecificationText] = useState("{}");
  const [specification, setSpecification] = useState<Record<string, unknown>>({});
  const [specificationValid, setSpecificationValid] = useState(true);
  const [createError, setCreateError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const rows = useMemo(() => materials ?? resource.data ?? [], [materials, resource.data]);

  const grouped = useMemo(() => CATEGORIES.map((groupCategory) => ({
    category: groupCategory,
    rows: rows.filter((material) => material.category === groupCategory),
  })).filter((group) => group.rows.length > 0), [rows]);

  function replaceMaterial(replacement: Material) {
    setMaterials((current) => upsertMaterial(current ?? rows, replacement));
  }

  async function createMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!specificationValid) {
      return;
    }
    setSubmitting(true);
    setCreateError(null);
    try {
      const created = await apiFetch<Material>("/api/materials", {
        method: "POST",
        body: {
          category,
          name: name.trim(),
          formula: formula.trim(),
          cas_number: casNumber.trim(),
          specification,
        },
      });
      replaceMaterial(created);
      setName("");
      setFormula("");
      setCasNumber("");
      setSpecificationText("{}");
      setSpecification({});
      setSpecificationValid(true);
      show(canManage ? "Material added to the active directory." : "Material submitted for review.", "success");
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Unable to save the material.");
    } finally {
      setSubmitting(false);
    }
  }

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading materials…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState message={resource.error ?? "Unable to load materials."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }

  return (
    <>
      <PageHeader
        title="Material directory"
        description="Reusable materials and supplier products for experiment planning. Student submissions remain pending until reviewed."
      />
      <section className="panel panel--accent" aria-labelledby="add-material-title">
        <h2 className="panel__title" id="add-material-title">Add material</h2>
        <form className="material-create-grid" onSubmit={(event) => void createMaterial(event)}>
          <FormField label="Material category" htmlFor="material-category" required>
            <select id="material-category" className="text-input" required value={category} onChange={(event) => setCategory(event.target.value as (typeof CATEGORIES)[number])}>
              {CATEGORIES.map((value) => <option key={value} value={value}>{CATEGORY_LABELS[value]}</option>)}
            </select>
          </FormField>
          <FormField label="Material name" htmlFor="material-name" required>
            <input id="material-name" className="text-input" required maxLength={160} value={name} onChange={(event) => setName(event.target.value)} />
          </FormField>
          <FormField label="Formula" htmlFor="material-formula">
            <input id="material-formula" className="text-input mono" maxLength={120} value={formula} onChange={(event) => setFormula(event.target.value)} />
          </FormField>
          <FormField label="CAS number" htmlFor="material-cas">
            <input id="material-cas" className="text-input mono" maxLength={64} value={casNumber} onChange={(event) => setCasNumber(event.target.value)} />
          </FormField>
          <div className="material-create-grid__specification">
            <JsonObjectField
              id="material-specification"
              label="Specification"
              value={specificationText}
              onTextChange={setSpecificationText}
              onValidChange={setSpecification}
              onValidityChange={setSpecificationValid}
            />
          </div>
          <div className="material-create-grid__action">
            <button className="button button--primary" type="submit" disabled={submitting || !specificationValid}>
              {submitting ? "Saving…" : canManage ? "Add active material" : "Submit material for review"}
            </button>
          </div>
        </form>
        <InlineFormError message={createError} />
      </section>

      {grouped.length === 0 ? (
        <EmptyState title="No materials have been recorded." description="Add the first reusable material to start the directory." />
      ) : grouped.map((group) => (
        <section className="catalog-group" key={group.category} aria-labelledby={`material-group-${group.category}`}>
          <div className="catalog-group__heading">
            <h2 id={`material-group-${group.category}`}>{CATEGORY_LABELS[group.category]}</h2>
            <span className="record-count">{group.rows.length} records</span>
          </div>
          <div className="material-list">
            {group.rows.map((material) => (
              <MaterialCard
                key={material.id}
                material={material}
                canManage={canManage}
                onChange={replaceMaterial}
              />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

interface MaterialCardProps {
  material: Material;
  canManage: boolean;
  onChange: (material: Material) => void;
}

function MaterialCard({ material, canManage, onChange }: MaterialCardProps) {
  const { show } = useToast();
  const [name, setName] = useState(material.name);
  const [formula, setFormula] = useState(material.formula);
  const [casNumber, setCasNumber] = useState(material.cas_number);
  const [status, setStatus] = useState(material.status);
  const [specificationText, setSpecificationText] = useState(jsonText(material.specification));
  const [specification, setSpecification] = useState(material.specification);
  const [specificationValid, setSpecificationValid] = useState(true);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [vendor, setVendor] = useState("");
  const [catalogNumber, setCatalogNumber] = useState("");
  const [productSpecificationText, setProductSpecificationText] = useState("{}");
  const [productSpecification, setProductSpecification] = useState<Record<string, unknown>>({});
  const [productSpecificationValid, setProductSpecificationValid] = useState(true);
  const [productError, setProductError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function updateMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!specificationValid) {
      return;
    }
    setSubmitting(true);
    setUpdateError(null);
    try {
      const updated = await apiFetch<Material>(`/api/materials/${material.id}`, {
        method: "PATCH",
        body: {
          name: name.trim(),
          formula: formula.trim(),
          cas_number: casNumber.trim(),
          specification,
          status,
        },
      });
      onChange(updated);
      show("Material updated.", "success");
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "Unable to update the material.");
    } finally {
      setSubmitting(false);
    }
  }

  async function createProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!productSpecificationValid) {
      return;
    }
    setSubmitting(true);
    setProductError(null);
    try {
      const updated = await apiFetch<Material>(`/api/materials/${material.id}/products`, {
        method: "POST",
        body: {
          vendor: vendor.trim(),
          catalog_number: catalogNumber.trim(),
          specification: productSpecification,
        },
      });
      onChange(updated);
      setVendor("");
      setCatalogNumber("");
      setProductSpecificationText("{}");
      setProductSpecification({});
      setProductSpecificationValid(true);
      show(canManage ? "Supplier product added." : "Supplier product submitted for review.", "success");
    } catch (error) {
      setProductError(error instanceof Error ? error.message : "Unable to save the supplier product.");
    } finally {
      setSubmitting(false);
    }
  }

  const titleId = `material-title-${material.id}`;
  return (
    <article className="material-card" aria-labelledby={titleId}>
      <header className="material-card__header">
        <div>
          <div className="material-card__title-line">
            <h3 id={titleId}>{material.name}</h3>
            <StatusBadge status={material.status} />
          </div>
          <p className="material-card__identity">
            {material.formula ? <code>{material.formula}</code> : "No formula"}
            {material.cas_number ? <span>CAS {material.cas_number}</span> : null}
          </p>
        </div>
        <span className="material-card__updated">Updated {formatDateTime(material.updated_at)}</span>
      </header>

      {canManage ? (
        <details className="inline-editor">
          <summary>Edit material</summary>
          <form className="inline-editor__body" onSubmit={(event) => void updateMaterial(event)}>
            <div className="material-edit-grid">
              <FormField label={`Name for ${material.name}`} htmlFor={`material-name-${material.id}`} required>
                <input id={`material-name-${material.id}`} className="text-input" required maxLength={160} value={name} onChange={(event) => setName(event.target.value)} />
              </FormField>
              <FormField label={`Formula for ${material.name}`} htmlFor={`material-formula-${material.id}`}>
                <input id={`material-formula-${material.id}`} className="text-input mono" maxLength={120} value={formula} onChange={(event) => setFormula(event.target.value)} />
              </FormField>
              <FormField label={`CAS number for ${material.name}`} htmlFor={`material-cas-${material.id}`}>
                <input id={`material-cas-${material.id}`} className="text-input mono" maxLength={64} value={casNumber} onChange={(event) => setCasNumber(event.target.value)} />
              </FormField>
              <FormField label={`Status for ${material.name}`} htmlFor={`material-status-${material.id}`} required>
                <select id={`material-status-${material.id}`} className="text-input" value={status} onChange={(event) => setStatus(event.target.value)}>
                  {STATUSES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
                </select>
              </FormField>
            </div>
            <JsonObjectField
              id={`material-specification-${material.id}`}
              label={`Specification for ${material.name}`}
              value={specificationText}
              onTextChange={setSpecificationText}
              onValidChange={setSpecification}
              onValidityChange={setSpecificationValid}
            />
            <InlineFormError message={updateError} />
            <button className="button button--secondary" type="submit" disabled={submitting || !specificationValid}>Save {material.name}</button>
          </form>
        </details>
      ) : null}

      {Object.keys(material.specification).length > 0 ? (
        <dl className="specification-list">
          {Object.entries(material.specification).map(([key, value]) => (
            <div key={key}><dt>{titleCase(key)}</dt><dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd></div>
          ))}
        </dl>
      ) : null}

      <section className="product-directory" aria-labelledby={`products-title-${material.id}`}>
        <h4 id={`products-title-${material.id}`}>Supplier products</h4>
        {material.products.length === 0 ? (
          <p className="table-empty">No supplier products have been recorded.</p>
        ) : (
          <div className="product-list">
            {material.products.map((product) => (
              <ProductRow key={product.id} materialName={material.name} product={product} canManage={canManage} onChange={onChange} />
            ))}
          </div>
        )}
        <details className="inline-editor inline-editor--product">
          <summary>{canManage ? "Add supplier product" : "Propose supplier product"}</summary>
          <form className="inline-editor__body" onSubmit={(event) => void createProduct(event)}>
            <div className="product-create-grid">
              <FormField label={`New vendor for ${material.name}`} htmlFor={`new-product-vendor-${material.id}`} required>
                <input id={`new-product-vendor-${material.id}`} className="text-input" required maxLength={160} value={vendor} onChange={(event) => setVendor(event.target.value)} />
              </FormField>
              <FormField label={`New catalog number for ${material.name}`} htmlFor={`new-product-code-${material.id}`} required>
                <input id={`new-product-code-${material.id}`} className="text-input mono" required maxLength={160} value={catalogNumber} onChange={(event) => setCatalogNumber(event.target.value)} />
              </FormField>
            </div>
            <JsonObjectField
              id={`new-product-specification-${material.id}`}
              label={`New product specification for ${material.name}`}
              value={productSpecificationText}
              onTextChange={setProductSpecificationText}
              onValidChange={setProductSpecification}
              onValidityChange={setProductSpecificationValid}
            />
            <InlineFormError message={productError} />
            <button className="button button--secondary" type="submit" disabled={submitting || !productSpecificationValid}>
              {canManage ? "Add product" : "Submit product for review"}
            </button>
          </form>
        </details>
      </section>
    </article>
  );
}

interface ProductRowProps {
  materialName: string;
  product: MaterialProduct;
  canManage: boolean;
  onChange: (material: Material) => void;
}

function ProductRow({ materialName, product, canManage, onChange }: ProductRowProps) {
  const { show } = useToast();
  const [vendor, setVendor] = useState(product.vendor);
  const [catalogNumber, setCatalogNumber] = useState(product.catalog_number);
  const [status, setStatus] = useState(product.status);
  const [specificationText, setSpecificationText] = useState(jsonText(product.specification));
  const [specification, setSpecification] = useState(product.specification);
  const [specificationValid, setSpecificationValid] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function updateProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!specificationValid) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<Material>(`/api/material-products/${product.id}`, {
        method: "PATCH",
        body: {
          vendor: vendor.trim(),
          catalog_number: catalogNumber.trim(),
          specification,
          status,
        },
      });
      onChange(updated);
      show("Supplier product updated.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update the supplier product.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!canManage) {
    return (
      <div className="product-row">
        <div><strong>{product.vendor}</strong><code>{product.catalog_number}</code></div>
        <StatusBadge status={product.status} />
        {Object.keys(product.specification).length > 0 ? <code className="product-row__specification">{JSON.stringify(product.specification)}</code> : null}
      </div>
    );
  }

  return (
    <details className="product-row product-row--editable">
      <summary>
        <span><strong>{product.vendor}</strong> <code>{product.catalog_number}</code></span>
        <StatusBadge status={product.status} />
      </summary>
      <form className="inline-editor__body" onSubmit={(event) => void updateProduct(event)}>
        <div className="product-create-grid">
          <FormField label={`Vendor for ${product.catalog_number}`} htmlFor={`product-vendor-${product.id}`} required>
            <input id={`product-vendor-${product.id}`} className="text-input" required maxLength={160} value={vendor} onChange={(event) => setVendor(event.target.value)} />
          </FormField>
          <FormField label={`Catalog number for ${materialName} product ${product.id}`} htmlFor={`product-code-${product.id}`} required>
            <input id={`product-code-${product.id}`} className="text-input mono" required maxLength={160} value={catalogNumber} onChange={(event) => setCatalogNumber(event.target.value)} />
          </FormField>
          <FormField label={`Status for ${product.vendor} ${product.catalog_number}`} htmlFor={`product-status-${product.id}`} required>
            <select id={`product-status-${product.id}`} className="text-input" value={status} onChange={(event) => setStatus(event.target.value)}>
              {STATUSES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
            </select>
          </FormField>
        </div>
        <JsonObjectField
          id={`product-specification-${product.id}`}
          label={`Specification for ${product.vendor} ${product.catalog_number}`}
          value={specificationText}
          onTextChange={setSpecificationText}
          onValidChange={setSpecification}
          onValidityChange={setSpecificationValid}
        />
        <InlineFormError message={error} />
        <button className="button button--secondary" type="submit" disabled={submitting || !specificationValid}>Save product</button>
      </form>
    </details>
  );
}
