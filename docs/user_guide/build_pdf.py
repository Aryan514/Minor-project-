# docs/user_guide/build_pdf.py
# Turns USER_GUIDE.md into a self-contained USER_GUIDE.html (images embedded as base64) and prints it to
# USER_GUIDE.pdf with headless Microsoft Edge (or Chrome). Small Markdown subset: headings, tables, lists, code
# blocks, images, bold/inline code. Fills the @RUN@/@VERDICT@/... placeholders from raw/run_log.txt.
# Documentation tooling only; not part of the testbed.
"""Build USER_GUIDE.md placeholders, USER_GUIDE.html and USER_GUIDE.pdf."""

from __future__ import annotations

import base64
import html
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def fill_placeholders(md_path: Path) -> str:
    """Replace @...@ placeholders in USER_GUIDE.md with values from raw/run_log.txt (written back once)."""
    text = md_path.read_text(encoding="utf-8")
    if "@RUN@" not in text:
        return text
    log = (HERE / "raw" / "run_log.txt").read_text(encoding="utf-8").splitlines()
    run_id = re.search(r"PANEL_\d{8}-\d{6}", (HERE / "raw" / "run_id.txt").read_text(encoding="utf-8")).group(0)
    replies = [l for l in log if " -> " in l]
    verdict = next(l for l in log if l.startswith("verdict:"))
    rows = [l.strip() for l in log if l.startswith("    I")]
    seq = re.search(r'"seq": (\d+)', next(l for l in log if l.startswith("wire match:"))).group(1)
    text = (text.replace("@RUN@", run_id).replace("@VERDICT@", verdict.split()[1])
            .replace("@REPLIES@", "\n".join(replies)).replace("@VERDICTROWS@", verdict + "\n" + "\n".join(rows))
            .replace("@SEQ@", seq))
    md_path.write_text(text, encoding="utf-8")
    return text


def inline(s: str) -> str:
    """Bold, inline code and escapes."""
    s = html.escape(s, quote=False).replace("\\|", "|")
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return re.sub(r"\*([^*]+)\*", r"<i>\1</i>", s)


def to_html(md: str) -> str:
    """Minimal Markdown → HTML for this guide."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = lambda r: [c.strip() for c in re.split(r"(?<!\\)\|", r.strip()[1:-1])]
            h = "<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells(rows[0])) + "</tr></thead><tbody>"
            for r in rows[2:]:
                h += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells(r)) + "</tr>"
            out.append(h + "</tbody></table>")
            continue
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", l)
        if m:
            data = base64.b64encode((HERE / m.group(2)).read_bytes()).decode()
            out.append(f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(m.group(1))}"></figure>')
        elif re.match(r"#{1,4} ", l):
            n = len(l.split()[0])
            out.append(f"<h{n}>{inline(l[n + 1:])}</h{n}>")
        elif l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                item = lines[i][2:]
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and not lines[i].startswith("- "):
                    item += " " + lines[i].strip()
                    i += 1
                items.append(f"<li>{inline(item)}</li>")
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif l.strip() == "---":
            out.append("<hr>")
        elif l.strip():
            para = l
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"(#|\||- |!\[|```|---)", lines[i + 1]):
                i += 1
                para += " " + lines[i]
            out.append(f"<p>{inline(para)}</p>")
        i += 1
    css = """body{font-family:Segoe UI,Arial,sans-serif;font-size:11pt;line-height:1.4;max-width:1100px;margin:auto;color:#111}
h1{font-size:20pt;border-bottom:3px solid #c22}h2{font-size:16pt;margin-top:28px;border-bottom:1px solid #ccc;page-break-before:always}
h3{font-size:13pt;margin-top:20px}table{border-collapse:collapse;width:100%;margin:8px 0;font-size:9.5pt}
td,th{border:1px solid #bbb;padding:4px 6px;vertical-align:top}th{background:#eee}code{background:#f2f2f2;padding:0 3px;font-size:9pt}
pre{background:#f5f5f5;border:1px solid #ddd;padding:8px;font-size:8.5pt;white-space:pre-wrap}
figure{margin:8px 0;page-break-inside:avoid}img{max-width:100%;border:1px solid #999}tr{page-break-inside:avoid}"""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Dashboard user guide</title><style>{css}</style></head><body>{''.join(out)}</body></html>"


def main() -> None:
    """Fill placeholders, write HTML, print PDF."""
    md = fill_placeholders(HERE / "USER_GUIDE.md")
    page = HERE / "USER_GUIDE.html"
    page.write_text(to_html(md), encoding="utf-8")
    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if not browser:
        print("no Edge/Chrome found: HTML only")
        return
    pdf = HERE / "USER_GUIDE.pdf"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", page.resolve().as_uri()], check=False, timeout=120,
                   capture_output=True)
    print(page, page.stat().st_size, "bytes;", pdf, pdf.stat().st_size if pdf.exists() else "NOT CREATED")


if __name__ == "__main__":
    main()
