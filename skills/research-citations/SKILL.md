---
name: research-citations
description: "Write real, readable source citations after web research as proper [text](url) Markdown links — never synthetic citation markers or bare/angle-bracket URLs Hermes's Slack renderer won't linkify — and don't state precise/technical claims sourced only from an unread search snippet."
version: 1.1.0
author: Fred
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, web-search, citations, accuracy, hallucination-prevention]
    related_skills: []
---

# Research Citations: Readable Sources, Grounded Claims

Applies whenever a response cites web sources after using `web_search` /
`web_extract` / the browser toolset — regardless of which search or extract
backend is connected. Not specific to any one MCP server or provider, so
it isn't covered by (and doesn't duplicate) `mcp-tool-discovery`.

## Rule 1: Never Emit Synthetic Citation Markers

Do not write citation markers like `【0†L1-L4】`, `【source†L13-L16】`, or any
similar bracket-and-line-range notation in a response. This is a citation
convention from other tools' training data — **Hermes has no renderer for
it**. It never becomes a clickable footnote; it is posted as literal text,
and on platforms with narrow-font UI surfaces (e.g. a Slack native table
cell) the CJK-style brackets `【` `】` and dagger `†` can render as garbled
placeholder glyphs, making the output look corrupted.

Write citations as plain, readable text instead:
- Inline: `(source : economie.gouv.fr)` or a proper Markdown link — see
  Rule 1b below for the exact syntax that matters on Slack.
- Or a "Sources" section/column with the real URL, exactly like a normal
  reference list — this already renders correctly everywhere, including
  inside a Slack table cell.

If you're tempted to reference "line N-M of document 0" — you don't
actually have addressable line numbers for a web result; that specificity
is itself a sign the citation is fabricated, not read. See Rule 2.

## Rule 1b: Cite With `[label](https://...)` — Not Bare or `<...>` URLs

On Slack (`platforms.slack.extra.rich_blocks: true`), the renderer only
turns a **standard Markdown link** — `[label](https://example.com)` — into
a clickable link element. It does **not** autolink a bare URL
(`https://example.com` on its own) and does **not** interpret Slack's own
`<https://example.com>` angle-bracket auto-link syntax (which the plain
mrkdwn path used to linkify before `rich_blocks` was enabled — a real
regression users will notice: "the link text is correct but not
clickable"). Either of those renders as inert plain text, brackets and
all.

Always write every citation, every source list entry, and every inline
reference as `[descriptive label](https://the-real-url)` — never a bare
URL, never `<https://...>`. This applies everywhere in a response, not
just inside tables (the same inline-parsing code path handles regular
paragraphs and lists too).

## Rule 2: Don't Over-Claim From an Unread Snippet

`web_search` results are short titles + 1-2 sentence descriptions, not full
page content. If a claim needs a precise number, date, threshold, or legal
detail, and you only have a search-result snippet for it — that detail is
not grounded yet.

- If `web_extract` is available, use it to read the actual page before
  stating the specific claim.
- If `web_extract` fails or isn't configured for the current backend (e.g.
  a search-only provider like SearXNG returns
  `"cannot extract URL content"`), **fall back to the `browser` toolset**
  (headless browser, no API key needed, always available) to actually load
  and read the page — don't just proceed to answer from the snippet alone
  and cite it as if you'd read the source.
- If neither is practical, say so plainly ("d'après le résumé de la
  recherche, à confirmer sur la page source") rather than presenting a
  snippet-derived guess with the same confidence as a verified fact.

This matters most for anything a reader might act on without
double-checking: dates, thresholds (CA/effectifs), penalty amounts, legal
references.
