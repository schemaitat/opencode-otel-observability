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
  parent_session_id: string | null;
}

export interface ModelUsage {
  model: string;
  calls: number;
  cost: number;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  providers: string[];
}

export interface AgentUsage {
  agent: string;
  calls: number;
  cost: number;
  total_tokens: number;
}

export interface ToolUsage {
  tool: string;
  calls: number;
  total_duration_ms: number;
  succeeded: number;
  failed: number;
}

export interface LlmCallRow {
  start_ns: number;
  session_id: string;
  agent: string;
  model: string;
  input: string | null;
  finish_reason: string | null;
  cost_usd: number;
  duration_ms: number;
}

export interface ToolCallRow {
  start_ns: number;
  session_id: string;
  tool: string;
  parameters: string | null;
  success: boolean | string | null;
  output: string | null;
  duration_ms: number;
}

export interface OverviewTimeseries {
  bucket_starts_ns: number[];
  cost_by_model: Record<string, number[]>;
  tokens_by_model: Record<string, number[]>;
  tool_calls_by_tool: Record<string, number[]>;
}

export interface Overview {
  total_sessions: number;
  total_cost_usd: number;
  total_tokens: number;
  total_llm_calls: number;
  total_tool_calls: number;
  by_model: ModelUsage[];
  by_agent: AgentUsage[];
  by_tool: ToolUsage[];
  llm_calls: LlmCallRow[];
  tool_calls: ToolCallRow[];
  timeseries: OverviewTimeseries;
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
  "subagent.session_id"?: string;
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
