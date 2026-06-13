import { useEffect, useState } from "react";
import { Activity, SearchCode } from "lucide-react";
import { fetchSessionSpans, fetchSessions } from "./api";
import type { SessionRange } from "./api";
import { usePolling } from "./hooks";
import { SessionList } from "./components/SessionList";
import { SessionStats } from "./components/SessionStats";
import { Waterfall } from "./components/Waterfall";
import { SpanDetailPanel } from "./components/SpanDetailPanel";
import type { Span } from "./types";

function App() {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sessionRange, setSessionRange] = useState<SessionRange>("24h");

  const { data: sessions = [], loading: sessionsLoading } = usePolling(
    () => fetchSessions(sessionRange),
    5000,
    [sessionRange],
  );

  const { data: spans = [] } = usePolling<Span[]>(
    () => (selectedSessionId ? fetchSessionSpans(selectedSessionId) : Promise.resolve([])),
    4000,
    [selectedSessionId],
  );

  // Auto-select the most recent session on first load.
  useEffect(() => {
    if (!selectedSessionId && sessions.length > 0) {
      setSelectedSessionId(sessions[0].session_id);
    }
  }, [sessions, selectedSessionId]);

  // Clear span selection when switching sessions.
  useEffect(() => {
    setSelectedSpanId(null);
  }, [selectedSessionId]);

  const selectedSession = sessions.find((s) => s.session_id === selectedSessionId);
  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) ?? null;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2.5">
        <Activity size={18} className="text-accent" />
        <h1 className="text-sm font-semibold">Trace Explorer</h1>
        <span className="text-xs text-text-muted">OpenCode session traces</span>
        <div
          className="ml-auto flex w-80 items-center gap-2 rounded border border-border bg-surface-2 px-2 py-1"
          title="Search within the selected session's spans"
        >
          <SearchCode size={14} className="text-text-muted" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search this session's spans..."
            className="w-full bg-transparent text-sm outline-none"
          />
        </div>
      </header>

      <div className="flex flex-1 overflow-x-auto overflow-y-hidden">
        <SessionList
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          onSelect={setSelectedSessionId}
          loading={sessionsLoading}
          range={sessionRange}
          onRangeChange={setSessionRange}
        />

        <main className="flex min-w-[28rem] flex-1 flex-col overflow-hidden">
          {selectedSession ? (
            <>
              <SessionStats session={selectedSession} />
              <Waterfall
                spans={spans}
                sessionId={selectedSessionId}
                selectedSpanId={selectedSpanId}
                onSelectSpan={(span) => setSelectedSpanId(span.span_id)}
                searchQuery={searchQuery}
              />
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-text-muted">
              {sessionsLoading ? "Loading sessions..." : "Select a session to begin."}
            </div>
          )}
        </main>

        <SpanDetailPanel
          span={selectedSpan}
          session={selectedSession ?? null}
          query={searchQuery}
          onClose={() => setSelectedSpanId(null)}
        />
      </div>
    </div>
  );
}

export default App;
