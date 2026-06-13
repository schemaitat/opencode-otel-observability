import { BarChart3 } from "lucide-react";
import type { SessionSummary } from "../types";
import { formatCost, formatDuration, formatTokens } from "../format";

export function SessionStats({ session, onShowStats }: { session: SessionSummary; onShowStats: () => void }) {
  const stats: { label: string; value: string }[] = [
    { label: "LLM calls", value: String(session.llm_calls) },
    { label: "Tool calls", value: String(session.tool_calls) },
    { label: "Total cost", value: formatCost(session.total_cost_usd) },
    { label: "Total tokens", value: formatTokens(session.total_tokens) },
    { label: "Wall clock", value: formatDuration(session.duration_ms) },
    { label: "Models", value: session.models.join(", ") || "—" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-3 py-2">
      <div className="flex items-center gap-1 rounded bg-surface-2 px-2 py-1 font-mono text-xs text-text-muted">
        {session.session_id}
      </div>
      {stats.map((s) => (
        <div key={s.label} className="flex items-center gap-1.5 rounded bg-surface-2 px-2 py-1 text-xs">
          <span className="text-text-muted">{s.label}</span>
          <span className="font-semibold">{s.value}</span>
        </div>
      ))}
      <button
        onClick={onShowStats}
        className="ml-auto flex items-center gap-1.5 rounded bg-surface-2 px-2 py-1 text-xs text-text-muted hover:bg-border hover:text-text"
        title="Show detailed session statistics"
      >
        <BarChart3 size={13} />
        Stats
      </button>
    </div>
  );
}
