import { useMemo, useState } from "react";
import { Filter } from "lucide-react";
import type { SessionSummary } from "../types";
import type { SessionRange } from "../api";
import { formatCost, formatDuration, formatRelativeTime, formatTokens } from "../format";

type SortKey = "recent" | "cost" | "duration" | "tokens";

const RANGE_OPTIONS: [SessionRange, string][] = [
  ["1h", "1h"],
  ["6h", "6h"],
  ["24h", "24h"],
  ["all", "All"],
];

interface SessionListProps {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  onSelect: (sessionId: string) => void;
  loading: boolean;
  range: SessionRange;
  onRangeChange: (range: SessionRange) => void;
}

export function SessionList({ sessions, selectedSessionId, onSelect, loading, range, onRangeChange }: SessionListProps) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("recent");

  const filtered = useMemo(() => {
    let list = sessions;
    const needle = filter.trim().toLowerCase();
    if (needle) {
      list = list.filter(
        (s) =>
          s.session_id.toLowerCase().includes(needle) ||
          s.models.some((m) => m.toLowerCase().includes(needle)) ||
          s.agents.some((a) => a.toLowerCase().includes(needle)),
      );
    }

    const sorted = [...list];
    switch (sortKey) {
      case "cost":
        sorted.sort((a, b) => b.total_cost_usd - a.total_cost_usd);
        break;
      case "duration":
        sorted.sort((a, b) => b.duration_ms - a.duration_ms);
        break;
      case "tokens":
        sorted.sort((a, b) => b.total_tokens - a.total_tokens);
        break;
      default:
        sorted.sort((a, b) => b.start_ns - a.start_ns);
    }
    return sorted;
  }, [sessions, filter, sortKey]);

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex flex-col gap-2 border-b border-border p-3">
        <div className="flex items-center gap-2 rounded border border-border bg-surface-2 px-2 py-1.5" title="Filter the session list">
          <Filter size={14} className="shrink-0 text-text-muted" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter sessions, models, agents..."
            className="w-full bg-transparent text-sm outline-none"
          />
        </div>
        <div className="flex gap-1 text-xs">
          {([
            ["recent", "Recent"],
            ["cost", "Cost"],
            ["duration", "Duration"],
            ["tokens", "Tokens"],
          ] as [SortKey, string][]).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setSortKey(key)}
              aria-pressed={sortKey === key}
              className={`rounded px-2 py-1 transition-colors ${
                sortKey === key
                  ? "bg-accent text-white"
                  : "bg-surface-2 text-text-muted hover:text-text"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-text-muted">Range</span>
          {RANGE_OPTIONS.map(([key, label]) => (
            <button
              key={key}
              onClick={() => onRangeChange(key)}
              aria-pressed={range === key}
              className={`rounded px-2 py-1 transition-colors ${
                range === key
                  ? "bg-accent text-white"
                  : "bg-surface-2 text-text-muted hover:text-text"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && sessions.length === 0 && (
          <div className="p-4 text-sm text-text-muted">Loading sessions...</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="p-4 text-sm text-text-muted">No sessions found.</div>
        )}
        {filtered.map((s) => (
          <SessionRow
            key={s.session_id}
            session={s}
            selected={s.session_id === selectedSessionId}
            onSelect={() => onSelect(s.session_id)}
          />
        ))}
      </div>
    </div>
  );
}

function SessionRow({
  session,
  selected,
  onSelect,
}: {
  session: SessionSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const shortId = session.session_id.replace(/^ses_/, "");

  return (
    <button
      onClick={onSelect}
      className={`block w-full border-b border-border px-3 py-2.5 text-left transition-colors ${
        selected ? "bg-accent/15" : "hover:bg-surface-2"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-xs text-text-muted">{shortId}</span>
        <span className="flex shrink-0 items-center gap-1 text-xs text-text-muted">
          {session.is_open && (
            <span className="flex items-center gap-1 rounded bg-success/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-success">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
              Live
            </span>
          )}
          {formatRelativeTime(session.start_ns)}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-xs">
        <span className="rounded bg-llm/20 px-1.5 py-0.5 text-llm">{session.llm_calls} LLM</span>
        <span className="rounded bg-tool/20 px-1.5 py-0.5 text-tool">{session.tool_calls} tool</span>
        <span className="text-text-muted">{formatDuration(session.duration_ms)}</span>
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs text-text-muted">
        <span className="truncate">{session.models.join(", ") || "—"}</span>
        <span className="shrink-0 font-semibold text-text">
          {formatCost(session.total_cost_usd)} · {formatTokens(session.total_tokens)} tok
        </span>
      </div>
    </button>
  );
}
