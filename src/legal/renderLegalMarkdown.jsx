// Tiny renderer for the legal pages' markdown (headings, paragraphs, lists, tables, bold).
function inline(text, key) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("**")) return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`")) return <code key={`${key}-${i}`}>{part.slice(1, -1)}</code>;
    return part;
  });
}

const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function fillTemplate(text, values) {
  return Object.entries(values).reduce((out, [k, v]) => out.split(`{${k}}`).join(v), text);
}

export default function renderLegalMarkdown(source) {
  const lines = source.split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `l${i}`;
    if (!line.trim()) { i += 1; continue; }
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      const Tag = `h${heading[1].length}`;
      out.push(<Tag key={key}>{inline(heading[2], key)}</Tag>);
      i += 1;
    } else if (line.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) { rows.push(lines[i]); i += 1; }
      const [head, , ...body] = rows;
      out.push(
        <div className="legal-table-wrap" key={key}><table><thead><tr>{cells(head).map((c, j) => <th key={j}>{inline(c, `${key}h${j}`)}</th>)}</tr></thead>
          <tbody>{body.map((r, ri) => <tr key={ri}>{cells(r).map((c, j) => <td key={j}>{inline(c, `${key}${ri}${j}`)}</td>)}</tr>)}</tbody></table></div>
      );
    } else if (line.startsWith("- ")) {
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) { items.push(lines[i].slice(2)); i += 1; }
      out.push(<ul key={key}>{items.map((t, j) => <li key={j}>{inline(t, `${key}${j}`)}</li>)}</ul>);
    } else {
      out.push(<p key={key}>{inline(line.replace(/^>\s*/, ""), key)}</p>);
      i += 1;
    }
  }
  return out;
}
