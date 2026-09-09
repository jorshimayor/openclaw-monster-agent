"use client";

import React from "react";
import { cn } from "@/lib/utils";

/**
 * Small dependency-free markdown renderer.
 *
 * Reports arrived on this page as raw markdown inside a <pre>, so you read
 * "## 4. Team Assembly" and "**Scope**:" as literal characters. This renders
 * them properly.
 *
 * Everything becomes React elements — never dangerouslySetInnerHTML — so report
 * text (which is model-generated and can contain anything) can't inject markup.
 */

type Inline = React.ReactNode;

/**
 * Inline spans: bold, italic, strikethrough, code, links, and the bare <br>
 * that models emit inside table cells.
 *
 * Order in the alternation matters — `**bold**` has to be tried before
 * `*italic*`, or the italic branch eats the first two asterisks and the page
 * fills with stray `*` characters. That is exactly what shipped: single-asterisk
 * emphasis rendered as literal punctuation everywhere.
 */
const INLINE_PATTERN = new RegExp(
  [
    "\\*\\*[^*]+\\*\\*", // bold
    "__[^_]+__", // bold (underscore)
    "~~[^~]+~~", // strikethrough
    "\\*(?!\\s)[^*\\n]+(?<!\\s)\\*", // italic — not a bullet or a stray asterisk
    "(?<![A-Za-z0-9_])_(?!\\s)[^_\\n]+(?<!\\s)_(?![A-Za-z0-9_])", // italic (underscore)
    "`[^`]+`", // code
    "<br\\s*/?>", // literal line break
    "\\[[^\\]]+\\]\\((?:https?://|/)[^)\\s]+\\)", // [label](href)
    "https?://[^\\s<>()]+" // bare url
  ].join("|"),
  "gi"
);

function link(key: string, href: string, label: string) {
  return (
    <a
      key={key}
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-matrix underline underline-offset-2 hover:text-matrix/80 break-all"
    >
      {label}
    </a>
  );
}

function renderInline(text: string, keyPrefix: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  INLINE_PATTERN.lastIndex = 0;

  while ((match = INLINE_PATTERN.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-i${i++}`;

    if (/^<br/i.test(token)) {
      out.push(<br key={key} />);
    } else if (token.startsWith("**") || token.startsWith("__")) {
      out.push(
        <strong key={key} className="text-matrix font-bold">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("~~")) {
      out.push(
        <s key={key} className="opacity-60">
          {token.slice(2, -2)}
        </s>
      );
    } else if (token.startsWith("`")) {
      out.push(
        <code
          key={key}
          className="px-1 py-0.5 rounded bg-matrix/10 border border-matrix/20 text-[0.95em]"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith("*") || token.startsWith("_")) {
      out.push(
        <em key={key} className="italic text-matrix/95">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith("[")) {
      const split = token.indexOf("](");
      out.push(link(key, token.slice(split + 2, -1), token.slice(1, split)));
    } else {
      out.push(link(key, token, token));
    }
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const HEADING_CLASS = [
  "text-lg font-bold tracking-wider glow-text mt-6 mb-2",
  "text-base font-bold tracking-wider text-matrix mt-5 mb-2",
  "text-sm font-bold tracking-widest text-matrix mt-4 mb-1.5",
  "text-xs font-bold tracking-widest text-matrix-dim mt-3 mb-1",
];

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

const isTableDivider = (line: string) => /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-");

export function Markdown({ source, className }: { source: string; className?: string }) {
  const lines = String(source ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];

  let i = 0;
  let key = 0;
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const text = paragraph.join(" ");
    blocks.push(
      <p key={`p${key++}`} className="text-matrix/90 leading-relaxed my-2">
        {renderInline(text, `p${key}`)}
      </p>
    );
    paragraph = [];
  };

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code
    if (/^\s*```/.test(line)) {
      flushParagraph();
      const lang = line.replace(/^\s*```/, "").trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++]);
      i++; // closing fence
      blocks.push(
        <div key={`c${key++}`} className="my-3">
          {lang && (
            <div className="text-[10px] tracking-widest text-matrix-dim mb-1">
              {lang.toUpperCase()}
            </div>
          )}
          <pre className="overflow-x-auto bg-bg/70 border border-matrix/20 rounded p-3 text-[11px] leading-relaxed text-matrix/85">
            <code>{body.join("\n")}</code>
          </pre>
        </div>
      );
      continue;
    }

    // Table
    if (line.trim().startsWith("|") && i + 1 < lines.length && isTableDivider(lines[i + 1])) {
      flushParagraph();
      const head = splitTableRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitTableRow(lines[i++]));
      }
      blocks.push(
        <div key={`t${key++}`} className="my-3 overflow-x-auto">
          <table className="w-full text-xs border border-matrix/20 rounded">
            <thead>
              <tr className="border-b border-matrix/20 bg-matrix/5">
                {head.map((h, hi) => (
                  <th
                    key={hi}
                    className="text-left px-3 py-2 font-normal tracking-widest text-matrix-dim whitespace-nowrap"
                  >
                    {renderInline(h, `th${hi}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-b border-bg-border/50 last:border-0">
                  {r.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 align-top text-matrix/85">
                      {renderInline(cell, `td${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Headings
    const heading = /^(\s*)(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[2].length, 4);
      const Tag = (`h${Math.min(level + 1, 6)}` as unknown) as keyof JSX.IntrinsicElements;
      blocks.push(
        React.createElement(
          Tag,
          { key: `h${key++}`, className: HEADING_CLASS[level - 1] },
          renderInline(heading[3], `h${key}`)
        )
      );
      i++;
      continue;
    }

    // Horizontal rule
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      flushParagraph();
      blocks.push(<hr key={`hr${key++}`} className="my-4 border-matrix/20" />);
      i++;
      continue;
    }

    // Blockquote
    if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      const body: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        body.push(lines[i++].replace(/^\s*>\s?/, ""));
      }
      blocks.push(
        <blockquote
          key={`q${key++}`}
          className="my-3 border-l-2 border-matrix/40 pl-3 text-matrix-dim italic"
        >
          {renderInline(body.join(" "), `q${key}`)}
        </blockquote>
      );
      continue;
    }

    // Lists (ordered + unordered, one level of nesting)
    const listItem = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (listItem) {
      flushParagraph();
      const ordered = /\d/.test(listItem[2]);
      const items: { depth: number; text: string }[] = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (!m) {
          // A wrapped continuation line belongs to the item above it.
          if (items.length && lines[i].trim() && /^\s{2,}\S/.test(lines[i])) {
            items[items.length - 1].text += " " + lines[i].trim();
            i++;
            continue;
          }
          break;
        }
        items.push({ depth: Math.floor(m[1].length / 2), text: m[3] });
        i++;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        React.createElement(
          ListTag,
          {
            key: `l${key++}`,
            className: cn(
              "my-2 space-y-1 text-matrix/90",
              ordered ? "list-decimal" : "list-disc",
              "pl-5 marker:text-matrix-dim"
            ),
          },
          items.map((it, ii) => (
            <li key={ii} style={{ marginLeft: `${it.depth * 1}rem` }} className="leading-relaxed">
              {renderInline(it.text, `li${ii}`)}
            </li>
          ))
        )
      );
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      i++;
      continue;
    }

    paragraph.push(line.trim());
    i++;
  }
  flushParagraph();

  return <div className={cn("text-sm", className)}>{blocks}</div>;
}

export default Markdown;
