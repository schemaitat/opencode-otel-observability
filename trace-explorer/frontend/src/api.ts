import type { Overview, SessionSummary, Span } from "./types";

export const BASE_URL = import.meta.env.VITE_API_URL ?? "";

export type SessionRange = "1h" | "6h" | "24h" | "all";

export const RANGE_OPTIONS: [SessionRange, string][] = [
  ["1h", "1h"],
  ["6h", "6h"],
  ["24h", "24h"],
  ["all", "All"],
];

export async function fetchSessions(range: SessionRange = "24h"): Promise<SessionSummary[]> {
  const res = await fetch(`${BASE_URL}/api/sessions?range=${range}`);
  if (!res.ok) throw new Error(`Failed to load sessions: ${res.status}`);
  return res.json();
}

export async function fetchOverview(range: SessionRange = "24h"): Promise<Overview> {
  const res = await fetch(`${BASE_URL}/api/overview?range=${range}`);
  if (!res.ok) throw new Error(`Failed to load overview: ${res.status}`);
  return res.json();
}

export async function fetchSessionSpans(sessionId: string): Promise<Span[]> {
  const res = await fetch(`${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}/spans`);
  if (!res.ok) throw new Error(`Failed to load spans: ${res.status}`);
  return res.json();
}
