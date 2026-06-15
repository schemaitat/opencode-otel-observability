import { useEffect, useState } from "react";
import { Activity, LayoutDashboard, SearchCode, Waypoints } from "lucide-react";
import { fetchOverview, fetchSessionSpans, fetchSessions } from "./api";
import type { SessionRange } from "./api";
import { usePolling } from "./hooks";
import { SessionList } from "./components/SessionList";
import { SessionStats } from "./components/SessionStats";
import { SessionStatsPanel } from "./components/SessionStatsPanel";
import { OverviewView } from "./components/OverviewView";
import { Waterfall } from "./components/Waterfall";
import { SpanDetailPanel } from "./components/SpanDetailPanel";
import type { Span } from "./types";

type View = "sessions" | "overview";

function App() {
  const [view, setView] = useState<View>("sessions");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sessionRange, setSessionRange] = useState<SessionRange>("24h");
  const [overviewRange, setOverviewRange] = useState<SessionRange>("24h");
  const [showStats, setShowStats] = useState(false);

  const { data: sessions = [], loading: sessionsLoading } = usePolling(
    () => fetchSessions(sessionRange),
    5000,
    [sessionRange],
  );

  const { data: overview, loading: overviewLoading } = usePolling(
    () => fetchOverview(overviewRange),
    10000,
    [overviewRange, view],
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

  // Clear span selection and stats panel when switching sessions.
  useEffect(() => {
    setSelectedSpanId(null);
    setShowStats(false);
  }, [selectedSessionId]);

  const selectedSession = sessions.find((s) => s.session_id === selectedSessionId);
  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) ?? null;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2.5">
        <Activity size={18} className="text-accent" />
        <h1 className="text-sm font-semibold">Trace Explorer</h1>
        <span className="text-xs text-text-muted">OpenCode session traces</span>

        <div className="ml-4 flex items-center gap-1 text-xs">
          <button
            onClick={() => setView("sessions")}
            aria-pressed={view === "sessions"}
            className={`flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
              view === "sessions" ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text"
            }`}
          >
            <Waypoints size={13} />
            Sessions
          </button>
          <button
            onClick={() => setView("overview")}
            aria-pressed={view === "overview"}
            className={`flex items-center gap-1.5 rounded px-2 py-1 transition-colors ${
              view === "overview" ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text"
            }`}
          >
            <LayoutDashboard size={13} />
            Overview
          </button>
        </div>

        {view === "sessions" && (
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
        )}
      </header>

      {view === "overview" ? (
        <OverviewView
          overview={overview}
          loading={overviewLoading}
          range={overviewRange}
          onRangeChange={setOverviewRange}
          onOpenSession={(sessionId) => {
            setSessionRange("all");
            setSelectedSessionId(sessionId);
            setView("sessions");
          }}
        />
      ) : (
        <div className="flex flex-1 overflow-x-auto overflow-y-hidden">
          <SessionList
            sessions={sessions}
            selectedSessionId={selectedSessionId}
            onSelect={setSelectedSessionId}
            loading={sessionsLoading}
            range={sessionRange}
            onRangeChange={setSessionRange}
          />

          <main className="relative flex min-w-[28rem] flex-1 flex-col overflow-hidden">
            {selectedSession ? (
              <>
                <SessionStats session={selectedSession} onShowStats={() => setShowStats(true)} />
                <Waterfall
                  spans={spans}
                  sessionId={selectedSessionId}
                  selectedSpanId={selectedSpanId}
                  onSelectSpan={(span) => setSelectedSpanId(span.span_id)}
                  searchQuery={searchQuery}
                />
                {showStats && <SessionStatsPanel spans={spans} onClose={() => setShowStats(false)} />}
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
            onOpenSession={(sessionId) => {
              setSessionRange("all");
              setSelectedSessionId(sessionId);
            }}
          />
        </div>
      )}
    </div>
  );
}

export default App;
