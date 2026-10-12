"""Turn platform rich-text formats into plain text for indexing.

- Confluence "storage" format: XHTML with ac:/ri: macro tags
- Jira descriptions/comments: Atlassian Document Format (ADF), a JSON tree

Both keep block structure as newlines (steps in a runbook stay separate lines)
and collect link targets so the connector can resolve them to uids.
"""
from html.parser import HTMLParser

_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "div", "br", "pre", "blockquote"}
_SKIP = {"script", "style", "ac:parameter"}  # macro parameters are config, not prose


class _Storage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.links, self._skip = [], [], [], 0
        self._in_link = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
            self._in_link += 1
        if tag == "ri:url":
            v = dict(attrs).get("ri:value")
            if v:
                self.links.append(v)
        if tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        if tag == "a":
            self._in_link = max(0, self._in_link - 1)
        if tag in _BLOCK:
            self._flush()

    def handle_data(self, data):
        # link-only lines (e.g. "PAY-101") are navigation, not content
        if not self._skip and not self._in_link:
            self.cur.append(data)

    def unknown_decl(self, data):
        # code / noformat macros keep their content in <![CDATA[...]]>
        if data.startswith("CDATA[") and not self._skip:
            self._flush()
            self.cur.append(data[len("CDATA["):])
            self._flush()

    def _flush(self):
        text = " ".join("".join(self.cur).split())
        if text:
            self.lines.append(text)
        self.cur = []


def storage_to_text(html: str) -> tuple[str, list[str]]:
    p = _Storage()
    p.feed(html or "")
    p.close()
    p._flush()
    return "\n".join(p.lines), p.links


def adf_to_text(node) -> tuple[str, list[str]]:
    """ADF -> (text, link hrefs). Paragraph-level nodes become lines."""
    lines, links = [], []

    def inline(n) -> str:
        out = ""
        for c in n.get("content", []) or []:
            if c.get("type") == "text":
                out += c.get("text", "")
                for m in c.get("marks", []) or []:
                    if m.get("type") == "link" and m.get("attrs", {}).get("href"):
                        links.append(m["attrs"]["href"])
            elif c.get("type") == "hardBreak":
                out += "\n"
            elif c.get("type") == "inlineCard" and c.get("attrs", {}).get("url"):
                links.append(c["attrs"]["url"])
            elif c.get("type") == "mention":
                out += c.get("attrs", {}).get("text", "")
            else:
                out += inline(c)
        return out

    def walk(n):
        t = n.get("type")
        if t in ("paragraph", "heading", "codeBlock"):
            s = inline(n).strip()
            if s:
                lines.append(s)
        elif t == "blockCard" and n.get("attrs", {}).get("url"):
            links.append(n["attrs"]["url"])
        else:
            for c in n.get("content", []) or []:
                walk(c)

    if isinstance(node, dict):
        walk(node)
    elif isinstance(node, str):  # API v2 / legacy plain-text descriptions
        lines = [node]
    return "\n".join(lines), links
