import { useEffect, useRef, useState } from "react";
import { Activity, LayoutDashboard, SearchCode, Waypoints } from "lucide-react";
import { ToggleButton } from "./components/ToggleButton";
import { fetchOverview, fetchSessions } from "./api";
import type { SessionRange } from "./api";
import { usePolling, useSpanStream } from "./hooks";
import { SessionList } from "./components/SessionList";
import { SessionStats } from "./components/SessionStats";
import { SessionStatsPanel } from "./components/SessionStatsPanel";
import { OverviewView } from "./components/OverviewView";
import { Waterfall } from "./components/Waterfall";
import { SpanDetailPanel } from "./components/SpanDetailPanel";

type View = "sessions" | "overview";

// Polling intervals for sessions and overview lists, configurable via env vars.
// The span waterfall now uses Server-Sent Events instead of polling, so
// VITE_SPANS_POLL_MS is no longer needed.
const SESSIONS_POLL_MS = Number(import.meta.env.VITE_SESSIONS_POLL_MS) || 5000;
const OVERVIEW_POLL_MS = Number(import.meta.env.VITE_OVERVIEW_POLL_MS) || 10000;

function App() {
  const [view, setView] = useState<View>("sessions");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sessionRange, setSessionRange] = useState<SessionRange>("24h");
  const [overviewRange, setOverviewRange] = useState<SessionRange>("24h");
  const [showStats, setShowStats] = useState(false);
  const [drawerHeight, setDrawerHeight] = useState(300);
  const drawerDragRef = useRef<{ startY: number; startH: number } | null>(null);

  const { data: sessions = [], loading: sessionsLoading } = usePolling(
    () => fetchSessions(sessionRange),
    SESSIONS_POLL_MS,
    [sessionRange],
  );

  const { data: overview, loading: overviewLoading } = usePolling(
    () => fetchOverview(overviewRange),
    OVERVIEW_POLL_MS,
    [overviewRange, view],
  );

  // Span waterfall uses SSE instead of polling: the server pushes updates
  // only when the span set changes, at ~500 ms latency, rather than
  // transmitting the full list every SPANS_POLL_MS regardless of changes.
  const { spans } = useSpanStream(selectedSessionId);

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

  const handleDrawerResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    drawerDragRef.current = { startY: e.clientY, startH: drawerHeight };
    const onMove = (ev: MouseEvent) => {
      if (!drawerDragRef.current) return;
      const delta = drawerDragRef.current.startY - ev.clientY;
      setDrawerHeight(Math.max(150, Math.min(drawerDragRef.current.startH + delta, window.innerHeight * 0.75)));
    };
    const onUp = () => {
      drawerDragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const selectedSession = sessions.find((s) => s.session_id === selectedSessionId);
  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) ?? null;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-2 border-b border-border bg-surface px-4 py-2.5">
        <Activity size={18} className="text-accent" />
        <h1 className="text-sm font-semibold">Trace Explorer</h1>
        <span className="text-xs text-text-muted">OpenCode session traces</span>

        <div className="ml-4 flex items-center gap-1">
          <ToggleButton active={view === "sessions"} onClick={() => setView("sessions")}>
            <Waypoints size={13} />
            Sessions
          </ToggleButton>
          <ToggleButton active={view === "overview"} onClick={() => setView("overview")}>
            <LayoutDashboard size={13} />
            Overview
          </ToggleButton>
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
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex flex-1 overflow-hidden">
            <SessionList
              sessions={sessions}
              selectedSessionId={selectedSessionId}
              onSelect={setSelectedSessionId}
              loading={sessionsLoading}
              range={sessionRange}
              onRangeChange={setSessionRange}
            />

            <main className="relative flex flex-1 flex-col overflow-hidden">
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
          </div>

          {selectedSpan && (
            <div
              style={{ height: drawerHeight }}
              className="flex shrink-0 flex-col border-t border-border bg-surface"
            >
              <div
                onMouseDown={handleDrawerResizeStart}
                className="h-1.5 shrink-0 cursor-ns-resize bg-border/50 transition-colors hover:bg-accent/60"
                title="Drag to resize"
              />
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
      )}
    </div>
  );
}

export default App;
