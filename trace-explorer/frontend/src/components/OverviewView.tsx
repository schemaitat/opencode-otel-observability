import type { ReactNode } from "react";
import type { AgentUsage, LlmCallRow, ModelUsage, Overview, ToolCallRow, ToolUsage } from "../types";
import type { SessionRange } from "../api";
import { formatCost, formatDuration, formatRelativeTime, formatTokens } from "../format";
import { HorizontalBarChart, StackedAreaChart, StackedBarChart } from "./Charts";

const RANGE_OPTIONS: [SessionRange, string][] = [
  ["1h", "1h"],
  ["6h", "6h"],
  ["24h", "24h"],
  ["all", "All"],
];

interface OverviewViewProps {
  overview: Overview | undefined;
  loading: boolean;
  range: SessionRange;
  onRangeChange: (range: SessionRange) => void;
  onOpenSession: (sessionId: string) => void;
}

export function OverviewView({ overview, loading, range, onRangeChange, onOpenSession }: OverviewViewProps) {
  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-text-muted text-xs">Range</span>
        {RANGE_OPTIONS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => onRangeChange(key)}
            aria-pressed={range === key}
            className={`rounded px-2 py-1 text-xs transition-colors ${
              range === key ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && !overview && <div className="text-sm text-text-muted">Loading overview...</div>}

      {overview && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <SummaryCard label="Sessions" value={String(overview.total_sessions)} />
            <SummaryCard label="Total cost" value={formatCost(overview.total_cost_usd)} />
            <SummaryCard label="Total tokens" value={formatTokens(overview.total_tokens)} />
            <SummaryCard label="LLM calls" value={String(overview.total_llm_calls)} />
            <SummaryCard label="Tool calls" value={String(overview.total_tool_calls)} />
          </div>

          <Section title="Cost by model (over time)">
            <StackedAreaChart
              bucketStarts={overview.timeseries.bucket_starts_ns}
              series={overview.timeseries.cost_by_model}
              valueFormatter={formatCost}
            />
          </Section>

          <Section title="Token usage by model (over time)">
            <StackedAreaChart
              bucketStarts={overview.timeseries.bucket_starts_ns}
              series={overview.timeseries.tokens_by_model}
              valueFormatter={formatTokens}
            />
          </Section>

          <Section title="Tool calls (over time)">
            <StackedBarChart
              bucketStarts={overview.timeseries.bucket_starts_ns}
              series={overview.timeseries.tool_calls_by_tool}
              valueFormatter={(v) => String(v)}
            />
          </Section>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Section title="Model usage">
              <ModelTable rows={overview.by_model} />
            </Section>

            <Section title="Cost by model">
              <HorizontalBarChart
                data={overview.by_model.map((m) => ({ label: m.model, value: m.cost }))}
                valueFormatter={formatCost}
              />
            </Section>

            <Section title="Agent activity">
              <AgentTable rows={overview.by_agent} />
            </Section>

            <Section title="Token usage by agent">
              <HorizontalBarChart
                data={overview.by_agent.map((a) => ({ label: a.agent, value: a.total_tokens }))}
                valueFormatter={formatTokens}
              />
            </Section>

            <Section title="Tool usage">
              <ToolTable rows={overview.by_tool} />
            </Section>

            <Section title="Tool success rate">
              <HorizontalBarChart
                data={overview.by_tool.map((t) => ({
                  label: t.tool,
                  value: t.succeeded + t.failed > 0 ? (t.succeeded / (t.succeeded + t.failed)) * 100 : 0,
                }))}
                valueFormatter={(v) => `${v.toFixed(0)}%`}
                colorFn={(v) => (v >= 95 ? "#3ddc97" : v >= 80 ? "#ffd369" : "#f25c54")}
              />
            </Section>
          </div>

          <Section title="LLM calls (prompt -> model -> outcome)">
            <LlmCallsTable rows={overview.llm_calls} onOpenSession={onOpenSession} />
          </Section>

          <Section title="Tool calls (tool -> parameters -> result)">
            <ToolCallsTable rows={overview.tool_calls} onOpenSession={onOpenSession} />
          </Section>
        </>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-surface-2 p-3">
      <div className="text-[10px] uppercase text-text-muted">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4 rounded border border-border bg-surface p-3">
      <h3 className="mb-2 text-[10px] font-semibold uppercase text-text-muted">{title}</h3>
      {children}
    </div>
  );
}

function ModelTable({ rows }: { rows: ModelUsage[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr className="text-left">
          <th className="py-1">Model</th>
          <th className="py-1 text-right">Calls</th>
          <th className="py-1 text-right">Cost</th>
          <th className="py-1 text-right">Tokens</th>
          <th className="py-1 text-right">Cache R/W</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.model} className="border-t border-border">
            <td className="py-1 font-medium">
              {r.model}
              {r.providers.length > 0 && <span className="ml-1 text-text-muted">({r.providers.join(", ")})</span>}
            </td>
            <td className="py-1 text-right">{r.calls}</td>
            <td className="py-1 text-right">{formatCost(r.cost)}</td>
            <td className="py-1 text-right">{formatTokens(r.total_tokens)}</td>
            <td className="py-1 text-right">
              {formatTokens(r.cache_read_tokens)} / {formatTokens(r.cache_write_tokens)}
            </td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={5} className="py-2 text-center text-text-muted">
              No LLM calls
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function AgentTable({ rows }: { rows: AgentUsage[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr className="text-left">
          <th className="py-1">Agent</th>
          <th className="py-1 text-right">LLM calls</th>
          <th className="py-1 text-right">Cost</th>
          <th className="py-1 text-right">Tokens</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.agent} className="border-t border-border">
            <td className="py-1 font-medium">{r.agent}</td>
            <td className="py-1 text-right">{r.calls}</td>
            <td className="py-1 text-right">{formatCost(r.cost)}</td>
            <td className="py-1 text-right">{formatTokens(r.total_tokens)}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={4} className="py-2 text-center text-text-muted">
              No LLM calls
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function ToolTable({ rows }: { rows: ToolUsage[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr className="text-left">
          <th className="py-1">Tool</th>
          <th className="py-1 text-right">Calls</th>
          <th className="py-1 text-right">Avg duration</th>
          <th className="py-1 text-right">Success rate</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const total = r.succeeded + r.failed;
          const rate = total > 0 ? `${((r.succeeded / total) * 100).toFixed(0)}%` : "—";
          return (
            <tr key={r.tool} className="border-t border-border">
              <td className="py-1 font-medium">{r.tool}</td>
              <td className="py-1 text-right">{r.calls}</td>
              <td className="py-1 text-right">{formatDuration(r.total_duration_ms / r.calls)}</td>
              <td className={`py-1 text-right ${r.failed > 0 ? "text-error" : ""}`}>{rate}</td>
            </tr>
          );
        })}
        {rows.length === 0 && (
          <tr>
            <td colSpan={4} className="py-2 text-center text-text-muted">
              No tool calls
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function LlmCallsTable({ rows, onOpenSession }: { rows: LlmCallRow[]; onOpenSession: (sessionId: string) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-text-muted">
          <tr className="text-left">
            <th className="py-1">Time</th>
            <th className="py-1">Session</th>
            <th className="py-1">Agent</th>
            <th className="py-1">Model</th>
            <th className="py-1">Input</th>
            <th className="py-1">Finish reason</th>
            <th className="py-1 text-right">Cost</th>
            <th className="py-1 text-right">Duration</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border align-top">
              <td className="py-1 whitespace-nowrap text-text-muted">{formatRelativeTime(r.start_ns)}</td>
              <td className="py-1">
                <button
                  onClick={() => onOpenSession(r.session_id)}
                  className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-text-muted hover:bg-border hover:text-text"
                >
                  {r.session_id.replace(/^ses_/, "")}
                </button>
              </td>
              <td className="py-1">{r.agent}</td>
              <td className="py-1 font-medium">{r.model}</td>
              <td className="max-w-xs truncate py-1 text-text-muted" title={r.input ?? ""}>
                {r.input ?? "—"}
              </td>
              <td className="py-1">{r.finish_reason ?? "—"}</td>
              <td className="py-1 text-right">{formatCost(r.cost_usd)}</td>
              <td className="py-1 text-right">{formatDuration(r.duration_ms)}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={8} className="py-2 text-center text-text-muted">
                No LLM calls in range
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ToolCallsTable({ rows, onOpenSession }: { rows: ToolCallRow[]; onOpenSession: (sessionId: string) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-text-muted">
          <tr className="text-left">
            <th className="py-1">Time</th>
            <th className="py-1">Session</th>
            <th className="py-1">Tool</th>
            <th className="py-1">Parameters</th>
            <th className="py-1">Success</th>
            <th className="py-1">Output</th>
            <th className="py-1 text-right">Duration</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const success = r.success === true || r.success === "true";
            const failed = r.success === false || r.success === "false";
            return (
              <tr key={i} className="border-t border-border align-top">
                <td className="py-1 whitespace-nowrap text-text-muted">{formatRelativeTime(r.start_ns)}</td>
                <td className="py-1">
                  <button
                    onClick={() => onOpenSession(r.session_id)}
                    className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-text-muted hover:bg-border hover:text-text"
                  >
                    {r.session_id.replace(/^ses_/, "")}
                  </button>
                </td>
                <td className="py-1 font-medium">{r.tool}</td>
                <td className="max-w-xs truncate py-1 text-text-muted" title={r.parameters ?? ""}>
                  {r.parameters ?? "—"}
                </td>
                <td className={`py-1 ${failed ? "text-error" : success ? "text-success" : ""}`}>
                  {success ? "OK" : failed ? "FAIL" : "—"}
                </td>
                <td className="max-w-xs truncate py-1 text-text-muted" title={r.output ?? ""}>
                  {r.output ?? "—"}
                </td>
                <td className="py-1 text-right">{formatDuration(r.duration_ms)}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className="py-2 text-center text-text-muted">
                No tool calls in range
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
