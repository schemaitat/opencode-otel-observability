import os

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, dcc, html, no_update

import tempo_client
from narrative import build_narrative, build_summary

app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
app.title = "Session Explorer"

PLOTLY_TEMPLATE = "plotly_dark"
PANEL_STYLE = {"maxHeight": "500px", "overflowY": "auto"}
CALL_TYPE_COLORS = {"LLM": "#636EFA", "Tool": "#EF553B"}


def _empty_figure(message: str):
    fig = px.scatter()
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 16, "color": "#888"},
            }
        ],
    )
    return fig


def truncated_pre(text: str, limit: int = 4000) -> html.Pre:
    text = str(text)
    if len(text) > limit:
        text = text[:limit] + f"\n... (truncated, {len(text):,} chars total)"
    return html.Pre(text, className="bg-black bg-opacity-25 p-2 rounded", style={"whiteSpace": "pre-wrap"})


def fact(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Div(label, className="text-muted text-uppercase small"),
            html.Div(value, className="fw-semibold"),
        ],
        className="me-4 mb-2",
    )


def stat_card(label: str, value: str) -> dbc.Col:
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(value, className="fs-3 fw-bold"),
                    html.Div(label, className="text-muted small text-uppercase"),
                ],
                className="text-center",
            )
        ),
        xs=6,
        sm=4,
        md=True,
    )


app.layout = dbc.Container(
    [
        dbc.NavbarSimple(brand="Session Explorer", color="primary", dark=True, className="mb-3"),
        dbc.Row(
            [
                dbc.Col(
                    dcc.Dropdown(
                        id="session-dropdown",
                        options=[],
                        placeholder="Select a session...",
                    ),
                    md=7,
                ),
                dbc.Col(dbc.Button("Refresh sessions", id="refresh-button", color="secondary", className="w-100"), md=2),
                dbc.Col(
                    dbc.Checklist(
                        id="call-type-filter",
                        options=[{"label": "LLM", "value": "LLM"}, {"label": "Tool", "value": "Tool"}],
                        value=["LLM", "Tool"],
                        inline=True,
                        switch=True,
                    ),
                    md=3,
                    className="d-flex align-items-center justify-content-end",
                ),
            ],
            className="mb-3 g-2 align-items-center",
        ),
        dcc.Interval(id="live-interval", interval=5000, n_intervals=0),
        dbc.Row(id="summary-cards", className="g-2 mb-3"),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            dcc.Loading(
                                html.Div(
                                    dcc.Graph(id="waterfall-graph"),
                                    style={"maxHeight": "75vh", "overflowY": "auto"},
                                )
                            )
                        ),
                    ),
                    md=7,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Span Detail"),
                            dbc.CardBody(
                                html.Div(
                                    id="detail-panel",
                                    children=html.Div(
                                        "Click a span in the waterfall to inspect it here.",
                                        className="text-muted",
                                    ),
                                    style={"maxHeight": "70vh", "overflowY": "auto"},
                                )
                            ),
                        ],
                        style={"position": "sticky", "top": "1rem"},
                    ),
                    md=5,
                ),
            ],
            className="g-2 mb-3",
        ),
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Session Narrative"),
                        dbc.CardBody(
                            [
                                dbc.Input(
                                    id="narrative-search",
                                    placeholder="Filter steps (e.g. tool name, model)...",
                                    type="text",
                                    className="mb-2",
                                ),
                                html.Div(id="narrative-panel", style=PANEL_STYLE),
                            ]
                        ),
                    ]
                ),
                md=12,
            ),
            className="g-2",
        ),
        dcc.Store(id="spans-store"),
        dcc.Store(id="narrative-store"),
    ],
    fluid=True,
    className="py-3",
)


@app.callback(
    Output("session-dropdown", "options"),
    Input("refresh-button", "n_clicks"),
    Input("live-interval", "n_intervals"),
)
def refresh_sessions(_n_clicks, _n_intervals):
    sessions = tempo_client.list_sessions()
    return [
        {
            "label": f"{pd.to_datetime(s['start_ns'], unit='ns'):%Y-%m-%d %H:%M:%S}  {s['session_id']}",
            "value": s["session_id"],
        }
        for s in sessions
    ]


@app.callback(
    Output("spans-store", "data"),
    Output("summary-cards", "children"),
    Output("narrative-store", "data"),
    Input("session-dropdown", "value"),
    Input("live-interval", "n_intervals"),
)
def load_session(session_id, _n_intervals):
    if not session_id:
        return no_update, [], []

    spans = tempo_client.get_session_spans(session_id)
    if not spans:
        return {"session_id": session_id, "spans": []}, [], ["No spans found."]

    summary = build_summary(spans)
    cards = [
        stat_card("LLM calls", str(summary["llm_calls"])),
        stat_card("Tool calls", str(summary["tool_calls"])),
        stat_card("Total cost", f"${summary['total_cost_usd']:.4f}"),
        stat_card("Total tokens", f"{summary['total_tokens']:,.0f}"),
        stat_card("Wall clock", f"{summary['wall_clock_s']:.1f}s"),
    ]

    narrative = build_narrative(spans)

    return {"session_id": session_id, "spans": spans}, cards, narrative


