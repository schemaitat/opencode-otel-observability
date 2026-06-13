import { JsonTree } from "./JsonTree";
import { Highlight } from "./Highlight";

interface SmartValueProps {
  value: string;
  query?: string;
}

/** Renders a string value as a collapsible JSON tree if it parses as JSON,
 * otherwise as preformatted, search-highlighted text. */
export function SmartValue({ value, query = "" }: SmartValueProps) {
  const trimmed = value.trim();
  if ((trimmed.startsWith("{") || trimmed.startsWith("[")) && trimmed.length > 1) {
    try {
      const parsed = JSON.parse(trimmed);
      return (
        <div className="overflow-x-auto rounded bg-black/30 p-2 font-mono text-xs leading-relaxed whitespace-pre">
          <JsonTree value={parsed} query={query} collapsedByDefault />
        </div>
      );
    } catch {
      // fall through to plain text
    }
  }

  return (
    <pre className="rounded bg-black/30 p-2 text-xs leading-relaxed whitespace-pre-wrap break-words">
      <Highlight text={value} query={query} />
    </pre>
  );
}
