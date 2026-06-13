import type { Span } from "./types";

/** Flatten everything searchable about a span into one lowercase string. */
function searchHaystack(span: Span): string {
  const parts: string[] = [span.span_name, span.trace_id, span.span_id];
  for (const value of Object.values(span.attributes)) {
    if (value !== null && value !== undefined) parts.push(String(value));
  }
  return parts.join("\n").toLowerCase();
}

export function spanMatchesQuery(span: Span, query: string): boolean {
  if (!query.trim()) return true;
  return searchHaystack(span).includes(query.trim().toLowerCase());
}
