import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Span } from "../types";
import { spanKind, spanLabel } from "../types";
import { formatCost, formatDuration } from "../format";
import { spanMatchesQuery } from "../search";
import { ZoomIn, ZoomOut, Maximize2, ChevronDown, ChevronRight } from "lucide-react";

interface WaterfallProps {
  spans: Span[];
  sessionId: string | null;
  selectedSpanId: string | null;
  onSelectSpan: (span: Span) => void;
  searchQuery: string;
}

const ROW_HEIGHT = 28;
const LABEL_WIDTH = 320;
const RULER_HEIGHT = 28;
const INDENT_PX = 14;

export function Waterfall({ spans, sessionId, selectedSpanId, onSelectSpan, searchQuery }: WaterfallProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const rulerRef = useRef<HTMLDivElement>(null);
  const [pxPerMs, setPxPerMs] = useState(1);
  const [containerWidth, setContainerWidth] = useState(800);

  const { sessionStartNs, totalMs } = useMemo(() => {
    if (spans.length === 0) return { sessionStartNs: 0, totalMs: 1 };
    const start = Math.min(...spans.map((s) => s.start_ns));
    const end = Math.max(...spans.map((s) => s.start_ns + s.duration_ms * 1e6));
    return { sessionStartNs: start, totalMs: Math.max((end - start) / 1e6, 1) };
  }, [spans]);

  const fitPxPerMs = containerWidth > 0 ? containerWidth / totalMs : 1;

  // Track container width for "fit to screen"
  useLayoutEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      setContainerWidth(entries[0].contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Reset zoom to "fit" when the session changes, and keep re-fitting on later polls
  // as long as the view is still at "fit" (so the still-growing root span of an open
  // session stays visible). Once the user manually zooms, stop auto-refitting.
  const lastFitRef = useRef<{ sessionId: string | null; pxPerMs: number }>({ sessionId: null, pxPerMs: 1 });
  useEffect(() => {
    if (containerWidth <= 0 || spans.length === 0) return;
    const fit = containerWidth / totalMs;
    setPxPerMs((prev) => {
      const isNewSession = lastFitRef.current.sessionId !== sessionId;
      const isAtFit = Math.abs(prev - lastFitRef.current.pxPerMs) < 1e-9;
      if (!isNewSession && !isAtFit) return prev;
      lastFitRef.current = { sessionId, pxPerMs: fit };
      return fit;
    });
  }, [sessionId, containerWidth, totalMs, spans.length]);

  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  useEffect(() => setCollapsedIds(new Set()), [sessionId]);

  // Two-sided slider for narrowing the waterfall to a sub-range of the session's
  // timeline, expressed as fractions (0-1) of `totalMs`.
  const [timeRange, setTimeRange] = useState<[number, number]>([0, 1]);
  useEffect(() => setTimeRange([0, 1]), [sessionId]);
  const isRangeFiltered = timeRange[0] > 0 || timeRange[1] < 1;

  const childrenCount = useMemo(() => {
    const counts = new Map<string, number>();
    for (const span of spans) {
      if (span.parent_span_id) {
        counts.set(span.parent_span_id, (counts.get(span.parent_span_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [spans]);

  const visibleSpans = useMemo(() => {
    let result = spans;

    if (collapsedIds.size > 0) {
      const spanById = new Map(spans.map((s) => [s.span_id, s]));
      result = result.filter((span) => {
        let parentId = span.parent_span_id;
        while (parentId) {
          if (collapsedIds.has(parentId)) return false;
          parentId = spanById.get(parentId)?.parent_span_id ?? null;
        }
        return true;
      });
    }

    if (isRangeFiltered) {
      const windowStartMs = timeRange[0] * totalMs;
      const windowEndMs = timeRange[1] * totalMs;
      result = result.filter((span) => {
        const spanStartMs = (span.start_ns - sessionStartNs) / 1e6;
        const spanEndMs = spanStartMs + span.duration_ms;
        return spanEndMs >= windowStartMs && spanStartMs <= windowEndMs;
      });
    }

    return result;
  }, [spans, collapsedIds, isRangeFiltered, timeRange, totalMs, sessionStartNs]);

  const toggleCollapse = (spanId: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(spanId)) next.delete(spanId);
      else next.add(spanId);
      return next;
    });
  };

  const minPxPerMs = fitPxPerMs;
  const maxPxPerMs = fitPxPerMs * 500;
  const trackWidth = Math.max(totalMs * pxPerMs, containerWidth);

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const container = trackRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const cursorOffset = e.clientX - rect.left;
    const cursorTrackX = container.scrollLeft + cursorOffset;
    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
    const next = Math.min(Math.max(pxPerMs * factor, minPxPerMs), maxPxPerMs);

    const ratio = next / pxPerMs;
    setPxPerMs(next);

    requestAnimationFrame(() => {
      if (!trackRef.current) return;
      trackRef.current.scrollLeft = cursorTrackX * ratio - cursorOffset;
      if (rulerRef.current) rulerRef.current.scrollLeft = trackRef.current.scrollLeft;
    });
  };

  const syncScroll = (source: "track" | "ruler") => (e: React.UIEvent<HTMLDivElement>) => {
    const scrollLeft = e.currentTarget.scrollLeft;
    const target = source === "track" ? rulerRef.current : trackRef.current;
    if (target) target.scrollLeft = scrollLeft;
  };

  const zoom = (factor: number) => {
    const next = Math.min(Math.max(pxPerMs * factor, minPxPerMs), maxPxPerMs);
    setPxPerMs(next);
  };

  const resetZoom = () => setPxPerMs(fitPxPerMs);

  if (spans.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted">
        No spans in this session.
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center justify-end gap-1 border-b border-border bg-surface px-2 py-1">
        <button onClick={() => zoom(1 / 1.5)} className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text" title="Zoom out">
          <ZoomOut size={14} />
        </button>
        <button onClick={() => zoom(1.5)} className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text" title="Zoom in">
          <ZoomIn size={14} />
        </button>
        <button onClick={resetZoom} className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text" title="Fit to screen">
          <Maximize2 size={14} />
        </button>
        <span className="ml-2 text-xs text-text-muted">Ctrl/Cmd + scroll to zoom</span>
      </div>

      {/* Time-range selection slider */}
      <div className="flex items-center gap-2 border-b border-border bg-surface px-2 py-1.5">
        <div className="flex shrink-0 items-center gap-2 text-xs text-text-muted" style={{ width: LABEL_WIDTH }}>
          <span>
            {formatDuration(timeRange[0] * totalMs)} – {formatDuration(timeRange[1] * totalMs)}
          </span>
          {isRangeFiltered && (
            <button
              onClick={() => setTimeRange([0, 1])}
              className="rounded px-1.5 py-0.5 text-text-muted hover:bg-surface-2 hover:text-text"
            >
              Reset
            </button>
          )}
        </div>
        <TimeRangeSlider value={timeRange} onChange={setTimeRange} />
      </div>

      {/* Ruler */}
      <div className="flex border-b border-border bg-surface">
        <div className="shrink-0" style={{ width: LABEL_WIDTH, height: RULER_HEIGHT }} />
        <div ref={rulerRef} onScroll={syncScroll("ruler")} className="flex-1 overflow-x-hidden">
          <Ruler totalMs={totalMs} pxPerMs={pxPerMs} width={trackWidth} height={RULER_HEIGHT} />
        </div>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex">
          <div className="shrink-0" style={{ width: LABEL_WIDTH }}>
            {visibleSpans.map((span, idx) => (
              <SpanLabel
                key={span.span_id}
                span={span}
                index={idx}
                hasChildren={(childrenCount.get(span.span_id) ?? 0) > 0}
                collapsed={collapsedIds.has(span.span_id)}
                onToggleCollapse={() => toggleCollapse(span.span_id)}
                selected={span.span_id === selectedSpanId}
                dimmed={!spanMatchesQuery(span, searchQuery)}
                onClick={() => onSelectSpan(span)}
              />
            ))}
          </div>
          <div ref={trackRef} onWheel={handleWheel} onScroll={syncScroll("track")} className="flex-1 overflow-x-auto">
            <div className="relative" style={{ width: trackWidth, height: visibleSpans.length * ROW_HEIGHT }}>
              <GridLines totalMs={totalMs} pxPerMs={pxPerMs} height={visibleSpans.length * ROW_HEIGHT} />
              {visibleSpans.map((span, idx) => (
                <SpanBar
                  key={span.span_id}
                  span={span}
                  index={idx}
                  sessionStartNs={sessionStartNs}
                  pxPerMs={pxPerMs}
                  selected={span.span_id === selectedSpanId}
                  dimmed={!spanMatchesQuery(span, searchQuery)}
                  onClick={() => onSelectSpan(span)}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const KIND_STYLES: Record<string, string> = {
  llm: "bg-llm/20 text-llm",
  tool: "bg-tool/20 text-tool",
  agent: "bg-agent/20 text-agent",
};

const BAR_COLOR: Record<string, string> = {
  llm: "bg-llm",
  tool: "bg-tool",
  agent: "bg-agent",
};

function SpanLabel({
  span,
  index,
  hasChildren,
  collapsed,
  onToggleCollapse,
  selected,
  dimmed,
  onClick,
}: {
  span: Span;
  index: number;
  hasChildren: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  selected: boolean;
  dimmed: boolean;
  onClick: () => void;
}) {
  const kind = spanKind(span);
  const label = spanLabel(span);

  return (
    <div
      style={{ height: ROW_HEIGHT, paddingLeft: span.depth * INDENT_PX }}
      className={`flex w-full items-center gap-1 border-b border-border/50 text-xs transition-colors ${
        selected ? "bg-accent/20" : "hover:bg-surface-2"
      } ${dimmed ? "opacity-30" : ""}`}
    >
      <span className="w-5 shrink-0 text-right text-text-muted">{index + 1}</span>
      {hasChildren ? (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleCollapse();
          }}
          className="shrink-0 text-text-muted hover:text-text"
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </button>
      ) : (
        <span className="w-3 shrink-0" />
      )}
      <button onClick={onClick} title={label} className="flex min-w-0 flex-1 items-center gap-2 truncate text-left">
        <span className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-semibold uppercase ${KIND_STYLES[kind]}`}>
          {kind}
        </span>
        {span.attributes["session.is_open"] && (
          <span className="flex shrink-0 items-center gap-1 rounded bg-success/15 px-1 py-0.5 text-[10px] font-semibold uppercase text-success">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
            Live
          </span>
        )}
        <span className="truncate">{label}</span>
      </button>
    </div>
  );
}

function SpanBar({
  span,
  index,
  sessionStartNs,
  pxPerMs,
  selected,
  dimmed,
  onClick,
}: {
  span: Span;
  index: number;
  sessionStartNs: number;
  pxPerMs: number;
  selected: boolean;
  dimmed: boolean;
  onClick: () => void;
}) {
  const kind = spanKind(span);
  const offsetMs = (span.start_ns - sessionStartNs) / 1e6;
  const left = offsetMs * pxPerMs;
  const width = Math.max(span.duration_ms * pxPerMs, 2);

  // Tiny spans render as slivers a couple px wide, which are hard to spot and
  // click. Pad the clickable hit area to a minimum width, centered on the bar.
  const MIN_HIT_WIDTH = 8;
  const hitWidth = Math.max(width, MIN_HIT_WIDTH);
  const hitLeft = left - (hitWidth - width) / 2;

  const cost = span.attributes.cost_usd;
  const tooltip = `${spanLabel(span)}\n${formatDuration(span.duration_ms)}${
    kind === "llm" && cost ? `\n${formatCost(cost)}` : ""
  }`;

  return (
    <div
      style={{ height: ROW_HEIGHT, top: index * ROW_HEIGHT }}
      className="absolute left-0 w-full border-b border-border/50"
    >
      <button
        onClick={onClick}
        title={tooltip}
        style={{
          left: hitLeft,
          width: hitWidth,
          top: 4,
          height: ROW_HEIGHT - 8,
        }}
        className="absolute flex items-center"
      >
        <span
          style={{ width, minWidth: 2 }}
          className={`relative block h-full rounded transition-opacity ${BAR_COLOR[kind]} ${
            selected ? "ring-2 ring-white" : ""
          } ${dimmed ? "opacity-20" : "opacity-90 hover:opacity-100"} ${
            span.attributes["session.is_open"] ? "animate-pulse" : ""
          }`}
        >
          {width > 60 && (
            <span className="absolute inset-y-0 left-1.5 flex items-center truncate text-[10px] font-medium text-black/80">
              {formatDuration(span.duration_ms)}
            </span>
          )}
        </span>
      </button>
    </div>
  );
}

/** Two-sided range slider for narrowing the waterfall to [start, end] fractions (0-1) of the timeline. */
function TimeRangeSlider({
  value,
  onChange,
}: {
  value: [number, number];
  onChange: (value: [number, number]) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);

  const dragThumb = () => (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const moveThumb = (which: 0 | 1) => (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.buttons === 0) return;
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const frac = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    if (which === 0) onChange([Math.min(frac, value[1]), value[1]]);
    else onChange([value[0], Math.max(frac, value[0])]);
  };

  return (
    <div ref={trackRef} className="relative h-1.5 flex-1 rounded-full bg-surface-2">
      <div
        className="absolute h-full rounded-full bg-accent/40"
        style={{ left: `${value[0] * 100}%`, right: `${(1 - value[1]) * 100}%` }}
      />
      <Thumb frac={value[0]} onPointerDown={dragThumb()} onPointerMove={moveThumb(0)} />
      <Thumb frac={value[1]} onPointerDown={dragThumb()} onPointerMove={moveThumb(1)} />
    </div>
  );
}

function Thumb({
  frac,
  onPointerDown,
  onPointerMove,
}: {
  frac: number;
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      style={{ left: `${frac * 100}%` }}
      className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize rounded-full border-2 border-accent bg-surface shadow"
    />
  );
}

function Ruler({ totalMs, pxPerMs, width, height }: { totalMs: number; pxPerMs: number; width: number; height: number }) {
  const step = niceStep(totalMs, width / pxPerMs);
  const ticks: number[] = [];
  for (let t = 0; t <= totalMs; t += step) ticks.push(t);

  return (
    <div className="relative" style={{ width, height }}>
      {ticks.map((t) => (
        <div
          key={t}
          className="absolute top-0 h-full border-l border-border text-[10px] text-text-muted"
          style={{ left: t * pxPerMs }}
        >
          <span className="ml-1">{formatDuration(t)}</span>
        </div>
      ))}
    </div>
  );
}

function GridLines({ totalMs, pxPerMs, height }: { totalMs: number; pxPerMs: number; height: number }) {
  const step = niceStep(totalMs, height > 0 ? totalMs : totalMs);
  const ticks: number[] = [];
  for (let t = 0; t <= totalMs; t += step) ticks.push(t);

  return (
    <>
      {ticks.map((t) => (
        <div
          key={t}
          className="absolute top-0 border-l border-border/40"
          style={{ left: t * pxPerMs, height }}
        />
      ))}
    </>
  );
}

/** Pick a "nice" tick interval (in ms) so we get roughly 6-10 ticks across the view. */
function niceStep(totalMs: number, _visibleMs: number): number {
  const targetTicks = 8;
  const raw = totalMs / targetTicks;
  const steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000, 60000, 120000, 300000, 600000];
  for (const s of steps) {
    if (raw <= s) return s;
  }
  return steps[steps.length - 1];
}
