import { useEffect, useRef, useState } from "react";
import { BASE_URL } from "./api";
import type { Span } from "./types";

/** Calls `fn` immediately and then every `intervalMs`. Re-runs when `deps` change. */
export function usePolling<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  deps: unknown[],
): { data: T | undefined; error: Error | null; loading: boolean } {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const tick = async () => {
      try {
        const result = await fnRef.current();
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e as Error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading };
}

/**
 * Streams span updates for a session via Server-Sent Events.
 *
 * Connects to `GET /api/sessions/{sessionId}/spans/stream` and replaces the
 * span array each time the server pushes a `spans` event.  The stream is
 * closed automatically by the server when the session finishes (a `done`
 * event is received) and is torn down on the client side when `sessionId`
 * changes or the component unmounts.
 *
 * The browser's native `EventSource` handles reconnection automatically on
 * transient network errors (HTTP 200 with retry or connection drops).
 */
export function useSpanStream(sessionId: string | null): {
  spans: Span[];
  loading: boolean;
  error: Error | null;
} {
  const [spans, setSpans] = useState<Span[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setSpans([]);
      setLoading(false);
      setError(null);
      return;
    }

    setSpans([]);
    setLoading(true);
    setError(null);

    const url = `${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}/spans/stream`;
    const es = new EventSource(url);

    es.addEventListener("spans", (e: MessageEvent<string>) => {
      try {
        setSpans(JSON.parse(e.data) as Span[]);
        setError(null);
      } catch (err) {
        setError(err as Error);
      } finally {
        setLoading(false);
      }
    });

    es.addEventListener("heartbeat", () => {
      // Keep-alive tick — no state change needed, but clear the initial
      // loading spinner if we haven't received any spans yet.
      setLoading(false);
    });

    es.addEventListener("done", () => {
      // Session closed; the server will send no more events.  Close the
      // EventSource to release the connection rather than waiting for the
      // browser to retry a stream the server no longer intends to send.
      es.close();
    });

    es.addEventListener("error", (e: MessageEvent<string>) => {
      try {
        const detail = (JSON.parse(e.data) as { detail?: string }).detail ?? "Stream error";
        setError(new Error(detail));
      } catch {
        // Non-JSON error event; ignore — the browser will reconnect.
      }
      setLoading(false);
    });

    es.onerror = () => {
      // The browser fires onerror when the connection drops.  EventSource
      // will retry automatically (using the server-specified retry interval
      // or the browser default of ~3 s), so we only update loading state.
      setLoading(false);
    };

    return () => {
      es.close();
    };
  }, [sessionId]);

  return { spans, loading, error };
}
