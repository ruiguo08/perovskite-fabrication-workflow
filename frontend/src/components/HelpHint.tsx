import { useId, useState, type ReactNode } from "react";

interface HelpHintProps {
  /** Topic name used for the accessible label, e.g. "VCD program". */
  label: string;
  /** Guidance shown in the hover panel. */
  children: ReactNode;
}

/**
 * Small "?" affordance beside a form heading. The guidance panel appears on
 * hover and keyboard focus (CSS) and can be pinned by clicking, so touch
 * users can open it too. Pressing Escape closes a pinned panel.
 */
export function HelpHint({ label, children }: HelpHintProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <span className={`help-hint${open ? " help-hint--open" : ""}`}>
      <button
        type="button"
        className="help-hint__trigger"
        aria-label={`${label} help`}
        aria-expanded={open}
        aria-describedby={panelId}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        ?
      </button>
      <span className="help-hint__panel" role="tooltip" id={panelId}>
        {children}
      </span>
    </span>
  );
}
