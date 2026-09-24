import { useEffect, useRef, useState } from "react";
import { FormField } from "./FormField";
import { trapModalFocus } from "../lib/modalFocus";
import type { FrozenBatchCondition } from "../types/api";

export interface CompleteConditionInput {
  /** Number of substrates actually made; "" until the operator enters one. */
  actualCount: number | "";
  /** Required when the actual count is below the planned count. */
  deviationDescription: string;
}

interface CompleteBatchDialogProps {
  open: boolean;
  conditions: FrozenBatchCondition[];
  submitting: boolean;
  error: string | null;
  onConfirm: (inputs: Record<number, CompleteConditionInput>) => void;
  onCancel: () => void;
}

/**
 * Collects one actual substrate count per frozen condition before the batch is
 * completed. A condition whose actual count is below the planned count must
 * carry a deviation description explaining the shortfall; the completion PATCH
 * submits the counts and the shortfall explanations together so the server can
 * record them in one transaction.
 */
export function CompleteBatchDialog({
  open,
  conditions,
  submitting,
  error,
  onConfirm,
  onCancel,
}: CompleteBatchDialogProps) {
  const [inputs, setInputs] = useState<Record<number, CompleteConditionInput>>({});
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) {
      setInputs(
        Object.fromEntries(
          conditions.map((condition) => [
            condition.id,
            {
              actualCount: condition.actual_substrate_count ?? condition.planned_substrate_count,
              deviationDescription: "",
            },
          ]),
        ),
      );
      confirmRef.current?.focus();
    }
  }, [open, conditions]);

  if (!open) {
    return null;
  }

  const countValid = (condition: FrozenBatchCondition): boolean => {
    const current = inputs[condition.id];
    return (
      typeof current?.actualCount === "number" &&
      Number.isInteger(current.actualCount) &&
      current.actualCount >= 0
    );
  };

  const validationPasses = conditions.every((condition) => {
    const current = inputs[condition.id];
    if (
      !current ||
      typeof current.actualCount !== "number" ||
      !Number.isInteger(current.actualCount) ||
      current.actualCount < 0
    ) {
      return false;
    }
    return (
      current.actualCount >= condition.planned_substrate_count ||
      current.deviationDescription.trim().length > 0
    );
  });

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <div
        className="dialog dialog--wide"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="complete-batch-title"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
            return;
          }
          trapModalFocus(dialogRef.current, event);
        }}
      >
        <h2 className="dialog__title" id="complete-batch-title">
          Complete batch
        </h2>
        <p className="dialog__message">
          Record how many substrates were actually made in each condition. A
          count below the planned number needs a deviation reason and counts of
          zero mean the whole group was abandoned.
        </p>
        <div className="completion-form">
          {conditions.map((condition) => {
            const current = inputs[condition.id] ?? { actualCount: "", deviationDescription: "" };
            const shortfall =
              current.actualCount !== "" &&
              current.actualCount < condition.planned_substrate_count;
            return (
              <div className="run-sheet-form completion-form__condition" key={condition.id}>
                <div className="completion-form__heading">
                  <strong>{condition.condition_name}</strong>
                  <span className="run-sheet-muted">
                    {condition.condition_code} · planned {condition.planned_substrate_count}
                  </span>
                </div>
                <FormField
                  label="Actual substrates"
                  htmlFor={`completion-count-${condition.id}`}
                  error={countValid(condition) ? null : "Enter how many substrates were actually made."}
                >
                  <input
                    className="text-input"
                    type="number"
                    min={0}
                    id={`completion-count-${condition.id}`}
                    data-completion-count={condition.id}
                    aria-invalid={!countValid(condition)}
                    aria-describedby={countValid(condition) ? undefined : `completion-count-${condition.id}-error`}
                    value={current.actualCount}
                    onChange={(event) =>
                      setInputs((previous) => ({
                        ...previous,
                        [condition.id]: {
                          ...(previous[condition.id] ?? { deviationDescription: "" }),
                          // A cleared field stays empty; it must not silently
                          // become "0 substrates made".
                          actualCount:
                            event.target.value === "" ? "" : Number(event.target.value),
                        },
                      }))
                    }
                  />
                </FormField>
                {shortfall ? (
                  <FormField
                    label="Deviation reason (required)"
                    htmlFor={`completion-deviation-${condition.id}`}
                  >
                    <textarea
                      className="text-input"
                      rows={2}
                      id={`completion-deviation-${condition.id}`}
                      data-completion-deviation={condition.id}
                      value={current.deviationDescription}
                      onChange={(event) =>
                        setInputs((previous) => ({
                          ...previous,
                          [condition.id]: {
                            ...(previous[condition.id] ?? { actualCount: "" }),
                            deviationDescription: event.target.value,
                          },
                        }))
                      }
                    />
                  </FormField>
                ) : null}
              </div>
            );
          })}
        </div>
        {error ? <p className="inline-form-error" role="alert">{error}</p> : null}
        <div className="dialog__actions">
          <button
            type="button"
            className="button button--secondary"
            disabled={submitting}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="button button--primary"
            ref={confirmRef}
            disabled={submitting || !validationPasses}
            onClick={() => onConfirm(inputs)}
          >
            Complete batch
          </button>
        </div>
      </div>
    </div>
  );
}
