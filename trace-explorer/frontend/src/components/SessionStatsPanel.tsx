import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { Span } from "../types";
import { spanKind } from "../types";
import { formatCost, formatDuration, formatTokens } from "../format";

interface SessionStatsPanelProps {
  spans: Span[];
  onClose: () => void;
}

interface ModelRow {
  model: string;
  calls: number;
  cost: number;
  promptTokens: number;
  completionTokens: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
}

interface AgentRow {
  agent: string;
  calls: number;
  cost: number;
  totalTokens: number;
}

interface ToolRow {
  tool: string;
  calls: number;
  totalDuration: number;
  succeeded: number;
  failed: number;
}

function num(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function SessionStatsPanel({ spans, onClose }: SessionStatsPanelProps) {
  const byModel = new Map<string, ModelRow>();
  const byAgent = new Map<string, AgentRow>();
  const byTool = new Map<string, ToolRow>();

  let totalReasoningTokens = 0;
  let messageCount = 0;

  for (const span of spans) {
    const attrs = span.attributes;
    const kind = spanKind(span);
    const agent = String(attrs["agent.name"] ?? "unknown");

    if (kind === "llm") {
      messageCount += 1;
      const model = String(attrs["llm.model_name"] ?? "unknown");
      const cost = num(attrs["cost_usd"]);
      const promptTokens = num(attrs["llm.token_count.prompt"]);
      const completionTokens = num(attrs["llm.token_count.completion"]);
      const cacheRead = num(attrs["llm.token_count.prompt_details.cache_read"]);
      const cacheWrite = num(attrs["llm.token_count.prompt_details.cache_write"]);
      const reasoning = num(attrs["llm.token_count.completion_details.reasoning"]);
      const total = num(attrs["llm.token_count.total"]);
      totalReasoningTokens += reasoning;

      const modelRow = byModel.get(model) ?? {
        model,
        calls: 0,
        cost: 0,
        promptTokens: 0,
        completionTokens: 0,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 0,
      };
      modelRow.calls += 1;
      modelRow.cost += cost;
      modelRow.promptTokens += promptTokens;
      modelRow.completionTokens += completionTokens;
      modelRow.cacheRead += cacheRead;
      modelRow.cacheWrite += cacheWrite;
      modelRow.totalTokens += total;
      byModel.set(model, modelRow);

      const agentRow = byAgent.get(agent) ?? { agent, calls: 0, cost: 0, totalTokens: 0 };
      agentRow.calls += 1;
      agentRow.cost += cost;
      agentRow.totalTokens += total;
      byAgent.set(agent, agentRow);
    } else if (kind === "tool") {
      const tool = String(attrs["tool.name"] ?? span.span_name.replace(/^opencode\.tool\./, ""));
      const success = attrs["tool.success"];
      const succeeded = success === true || success === "true";
      const failed = success === false || success === "false";

      const toolRow = byTool.get(tool) ?? { tool, calls: 0, totalDuration: 0, succeeded: 0, failed: 0 };
      toolRow.calls += 1;
      toolRow.totalDuration += span.duration_ms;
      if (succeeded) toolRow.succeeded += 1;
      if (failed) toolRow.failed += 1;
      byTool.set(tool, toolRow);
    }
  }

  const modelRows = [...byModel.values()].sort((a, b) => b.cost - a.cost);
  const agentRows = [...byAgent.values()].sort((a, b) => b.cost - a.cost);
  const toolRows = [...byTool.values()].sort((a, b) => b.calls - a.calls);

  const totalCacheRead = modelRows.reduce((sum, r) => sum + r.cacheRead, 0);
  const totalCacheWrite = modelRows.reduce((sum, r) => sum + r.cacheWrite, 0);
  const totalPrompt = modelRows.reduce((sum, r) => sum + r.promptTokens, 0);
  const totalCompletion = modelRows.reduce((sum, r) => sum + r.completionTokens, 0);

  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50">
      <div className="flex max-h-[85vh] w-[40rem] flex-col rounded border border-border bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Session statistics</h2>
          <button onClick={onClose} className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <div className="mb-4 grid grid-cols-3 gap-2">
            <SummaryCard label="Messages" value={String(messageCount)} />
            <SummaryCard label="Prompt tokens" value={formatTokens(totalPrompt)} />
            <SummaryCard label="Completion tokens" value={formatTokens(totalCompletion)} />
            <SummaryCard label="Cache read tokens" value={formatTokens(totalCacheRead)} />
            <SummaryCard label="Cache write tokens" value={formatTokens(totalCacheWrite)} />
            <SummaryCard label="Reasoning tokens" value={formatTokens(totalReasoningTokens)} />
          </div>

          <Section title="By model">
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
                {modelRows.map((r) => (
                  <tr key={r.model} className="border-t border-border">
                    <td className="py-1 font-medium">{r.model}</td>
                    <td className="py-1 text-right">{r.calls}</td>
                    <td className="py-1 text-right">{formatCost(r.cost)}</td>
                    <td className="py-1 text-right">{formatTokens(r.totalTokens)}</td>
                    <td className="py-1 text-right">
                      {formatTokens(r.cacheRead)} / {formatTokens(r.cacheWrite)}
                    </td>
                  </tr>
                ))}
                {modelRows.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-2 text-center text-text-muted">
                      No LLM calls
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Section>

          <Section title="By agent">
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
                {agentRows.map((r) => (
                  <tr key={r.agent} className="border-t border-border">
                    <td className="py-1 font-medium">{r.agent}</td>
                    <td className="py-1 text-right">{r.calls}</td>
                    <td className="py-1 text-right">{formatCost(r.cost)}</td>
                    <td className="py-1 text-right">{formatTokens(r.totalTokens)}</td>
                  </tr>
                ))}
                {agentRows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-2 text-center text-text-muted">
                      No LLM calls
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Section>

          <Section title="By tool">
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
                {toolRows.map((r) => {
                  const total = r.succeeded + r.failed;
                  const rate = total > 0 ? `${((r.succeeded / total) * 100).toFixed(0)}%` : "—";
                  return (
                    <tr key={r.tool} className="border-t border-border">
                      <td className="py-1 font-medium">{r.tool}</td>
                      <td className="py-1 text-right">{r.calls}</td>
                      <td className="py-1 text-right">{formatDuration(r.totalDuration / r.calls)}</td>
                      <td className={`py-1 text-right ${r.failed > 0 ? "text-error" : ""}`}>{rate}</td>
                    </tr>
                  );
                })}
                {toolRows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-2 text-center text-text-muted">
                      No tool calls
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Section>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-surface-2 p-2">
      <div className="text-[10px] uppercase text-text-muted">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-[10px] font-semibold uppercase text-text-muted">{title}</h3>
      {children}
    </div>
  );
}
