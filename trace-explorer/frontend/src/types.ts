export interface SessionSummary {
  session_id: string;
  start_ns: number;
  end_ns: number;
  duration_ms: number;
  llm_calls: number;
  tool_calls: number;
  total_cost_usd: number;
  total_tokens: number;
  models: string[];
  agents: string[];
  is_open: boolean;
}

export interface SpanAttributes {
  [key: string]: string | number | boolean | null | undefined;
  "session.id"?: string;
  "openinference.span.kind"?: string;
  "agent.name"?: string;
  "llm.model_name"?: string;
  "llm.provider"?: string;
  "llm.finish_reason"?: string;
  "llm.token_count.prompt"?: number;
  "llm.token_count.completion"?: number;
  "llm.token_count.total"?: number;
  "cost_usd"?: number;
  "duration_ms"?: number;
  "input.value"?: string;
  "output.value"?: string;
  "tool.name"?: string;
  "tool.parameters"?: string;
  "tool.success"?: boolean | string;
  "session.is_open"?: boolean;
  "session.total_tokens"?: number;
  "session.total_cost_usd"?: number;
}

export interface Span {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  span_name: string;
  start_ns: number;
  duration_ms: number;
  depth: number;
  attributes: SpanAttributes;
}

export type SpanKind = "llm" | "tool" | "agent";

export function spanKind(span: Span): SpanKind {
  if (span.span_name === "opencode.llm") return "llm";
  if (span.span_name.startsWith("opencode.tool.")) return "tool";
  return "agent";
}

export function spanLabel(span: Span): string {
  const kind = spanKind(span);
  if (kind === "llm") {
    return span.attributes["llm.model_name"] || "unknown model";
  }
  if (kind === "tool") {
    return span.attributes["tool.name"] || span.span_name.replace(/^opencode\.tool\./, "");
  }
  return span.attributes["agent.name"] || span.span_name.replace(/^opencode\./, "");
}