@app.callback(
    Output("waterfall-graph", "figure"),
    Input("spans-store", "data"),
    Input("call-type-filter", "value"),
)
def update_waterfall(store_data, call_types):
    if not store_data or not store_data.get("spans"):
        return _empty_figure("Select a session to view its waterfall")

    session_id = store_data["session_id"]
    call_types = call_types or []

    df = pd.DataFrame(store_data["spans"])
    df["start_dt"] = pd.to_datetime(df["start_ns"], unit="ns")
    df["end_dt"] = df["start_dt"] + pd.to_timedelta(df["duration_ms"], unit="ms")
    df["step"] = range(1, len(df) + 1)
    df["call_type"] = df.apply(
        lambda r: "LLM" if r["span_name"] == "opencode.llm" else "Tool", axis=1
    )

    df = df[df["call_type"].isin(call_types)]
    if df.empty:
        return _empty_figure("No spans match the selected filters")

    # Spans with very short (or zero) duration collapse to an invisible sliver
    # in a real gantt chart, so give every bar a minimum visible width based on
    # the overall session time range. The tooltip still shows the real duration.
    total_range_ms = (df["end_dt"].max() - df["start_dt"].min()).total_seconds() * 1000
    min_visible_ms = max(total_range_ms * 0.01, 100)
    df["display_end_dt"] = df["start_dt"] + pd.to_timedelta(
        df["duration_ms"].clip(lower=min_visible_ms), unit="ms"
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
        color_discrete_map=CALL_TYPE_COLORS,
    )
    # Order bars top-to-bottom by call sequence (step 1 at top)
    fig.update_yaxes(categoryorder="array", categoryarray=df["label"].tolist()[::-1])
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        title=f"Session {session_id} timeline",
        xaxis_title="Time",
        yaxis_title=None,
        showlegend=True,
        uirevision=session_id,
        height=max(500, 28 * len(df)),
        margin={"l": 0, "r": 16, "t": 48, "b": 32},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    return fig


@app.callback(
    Output("narrative-panel", "children"),
    Input("narrative-store", "data"),
    Input("narrative-search", "value"),
)
def update_narrative(lines, search):
    if not lines:
        return [html.P("Select a session to view its narrative.")]

    if search:
        needle = search.lower()
        lines = [line for line in lines if needle in line.lower()]
        if not lines:
            return [html.P("No steps match your filter.", className="text-muted")]

    return [html.P(dcc.Markdown(line)) for line in lines]


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

    span_kind = attrs.get("openinference.span.kind")

    if span_kind == "LLM":
        title = str(attrs.get("llm.model_name"))
        badge_color = CALL_TYPE_COLORS["LLM"]
        facts = [
            fact("Agent", str(attrs.get("agent.name"))),
            fact(
                "Tokens",
                f"{attrs.get('llm.token_count.prompt', 0):,.0f} in / "
                f"{attrs.get('llm.token_count.completion', 0):,.0f} out / "
                f"{attrs.get('llm.token_count.total', 0):,.0f} total",
            ),
            fact("Cost", f"${attrs.get('cost_usd', 0):.4f}"),
            fact("Finish reason", str(attrs.get("llm.finish_reason"))),
        ]
        sections = [
            ("Input", attrs.get("input.value", "")),
            ("Output", attrs.get("output.value", "")),
        ]
    else:
        title = str(attrs.get("tool.name"))
        badge_color = CALL_TYPE_COLORS["Tool"]
        facts = [
            fact("Success", str(attrs.get("tool.success"))),
            fact("Duration", f"{attrs.get('duration_ms', 0):,.0f} ms"),
        ]
        sections = [
            ("Parameters", attrs.get("tool.parameters", attrs.get("input.value", ""))),
            ("Output", attrs.get("output.value", "")),
        ]

    header = html.Div(
        [
            html.Span(
                span_kind,
                className="badge me-2",
                style={"backgroundColor": badge_color, "color": "#fff"},
            ),
            html.Span(title, className="fs-5 fw-bold"),
        ],
        className="mb-2",
    )

    fact_row = html.Div(facts, className="d-flex flex-wrap mb-3")

    body = []
    for label, value in sections:
        body.append(html.H6(label, className="text-uppercase text-muted mt-2"))
        body.append(truncated_pre(value))

    return [header, fact_row, html.Hr(), *body]


if __name__ == "__main__":
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=8050, debug=debug)
