import type { ReactNode } from "react";

export function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs transition-colors ${
        active ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}
