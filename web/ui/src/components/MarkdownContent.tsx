import type { ReactNode } from "react";

type MarkdownBlock =
  | { type: "code"; language: string; content: string }
  | { type: "text"; content: string };

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      {splitMarkdownBlocks(content).map((block, index) =>
        block.type === "code" ? (
          <pre key={index}>
            <code>{block.content}</code>
          </pre>
        ) : (
          <TextBlock content={block.content} key={index} />
        ),
      )}
    </div>
  );
}

function TextBlock({ content }: { content: string }) {
  const lines = content.split("\n");
  const nodes: ReactNode[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) {
      continue;
    }

    if (isHorizontalRule(line)) {
      nodes.push(<hr key={index} />);
      continue;
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const children = renderInlineMarkdown(heading[2]);
      nodes.push(level === 1 ? <h3 key={index}>{children}</h3> : <h4 key={index}>{children}</h4>);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      index -= 1;
      nodes.push(
        <ul key={index}>
          {items.map((item, itemIndex) => (
            <li key={`${index}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      index -= 1;
      nodes.push(
        <ol key={index}>
          {items.map((item, itemIndex) => (
            <li key={`${index}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    if (isTableHeader(lines, index)) {
      const headers = parseTableRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && isTableRow(lines[index])) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      index -= 1;
      nodes.push(
        <div className="markdown-table-wrap" key={index}>
          <table>
            <thead>
              <tr>
                {headers.map((header, headerIndex) => (
                  <th key={`${index}-h-${headerIndex}`}>{renderInlineMarkdown(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`${index}-r-${rowIndex}`}>
                  {headers.map((_, cellIndex) => (
                    <td key={`${index}-r-${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(row[cellIndex] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^>\s?/.test(line)) {
      nodes.push(<blockquote key={index}>{renderInlineMarkdown(line.replace(/^>\s?/, ""))}</blockquote>);
      continue;
    }

    const paragraphLines = [line];
    while (
      index + 1 < lines.length &&
      lines[index + 1].trim() &&
      !isHorizontalRule(lines[index + 1]) &&
      !/^(#{1,6})\s+/.test(lines[index + 1]) &&
      !/^\s*[-*]\s+/.test(lines[index + 1]) &&
      !/^\s*\d+\.\s+/.test(lines[index + 1]) &&
      !/^>\s?/.test(lines[index + 1])
    ) {
      paragraphLines.push(lines[index + 1]);
      index += 1;
    }
    nodes.push(<p key={index}>{renderInlineMarkdown(paragraphLines.join("\n"))}</p>);
  }
  return <>{nodes}</>;
}

function isHorizontalRule(line: string): boolean {
  return /^\s*-{3,}\s*$/.test(line);
}

function isTableHeader(lines: string[], index: number): boolean {
  return isTableRow(lines[index]) && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1]);
}

function isTableRow(line: string): boolean {
  return line.includes("|") && line.split("|").filter((cell) => cell.trim()).length >= 2;
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function splitMarkdownBlocks(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const pattern = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(content)) !== null) {
    if (match.index > lastIndex) {
      blocks.push({ type: "text", content: content.slice(lastIndex, match.index) });
    }
    blocks.push({ type: "code", language: match[1] ?? "", content: match[2].trimEnd() });
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < content.length) {
    blocks.push({ type: "text", content: content.slice(lastIndex) });
  }
  return blocks.length > 0 ? blocks : [{ type: "text", content }];
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern =
    /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|(?:^|(?<![\d.]))[+\-−]\d+(?:\.\d+)?%|(?:^|(?<![\d.]))[+\-−]?\d+(?:\.\d+)?%?)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={match.index}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={match.index}>{token.slice(1, -1)}</code>);
    } else if (isSignedPercent(token.trim())) {
      const leadingText = token.match(/^\s*/)?.[0] ?? "";
      const percentText = token.trim();
      if (leadingText) {
        nodes.push(leadingText);
      }
      nodes.push(
        <span className={percentText.startsWith("+") ? "markdown-percent-up" : "markdown-percent-down"} key={match.index}>
          {percentText}
        </span>,
      );
    } else if (isNumberToken(token.trim())) {
      const leadingText = token.match(/^\s*/)?.[0] ?? "";
      const numberText = token.trim();
      if (leadingText) {
        nodes.push(leadingText);
      }
      nodes.push(
        <span className="markdown-number" key={match.index}>
          {numberText}
        </span>,
      );
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(token);
      if (link) {
        nodes.push(
          <a href={link[2]} key={match.index} rel="noreferrer" target="_blank">
            {link[1]}
          </a>,
        );
      }
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function isSignedPercent(token: string): boolean {
  return /^[+\-−]\d+(?:\.\d+)?%$/.test(token);
}

function isNumberToken(token: string): boolean {
  return /^[+\-−]?\d+(?:\.\d+)?%?$/.test(token);
}
