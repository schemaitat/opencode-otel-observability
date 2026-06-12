def build_narrative(spans: list[dict]) -> list[str]:
    """Turn a list of spans (sorted by start time) into a step-by-step
    human-readable narrative of what happened during the session."""
    lines = []
    for i, span in enumerate(spans, start=1):
        duration_s = span["duration_ms"] / 1000

        if span["span_name"] == "opencode.llm":
            model = span["model"] or "unknown model"
            tokens = span["tokens_total"]
            cost = span["cost_usd"]
            finish = span["finish_reason"] or "n/a"
            lines.append(
                f"**Step {i}: LLM call** to `{model}` "
                f"({duration_s:.1f}s, {tokens:,.0f} tokens, "
                f"${cost:.4f}, finish: {finish})"
            )
        else:
            tool = span["tool_name"] or span["span_name"].removeprefix("opencode.tool.")
            success = span["tool_success"]
            status = "succeeded" if success in (True, "true", "True") else "failed" if success is not None else "unknown"
            lines.append(
                f"**Step {i}: Tool call** `{tool}` "
                f"({duration_s:.2f}s, {status})"
            )

    return lines


def build_summary(spans: list[dict]) -> dict:
    llm_spans = [s for s in spans if s["span_name"] == "opencode.llm"]
    tool_spans = [s for s in spans if s["span_name"] != "opencode.llm"]

    total_cost = sum(s["cost_usd"] for s in llm_spans)
    total_tokens = sum(s["tokens_total"] for s in llm_spans)

    if spans:
        start = min(s["start_ns"] for s in spans)
        end = max(s["start_ns"] + s["duration_ms"] * 1e6 for s in spans)
        wall_clock_s = (end - start) / 1e9
    else:
        wall_clock_s = 0

    return {
        "llm_calls": len(llm_spans),
        "tool_calls": len(tool_spans),
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "wall_clock_s": wall_clock_s,
    }
