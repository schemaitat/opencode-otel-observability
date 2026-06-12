import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, dcc, html, no_update

import tempo_client
from narrative import build_narrative, build_summary

app = Dash(__name__)
app.title = "Session Explorer"

CARD_STYLE = {
    "border": "1px solid #ddd",
    "borderRadius": "6px",
    "padding": "12px 16px",
    "textAlign": "center",
    "flex": "1",
    "backgroundColor": "#fafafa",
}

PANEL_STYLE = {
    "border": "1px solid #ddd",
    "borderRadius": "6px",
    "padding": "16px",
    "flex": "1",
    "minHeight": "300px",
    "overflowY": "auto",
    "maxHeight": "500px",
}


def stat_card(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Div(value, style={"fontSize": "24px", "fontWeight": "bold"}),
            html.Div(label, style={"fontSize": "12px", "color": "#666"}),
        ],
        style=CARD_STYLE,
    )


app.layout = html.Div(
    [
        html.H2("Session Explorer"),
        html.Div(
            [
                dcc.Dropdown(
                    id="session-dropdown",
                    options=[],
                    placeholder="Select a session...",
                    style={"flex": "1"},
                ),
                html.Button("Refresh sessions", id="refresh-button", n_clicks=0),
            ],
            style={"display": "flex", "gap": "8px", "marginBottom": "16px"},
        ),
        dcc.Interval(id="live-interval", interval=5000, n_intervals=0),
        html.Div(id="summary-cards", style={"display": "flex", "gap": "12px", "marginBottom": "16px"}),
        dcc.Graph(id="waterfall-graph", style={"height": "500px"}),
        html.Div(
            [
                html.Div(
                    [html.H4("Session Narrative"), html.Div(id="narrative-panel")],
                    style=PANEL_STYLE,
                ),
                html.Div(
                    [html.H4("Span Detail"), html.Div(id="detail-panel", children="Click a bar in the waterfall above for details.")],
                    style=PANEL_STYLE,
                ),
            ],
            style={"display": "flex", "gap": "16px", "marginTop": "16px"},
        ),
        dcc.Store(id="spans-store"),
    ],
    style={"fontFamily": "sans-serif", "padding": "24px", "maxWidth": "1200px", "margin": "0 auto"},
)


@app.callback(
    Output("session-dropdown", "options"),
    Input("refresh-button", "n_clicks"),
    Input("live-interval", "n_intervals"),
)
def refresh_sessions(_n_clicks, _n_intervals):
    sessions = tempo_client.list_sessions()
    return [{"label": s, "value": s} for s in sessions]


