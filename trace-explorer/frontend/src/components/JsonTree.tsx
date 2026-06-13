import { useState } from "react";
import { Highlight } from "./Highlight";

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

interface JsonTreeProps {
  value: JsonValue;
  query?: string;
  depth?: number;
  collapsedByDefault?: boolean;
}

const INDENT = 14;

export function JsonTree({ value, query = "", depth = 0, collapsedByDefault = false }: JsonTreeProps) {
  if (Array.isArray(value)) {
    return (
      <JsonContainer
        open="["
        close="]"
        depth={depth}
        empty={value.length === 0}
        count={value.length}
        collapsedByDefault={collapsedByDefault}
      >
        {value.map((item, idx) => (
          <div key={idx} style={{ marginLeft: INDENT }}>
            <JsonTree value={item} query={query} depth={depth + 1} />
            {idx < value.length - 1 && <span className="text-text-muted">,</span>}
          </div>
        ))}
      </JsonContainer>
    );
  }

  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    return (
      <JsonContainer
        open="{"
        close="}"
        depth={depth}
        empty={entries.length === 0}
        count={entries.length}
        collapsedByDefault={collapsedByDefault}
      >
        {entries.map(([key, val], idx) => (
          <div key={key} style={{ marginLeft: INDENT }}>
            <span className="text-accent">"{key}"</span>
            <span className="text-text-muted">: </span>
            <JsonTree value={val} query={query} depth={depth + 1} />
            {idx < entries.length - 1 && <span className="text-text-muted">,</span>}
          </div>
        ))}
      </JsonContainer>
    );
  }

  return <JsonScalar value={value} query={query} />;
}

function JsonScalar({ value, query }: { value: string | number | boolean | null; query: string }) {
  if (value === null) return <span className="text-text-muted">null</span>;
  if (typeof value === "boolean") {
    return <span className={value ? "text-success" : "text-error"}>{String(value)}</span>;
  }
  if (typeof value === "number") return <span className="text-llm">{value}</span>;
  return (
    <span className="text-tool">
      "<Highlight text={value} query={query} />"
    </span>
  );
}

function JsonContainer({
  open,
  close,
  depth,
  empty,
  count,
  collapsedByDefault,
  children,
}: {
  open: string;
  close: string;
  depth: number;
  empty: boolean;
  count: number;
  collapsedByDefault: boolean;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(collapsedByDefault && depth > 0);

  if (empty) {
    return (
      <span className="text-text-muted">
        {open}
        {close}
      </span>
    );
  }

  if (collapsed) {
    return (
      <span
        className="cursor-pointer text-text-muted hover:text-text"
        onClick={() => setCollapsed(false)}
        title="Expand"
      >
        {open}
        <span className="text-xs"> {count} {count === 1 ? "item" : "items"} </span>
        {close}
      </span>
    );
  }

  return (
    <span>
      <span className="cursor-pointer text-text-muted hover:text-text" onClick={() => setCollapsed(true)} title="Collapse">
        {open}
      </span>
      {children}
      <div style={{ marginLeft: 0 }}>
        <span className="text-text-muted">{close}</span>
      </div>
    </span>
  );
}
