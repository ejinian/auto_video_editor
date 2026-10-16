"use client";

export interface SegOption<T extends string | number> { value: T; label: string; sub?: string }

/** A large segmented control: one button per option, the chosen one lit. */
export function Seg<T extends string | number>({ options, value, onChange, ariaLabel }: { options: SegOption<T>[]; value: T | null; onChange: (v: T) => void; ariaLabel?: string }) {
  return (
    <div className="seg" role="radiogroup" aria-label={ariaLabel}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          <b>{o.label}</b>
          {o.sub && <small>{o.sub}</small>}
        </button>
      ))}
    </div>
  );
}
