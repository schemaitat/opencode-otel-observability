// ponytail: large prop covers two call sites — OverviewView (p-3/text-lg) vs SessionStatsPanel (p-2/text-sm)
export function SummaryCard({
  label,
  value,
  large = false,
}: {
  label: string;
  value: string;
  large?: boolean;
}) {
  return (
    <div className={`rounded bg-surface-2 ${large ? "p-3" : "p-2"}`}>
      <div className="text-[10px] uppercase text-text-muted">{label}</div>
      <div className={`font-semibold ${large ? "text-lg" : "text-sm"}`}>{value}</div>
    </div>
  );
}
