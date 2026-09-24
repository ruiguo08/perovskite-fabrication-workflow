import type { ReactNode } from "react";

export interface Column<T> {
  /** Stable key; also used as the `headers` value for the column. */
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  empty?: ReactNode;
  ariaLabel?: string;
  /** While true with no rows yet, a skeleton shows instead of the empty state. */
  loading?: boolean;
}

/** Compact, dense table used across the console. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  ariaLabel,
  loading = false,
}: DataTableProps<T>) {
  if (loading && rows.length === 0) {
    return (
      <div className="table-skeleton" role="status" aria-label={ariaLabel ? `${ariaLabel} — loading` : "Loading records"}>
        <span className="visually-hidden">Loading records…</span>
        {[0, 1, 2].map((row) => (
          <div className="table-skeleton__row" key={row} aria-hidden="true">
            {columns.map((column) => (
              <span key={column.key} className="table-skeleton__cell" />
            ))}
          </div>
        ))}
      </div>
    );
  }
  if (rows.length === 0) {
    return <>{empty ?? <p className="table-empty">No records.</p>}</>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table" aria-label={ariaLabel}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.className}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td key={column.key} className={column.className}>
                  {column.render ? column.render(row) : String((row as Record<string, unknown>)[column.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}