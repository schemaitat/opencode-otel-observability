interface HighlightProps {
  text: string;
  query: string;
}

/** Renders `text`, wrapping case-insensitive matches of `query` in <mark>. */
export function Highlight({ text, query }: HighlightProps) {
  if (!query.trim()) return <>{text}</>;

  const lower = text.toLowerCase();
  const needle = query.trim().toLowerCase();
  const parts: { chunk: string; match: boolean }[] = [];

  let i = 0;
  while (i < text.length) {
    const idx = lower.indexOf(needle, i);
    if (idx === -1) {
      parts.push({ chunk: text.slice(i), match: false });
      break;
    }
    if (idx > i) parts.push({ chunk: text.slice(i, idx), match: false });
    parts.push({ chunk: text.slice(idx, idx + needle.length), match: true });
    i = idx + needle.length;
  }

  return (
    <>
      {parts.map((p, idx) =>
        p.match ? <mark key={idx}>{p.chunk}</mark> : <span key={idx}>{p.chunk}</span>,
      )}
    </>
  );
}
