# report/build_report.py
# Builds report/Minor_Project_Report.docx with python-docx from the content in report/content.py: university format
# (A4, Times New Roman 12 pt, 1.5 spacing, margins 3.5/2.5/1.25/1.25 cm), unnumbered title page, roman front matter,
# arabic main text, Word TOC / List of Figures / List of Tables fields and SEQ caption fields numbered per chapter.
# Documentation tooling only; not part of the testbed.
"""Generate the minor project report (.docx)."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

import content
from references import REFS

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "Minor_Project_Report.docx"
FONT = "Times New Roman"
TEXT_WIDTH_CM = 21.0 - 3.5 - 1.25


# ------------------------------------------------------------------ low-level helpers
def set_font(run_or_style, size=None, bold=None, italic=None, name=FONT):
    """Set font name (incl. East Asian), size and weight."""
    f = run_or_style.font
    f.name = name
    if size:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    f.color.rgb = RGBColor(0, 0, 0)
    el = run_or_style.element if hasattr(run_or_style, "element") else run_or_style._element
    rpr = el.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(a), name)


def spacing(pf, before=0, after=6, line=1.5):
    """Paragraph spacing: 1.5 lines everywhere."""
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE if line == 1.5 else WD_LINE_SPACING.SINGLE


def add_field(paragraph, instr, result=""):
    """Insert a complex field (begin / instrText / separate / result / end)."""
    def fld(t):
        r = OxmlElement("w:r")
        c = OxmlElement("w:fldChar")
        c.set(qn("w:fldCharType"), t)
        if t == "begin":
            c.set(qn("w:dirty"), "true")
        r.append(c)
        return r
    p = paragraph._p
    p.append(fld("begin"))
    r = OxmlElement("w:r")
    t = OxmlElement("w:instrText")
    t.set(qn("xml:space"), "preserve")
    t.text = f" {instr} "
    r.append(t)
    p.append(r)
    p.append(fld("separate"))
    run = paragraph.add_run(result)
    set_font(run)
    p.append(fld("end"))
    return run


def add_rich(paragraph, text, size=None, base_bold=False):
    """Add text with **bold**, *italic* and `code` markup; ⟦key⟧ becomes an APA in-text citation."""
    text = re.sub(r"⟦([^⟧]+)⟧", lambda m: cite(m.group(1)), text)
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            r = paragraph.add_run(part[2:-2]); set_font(r, size, bold=True)
        elif part.startswith("`"):
            r = paragraph.add_run(part[1:-1]); set_font(r, (size or 12) - 1.5, name="Courier New")
        elif part.startswith("*"):
            r = paragraph.add_run(part[1:-1]); set_font(r, size, bold=base_bold, italic=True)
        else:
            r = paragraph.add_run(part); set_font(r, size, bold=base_bold)


def cite(spec):
    """'golra21' → (Golra & Engel, 2021); 'golra21;sun21' → (A, 2021; B, 2021); 'golra21|n' → Golra and Engel (2021)."""
    narrative = spec.endswith("|n")
    keys = spec[:-2].split(";") if narrative else spec.split(";")
    if narrative:
        return "; ".join(REFS[k]["narrative"] for k in keys)
    return "(" + "; ".join(REFS[k]["cite"] for k in keys) + ")"


def keep_with_next(p):
    p.paragraph_format.keep_with_next = True


# ------------------------------------------------------------------ document builder
class Report:
    """Thin wrapper that keeps the chapter number for captions."""

    def __init__(self) -> None:
        self.doc = Document()
        self.chapter = ""
        self.counts = {"Table": 0, "Figure": 0}
        self._styles()

    # ---- styles
    def _styles(self) -> None:
        st = self.doc.styles
        normal = st["Normal"]
        set_font(normal, 12)
        spacing(normal.paragraph_format)
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for name, size, align in (("Heading 1", 16, WD_ALIGN_PARAGRAPH.CENTER), ("Heading 2", 14, WD_ALIGN_PARAGRAPH.LEFT),
                                  ("Heading 3", 12, WD_ALIGN_PARAGRAPH.LEFT)):
            s = st[name]
            set_font(s, size, bold=True, italic=False)
            spacing(s.paragraph_format, before=12 if name != "Heading 1" else 0, after=12 if name == "Heading 1" else 6)
            s.paragraph_format.alignment = align
            s.paragraph_format.keep_with_next = True
        st["Heading 1"].paragraph_format.page_break_before = True
        cap = st["Caption"]
        set_font(cap, 12, bold=False, italic=False)
        spacing(cap.paragraph_format, before=6, after=12)
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for name in ("List Bullet", "List Number"):
            set_font(st[name], 12)
            spacing(st[name].paragraph_format, after=3)
            st[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for name in ("TOC 1", "TOC 2", "TOC 3", "Table of Figures"):
            try:
                s = st[name]
            except KeyError:
                s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            set_font(s, 12)
            spacing(s.paragraph_format, after=0)
        code = st.add_style("CodeBlock", WD_STYLE_TYPE.PARAGRAPH)
        set_font(code, 10, name="Courier New")
        spacing(code.paragraph_format, after=0)
        code.paragraph_format.left_indent = Cm(0.6)
        code.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        tbl = st.add_style("TableText", WD_STYLE_TYPE.PARAGRAPH)
        set_font(tbl, 10)
        spacing(tbl.paragraph_format, after=0, line=1.0)   # table cells: single spacing
        tbl.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # ---- sections and page numbers
    def page_setup(self, section) -> None:
        section.page_height, section.page_width = Cm(29.7), Cm(21.0)
        section.left_margin, section.right_margin = Cm(3.5), Cm(1.25)
        section.top_margin, section.bottom_margin = Cm(2.5), Cm(1.25)
        section.footer_distance = Cm(0.5)
        section.header_distance = Cm(1.0)

    def numbering(self, section, fmt=None, start=None, footer=True) -> None:
        """Page-number format/start for a section and a centred PAGE field in its footer."""
        sect = section._sectPr
        pg = sect.find(qn("w:pgNumType"))
        if pg is None:
            pg = OxmlElement("w:pgNumType")
            sect.append(pg)
        if fmt:
            pg.set(qn("w:fmt"), fmt)
        if start is not None:
            pg.set(qn("w:start"), str(start))
        section.footer.is_linked_to_previous = False
        p = section.footer.paragraphs[0]
        p.text = ""
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        spacing(p.paragraph_format, after=0)
        if footer:
            add_field(p, "PAGE", "1")

    def new_section(self, fmt=None, start=None):
        s = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self.page_setup(s)
        self.numbering(s, fmt, start)
        return s

    # ---- blocks
    def h1(self, text, toc=True) -> None:
        m = re.match(r"(CHAPTER (\d+)|APPENDIX ([A-Z]))", text)
        self.chapter = (m.group(2) or m.group(3)) if m else ""
        self.counts = {"Table": 0, "Figure": 0}
        if toc:
            p = self.doc.add_paragraph(style="Heading 1")
        else:
            p = self.doc.add_paragraph()
            p.paragraph_format.page_break_before = True
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            spacing(p.paragraph_format, after=12)
        r = p.add_run(text.upper())
        set_font(r, 16, bold=True)

    def h2(self, text) -> None:
        p = self.doc.add_paragraph(style="Heading 2")
        set_font(p.add_run(text), 14, bold=True)

    def h3(self, text) -> None:
        p = self.doc.add_paragraph(style="Heading 3")
        set_font(p.add_run(text), 12, bold=True)

    def p(self, text, align=None, bold=False, size=None, after=6, indent_first=False):
        para = self.doc.add_paragraph()
        add_rich(para, text, size, base_bold=bold)
        if align == "center":
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "left":
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif align == "right":
            para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        para.paragraph_format.space_after = Pt(after)
        return para

    def bullets(self, items, numbered=False) -> None:
        for it in items:
            para = self.doc.add_paragraph(style="List Number" if numbered else "List Bullet")
            add_rich(para, it)

    def code(self, text) -> None:
        lines = text.strip("\n").split("\n")
        for i, line in enumerate(lines):
            para = self.doc.add_paragraph(style="CodeBlock")
            r = para.add_run(line if line else " ")
            set_font(r, 10, name="Courier New")
            if i < len(lines) - 1:
                keep_with_next(para)
        self.doc.paragraphs[-1].paragraph_format.space_after = Pt(8)

    def caption(self, kind, title):
        """'Table 5.1: …' / 'Fig. 5.1: …' with a SEQ field that restarts at each Heading 1."""
        self.counts[kind] += 1
        para = self.doc.add_paragraph(style="Caption")
        label = "Table" if kind == "Table" else "Fig."
        r = para.add_run(f"{label} {self.chapter}."); set_font(r, 12, bold=True)
        res = add_field(para, f"SEQ {kind} \\* ARABIC \\s 1", str(self.counts[kind]))
        res.bold = True
        add_rich(para, f": {title}")
        return para

    def table(self, title, header, rows, widths_cm, size=10):
        """Caption above, grid table, header row repeated, rows not split across pages."""
        cap = self.caption("Table", title)
        keep_with_next(cap)
        total = sum(widths_cm)
        widths = [w * (TEXT_WIDTH_CM - 0.25) / total for w in widths_cm]   # always span the text width
        t = self.doc.add_table(rows=1 + len(rows), cols=len(header))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for ri, row in enumerate([header] + rows):
            tr = t.rows[ri]._tr
            trpr = tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit"); trpr.append(cs)
            if ri == 0:
                th = OxmlElement("w:tblHeader"); trpr.append(th)
            for ci, val in enumerate(row):
                cell = t.cell(ri, ci)
                cell.width = Cm(widths[ci])
                para = cell.paragraphs[0]
                para.style = self.doc.styles["TableText"]
                add_rich(para, str(val), size, base_bold=(ri == 0))
                if ri == 0:
                    para.paragraph_format.keep_with_next = True   # header never alone at a page bottom
                if ri == 0:
                    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "E7E6E6")
                    cell._tc.get_or_add_tcPr().append(shd)
        for ci, w in enumerate(widths):          # grid columns: Word uses these for the layout
            t.columns[ci].width = Cm(w)
        tblw = OxmlElement("w:tblW"); tblw.set(qn("w:w"), str(int(sum(widths) * 567))); tblw.set(qn("w:type"), "dxa")
        old = t._tbl.tblPr.find(qn("w:tblW"))
        if old is not None:
            t._tbl.tblPr.remove(old)
        t._tbl.tblPr.append(tblw)
        # fixed layout so Word keeps the widths
        tblpr = t._tbl.tblPr
        lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblpr.append(lay)
        after = self.doc.add_paragraph()
        after.paragraph_format.space_after = Pt(4)
        return t

    def figure(self, path, title, width_cm=15.5):
        """Picture centred, caption below."""
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        spacing(para.paragraph_format, before=6, after=0, line=1.0)
        para.add_run().add_picture(str(ROOT / path), width=Cm(width_cm))
        keep_with_next(para)
        self.caption("Figure", title)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def toc_field(self, title, instr, placeholder):
        """Heading-less title (front matter list) + field."""
        self.h1(title)
        para = self.doc.add_paragraph()
        add_field(para, instr, placeholder)

    def h1_plain(self, text):
        """Front-matter title that is not itself listed in the TOC."""
        self.h1(text, toc=False)

    def field(self, instr, placeholder):
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        add_field(para, instr, placeholder)

    def abbrev(self, items):
        """Abbreviation list: term, tab, meaning (1.5 spacing like all text)."""
        for term, meaning in items:
            para = self.doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            para.paragraph_format.tab_stops.add_tab_stop(Cm(3.5))
            para.paragraph_format.left_indent = Cm(3.5)
            para.paragraph_format.first_line_indent = Cm(-3.5)
            para.paragraph_format.space_after = Pt(0)
            r = para.add_run(term); set_font(r, 12, bold=True)
            add_rich(para, "\t" + meaning)

    def ref(self, text):
        """APA reference with a 1.27 cm hanging indent."""
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        para.paragraph_format.left_indent = Cm(1.27)
        para.paragraph_format.first_line_indent = Cm(-1.27)
        add_rich(para, text)

    def truth_table(self):
        """Appendix A: arbiter.decide for every state × lease × origin × action (computed, not typed)."""
        import sys
        sys.path.insert(0, str(ROOT))
        from equipment import arbiter
        from equipment.config import Action, ControlState, Origin
        rows = []
        for cs in (ControlState.ONLINE_REMOTE, ControlState.ONLINE_LOCAL, ControlState.EQUIPMENT_OFFLINE):
            for lease in (False, True):
                for o in (Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR):
                    cells = []
                    for a in (Action.START, Action.STOP, Action.EC_WRITE):
                        d = arbiter.decide(cs, lease, o, a)
                        cells.append("allowed" if d.allowed else "rejected: " + d.reason)
                    rows.append([cs.name, "yes" if lease else "no", o.value] + cells)
        self.table("Arbiter decision for every combination of control state, lease, origin and action",
                   ["Control state", "Lease", "Origin", "START", "STOP", "EC_WRITE"], rows, [3.8, 1.4, 2.3, 2.9, 2.9, 2.7], 9)

    def save(self):
        self.doc.save(OUT)


def build() -> Path:
    """Run every block of content.BLOCKS through the builder."""
    rep = Report()
    first = rep.doc.sections[0]
    rep.page_setup(first)
    rep.numbering(first, footer=False)
    for kind, *args in content.blocks():
        getattr(rep, kind)(*args)
    rep.save()
    return OUT


if __name__ == "__main__":
    print(build())
