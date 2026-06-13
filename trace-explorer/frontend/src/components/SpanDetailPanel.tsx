import { useState } from "react";
import { Check, Copy, X } from "lucide-react";
import type { SessionSummary, Span, SpanKind } from "../types";
import { spanKind, spanLabel } from "../types";
import { formatCost, formatDuration, formatTimestamp, formatTokens } from "../format";
import { SmartValue } from "./SmartValue";

interface SpanDetailPanelProps {
  span: Span | null;
  session: SessionSummary | null;
  query: string;
  onClose: () => void;
}

export function SpanDetailPanel({ span, session, query, onClose }: SpanDetailPanelProps) {
  if (!span) {
    return (
      <div className="flex h-full w-[30rem] shrink-0 flex-col items-center justify-center border-l border-border bg-surface p-6 text-center text-sm text-text-muted">
        Select a span in the waterfall to inspect its details.
      </div>
    );
  }

  const kind = spanKind(span);
  const attrs = span.attributes;

  return (
    <div className="flex h-full w-[30rem] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${KIND_STYLES[kind]}`}>
            {kind}
          </span>
          <h2 className="truncate text-sm font-semibold">{spanLabel(span)}</h2>
        </div>
        <button onClick={onClose} className="shrink-0 rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <FactGrid kind={kind} span={span} session={session} />

        {kind === "llm" && (
          <>
            <Section title="Prompt" value={attrs["input.value"]} query={query} />
            <Section title="Response" value={attrs["output.value"]} query={query} />
          </>
        )}
        {kind === "tool" && (
          <>
            <Section title="Parameters" value={attrs["tool.parameters"] ?? attrs["input.value"]} query={query} />
            <Section title="Output" value={attrs["output.value"]} query={query} />
          </>
        )}
        {kind === "agent" && <Section title="Input" value={attrs["input.value"]} query={query} />}

        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-text-muted hover:text-text">
            All attributes
          </summary>
          <div className="mt-2 rounded bg-black/30 p-2 font-mono text-[11px] leading-relaxed">
            {Object.entries(attrs)
              .filter(([, v]) => v !== null && v !== undefined)
              .map(([key, value]) => (
                <div key={key} className="flex gap-2 py-0.5">
                  <span className="shrink-0 text-text-muted">{key}</span>
                  <span className="truncate text-text" title={String(value)}>
                    {String(value)}
                  </span>
                  <CopyButton value={String(value)} />
                </div>
              ))}
          </div>
        </details>
      </div>
    </div>
  );
}

const KIND_STYLES: Record<SpanKind, string> = {
  llm: "bg-llm/20 text-llm",
  tool: "bg-tool/20 text-tool",
  agent: "bg-agent/20 text-agent",
};

function FactGrid({ kind, span, session }: { kind: SpanKind; span: Span; session: SessionSummary | null }) {
  const attrs = span.attributes;
  const facts: { label: string; value: string; valueClassName?: string }[] = [
    { label: "Started", value: formatTimestamp(span.start_ns) },
    { label: "Duration", value: formatDuration(span.duration_ms) },
    { label: "Agent", value: String(attrs["agent.name"] ?? "—") },
  ];

  if (kind === "llm") {
    facts.push(
      { label: "Provider", value: String(attrs["llm.provider"] ?? "—") },
      { label: "Finish reason", value: String(attrs["llm.finish_reason"] ?? "—") },
      {
        label: "Tokens (in/out/total)",
        value: `${formatTokens(Number(attrs["llm.token_count.prompt"] ?? 0))} / ${formatTokens(
          Number(attrs["llm.token_count.completion"] ?? 0),
        )} / ${formatTokens(Number(attrs["llm.token_count.total"] ?? 0))}`,
      },
      { label: "Cost", value: formatCost(Number(attrs["cost_usd"] ?? 0)) },
    );
  } else if (kind === "tool") {
    const success = attrs["tool.success"];
    const succeeded = success === true || success === "true";
    facts.push({
      label: "Success",
      value: succeeded ? "yes" : success === undefined ? "—" : "no",
      valueClassName: success === undefined ? undefined : succeeded ? "text-success" : "text-error",
    });
  } else {
    // The placeholder root span for an open session doesn't carry session-level
    // totals yet, so fall back to the session summary's running totals.
    const isOpenRoot = attrs["session.is_open"] === true;
    const totalTokens = isOpenRoot
      ? session?.total_tokens ?? 0
      : Number(attrs["session.total_tokens"] ?? 0);
    const totalCost = isOpenRoot
      ? session?.total_cost_usd ?? 0
      : Number(attrs["session.total_cost_usd"] ?? 0);
    facts.push(
      { label: "Total tokens", value: formatTokens(totalTokens) },
      { label: "Total cost", value: formatCost(totalCost) },
    );
  }

  facts.push(
    { label: "Trace ID", value: span.trace_id },
    { label: "Span ID", value: span.span_id },
  );

  return (
    <div className="mb-3 grid grid-cols-2 gap-2">
      {facts.map((f) => (
        <div key={f.label} className="rounded bg-surface-2 p-2">
          <div className="text-[10px] uppercase text-text-muted">{f.label}</div>
          <div className={`truncate text-xs font-medium ${f.valueClassName ?? ""}`} title={f.value}>
            {f.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1000);
      }}
      title="Copy value"
      className="shrink-0 text-text-muted hover:text-text"
    >
      {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
    </button>
  );
}

function Section({ title, value, query }: { title: string; value: unknown; query: string }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="mb-3">
      <h3 className="mb-1 text-[10px] font-semibold uppercase text-text-muted">{title}</h3>
      <SmartValue value={String(value)} query={query} />
    </div>
  );
}
