import { Pencil } from "lucide-react";
import type { KeyboardEvent } from "react";
import { useEffect, useRef, useState } from "react";

type EditablePriceCellProps = {
  value: string;
  isSaving: boolean;
  onChange: (value: string) => void;
  onSave: () => void;
};

export function EditablePriceCell({
  value,
  isSaving,
  onChange,
  onSave,
}: EditablePriceCellProps) {
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const displayValue = formatDisplayPrice(value);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  function startEditing() {
    if (isSaving) return;
    onChange(formatEditPrice(value));
    setIsEditing(true);
  }

  function saveAndClose() {
    setIsEditing(false);
    onSave();
  }

  if (!isEditing) {
    return (
      <button
        type="button"
        onClick={startEditing}
        className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-sm hover:bg-slate-100"
        title={displayValue ? "Edit sell price" : "Update sell price"}
      >
        {displayValue ? (
          <span className="font-medium text-slate-900">{displayValue}</span>
        ) : (
          <span className="text-xs font-medium text-slate-500">Update</span>
        )}

        <Pencil className="h-3 w-3 text-slate-400" />
        {isSaving && <span className="text-xs text-slate-500">Saving</span>}
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-sm text-slate-500">
          $
        </span>
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onBlur={saveAndClose}
          onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
          className="w-24 rounded-md border border-slate-300 py-1 pl-5 pr-2 text-sm"
          inputMode="decimal"
          placeholder="0.00"
        />
      </div>

      {isSaving && <span className="text-xs text-slate-500">Saving</span>}
    </div>
  );
}

function formatDisplayPrice(value: string) {
  const numericValue = Number(value);

  if (!value.trim() || Number.isNaN(numericValue)) return "";

  return numericValue.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function formatEditPrice(value: string) {
  const numericValue = Number(value);

  if (!value.trim() || Number.isNaN(numericValue)) return value;

  return numericValue.toFixed(2);
}