@app.callback(
    Output("spans-store", "data"),
    Output("summary-cards", "children"),
    Output("waterfall-graph", "figure"),
    Output("narrative-panel", "children"),
    Input("session-dropdown", "value"),
    Input("live-interval", "n_intervals"),
)
def load_session(session_id, _n_intervals):
    if not session_id:
        return no_update, [], px.scatter(title="Select a session to view its waterfall"), []

    spans = tempo_client.get_session_spans(session_id)
    if not spans:
        return [], [], px.scatter(title="No spans found for this session"), [html.P("No spans found.")]

    summary = build_summary(spans)
    cards = [
        stat_card("LLM calls", str(summary["llm_calls"])),
        stat_card("Tool calls", str(summary["tool_calls"])),
        stat_card("Total cost", f"${summary['total_cost_usd']:.4f}"),
        stat_card("Total tokens", f"{summary['total_tokens']:,.0f}"),
        stat_card("Wall clock", f"{summary['wall_clock_s']:.1f}s"),
    ]

    df = pd.DataFrame(spans)
    df["start_dt"] = pd.to_datetime(df["start_ns"], unit="ns")
    df["end_dt"] = df["start_dt"] + pd.to_timedelta(df["duration_ms"], unit="ms")

    # Spans with very short (or zero) duration collapse to an invisible sliver
    # in a real gantt chart, so give every bar a minimum visible width based on
    # the overall session time range. The tooltip still shows the real duration.
    total_range_ms = (df["end_dt"].max() - df["start_dt"].min()).total_seconds() * 1000
    min_visible_ms = max(total_range_ms * 0.01, 100)
    df["display_end_dt"] = df["start_dt"] + pd.to_timedelta(
        df["duration_ms"].clip(lower=min_visible_ms), unit="ms"
    )

    df["step"] = range(1, len(df) + 1)
    df["call_type"] = df.apply(
        lambda r: "LLM" if r["span_name"] == "opencode.llm" else "Tool", axis=1
    )
    df["label_name"] = df.apply(
        lambda r: r["model"] if r["call_type"] == "LLM" else (r["tool_name"] or r["span_name"]),
        axis=1,
    )
    df["label"] = df.apply(lambda r: f"{r['step']:>2}. {r['call_type']}: {r['label_name']}", axis=1)
    df["hover"] = df.apply(
        lambda r: (
            f"{r['label']}<br>Duration: {r['duration_ms']:.0f} ms"
            + (f"<br>Cost: ${r['cost_usd']:.4f}<br>Tokens: {r['tokens_total']:,.0f}" if r["call_type"] == "LLM" else "")
        ),
        axis=1,
    )

    fig = px.timeline(
        df,
        x_start="start_dt",
        x_end="display_end_dt",
        y="label",
        color="call_type",
        custom_data=["trace_id"],
        hover_name="hover",
        color_discrete_map={"LLM": "#636EFA", "Tool": "#EF553B"},
    )
    # Order bars top-to-bottom by call sequence (step 1 at top)
    fig.update_yaxes(categoryorder="array", categoryarray=df["label"].tolist()[::-1])
    fig.update_layout(
        title=f"Session {session_id} timeline",
        xaxis_title="Time",
        yaxis_title=None,
        showlegend=True,
    )

    narrative = [html.P(dcc.Markdown(line)) for line in build_narrative(spans)]

    return spans, cards, fig, narrative


@app.callback(
    Output("detail-panel", "children"),
    Input("waterfall-graph", "clickData"),
)
def show_detail(click_data):
    if not click_data:
        return "Click a bar in the waterfall above for details."

    point = click_data["points"][0]
    trace_id = point["customdata"][0]
    attrs = tempo_client.get_trace_detail(trace_id)

    if not attrs:
        return "Could not load trace details."

    rows = []
    span_name = attrs.get("openinference.span.kind")

    if span_name == "LLM":
        rows.append(html.P([html.B("Model: "), str(attrs.get("llm.model_name"))]))
        rows.append(html.P([html.B("Agent: "), str(attrs.get("agent.name"))]))
        rows.append(
            html.P(
                [
                    html.B("Tokens: "),
                    f"prompt={attrs.get('llm.token_count.prompt', 0):,} / "
                    f"completion={attrs.get('llm.token_count.completion', 0):,} / "
                    f"total={attrs.get('llm.token_count.total', 0):,}",
                ]
            )
        )
        rows.append(html.P([html.B("Cost: "), f"${attrs.get('cost_usd', 0):.4f}"]))
        rows.append(html.P([html.B("Finish reason: "), str(attrs.get("llm.finish_reason"))]))
        rows.append(html.H5("Input"))
        rows.append(html.Pre(str(attrs.get("input.value", ""))[:4000], style={"whiteSpace": "pre-wrap"}))
        rows.append(html.H5("Output"))
        rows.append(html.Pre(str(attrs.get("output.value", ""))[:4000], style={"whiteSpace": "pre-wrap"}))
    else:
        rows.append(html.P([html.B("Tool: "), str(attrs.get("tool.name"))]))
        rows.append(html.P([html.B("Success: "), str(attrs.get("tool.success"))]))
        rows.append(html.P([html.B("Duration: "), f"{attrs.get('duration_ms', 0):,.0f} ms"]))
        rows.append(html.H5("Parameters"))
        rows.append(html.Pre(str(attrs.get("tool.parameters", attrs.get("input.value", ""))), style={"whiteSpace": "pre-wrap"}))
        rows.append(html.H5("Output"))
        rows.append(html.Pre(str(attrs.get("output.value", ""))[:4000], style={"whiteSpace": "pre-wrap"}))

    return rows


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
