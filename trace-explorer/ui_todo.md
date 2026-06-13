# Trace Explorer UI/UX TODO

Findings from a UI/UX review of the frontend, using a seeded demo session.

## Bugs

- [ ] **Span ID / Trace ID format mismatch** (`backend/tempo.py`, `SpanDetailPanel.tsx`)
  Trace ID renders as hex (`bbbbb...`), but Span ID renders as base64
  (`AAAAAAAAAAE=`). `tempo.py` passes OTLP `spanId`/`parentSpanId` through
  as-is (base64) while `traceID` comes from the search-result field (hex).
  Span IDs won't match Grafana's Tempo UI (hex), making cross-referencing
  impossible. Decode span/parent span IDs to hex in `tempo.py`.

- [ ] **Layout breaks below ~1200px width**
  At 1024px the waterfall's timeline track (ruler + bars) disappears
  entirely — only the label column renders. Fixed widths (`w-80` sidebar +
  `LABEL_WIDTH=320` + `w-[30rem]` detail panel) leave zero/negative space
  for the track. Needs a responsive fallback (e.g. collapsible sidebar/detail
  panel, or min-width + horizontal scroll for the whole layout).

- [ ] **Tool success/failure has no visual cue** (`SpanDetailPanel.tsx`,
  `FactGrid`)
  The `SUCCESS` fact shows plain "yes"/"no" with no color, even though
  `--color-success`/`--color-error` tokens exist and are used elsewhere
  (e.g. `JsonTree` booleans). A failed tool call looks identical to a
  successful one at a glance.

- [ ] **"All attributes" values are truncated with no way to see full
  content** (`SpanDetailPanel.tsx`)
  `<span className="truncate">{String(value)}</span>` has no `title`
  attribute and no copy button, so long `output.value`/`tool.parameters`
  strings are permanently cut off.

## New issues from the `opencode.session` span staying open (plugin v1.1.0+)

`opencode-plugin-otel` 1.1.0 keeps the root `opencode.session` span open across
`session.idle` so later turns nest under it, only exporting it to Tempo on
`session.deleted`/shutdown. `tempo.py` already synthesizes a placeholder root
row (`session.is_open: true`) for the still-open span, but the frontend has no
awareness of this flag, causing:

- [ ] **"Wall clock" stat is wrong (and shrinks back to "correct") while a
  session is active** (`SessionStats.tsx`, `tempo.py:list_sessions`)
  `list_sessions` derives `duration_ms` only from spans that have already been
  exported to Tempo (LLM/tool spans), since the still-open root span isn't
  there yet. For an active session this massively undercounts: observed
  "Wall clock 3.46s" while the synthesized root span in the waterfall already
  shows "1m 12s" and counting. The header stat and the waterfall disagree
  about how long the session has been running.

- [ ] **No "live"/"in progress" indicator anywhere** (`SessionList.tsx`,
  `SpanLabel`/`SpanBar` in `Waterfall.tsx`)
  The synthesized placeholder root span (`session.is_open: true`) renders
  exactly like any completed `AGENT` span — same purple bar, same label. There's
  no badge in the session list or waterfall to show a session is still
  receiving turns, even though the backend now distinguishes this case.

- [ ] **Root span detail panel shows "Total tokens: 0" / "Total cost: $0" for
  an open session** (`SpanDetailPanel.tsx` `FactGrid`, `tempo.py`)
  The synthesized placeholder root span only carries `session.id`,
  `agent.name`, and `session.is_open` — not `session.total_tokens`/
  `session.total_cost_usd` (those are only set when the real span is finalized
  on `session.deleted`). Clicking the root row of an active session shows
  "Total tokens 0" / "Total cost $0" even though the header bar above
  correctly shows the real running totals.

- [ ] **Open session's root span bar overflows the waterfall with no re-fit**
  (`Waterfall.tsx`)
  "Fit to screen" zoom is applied once per session on first load (so manual
  zoom survives live refresh, per the previous fix). But for an active
  session, the placeholder root span's duration keeps growing every poll, so
  `totalMs` keeps growing while `pxPerMs` stays fixed — the root span's bar
  increasingly overflows past the right edge of the visible track with no
  obvious affordance (scrollbar is thin/easy to miss) showing the session is
  still extending.

## UX improvements

- [ ] **Add a time-range slider/picker for the session list**
  Currently `list_sessions` always pulls everything (limit 4000) with no
  way to scope the query. Add a time-box selector (e.g. last 1h/6h/24h or
  a draggable range) in the header/sidebar that filters which sessions are
  fetched/displayed, so older sessions don't clutter the list and large
  Tempo deployments don't require pulling the full history on every poll.

- [ ] **Two overlapping search inputs**
  Header "Search prompts, tools, outputs…" highlights/dims spans in the
  waterfall, while the sidebar "Filter sessions, models, agents…" filters
  the session list. Same visual style and similar wording but very
  different scope — consider distinguishing them more clearly (icon,
  placement, or label).

- [ ] **Tiny spans are hard to interact with**
  Sub-second spans (e.g. a 320ms tool call in a 2m12s session) render as
  ~2px slivers — easy to miss and fiddly to click. Consider a minimum
  clickable width, or "jump to next/prev span" navigation.

- [ ] **Locale-dependent timestamps** (`format.ts`, `formatTimestamp`)
  Uses `toLocaleString(undefined, …)`, so on a non-English locale machine
  it renders e.g. "13. Juni, 07:58:22" inside an otherwise all-English UI.
  Consider forcing a fixed locale (e.g. `en-US`) for consistency.

- [ ] **Sort buttons lack `aria-pressed`** (`SessionList.tsx`)
  Recent/Cost/Duration/Tokens buttons rely purely on background color for
  active state — not announced to screen readers.

## Notes / things that work well (no action needed)

- Dark theme, color-coded LLM/Tool/Agent kinds, and the cost/token summary
  bar are clean and information-dense.
- Waterfall zoom (ctrl/cmd+scroll, fit-to-screen, collapse subtrees) feels
  solid; zoom state is preserved across live refresh.
- `SmartValue`/`JsonTree` auto-pretty-printing of JSON params/output with
  collapsible nodes is a great detail.
- Search-and-dim highlighting across the waterfall + detail panel works
  correctly and is useful for finding relevant spans in a long session.
