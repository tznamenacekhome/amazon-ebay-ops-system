import type { KeyboardEvent } from "react";

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
  return (
    <div className="flex items-center gap-2">
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onSave}
        onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
          if (event.key === "Enter") event.currentTarget.blur();
        }}
        className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
        placeholder="0.00"
      />

      {isSaving && <span className="text-xs text-slate-500">Saving</span>}
    </div>
  );
}
