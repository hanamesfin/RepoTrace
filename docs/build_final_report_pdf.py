#!/usr/bin/env python3
"""Build the HiLCoE senior-project final report for RepoTrace.

A4, 1 inch margins, Times New Roman 12 pt, leading 18.
Preliminary pages are not numbered. Page numbers start at 1 on the
Introduction and sit at the bottom centre.

Cooper Black and Calibri are used when the font files are installed.
On this machine they are not, so those lines use Times New Roman Bold
at the sizes the guideline names.
"""
import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Flowable, Frame, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'RepoTrace_Final_Report.pdf'
COPY_TO = Path(
    '/Users/janus/Downloads/Senior Project Deleverables Guideline & References+'
    '/RepoTrace_Final_Report.pdf'
)
SUP = Path('/System/Library/Fonts/Supplemental')
LIB = Path('/Library/Fonts')
USER = Path.home() / 'Library' / 'Fonts'
PAGE_W, PAGE_H = A4
MARGIN = inch
CONTENT_W = PAGE_W - 2 * MARGIN
CONTENT_H = PAGE_H - 2 * MARGIN


def find_font(*names):
    for base in (SUP, LIB, USER, Path('/System/Library/Fonts')):
        for name in names:
            path = base / name
            if path.is_file():
                return str(path)
    return None


def register_fonts():
    files = {
        'TNR': ['Times New Roman.ttf'],
        'TNR-B': ['Times New Roman Bold.ttf'],
        'TNR-I': ['Times New Roman Italic.ttf'],
        'TNR-BI': ['Times New Roman Bold Italic.ttf'],
        'Cal': ['Calibri.ttf'],
        'Cal-B': ['Calibri Bold.ttf'],
        'Cooper': ['CooperBlack.ttf', 'Cooper Black.ttf'],
    }
    found = {key: find_font(*names) for key, names in files.items()}
    if not (found['TNR'] and found['TNR-B']):
        raise SystemExit('Times New Roman was not found under /System/Library/Fonts/Supplemental.')
    pdfmetrics.registerFont(TTFont('TNR', found['TNR']))
    pdfmetrics.registerFont(TTFont('TNR-B', found['TNR-B']))
    italic = 'TNR'
    if found['TNR-I']:
        pdfmetrics.registerFont(TTFont('TNR-I', found['TNR-I']))
        italic = 'TNR-I'
    if found['TNR-BI']:
        pdfmetrics.registerFont(TTFont('TNR-BI', found['TNR-BI']))
    pdfmetrics.registerFontFamily('TNR', normal='TNR', bold='TNR-B', italic=italic, boldItalic='TNR-BI' if found['TNR-BI'] else 'TNR-B')
    if found['Cal'] and found['Cal-B']:
        pdfmetrics.registerFont(TTFont('Cal', found['Cal']))
        pdfmetrics.registerFont(TTFont('Cal-B', found['Cal-B']))
        cover, cover_b = 'Cal', 'Cal-B'
    else:
        cover, cover_b = 'TNR', 'TNR-B'
    school = 'Cooper' if found['Cooper'] else 'TNR-B'
    if found['Cooper']:
        pdfmetrics.registerFont(TTFont('Cooper', found['Cooper']))
    return 'TNR', 'TNR-B', italic, cover, cover_b, school


BODY, BOLD, ITAL, COVER, COVER_B, SCHOOL = register_fonts()
MONO = 'Courier'


def S(name, **kw):
    return ParagraphStyle(name, **kw)


STY = {
    'body': S('body', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT,
              textColor=colors.black, spaceAfter=8, spaceBefore=0),
    'left': S('left', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT,
              textColor=colors.black, spaceAfter=6),
    'li': S('li', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT,
            textColor=colors.black, leftIndent=16, firstLineIndent=0, spaceAfter=3),
    'h1': S('h1', fontName=BOLD, fontSize=15, leading=23, alignment=TA_LEFT,
            textColor=colors.black, spaceBefore=0, spaceAfter=8, keepWithNext=True),
    'h2': S('h2', fontName=BOLD, fontSize=14, leading=21, alignment=TA_LEFT,
            textColor=colors.black, spaceBefore=14, spaceAfter=6, keepWithNext=True),
    'h3': S('h3', fontName=BOLD, fontSize=13, leading=20, alignment=TA_LEFT,
            textColor=colors.black, spaceBefore=12, spaceAfter=4, keepWithNext=True),
    'caption': S('caption', fontName=ITAL, fontSize=12, leading=18, alignment=TA_LEFT,
                 textColor=colors.black, spaceBefore=8, spaceAfter=4, keepWithNext=True),
    'figcap': S('figcap', fontName=ITAL, fontSize=12, leading=18, alignment=TA_LEFT,
                textColor=colors.black, spaceBefore=0, spaceAfter=0),
    'th': S('th', fontName=BOLD, fontSize=12, leading=18, alignment=TA_LEFT, textColor=colors.black),
    'td': S('td', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT, textColor=colors.black),
    'fronthead': S('fronthead', fontName=BOLD, fontSize=15, leading=23, alignment=TA_LEFT,
                   textColor=colors.black, spaceBefore=0, spaceAfter=8),
    'label': S('label', fontName=BOLD, fontSize=14, leading=21, alignment=TA_LEFT,
               textColor=colors.black, spaceBefore=10, spaceAfter=4),
    'code': S('code', fontName=MONO, fontSize=9, leading=12, alignment=TA_LEFT, textColor=colors.black),
    'ref': S('ref', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT,
             textColor=colors.black, leftIndent=18, firstLineIndent=-18, spaceAfter=8),
    'tocnote': S('tocnote', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT,
                 textColor=colors.black, spaceAfter=4),
    'hilcoe': S('hilcoe', fontName=SCHOOL, fontSize=14, leading=21, alignment=TA_CENTER,
                textColor=colors.black, spaceAfter=0),
    'c16': S('c16', fontName=COVER_B, fontSize=16, leading=24, alignment=TA_CENTER,
             textColor=colors.black, spaceAfter=0),
    'c16r': S('c16r', fontName=COVER, fontSize=16, leading=24, alignment=TA_CENTER,
              textColor=colors.black, spaceAfter=0),
    'front': S('front', fontName=BODY, fontSize=12, leading=18, alignment=TA_JUSTIFY,
               textColor=colors.black, spaceAfter=8),
    'signlab': S('signlab', fontName=BOLD, fontSize=16, leading=24, alignment=TA_LEFT,
                 textColor=colors.black, spaceBefore=8, spaceAfter=6),
    'mile': S('mile', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT,
              textColor=colors.black, spaceAfter=4),
    'mileb': S('mileb', fontName=BOLD, fontSize=12, leading=18, alignment=TA_LEFT,
               textColor=colors.black, spaceAfter=2),
}


def P(text, style='body'):
    return Paragraph(text, STY[style])


def widths(*fracs):
    if abs(sum(fracs) - 1) > 0.02:
        raise ValueError(fracs)
    return [CONTENT_W * f for f in fracs]


def add_table(story, caption, headers, rows, fracs):
    story.append(P(caption, 'caption'))
    data = [[P(h, 'th') for h in headers]]
    for row in rows:
        data.append([P(c, 'td') for c in row])
    table = Table(data, colWidths=widths(*fracs), repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#efefef')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    story.append(Spacer(1, 8))


class Rule(Flowable):
    def wrap(self, aw, ah):
        self.aw = aw
        return aw, 10

    def draw(self):
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(0.6)
        self.canv.line(0, 4, self.aw, 4)


def chapter(story, title):
    story.append(PageBreak())
    story.append(P(title, 'h1'))
    rule = Rule()
    rule.keepWithNext = True
    story.append(rule)


def h2(story, title):
    story.append(CondPageBreak(150))
    story.append(P(title, 'h2'))


def h3(story, title):
    story.append(CondPageBreak(120))
    story.append(P(title, 'h3'))


def prose(story, text, style='body'):
    for block in text.strip().split('\n\n'):
        story.append(P(' '.join(block.split()), style))


def bullet(story, text):
    story.append(P('–  ' + text, 'li'))


def code(story, text):
    block = Preformatted(text.rstrip() + '\n', STY['code'])
    story.append(Spacer(1, 4))
    story.append(block)
    story.append(Spacer(1, 8))


class CenterBlock(Flowable):
    def __init__(self, flowables, height):
        Flowable.__init__(self)
        self.flowables = list(flowables)
        self.box_h = height

    def wrap(self, aw, ah):
        self.aw = aw
        self.heights = []
        total = 0
        for flowable in self.flowables:
            _, h = flowable.wrap(aw, ah)
            self.heights.append(h)
            total += h
        self.total = total
        if total > self.box_h:
            print('CENTER OVERFLOW by', round(total - self.box_h, 1))
        return aw, min(self.box_h, ah)

    def draw(self):
        y = self.box_h
        slack = self.box_h - self.total
        if slack > 0:
            y -= slack / 2
        for flowable, h in zip(self.flowables, self.heights):
            y -= h
            flowable.drawOn(self.canv, 0, y)


class SignRow(Flowable):
    def __init__(self, left, right):
        Flowable.__init__(self)
        self.left = left
        self.right = right

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, 36

    def draw(self):
        c = self.canv
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.setFont(BOLD, 12)
        y = 14
        w1 = c.stringWidth(self.left + '  ', BOLD, 12)
        c.drawString(0, y, self.left)
        mid = self.aw * 0.48
        c.line(w1, y - 1, mid - 10, y - 1)
        x2 = self.aw * 0.52
        w2 = c.stringWidth(self.right + '  ', BOLD, 12)
        c.drawString(x2, y, self.right)
        c.line(x2 + w2, y - 1, self.aw, y - 1)


def draw_stack(canvas, x, y, w, h, rows, note):
    canvas.saveState()
    n = len(rows)
    gap = 12
    box_h = 34
    box_w = min(w * 0.88, 390)
    bx = x + (w - box_w) / 2.0
    cursor = y + h - 4
    for i, (title, sub) in enumerate(rows):
        cursor -= box_h
        canvas.setFillColor(colors.HexColor('#f4f4f4'))
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(1)
        canvas.roundRect(bx, cursor, box_w, box_h, 3, fill=1, stroke=1)
        canvas.setFillColor(colors.black)
        canvas.setFont(BOLD, 11)
        canvas.drawCentredString(bx + box_w / 2.0, cursor + 18, title)
        canvas.setFont(BODY, 8)
        canvas.drawCentredString(bx + box_w / 2.0, cursor + 6, sub)
        if i < n - 1:
            ax = bx + box_w / 2.0
            canvas.setStrokeColor(colors.black)
            canvas.line(ax, cursor, ax, cursor - gap + 4)
            canvas.line(ax, cursor - gap + 4, ax - 3.2, cursor - gap + 9)
            canvas.line(ax, cursor - gap + 4, ax + 3.2, cursor - gap + 9)
            cursor -= gap
    if note:
        canvas.setFillColor(colors.black)
        canvas.setFont(BODY, 9)
        canvas.drawCentredString(x + w / 2.0, y + 2, note)
    canvas.restoreState()


class Captioned(Flowable):
    def __init__(self, kind, text, height, rows, note):
        Flowable.__init__(self)
        self.toc_kind = kind
        self.toc_text = text
        self.inner_h = height
        self.rows = rows
        self.note = note

    def wrap(self, aw, ah):
        self.aw = aw
        self.cap = Paragraph(self.toc_text, STY['figcap'])
        _, self.cap_h = self.cap.wrap(aw, ah)
        self.height = self.cap_h + 6 + self.inner_h
        return aw, self.height

    def draw(self):
        self.cap.drawOn(self.canv, 0, self.inner_h + 6)
        draw_stack(self.canv, 0, 0, self.aw, self.inner_h, self.rows, self.note)


def on_blank(canvas, doc):
    return


def on_body(canvas, doc):
    if doc.body_first is None:
        doc.body_first = doc.page
    number = doc.page - doc.body_first + 1
    canvas.saveState()
    canvas.setFillColor(colors.black)
    canvas.setFont(BODY, 12)
    canvas.drawCentredString(PAGE_W / 2.0, 0.50 * inch, str(number))
    canvas.restoreState()


class Report(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        BaseDocTemplate.__init__(self, filename, **kwargs)
        self.body_first = None
        self._bm = 0

    def handle_documentBegin(self):
        self.body_first = None
        self._bm = 0
        BaseDocTemplate.handle_documentBegin(self)

    def shown(self):
        if not self.body_first:
            raise RuntimeError('A numbered heading was placed before the body.')
        return self.page - self.body_first + 1

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ('h1', 'h2'):
            text = flowable.getPlainText()
            level = 0 if flowable.style.name == 'h1' else 1
            self.notify('TOCEntry', (level, text, self.shown()))
            self._bm += 1
            key = 'b%d' % self._bm
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=0)
        elif isinstance(flowable, Paragraph) and flowable.style.name == 'caption':
            text = flowable.getPlainText()
            kind = 'FigureEntry' if text.startswith('Figure') else 'TableEntry'
            self.notify(kind, (0, text, self.shown()))
        elif getattr(flowable, 'toc_kind', None):
            self.notify(flowable.toc_kind, (0, flowable.toc_text, self.shown()))


def contents_styles():
    common = dict(fontName=BODY, fontSize=12, leading=18, textColor=colors.black)
    return [
        ParagraphStyle(name='toc0', leftIndent=0, firstLineIndent=0, spaceBefore=3, spaceAfter=2, **common),
        ParagraphStyle(name='toc1', leftIndent=16, firstLineIndent=0, spaceBefore=1, spaceAfter=1, **common),
    ]


def make_toc(kind):
    toc = TableOfContents()
    toc.levelStyles = contents_styles()
    toc.dotsMinLevel = 0
    toc.tableStyle = TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ])
    toc._notifyKind = kind
    return toc


def names():
    out = [P('Prepared by:', 'c16'), Spacer(1, 4)]
    for name in ('HANA MESFIN', 'ISRAEL HAYALSEW', 'JAFFER HUSSIEN', 'KAL TSEGAYE'):
        out.append(P(name, 'c16'))
    return out


TITLE = 'REPOTRACE: A LOCAL SYSTEM FOR EXPLORING PYTHON CODE AND REVIEWING THE IMPACT OF A CHANGE'
TITLE_HTML = 'REPOTRACE:<br/>A LOCAL SYSTEM FOR EXPLORING PYTHON CODE<br/>AND REVIEWING THE IMPACT OF A CHANGE'
HEADLINE = 'RepoTrace: A Local System for Exploring Python Code and Reviewing the Impact of a Change'
def assemble(story):
    block_h = CONTENT_H - 8
    story.append(CenterBlock([
        P('HiLCoE', 'hilcoe'),
        Spacer(1, 14),
        P('School of Computer Science and Technology', 'c16'),
        Spacer(1, 26),
        P(TITLE_HTML, 'c16'),
        Spacer(1, 20),
        P('SENIOR PROJECT FINAL DOCUMENT', 'c16'),
        Spacer(1, 26),
        *names(),
        Spacer(1, 20),
        P('NOVEMBER 2026', 'c16'),
    ], block_h))
    story.append(NextPageTemplate('front'))
    story.append(PageBreak())

    story.append(CenterBlock([
        P(TITLE_HTML, 'c16'),
        Spacer(1, 18),
        *names(),
        Spacer(1, 16),
        P('A SENIOR PROJECT DOCUMENT SUBMITTED TO THE UNDERGRADUATE PROGRAMME OFFICE IN PARTIAL FULFILLMENT OF THE REQUIREMENTS FOR THE DEGREE OF BACHELOR OF SCIENCE IN COMPUTER SCIENCE', 'c16'),
        Spacer(1, 16),
        P('Advisor:', 'c16'),
        P('DR. HASSEN', 'c16'),
        Spacer(1, 16),
        P('NOVEMBER 2026', 'c16'),
    ], block_h))
    story.append(PageBreak())

    story.append(CenterBlock([
        P('HiLCoE', 'hilcoe'),
        Spacer(1, 12),
        P('School of Computer Science and Technology', 'c16'),
        Spacer(1, 18),
        P('RepoTrace: A Local System for Exploring<br/>Python Code and Reviewing the Impact of a Change', 'c16'),
        Spacer(1, 14),
        *names(),
        Spacer(1, 12),
        P('Approved By:', 'signlab'),
        SignRow('Advisor:', 'Signature:'),
        SignRow('Examiner:', 'Signature:'),
    ], block_h))
    story.append(PageBreak())

    story.append(P('Acknowledgement', 'fronthead'))
    story.append(Rule())
    prose(story, '''
The authors thank Dr. Hassen, advisor of this senior project, and the School of Computer Science and Technology at HiLCoE. The four authors shared the reading of the program, the checks, and the writing of this report.

The measurements quoted in Chapter 5 are copied from the project handbook of 15 November 2026 and from the tinydb evaluation note of 18 November 2026. They were not measured again for this document. This report describes the program in the repository as it was read for the report, including the limits that were already known.
''')
    story.append(PageBreak())

    story.append(P('Table of Contents', 'fronthead'))
    story.append(Rule())
    prose(story, '''
The pages before the Introduction are not numbered. Numbering starts at the Introduction and continues through the annexes. The preliminary pages are listed here without a page number.
''')
    for line in (
        'Acknowledgement',
        'Table of Contents',
        'List of Figures',
        'List of Tables',
        'Executive Summary',
    ):
        story.append(P(line, 'tocnote'))
    story.append(P('Numbered pages', 'label'))
    story.append(make_toc('TOCEntry'))
    story.append(PageBreak())

    story.append(P('List of Figures', 'fronthead'))
    story.append(Rule())
    prose(story, '''
Only the figures drawn in this report are listed.
''')
    story.append(make_toc('FigureEntry'))
    story.append(PageBreak())

    story.append(P('List of Tables', 'fronthead'))
    story.append(Rule())
    prose(story, '''
Only the tables included in this report are listed.
''')
    story.append(make_toc('TableEntry'))
    story.append(PageBreak())

    story.append(P('Executive Summary', 'fronthead'))
    story.append(Rule())
    prose(story, '''
A developer who edits a Python project can read a diff and still not see which functions the edit could reach, or which tests are connected to it. Running the program is not always the next step the developer wants to take, and a review that went past the evidence would not be a review.

The method is static. RepoTrace reads each Python file with the ast library, joins the files into a call map, and grades each link. When the folder is a Git repository, the same map can be built for two commits and compared. The person uses a guided page that the program serves on that computer.

What was built is a local, read-only system for the developer who owns the repository. It opens a folder and can explore it without Git. It compares two commits, shows progress, and can be cancelled. Reversing the comparison swaps those two commits in the analysis and leaves the repository as it was. The review shows what to check, the changed code, a shortlist of related tests with commands that can be copied, and the limits and history of the read. Recommendations are rules applied to that review. The map can be read physically, logically, or in an experimental conceptual view. The review can be exported as JSON or CSV. Theme and recommendation marks stay in the browser. The page also shows local Git status.

The hard part is what a static reading cannot see. Calls that Python decides while the program is running are missing from the map. Measurements already written in the project handbook and in the tinydb note show that a named test is often connected for real, and that many relevant tests are still missed. The screen is written to show those holes. The program does not upload the project, does not run the project, and does not forecast an outcome.
''')

    story.append(NextPageTemplate('body'))
    story.append(PageBreak())
    story.append(P('Chapter 1. Introduction', 'h1'))
    rule = Rule()
    rule.keepWithNext = True
    story.append(rule)

    h2(story, '1.1 Background')
    prose(story, '''
A developer who changes a Python project usually starts from a diff. The diff shows the lines that were added and the lines that were removed. It does not, by itself, show which other functions call the changed one, or which tests are connected to it. Finding that out by reading the whole tree is slow, and running the project is not always what the developer wants to do next. Some paths are not taken in a single run. Some projects are large enough that running the suite is the last step, not the first look.

Git is the record of those saved versions [1]. RepoTrace uses that record when the person asks for a comparison, and it can also read the folder that is on disk when no comparison is wanted. In both cases it reads the source as text. It does not import the project and it does not run it.

The reading is done with the ast library in the Python standard library [2]. The library turns a file into a tree of definitions, imports, and calls. RepoTrace walks that tree, joins the files of one project into a map, and keeps a grade on every link it draws. The grade is the amount of evidence the text supplied. A later chapter describes the grades. The point of the grade is that a single yes or no would hide how much of the map is solid.

The same map can be built twice, once for each of two commits, and then compared. The comparison lists the definitions that changed and the places that could be affected. It also looks for tests that the map connects to those definitions. The result is a review the developer can read before deciding which tests to run. The review is a starting point. It is not a substitute for the suite, and it is not a forecast of what will fail.

The person meets this work through a page on the same computer. The guided screens are opened with <font face="Courier" size="11">python3 -m repotrace --lab</font>. The earlier screen is still opened by <font face="Courier" size="11">python3 -m repotrace</font> and by double-clicking <font face="Courier" size="11">RepoTrace.command</font>. This report describes the system as it stands, and it treats the guided screens as the interface of the finished work.
''')

    h2(story, '1.2 Statement of the Problem')
    prose(story, '''
The problem is not that diffs are useless. The problem is that a diff answers a narrower question than the one a developer asks next. The next question is what else might have to be looked at, and how sure the tool is. A developer who guesses from the diff can miss a caller in another file, or can spend time on a file that the change does not reach.

A tool that filled that gap by saying the change was safe would be answering a different question from the one the evidence supports. A missing link can mean that the call is not there. It can also mean that the call is decided at run time and the reader could not see it. Those two meanings must not be collapsed. The project handbook records the rule that a quiet result means nothing was found, and it records the measurements that show how often the map is incomplete [3].

The developer who owns the repository needs a local way to see the map, to compare two saved versions, and to read the limits of that reading on the same page as the result. The system has to stay on that computer. Sending the source to a hosted service would turn a private reading into an upload.
''')

    h2(story, '1.3 Objectives')
    h3(story, '1.3.1 General objective')
    prose(story, '''
The general objective is to give the developer who owns a Python repository a local, read-only way to explore the code and to review what a change between two Git versions could affect, with the strength of the evidence kept visible.
''')
    h3(story, '1.3.2 Specific objectives')
    prose(story, '''
The specific objectives are the activities that make the general objective concrete. They are stated as what the program does in this repository.
''')
    for item in (
        'Read one Python file with ast and list its definitions and calls without executing the file.',
        'Join the files of a project into one map and grade each link.',
        'Answer, from that map, which functions call a chosen function and what a chosen function can reach.',
        'Compare two Git commits, list the definitions that changed, and show what each change could affect.',
        'Select a shortlist of tests that the map connects to the change, and keep the rest of the suite in view as a count rather than as a permission to skip it.',
        'Present the result in a guided local page: a review, recommendations drawn from that review, and a map that can be explored.',
        'Show the limits of the reading on the screen, including calls that could not be traced.',
    ):
        bullet(story, item)

    h2(story, '1.4 Scope and Limitations')
    prose(story, '''
The system is local. It listens on 127.0.0.1. It reads a folder the person already has. It does not upload the source, the path, or the review. It is read-only toward the Git repository: a comparison reads commits out of the object database into a temporary folder, and it does not commit, switch branches, or edit the working tree.

The language in scope is Python. The analysis is static. The program does not execute the project it is reading, and it does not run the tests it lists. A command is copied so the developer can run it in the project's own environment. The system does not forecast a failure with a probability model. Recommendations are rules over the review that was just built.

The guided comparison uses two commits. Unsaved edits are not part of that comparison. The explore path reads the working folder as it is on disk, and the version line says so when the work tree is dirty. The program does not watch the folder after the snapshot has been taken. A later edit is seen only if the person opens the project again.

The map cannot see every call. Python can choose a callee while the program is running, through a factory, a dependency container, a dynamic attribute, or a fixture the reader does not follow. The screen is required to leave those holes visible. The conceptual view of the map is an experiment. It groups files by calls and by common words, and the page marks it as experimental because the groups are often wrong.

There is no account, and there is no connection to GitHub, GitLab, Slack, Jira, or any other hosted service. The settings page says so. Search matches words. It does not call a language model. A sentence on the explore screen mentions an optional summary that would cite the same lines. No such summary is implemented, and there is no control that starts one.
''')

    h2(story, '1.5 Methodology')
    prose(story, '''
The method has four steps, and they are the steps the code actually takes. First, read each Python file with ast and collect definitions, imports, and calls. Second, build one call map for the project and grade each link as sure, maybe, or name only. Third, when the person chooses two commits, build the map for each commit and compare them. Fourth, present the result in a guided page served on the same computer.

The layers follow that order. Reading does not know about the page. The graph answers questions about a finished map and does not open source files. The change comparison uses the graph. The report turns the comparison into words and into the data the page reads. The local server is the door. Chapter 3 describes the rule that keeps this order, and the test that enforces it.

The work was checked with the unittest module in the standard library, and with reading the modules that the page depends on. Chapter 5 names the checks that were run for this report and the checks that exist and were not re-run. No questionnaire and no count of users is claimed here. The accuracy figures in Chapter 5 are the ones already written in the handbook and in the tinydb note.
''')

    h2(story, '1.6 Significance and Beneficiaries')
    prose(story, '''
The beneficiary is the developer who owns the repository. The useful outcome is a shorter path from a diff to the definitions and tests that are worth opening, with a visible distinction between a link the text shows and a link that depends on an assumption. The same person can explore a folder that has no Git history at all, which matters when the question is the shape of the code rather than a particular commit.

The benefit stops where the evidence stops. A connected test is a reason to run that test first. It is not a reason to ignore the rest of the suite. A definition with no connected test is a hole in the report, not a proof that the definition is untested. The significance of the project is that it makes this distinction ordinary, on a page the developer can open without sending the code away.
''')

    h2(story, '1.7 Feasibility')
    prose(story, '''
The project is practical on one computer. Python 3.9 or newer and Git are the requirements recorded for the program [3]. The application uses the standard library for reading, for the local server, and for its checks. No database is required, and no account is required. The difficult part is not hosting. It is the honesty of a static map. That limit is handled by showing what was not traced, rather than by hiding it. The work that this report compiles is the proposal, the requirements, the design, the implementation, and the manual. Table 1.1 names those phases and the outcome of each. It does not assign weeks. Dates for a Gantt chart were not verified for this report, so none are printed.
''')
    add_table(
        story,
        'Table 1.1 Phases of the work',
        ['Phase', 'Work', 'Outcome'],
        [
            ['Proposal', 'Problem, objectives, scope, and method', 'Chapter 1, the revised proposal'],
            ['Requirements', 'What the system should do, taken from the program', 'Chapter 2'],
            ['Design', 'Layers, subsystems, persistence, and access', 'Chapters 3 and 4'],
            ['Implementation', 'Engine, guided lab, reverse comparison, recommendations', 'The program under repotrace/, and Chapter 5'],
            ['Manual', 'Install, use, errors, and the help already on the screens', 'Annex A, and the full manual file'],
        ],
        (0.22, 0.40, 0.38),
    )

    h2(story, '1.8 Organisation of the Report')
    prose(story, '''
The report follows the school's final-report structure [4]. Chapter 1 is the revised proposal. Chapter 2 is the requirements specification. Chapter 3 is the system design and Chapter 4 is the object design. Chapter 5 is the implementation report. The references come next. Annex A is the user manual, in a shorter form than the full manual kept at <font face="Courier" size="11">docs/RepoTrace_User_Manual.pdf</font> [5]. Annex B is the milestone sheet for this final report.
''')
    chapter(story, 'Chapter 2. Requirements Specification')
    h2(story, '2.1 Purpose')
    prose(story, '''
This chapter states what the system should do. It is the requirements specification for the program that is in the repository, revised into the form of a report. The requirements are drawn from the guided screens and from the engine those screens call. They are not a list of features that were only discussed.

The purpose of the system is to let one developer, on one computer, open a Python folder, explore it, and, when two commits are chosen, read what that change could affect. The scope is the scope in Chapter 1. A requirement that would need an account, an upload, or a forecast is out of scope, and it is not written here as if it had been built.
''')
    h2(story, '2.2 Current Situation')
    prose(story, '''
The current situation is the ordinary one. The developer reads a diff, follows a few names by hand, and guesses which tests are worth running. That guess is sometimes right. It is also easy to miss a caller in another file, or to treat a file that only shares a name as if it were connected.

The tool that replaces the guess must not claim that a change is safe. An empty list can mean that nothing was found. It can also mean that the reader stopped at a call it could not follow. The requirements below are written so that the second meaning stays on the screen. The page the developer already has, the diff, remains the place where the lines themselves are read. RepoTrace adds the map and the limits. It does not replace the developer's judgement.
''')
    h2(story, '2.3 Proposed System')
    prose(story, '''
The proposed system, and the system that was built, is a local program. The person starts it from the RepoTrace folder. The guided screens open in a browser on 127.0.0.1. The first screen asks for a folder. From there the person can explore the working folder, or choose two commits and compare them.

The comparison can be reversed. Reversal is a second reading of the same two commits in the opposite direction. The Git repository is not modified. While the reading runs, the page shows the step that is in progress and offers Cancel. When the reading finishes, the workspace offers a review, a map, a file list, and settings. The review has what to check, the changed code, related tests, limits and history, and recommendations. The map has a physical view, a logical view, and an experimental conceptual view. Settings show the local Git status and can export the review as JSON or as CSV.

The earlier screen is still present. It is the screen opened without the lab flag. The requirements in this chapter are the requirements of the guided screens, because that is the interface this report specifies. The engine underneath is the same engine.
''')
    h2(story, '2.4 Terms')
    prose(story, '''
A few words are used with a fixed meaning. A link graded <i>sure</i> is a call the source text shows. A link graded <i>maybe</i> depends on an assumption, including a call on self that a subclass could override. A link graded <i>name only</i> is another call with the same name, and it is the weakest of the three. A snapshot is the set of files read for one analysis. A review is the comparison prepared for the screens. The shortlist is at most 20 tests the map connects to the change. It is a starting list. Reverse means the same two commits read from the newer one back toward the older one.
''')
    h2(story, '2.5 Functional Requirements')
    prose(story, '''
Each requirement is phrased as what the system should do. The list is limited to behaviour the lab actually has.
''')
    add_table(
        story,
        'Table 2.1 Functional requirements',
        ['ID', 'The system should'],
        [
            ['FR1', 'The system should open a folder that is already on this computer.'],
            ['FR2', 'The system should explore that folder without using Git, including a folder that has no commits.'],
            ['FR3', 'The system should compare two commits when both are chosen, and it should refuse a request that names only one of them.'],
            ['FR4', 'The system should reverse a comparison by swapping those two commits in the analysis only, and it should leave the Git repository unchanged.'],
            ['FR5', 'The system should show the progress of a read, in the order of the steps the engine runs, and it should let the person cancel the read.'],
            ['FR6', 'The system should present a review with what to check, the changed code, related tests, and the limits and history of the comparison.'],
            ['FR7', 'The system should build recommendations from the evidence already in that review, and it should leave the list empty when no item meets the rules.'],
            ['FR8', 'The system should show an explore map with a physical view, a logical view, and an experimental conceptual view.'],
            ['FR9', 'The system should search by words in names, paths, comments, and code, and it should say when nothing matches.'],
            ['FR10', 'The system should offer themes and keep the chosen theme in the browser for the next time the page opens.'],
            ['FR11', 'The system should export the review already on screen as JSON and as CSV, built in the browser, without uploading it.'],
            ['FR12', 'The system should show the local Git status of the opened folder: the branch, whether the work tree is dirty, HEAD, and how many recent commits were listed.'],
            ['FR13', 'The system should copy a stored test command and should not run that command.'],
            ['FR14', 'The system should keep dismiss, save, and completed marks for recommendations in the browser, for that folder and that pair of versions.'],
            ['FR15', 'The system should remember recent folders as paths on this computer, and on a Mac it should offer the system folder dialog.'],
            ['FR16', 'The system should serve the guided screens only on this computer and should require the token created for that launch.'],
        ],
        (0.14, 0.86),
    )
    prose(story, '''
FR4 is implemented in one function, <font face="Courier" size="11">lab_direction</font>, which is the only place the two commits are swapped. FR7 does not add a model. A follow-up question searches the words of the recommendations that were already built. FR13 copies the command the review stored. If the browser cannot copy, the page tells the person to select the command that is already visible.
''')
    h2(story, '2.6 Non-functional Requirements')
    prose(story, '''
The non-functional requirements are the constraints on how those functions run. The 12-point type, the 1.5 line spacing, and the one-inch margins in this document are rules for the document. They are not rules for the application screens. The screens use their own type sizes.
''')
    add_table(
        story,
        'Table 2.2 Non-functional requirements',
        ['Area', 'Requirement'],
        [
            ['Place', 'The system should stay on the computer that started it. The server binds to 127.0.0.1.'],
            ['Language', 'The system should run on Python 3.9 or newer. Git is required only for a comparison.'],
            ['Upload', 'The system should not upload the project, the path, or the review.'],
            ['Repository', 'The system should be read-only toward Git. A comparison reads commits. It does not commit, switch branches, or edit files.'],
            ['Execution', 'The system should not execute the project it is reading, and it should not run the tests it lists.'],
            ['Access', 'The system should create a new token for each launch and should refuse an API call that does not present it.'],
            ['Dependencies', 'The application should use the Python standard library. No package is installed to run it.'],
            ['Forecast', 'The system should not emit a probability, a numeric score, or a level-3 prediction. It has no probability model.'],
        ],
        (0.22, 0.78),
    )
    h2(story, '2.7 Main Scenarios')
    prose(story, '''
Four scenarios cover the ordinary use. They are described in words. No diagram is drawn for them, because a diagram that was not drawn should not be implied.

In the first scenario the person wants the shape of a project and does not have two versions, or does not want them. The person types a path, or on a Mac presses Browse, and chooses Explore without comparing. The system checks the folder, reads the Python files, and opens the map. Git is not required. The review list is empty. The map is the working folder.

In the second scenario the folder is a Git repository and the person chooses two different commits. The system inspects the repository, lists branches, tags, and recent commits, and notes whether the work tree is dirty. The person leaves Reverse set to No and starts the analysis. The page moves through check, map, read the older version, read the newer version, compare, find what could be affected, and prepare the screens. The review then shows the change in the direction it was made.

In the third scenario the person wants the opposite direction. Reverse is set to Yes before the analysis, or the switch on the review is used afterwards. The system reads the same two commits from the newer one toward the older one. A definition the later version added is shown as removed, and a definition it removed is shown as added. A banner says the review is reversed. The repository's HEAD is unchanged. Asking again with the opposite answer returns to the first direction. Each direction is a new read.

In the fourth scenario the review is open. The person reads what to check, opens the changed code, and copies a test command from the shortlist. The command is not executed. The person may open recommendations, dismiss one, or export the review. Dismiss, save, and completed stay in the browser. The export file is built from the review already on screen. Nothing is uploaded. The person may also refresh the local Git status. That status is a reading of the folder. It is not a connection to a hosted forge.

Table 2.3 collects these scenarios as use cases. The actor is the developer who owns the folder.
''')
    add_table(
        story,
        'Table 2.3 Use cases',
        ['Use case', 'What the person does', 'What the system does'],
        [
            ['UC1 Explore', 'Opens a folder and chooses explore without comparing.', 'Maps the working folder. Does not ask for commits.'],
            ['UC2 Compare', 'Chooses two commits and starts the analysis.', 'Reads both commits and returns one review.'],
            ['UC3 Reverse', 'Asks for the same pair in the opposite direction.', 'Swaps the commits in the analysis only. Does not modify Git.'],
            ['UC4 Cancel', 'Stops a read that is still running.', 'Ends the job at the next step and returns to the previous screen.'],
            ['UC5 Review', 'Reads the review and copies a test command.', 'Shows the evidence and copies the stored command. Does not run it.'],
            ['UC6 Recommend', 'Opens recommendations or types a follow-up.', 'Lists items built from the review, or searches those items by words.'],
            ['UC7 Export', 'Exports JSON or CSV.', 'Downloads the review from the browser. Does not upload it.'],
            ['UC8 Appearance', 'Chooses a theme.', 'Saves the theme in the browser and applies it on the next open.'],
            ['UC9 Git status', 'Refreshes local Git on the settings page.', 'Shows branch, dirty state, HEAD, and the recent commit count.'],
        ],
        (0.18, 0.38, 0.44),
    )
    h2(story, '2.8 What This Specification Does Not Claim')
    prose(story, '''
The specification does not claim a hosted sign-in, a language model, or a probability. It does not claim that every call in a Python project will be traced. It does not claim that the shortlist is the whole suite. It does not claim that a quiet review has proved anything about the change. Those limits are part of the requirements, because the screen is required to keep them visible.
''')

    chapter(story, 'Chapter 3. System Design')
    h2(story, '3.1 Purpose and Design Goals')
    prose(story, '''
The design has three goals, and they are the goals the program was built around. The first is evidence on the screen: a link, a test, or a recommendation should be traceable to something the reading recorded. The second is honesty: a hole in the map stays a hole, and a grade is not promoted because a stronger word would be more comforting. The third is locality: the analysis runs on the computer that holds the repository, and the result is a snapshot for that run.

This chapter is the system design. It names the architecture, the subsystems, the persistence, and the access control. It does not introduce a database, a login system, or a cloud service, because the program has none of those. Chapter 4 then opens the packages and the public behaviour of the modules that carry this design.
''')
    h2(story, '3.2 Architecture')
    prose(story, '''
The architecture is a pipeline. Each station uses what the stations before it produced. The order, from the file on disk to the page, is reading, mapping, graph, changes, report, and then the two doors, app and cli. The evaluation package stands aside. It measures the map. The product does not call it. The architecture note in the repository describes the same pipeline and the reasons for it [6].

A layer may call only a layer earlier in that list. app and cli are the same rank, so they may both call report, and they may not call each other. The rule is checked by reading the import statements, including imports inside functions and imports written with relative dots. The check lives in <font face="Courier" size="11">tests/test_architecture.py</font>. Chapter 5 records the result of running that file for this report.

Figure 3.1 draws the pipeline. The boxes are the layers. The arrow is the only direction a call may travel: downward, toward a layer that has already done its work. evaluation is named under the figure because it is not a step in the path the user runs.
''')
    story.append(Captioned(
        'FigureEntry',
        'Figure 3.1 The layers, from the file read to the screen',
        292,
        [
            ('reading', 'Read one Python file with ast'),
            ('mapping', 'Join the files and grade each link'),
            ('graph', 'Ask who calls a function, and what it reaches'),
            ('changes', 'Compare two Git versions of the map'),
            ('report', 'Review, recommendations, and the pages'),
            ('app and cli', 'Local server, guided screens, and the terminal'),
        ],
        'evaluation stands aside and is not called by these layers.',
    ))
    story.append(Spacer(1, 8))
    prose(story, '''
Table 3.1 says the same rule in words. "May use" means a layer earlier in the pipeline. "Does not use" is the constraint the test enforces.
''')
    add_table(
        story,
        'Table 3.1 Layers and what each may use',
        ['Layer', 'Role', 'May use'],
        [
            ['reading', 'One file: definitions and calls', 'Nothing else in the pipeline'],
            ['mapping', 'One project map, with grades', 'reading'],
            ['graph', 'Questions about a finished map', 'reading and mapping'],
            ['changes', 'Two versions, and what a change reaches', 'The layers above it'],
            ['report', 'Words, the review, the recommendations, the pages', 'The layers above it'],
            ['app', 'The local server and the guided screens', 'report and the layers above it, not cli'],
            ['cli', 'Terminal commands', 'report and the layers above it, not app'],
            ['evaluation', 'Measurement against recorded runs', 'The product must not depend on it'],
        ],
        (0.20, 0.42, 0.38),
    )
    prose(story, '''
Other shapes were considered and were not chosen. A hosted service would move the source off the computer. A database would store analyses the program does not need to keep. A single script with no layers would make the page and the map hard to change separately. The pipeline lets the page change without changing the grades, and it lets the map be tested without a browser. That is the reason the architecture note gives, and it is the reason the test exists.

There is one known compromise inside mapping. Four modules call one another in a loop, using imports inside functions. The architecture note records that the loop was left in place on purpose, because moving the files was not supposed to change behaviour. The layer test still holds: the loop stays inside mapping.
''')
    h2(story, '3.3 Subsystems and How They Interact')
    prose(story, '''
Five subsystems carry a guided comparison. The engine is the pipeline from reading through changes. The review builder, <font face="Courier" size="11">repotrace/report/lab_data.py</font>, turns an engine report into the structure the screens read. The recommendation builder, <font face="Courier" size="11">repotrace/report/recommendations.py</font>, reads that structure and returns items. The local server, <font face="Courier" size="11">repotrace/app/server.py</font>, accepts the folder and the two commits, runs the job, and serves the pages. The lab front end, the files under <font face="Courier" size="11">repotrace/report/lab/</font>, is the page in the browser.

Figure 3.2 shows the order of a guided comparison. The person talks only to the page. The page talks only to the server on this computer, and it sends the token. The server is the only subsystem that starts the engine. The engine does not know about themes, exports, or dismissed recommendations. Those stay in the browser after the snapshot has been delivered.
''')
    story.append(Captioned(
        'FigureEntry',
        'Figure 3.2 Path of one guided comparison',
        250,
        [
            ('Guided page', 'report/lab, in the browser'),
            ('Local server', 'app/server.py, on 127.0.0.1'),
            ('Job', 'Map the folder, then compare if asked'),
            ('Review builder', 'lab_data.build_review'),
            ('Recommendations', 'Rules over that review'),
        ],
        'The snapshot stops at the browser. Theme and recommendation marks stay there.',
    ))
    story.append(Spacer(1, 8))
    prose(story, '''
The interaction is one way during a run. The server calls <font face="Courier" size="11">analyze_repository</font> on the working folder. If two commits were given, it calls <font face="Courier" size="11">analyze_change_impact</font> on those commits after <font face="Courier" size="11">lab_direction</font> has applied a reversal. The change report and the per-version maps are passed to <font face="Courier" size="11">build_review</font>, which attaches the recommendations. The job then marks itself done, and the page reads the result. Cancel is a flag the job checks at the next progress step. It does not roll back a Git operation, because no Git operation has changed the repository.

The server is the standard-library HTTP server [7]. It is threaded so that a poll for progress can be answered while the job is still running. There is no separate worker machine and no queue service.
''')
    h2(story, '3.4 Persistence')
    prose(story, '''
There is no database. An analysis is a snapshot. The server holds the job in memory until the process stops or the job is dropped because newer jobs have filled the small list the server keeps. Closing the program drops the snapshot. Opening the project again reads the files again.

Three small pieces of state do last, and none of them is the analysis. The chosen theme is stored in the browser under the key <font face="Courier" size="11">repotrace-theme</font>. Dismiss, save, and completed marks for recommendations are stored in the browser under a key that includes the folder and the pair of versions. Recent search strings are stored in the browser as well. Recent folders are a list of paths in <font face="Courier" size="11">~/.repotrace/recent.json</font>, or in the file the server was given. That list is a convenience. It is not a store of results. A folder that no longer exists is dropped from the list the next time it is read.
''')
    h2(story, '3.5 Access')
    prose(story, '''
Access control is about the machine, not about user accounts. There are no accounts. The server binds to 127.0.0.1. Each launch creates a token with <font face="Courier" size="11">secrets.token_urlsafe</font>. The page receives the token in a meta element. API calls send it back in the header <font face="Courier" size="11">X-RepoTrace-Token</font>. A call with the wrong token is refused. A request whose Host header is not 127.0.0.1 or localhost on the port of this launch is refused. A request whose Origin is some other site is refused.

The comparison itself does not grant access to anything outside the folder the person named. Git is invoked as a read of that repository, with terminal prompts disabled, so a missing credential cannot open an interactive prompt. The design does not include a role, a password, or a session that survives the process.
''')
    h2(story, '3.6 Boundary Conditions')
    prose(story, '''
The design names a few boundaries so that later changes do not quietly cross them. The working-folder map and the commit comparison are different readings. The map can include unsaved edits. The comparison uses the two commits. A file that fails to parse is listed as a gap, and its functions are absent, rather than invented. Library and built-in calls are counted and are not drawn, so that the map is not filled with <font face="Courier" size="11">print</font> and <font face="Courier" size="11">list.append</font>. A name imported from outside the project is not matched to a same-named class elsewhere in the project.

The page may be closed, the process may be stopped, and the job may be cancelled. None of those events is specified as a write to the repository. The temporary folder used to hold a commit snapshot is removed when the comparison finishes. The design goal of locality is met by keeping every one of these boundaries on the same computer.
''')
    chapter(story, 'Chapter 4. Object Design')
    h2(story, '4.1 Trade-offs')
    prose(story, '''
The object design records the trade-offs that are actually in the program. The first is static analysis instead of running the code. Running the project would show one execution. It would also execute whatever the repository contains, and it would miss the paths that did not run. Reading the text avoids the execution and misses the calls that are decided later. The program takes the second loss, and it records the miss.

The second trade-off is the grade on a link. A sure link is one the source text shows. A maybe link depends on an assumption. A name-only link is another call with the same name, and it is the weakest. Collapsing these into one bit would make the map look more certain than the reading was. Creating an object is graded maybe. A call on self stays maybe, because a subclass can override it. The grade is not promoted without new evidence.

The third trade-off is the test shortlist. The comparison builds a plan of at most 20 tests. The ranking prefers stronger evidence, a path that exists only in the older version, an explicit use over a shared setup or an autouse fixture, and a shorter call path. It does not estimate the chance of failure, and it does not estimate how long a test takes. The screen says how many connected tests sit outside the list. The list is a place to start. It is not permission to skip the rest of the suite.

The fourth trade-off is the recommendations. They are rules over the review that was just built. They are not a model, and they are not a score. Level 3, the predictive level, is not emitted, because a forecast would have to be invented. A follow-up question searches the words of the items. The search says so on the page.
''')
    add_table(
        story,
        'Table 4.1 Grades of a link',
        ['Grade', 'What it means in this program'],
        [
            ['Sure', 'The source text shows the call. The screen can treat it as the strongest evidence it has.'],
            ['Maybe', 'One step depends on an assumption. A call on self stays here, because a subclass can override it.'],
            ['Name only', 'Another call uses the same name. This is the weakest evidence, and a common name is noisier still.'],
        ],
        (0.22, 0.78),
    )
    add_table(
        story,
        'Table 4.2 Recommendation levels',
        ['Level', 'What the module emits'],
        [
            ['1 Immediate', 'A concern, a test whose path exists only in the older version, a removed test, or a changed definition with no connected test.'],
            ['2 Analytical', 'Files edited in the same commits. The module treats this as correlation, not as a call.'],
            ['3 Predictive', 'Not emitted. The program has no probability model, so it does not invent a forecast.'],
            ['4 Strategic', 'At most one item, choosing between two actions the review already lists.'],
        ],
        (0.24, 0.76),
    )
    prose(story, '''
Priority is separate from the level. A concern, a lost or removed test path, or a changed definition with no connected test is marked now. Two files edited together at least twice, and the one strategic choice, are marked soon. Two files edited together once are marked later. Confidence is high when the link is written in the source, medium when it is maybe or an assumption, and low when the only support is history. There is no numeric score.

The caps on the list are part of the design. Concerns are kept up to 14, lost paths up to 8, removed tests up to 6, definitions with no connected test up to 8, and history pairs up to 6. Names that do not fit are not dropped silently. A further note names them. A gap by itself is not turned into advice.
''')
    h2(story, '4.2 Packages')
    h3(story, '4.2.1 repotrace.reading')
    prose(story, '''
The reading package reads one file. <font face="Courier" size="11">analyzer.py</font> walks the ast tree and records symbols, imports, calls, and the edges it can resolve inside that file. <font face="Courier" size="11">resolver.py</font> links the simple local calls. The public entry is <font face="Courier" size="11">analyze_file</font>. It returns a report for that file, including a status and a list of limitations. A file larger than the byte limit is not fully analysed. The package does not open Git, and it does not know about the page.
''')
    h3(story, '4.2.2 repotrace.mapping')
    prose(story, '''
The mapping package joins the files. <font face="Courier" size="11">repository.py</font> walks the folder, skips virtual environments, caches, and hidden directories, and calls the one-file analyser. If the caller does not pass source roots, the package reads a pytest <font face="Courier" size="11">pythonpath</font> when the project declares one, and otherwise uses the folder itself or <font face="Courier" size="11">src</font> when that is where the code sits. <font face="Courier" size="11">project_resolver.py</font>, <font face="Courier" size="11">method_resolver.py</font>, <font face="Courier" size="11">argument_flow.py</font>, and <font face="Courier" size="11">resolution_summary.py</font> grade the links across files. <font face="Courier" size="11">fixture_flow.py</font> follows a pytest fixture a limited number of steps. <font face="Courier" size="11">library_objects.py</font> classifies calls that go to Python itself or to an installed library so that they can be counted without being drawn.

The package's own limitations are written on the repository report. Supported links are potential links, not proof that the call runs. Wildcard imports are not expanded. Symbolic links are not followed, and gitignore rules are not applied. Tests are read as source and are not executed.
''')
    h3(story, '4.2.3 repotrace.graph')
    prose(story, '''
The graph package answers questions about a finished map. It does not read source files. <font face="Courier" size="11">graph_index.py</font> is the index. <font face="Courier" size="11">impact.py</font> walks callers up to a depth, a node count, and an edge count, and it returns one witness chain per caller. When a limit is hit, the result says it is limited. <font face="Courier" size="11">graph_explore.py</font> supports the neighbour and search questions the earlier screen asks. <font face="Courier" size="11">structure.py</font> supplies files, classes, and the relations the outline uses. A picture in the product is of one thing and its neighbours, because a picture of a whole repository becomes a tangle.
''')
    h3(story, '4.2.4 repotrace.changes')
    prose(story, '''
The changes package compares two versions. <font face="Courier" size="11">git_snapshot.py</font> reads the Python files of one commit into a temporary folder. The module states that only the Git object database is read, and that the branch, the index, and the working files are not changed. <font face="Courier" size="11">change_detector.py</font> pairs definitions between the two analyses. A rename or a move is reported only when the bodies match apart from the name. <font face="Courier" size="11">change_impact.py</font> is the comparison entry. <font face="Courier" size="11">signature_review.py</font> checks whether an explicit call still fits a changed plain function. <font face="Courier" size="11">decorator_impact.py</font> follows a changed decorator to the functions it wraps, within a limit. <font face="Courier" size="11">name_matches.py</font> records unresolved calls that use a changed name. <font face="Courier" size="11">test_selection.py</font> builds the per-change test list and the project shortlist.

A test file can contain tests, setup hooks, fixtures, and helpers. Only tests are recommended. When a setup hook or a fixture reaches the change, the tests that use it are recommended through that hook, and the chain says so. "Recommended" means the static graph connects the test to the change. It does not mean the test will fail.
''')
    h3(story, '4.2.5 repotrace.report')
    prose(story, '''
The report package turns results into words and into a page. <font face="Courier" size="11">story.py</font> writes the plain-language account of a comparison. <font face="Courier" size="11">overview.py</font> summarises a map. <font face="Courier" size="11">dashboard.py</font> builds the view the earlier screen reads, and <font face="Courier" size="11">dashboard_template.html</font> is that screen. <font face="Courier" size="11">lab_data.py</font> builds the graph and the review the guided screens read. <font face="Courier" size="11">recommendations.py</font> builds the recommendation list. The directory <font face="Courier" size="11">report/lab/</font> holds the guided pages: the picker, the workspace, the explore frame, and the themes.
''')
    h3(story, '4.2.6 repotrace.app, repotrace.cli, and the front end')
    prose(story, '''
<font face="Courier" size="11">repotrace.app.server</font> is the local server. <font face="Courier" size="11">examples.py</font> prepares the small built-in examples used by the earlier screen. The cli package is the other door: <font face="Courier" size="11">change</font>, <font face="Courier" size="11">map</font>, <font face="Courier" size="11">impact</font>, and <font face="Courier" size="11">arrows</font>. The front door <font face="Courier" size="11">python3 -m repotrace</font> selects one of those commands, and with no command it opens the server. The flag <font face="Courier" size="11">--lab</font> selects the guided screens. The two doors do not import each other.

The lab front end is static files served by that server. <font face="Courier" size="11">picker.js</font> is the open screen and the progress screen. <font face="Courier" size="11">app.js</font> is the workspace: the review, the recommendations, the settings, and the export. <font face="Courier" size="11">explore.js</font> is the map. <font face="Courier" size="11">theme.js</font> is the twelve themes. The page does not read the disk itself. It asks the server, and it sends the token.
''')
    h2(story, '4.3 Interfaces of the Main Modules')
    h3(story, '4.3.1 analyze_change_impact')
    prose(story, '''
<font face="Courier" size="11">analyze_change_impact(repo, base, head, ...)</font> returns one change-impact report, or raises <font face="Courier" size="11">GitError</font> when the repository or a commit cannot be used. The progress callback is told the stage and a short detail. The callback does not change the result. A caller that needs the per-version maps passes a dictionary as <font face="Courier" size="11">keep</font>, and the function stores the indexes and the reports there.

The report names the two commits, says whether the work tree was dirty, and lists files, changes, gaps, warnings, coverage, and a summary. Each changed definition carries the callers the graph found, a signature review when one was made, name matches, and a test selection. The project test plan is attached at the end. The function appends a warning that the suggestions are places to inspect, not proof of breakage or safety. If there are gaps, it also warns that an empty result must not be read as a proof that nothing is there.

Bounds are arguments, not hidden constants. The defaults used by the guided path include a cap of 500 changed definitions queried, 20 name-match sites, and 20 tests in the plan. A result that hits a bound says so.
''')
    h3(story, '4.3.2 build_review')
    prose(story, '''
<font face="Courier" size="11">build_review(report, view, reports, repo=None, name="project")</font> returns the review and the graph of the newer version, with removed definitions added so the page can still point at them. The review contains the changed definitions, a limited list of concerns, related code, the affected set, the tests in the plan, tests that were removed, history hints, gaps, unresolved calls inside changed definitions, and the recommendations.

Concerns are of three kinds the comparison can support. A leftover is a caller that may still use a removed name. A decorator concern names the functions a changed decorator wraps. A signature concern is an explicit call that fits the old parameters and not the new ones. The gaps text repeats the limits of the signature check: methods, decorated targets, constructors, and calls that use star-args are not checked. History hints come from <font face="Courier" size="11">history_hints</font>, which looks at recent commits and counts files edited together. Those counts are hints. They are not call links. A commit that touches more than the bulk limit of Python files is skipped so that a mass edit does not look like a relationship.
''')
    h3(story, '4.3.3 build_recommendations')
    prose(story, '''
<font face="Courier" size="11">build_recommendations(review)</font> returns a list of items. It does not mutate the review. Each item has the fields the screen reads: the recommendation, the reasoning, the evidence, the expected impact, the priority, the confidence, how to carry it out, what is required first, the risks, and the next action. The identifier is stable for that item so the browser can remember dismiss, save, and completed against it.

The kinds are concern, lost path, removed test, no connected test, history, and at most one strategic choice. <font face="Courier" size="11">answer_followup</font> searches those fields and returns at most three hits. When nothing matches, it says so. The note on a hit says the match is a search of this review's recommendations, and that it is not an AI answer.
''')
    h3(story, '4.3.4 The server')
    prose(story, '''
<font face="Courier" size="11">lab_direction(base, head, reverse)</font> is the whole of the reversal rule. The lines that decide it are these.
''')
    code(story, '''def lab_direction(base, head, reverse):
    reverse = bool(reverse) and bool(base) and bool(head)
    return (head, base, True) if reverse else (base, head, False)''')
    prose(story, '''
<font face="Courier" size="11">Job.run_lab</font> is the guided job. It maps the working folder, and if both commits are present it runs the comparison, builds the review, and stores a lab payload. <font face="Courier" size="11">make_server</font> binds the handler. The routes the guided page uses are the lab page, the lab files, <font face="Courier" size="11">/api/state</font>, <font face="Courier" size="11">/api/inspect</font>, <font face="Courier" size="11">/api/lab</font>, <font face="Courier" size="11">/api/job</font>, and <font face="Courier" size="11">/api/cancel</font>. Inspect is also what the settings page calls when it refreshes local Git status. The classic screen has its own routes for map, analyse, explore, and an HTML export. Those routes are not the guided export. The guided export is built in the browser.

<font face="Courier" size="11">main</font> parses the optional folder, the port, and the lab flag. It prints the local address and the statement that the program only listens on this computer and never runs the project code. It opens the browser unless asked not to.
''')
    h3(story, '4.3.5 The lab front end')
    prose(story, '''
The front end's public behaviour is the behaviour of the screens. The picker posts the folder, the two commits or neither, and the reverse flag. It renders the steps the job reports. A commit id under a step is a note about the step, not an extra step. Cancel posts the job id.

The workspace has Start, the review, the map, the file list, and Settings. The review tabs are what to check, changed code, related tests, limits and history, and recommendations. The reverse switch calls the picker again with the same chosen pair and the opposite flag. Export builds a JSON object or a CSV table from the review and downloads it. The integrations section states that hosted services are not connected.

The explore frame has three lenses. Physical groups by folder. Logical lays the nodes out by the recorded calls and does not pull them into folder clusters. Conceptual uses the experimental topic groups from <font face="Courier" size="11">concepts</font> in <font face="Courier" size="11">lab_data.py</font>, and the control is marked experimental. Search matches words in names, paths, comments, and code. The frame says the result is not an AI explanation.
''')

    chapter(story, 'Chapter 5. Implementation')
    h2(story, '5.1 How a Comparison Runs')
    prose(story, '''
A guided comparison runs in a fixed order. The person opens a folder. On a Mac, Browse asks the system for a folder. The server inspects a Git repository when the person is choosing versions: it checks that the path is a repository, reads HEAD, lists branches, tags, and recent commits, suggests source roots, and records whether the work tree is dirty. A repository with no commits is reported as such. A path that is not a repository can still be explored.

The person then chooses two commits, or neither, and answers whether to reverse. The server calls <font face="Courier" size="11">lab_direction</font>. That call is the only place the commits are swapped. The repository is not modified. A job starts on a background thread. For a comparison the page lists the steps check, map, analyse the older version, analyse the newer version, compare, find what could be affected, and prepare the screens. On a reversed run the reading steps name the newer version as the start and the older version as the end, because that is the direction the analysis now uses. Cancel sets an event. The next progress callback raises <font face="Courier" size="11">Cancelled</font>, the job is marked cancelled, and the page returns to the previous screen.

The map step calls <font face="Courier" size="11">analyze_repository</font> on the working folder. The comparison step calls <font face="Courier" size="11">analyze_change_impact</font>. That function resolves the two commits, writes each commit's Python files into a temporary directory, analyses each snapshot, detects changed definitions, reviews signatures, and asks the graph what each change reaches. It then builds the test plan. <font face="Courier" size="11">build_review</font> turns the report into the review, and it calls <font face="Courier" size="11">build_recommendations</font>. The payload is what the page renders. The temporary directory is removed when the comparison function returns.
''')
    h2(story, '5.2 Algorithm')
    prose(story, '''
The pipeline can be read as one procedure. The names are the functions in the repository.
''')
    for step in (
        'Inspect the folder if the person is choosing commits. Record the branch, the dirty flag, and the recent commits.',
        'Apply lab_direction(base, head, reverse). If reverse is true and both commits are present, swap them. Otherwise keep the pair.',
        'Report the check step, then map the working folder with analyze_repository.',
        'If either commit is missing, stop after the map. The explore path reports check, map, and finish.',
        'If both commits are present, call analyze_change_impact on the pair from step 2. Ignore the engine\'s own repeated check so the page does not show that step twice.',
        'Inside the comparison: snapshot each commit, detect changed definitions, query impact, select tests, and build a plan of at most 20 tests.',
        'Call build_review, which attaches build_recommendations(review).',
        'Mark the reversed flag and the original selection on the review, so the page can ask for the opposite direction without swapping twice.',
        'Return the payload to the browser. Do not write the repository.',
    ):
        bullet(story, step)
    prose(story, '''
In short form, the same procedure is this.
''')
    code(story, '''function guided_comparison(folder, base, head, reverse):
    base, head, reversed = lab_direction(base, head, reverse)
    working = analyze_repository(folder)
    review = none
    if base and head:
        impact = analyze_change_impact(folder, base, head)
        review, graph = build_review(impact, view, snapshots, folder)
        review.recommendations = the list just attached
        review.reversed = reversed
        review.selection = the pair the person chose
    return screens(working, review)''')
    h2(story, '5.3 Important Files and Short Excerpts')
    prose(story, '''
The files that carry the pipeline are <font face="Courier" size="11">repotrace/reading/analyzer.py</font>, <font face="Courier" size="11">repotrace/mapping/repository.py</font>, <font face="Courier" size="11">repotrace/graph/impact.py</font>, <font face="Courier" size="11">repotrace/changes/git_snapshot.py</font>, <font face="Courier" size="11">repotrace/changes/change_impact.py</font>, <font face="Courier" size="11">repotrace/report/lab_data.py</font>, <font face="Courier" size="11">repotrace/report/recommendations.py</font>, and <font face="Courier" size="11">repotrace/app/server.py</font>. The guided page is <font face="Courier" size="11">repotrace/report/lab/</font>.

One file is read here.
''')
    code(story, '''def analyze_file(filename, *, root=None, max_bytes=MAX_FILE_BYTES):
    """Read one file; root makes every file key relative to the project folder."""''')
    prose(story, '''
The comparison report appends this warning, which is kept as a sentence rather than softened.
''')
    prose(story, '''
<i>Review suggestions are potential places to inspect, not proof of breakage or safety.</i>
''')
    prose(story, '''
The recommendation entry is one function over one review.
''')
    code(story, '''def build_recommendations(review):
    """Build the recommendation list from one review. Does not mutate review."""''')
    prose(story, '''
The second line is the contract. The docstring in the source also says that the review is not mutated. The server assigns the returned list onto the review after the call. That assignment is in <font face="Courier" size="11">build_review</font>, not inside the recommendation function.
''')
    h2(story, '5.4 Testing')
    prose(story, '''
The repository contains a large unittest suite [9]. This report did not re-run the whole suite, so it does not state a new total. The README in this tree says 513 checks. The handbook of 15 November 2026 records 497 passing. An older line in the architecture note says 459. Those figures belong to the dates of those documents. They are not repeated here as a result of this report.

Two small runs were made on 23 November 2026 in this working tree. The first was the recommendation tests and three lab tests.
''')
    code(story, '''python3 -m unittest tests.test_recommendations
  tests.test_app.LabTests.test_the_direction_is_applied_in_exactly_one_place
  tests.test_app.LabTests.test_the_lab_job_never_changes_the_repository
  tests.test_app.LabTests.test_exploring_needs_no_second_version_and_no_git -v''')
    prose(story, '''
The result that was printed was: Ran 7 tests in 3.609s, OK. The seven names were <font face="Courier" size="11">test_a_gap_alone_is_not_advice_and_overflow_names_are_kept</font>, <font face="Courier" size="11">test_every_item_is_specific_complete_and_free_of_a_fake_score</font>, <font face="Courier" size="11">test_follow_up_searches_the_fields_and_does_not_invent_an_answer</font>, <font face="Courier" size="11">test_build_review_attaches_recommendations_from_the_comparison</font>, <font face="Courier" size="11">test_the_direction_is_applied_in_exactly_one_place</font>, <font face="Courier" size="11">test_the_lab_job_never_changes_the_repository</font>, and <font face="Courier" size="11">test_exploring_needs_no_second_version_and_no_git</font>.

The second run was the architecture file.
''')
    code(story, '''python3 -m unittest tests.test_architecture -v''')
    prose(story, '''
The result that was printed was: Ran 11 tests in 0.709s, OK. Those tests check that every package is a known layer, that a layer does not import a later layer, that nothing depends on evaluation, that the package does not import the tests, and that the guard itself fails when a forbidden import is planted, including an import between app and cli.
''')
    add_table(
        story,
        'Table 5.1 Checks run for this report',
        ['Command', 'Result seen'],
        [
            ['tests.test_recommendations and three LabTests, as named above', 'Ran 7 tests in 3.609s. OK.'],
            ['tests.test_architecture', 'Ran 11 tests in 0.709s. OK.'],
        ],
        (0.58, 0.42),
    )
    prose(story, '''
Other checks exist and were not part of these two runs. They are named so that the report does not treat them as passed. In <font face="Courier" size="11">tests/test_app.py</font> the remaining LabTests are <font face="Courier" size="11">test_the_page_and_its_files_are_served_safely</font>, <font face="Courier" size="11">test_a_comparison_comes_back_as_exactly_what_the_screens_read</font>, <font face="Courier" size="11">test_reversing_runs_the_same_two_commits_in_the_opposite_direction</font>, <font face="Courier" size="11">test_the_steps_are_reported_once_and_in_the_order_the_page_shows_them</font>, <font face="Courier" size="11">test_a_running_job_can_be_cancelled_and_says_so</font>, and <font face="Courier" size="11">test_bad_requests_get_clear_answers</font>. The file also holds MapTests, SecurityTests, and WorkflowTests.

<font face="Courier" size="11">tests/test_trust.py</font> holds the trust checks. InheritanceBinding checks that an external base is not linked to a same-named local class, that a name which is not imported is not guessed from another file, that a base in the same file is linked, that the import decides between two files with the same name, that aliases and re-exports are followed, and that a name which is both imported and defined is left unlinked. OwnershipBinding checks constructors, aliases, inner classes, and a class that was not imported. CompleteInventory checks that files, nested functions, and unreadable files are listed. HonestCoverage checks that a missing import is not counted as outside the project, that standard-library calls are counted as outside, and that a library which is not installed here is not confirmed as outside. SnapshotSource checks that the code on screen comes from the snapshot, and that each file carries a hash so a later edit can be noticed.

<font face="Courier" size="11">tests/test_recommendations.py</font> was run, as Table 5.1 says. The trust file was not run for this report.
''')
    h2(story, '5.5 Known Limits')
    prose(story, '''
The handbook's section 7 lists the weak spots as they stood when that note was written [3]. Table 5.2 copies them. One item in that section described an earlier state of the screens. The code in this tree, and section 2 of the same handbook, are what this report follows for that item.
''')
    add_table(
        story,
        'Table 5.2 Limits recorded in the handbook',
        ['Limit', 'What it means'],
        [
            ['Factories and containers', 'Objects built by a factory, a dependency container, or set from outside their class are not followed. The handbook names this as the reason Queuely and Shopkeep found few tests.'],
            ['A suggested test can pass', 'A path in the graph is not proof the test fails. An earlier check can stop the test before the changed line. The handbook\'s example is test_create_enrollment_rejects_missing_student.'],
            ['Import loop', 'Four modules in mapping import one another. The loop was left in place on purpose.'],
            ['Conceptual view', 'The topic view is rough. The handbook notes one topic that held 33 of 72 files. The view stays marked experimental.'],
            ['Live screens', 'Section 7 said the new design was not connected to live analysis. Section 2 of the handbook records the guided screens as live on 16 November 2026. In this tree, python3 -m repotrace --lab runs that live path.'],
            ['Pytest for measurement', 'pytest 8.3.3, used when measuring pytest projects, lived only in a throwaway environment, not in the repository.'],
        ],
        (0.28, 0.72),
    )
    prose(story, '''
Two further limits are written in the program itself. The signature check covers explicit calls to plain functions. Methods, decorated targets, constructors, and calls that use star-args are not checked, and the review says that no findings does not settle the question. The test plan stops at 20 tests. Connected tests beyond that cap remain in the per-change evidence and are counted on the screen.

The explore screen still contains a sentence about an optional summary that would cite the matched lines. No language model is called. The sentence should be read as a description of something that is not in the program.
''')
    h2(story, '5.6 Measurements Copied from the Notes')
    prose(story, '''
This section does not add a new accuracy figure. The numbers below are copied from the project handbook [3] and from the tinydb evaluation note [8]. Both notes say the figures were measured. They were not measured again for this report. Coverage is not the same thing as accuracy. A quiet cell is not a claim about the change.

The handbook's practice projects are Shopkeep, Ledgerly, Queuely, and StudentManagement. Those folders are not in this repository. The handbook says the arrows were scored against a recorded run.
''')
    add_table(
        story,
        'Table 5.3 Measurements copied from the handbook',
        ['What was measured', 'Figure copied from the handbook'],
        [
            ['Confident arrows, right where the run passed that line', '138 of 138, and 156 of 156'],
            ['Uncertain arrows, same condition', '128 of 128, and 399 of 400'],
            ['Real calls found', '32.7 percent on Shopkeep, and 44.8 percent on Ledgerly'],
            ['StudentManagement, calls that could be the project\'s own code', 'About 25 percent sure, 59 percent maybe, and 15 percent not traced'],
            ['Queuely, traced', '35 percent'],
            ['Shopkeep, traced', 'About a third'],
            ['StudentManagement test shortlist', '78 of 78 relevant tests found. Suggestions about 94 percent right. The 8 tests that break at step-07 were all found.'],
            ['Ledgerly test shortlist, measured once, untuned', '45 of 157 relevant (29 percent). 45 of 46 suggestions right (98 percent).'],
            ['Queuely, before the fixture work', '4 of 128 relevant. 4 of 5 suggestions right.'],
            ['Shopkeep, before the fixture work', '0 of 72. None suggested.'],
        ],
        (0.40, 0.60),
    )
    prose(story, '''
The handbook's reading of the shortlist is that a test it names is often connected for real, and that on the larger pytest projects it still misses most of the relevant tests. It also says the fixture work was tested and added no measured gain on those projects, because other patterns block them first. Failing-test truth, in that note, exists only on StudentManagement.

The tinydb note is the first full evaluation on a project the authors did not write. The note says tinydb was scored once, untuned, at one commit, over 30 commit pairs for the shortlist. It names <font face="Courier" size="11">TinyDB.__getattr__</font>, which forwards calls dynamically, as the main cause of the misses.
''')
    add_table(
        story,
        'Table 5.4 Measurements copied from the tinydb note',
        ['What was measured', 'Figure copied from the note'],
        [
            ['Sure arrows, where the line ran', '150 of 151'],
            ['Maybe arrows, where the line ran', '207 of 207'],
            ['Real calls in tinydb\'s own code, any arrow', '63.3 percent'],
            ['Real calls in tinydb\'s own code, sure or maybe', '37.6 percent'],
            ['Suggested tests that really execute the change', '119 of 119'],
            ['Relevant tests found, over 30 commit pairs', '119 of 1,243 (9.6 percent)'],
            ['Tests that went from pass to fail', '0 in those 30 pairs. That part was not measured.'],
        ],
        (0.46, 0.54),
    )
    prose(story, '''
The plain reading, which both notes already give, is the one this report keeps. When the shortlist names a test, the measurement often agrees that the test executes the changed function. The shortlist still misses most relevant tests on the projects where the calls are dynamic. The screen is required to show the untraced calls and the size of the list it did not print. This report does not turn either table into a new percentage.
''')

    chapter(story, 'References')
    prose(story, '''
The references are numbered in the order they are first used in the report. Web pages were used as the documentation of the tools the program actually calls.
''', 'ref')
    for ref in (
        '[1] Git community, "Git Documentation." [Online]. Available: https://git-scm.com/doc. [Accessed: Nov. 23, 2026].',
        '[2] Python Software Foundation, "ast - Abstract Syntax Trees," Python 3 documentation. [Online]. Available: https://docs.python.org/3/library/ast.html. [Accessed: Nov. 23, 2026].',
        '[3] H. Mesfin, I. Hayalsew, J. Hussien, and K. Tsegaye, "RepoTrace project handbook," unpublished project note, Nov. 15, 2026.',
        '[4] HiLCoE, School of Computer Science and Technology, "Senior Project Documentation Guideline," version 1.4.3, 2024.',
        '[5] H. Mesfin, I. Hayalsew, J. Hussien, and K. Tsegaye, "RepoTrace user manual," senior project user manual, Nov. 2026. Available in the project as docs/RepoTrace_User_Manual.pdf.',
        '[6] RepoTrace team, "How RepoTrace is built," unpublished project note, docs/ARCHITECTURE.md, 2026.',
        '[7] Python Software Foundation, "http.server - HTTP servers," Python 3 documentation. [Online]. Available: https://docs.python.org/3/library/http.server.html. [Accessed: Nov. 23, 2026].',
        '[8] H. Mesfin, I. Hayalsew, J. Hussien, and K. Tsegaye, "RepoTrace on a project we did not write: tinydb," unpublished evaluation note, Nov. 18, 2026.',
        '[9] Python Software Foundation, "unittest - Unit testing framework," Python 3 documentation. [Online]. Available: https://docs.python.org/3/library/unittest.html. [Accessed: Nov. 23, 2026].',
    ):
        story.append(P(ref.replace('&', '&amp;'), 'ref'))

    chapter(story, 'Annex A. User Manual')
    prose(story, '''
This annex is the user manual in a shorter form, as the final report requires [4]. The full manual, with the same install steps, the same error table, and the same help frames, is <font face="Courier" size="11">docs/RepoTrace_User_Manual.pdf</font> [5]. This annex does not redraw that manual with screenshots. It tells a person how to install the system, how to use it, what the screens say when something cannot be done, and where the help already sits.
''')
    h2(story, 'A.1 What is required, and how to start')
    prose(story, '''
The computer needs Python 3.9 or newer and, for a comparison, Git. No other package is installed. The RepoTrace folder is the folder that contains the <font face="Courier" size="11">repotrace</font> directory and <font face="Courier" size="11">RepoTrace.command</font>.
''')
    add_table(
        story,
        'Table A.1 How to start',
        ['Action', 'What opens'],
        [
            ['python3 -m repotrace --lab', 'The guided screens. This annex describes these screens.'],
            ['python3 -m repotrace --lab "/path/to/project"', 'The same screens, with the path already filled in.'],
            ['python3 -m repotrace', 'The earlier screen.'],
            ['Double-click RepoTrace.command', 'The earlier screen. The command file does not pass --lab.'],
            ['Ctrl+C in the terminal', 'Stops the program. Closing the browser does not stop it.'],
        ],
        (0.46, 0.54),
    )
    prose(story, '''
The address looks like <font face="Courier" size="11">http://127.0.0.1:58510/lab</font>. The port can differ each time. Use the address the terminal prints. An old address belongs to an old run.
''')
    h2(story, 'A.2 Open a project and choose versions')
    prose(story, '''
Type a folder path, or press Browse on a Mac, and press Open. Folders opened before are listed under the form. Explore without comparing reads the working folder and does not ask for two versions. Use it when the folder has no Git history, or when the map is enough.

When the folder has at least two commits, Choose what to compare shows an older version and a newer version. Only explore the map turns the comparison off. Analyse starts it. The two versions must be different. Unsaved edits are not part of the comparison. The map of the working folder can still show them, and the version line says so when the work tree is dirty. The snapshot is the reading. The program does not watch the folder. Open the project again after an edit.
''')
    h2(story, 'A.3 Reverse, progress, and cancel')
    prose(story, '''
Reverse this change has the answers No and Yes. No reads from the older version to the newer version. Yes reads the same two versions from the newer one back to the older one. Lines the later version added are then shown as removed, and lines it removed are shown as added. The sentence under the control states the direction before Analyse is pressed. The repository is not modified.

After a review is open, the switch Reverse this change asks for the same pair again with the opposite answer. A banner states when the review on screen is the reversed one.

While the system reads, one list is highlighted from top to bottom. The steps are check the project, map the working folder, read the older version, read the newer version, compare, find what could be affected, and prepare the screens. On a reversed run the reading steps name the newer version as the start. A commit identifier under a step is a note, not another step. Cancel stops at the end of the step that is running and returns to the previous screen.
''')
    h2(story, 'A.4 The workspace and the review')
    prose(story, '''
The workspace has Start, Check a change, Explore the project, File list, and Settings. On a narrow window they sit along the bottom. Back, or Alt together with the Left arrow, returns to the previous view. Find code, or Command+K on a Mac and Ctrl+K elsewhere, opens search. The slash key does the same when the cursor is not in a field.

The review title is the commit message of the change being read. The counts are definitions changed, places to inspect, and tests listed. A count of zero connected tests is marked, because a missing test is a gap in the report. What to check lists the places the comparison flagged. Changed code lists each changed definition. A removed definition is shown from the older version. Related tests lists tests connected by recorded calls, including unittest setUp hooks. A path that can be followed only in the older version is reported as lost. A command beside a test is copied. It is not executed. The list is a starting point. Tests outside the list are counted. Limits and history states what the review cannot establish. History is a correlation between files edited in the same commits. It is not a call, and it is not a prediction.
''')
    h2(story, 'A.5 Recommendations, the map, and settings')
    prose(story, '''
Recommendations are the items built from this review. Level 1 is immediate. Level 2 is a history correlation. Level 3 is not shown, because there is no probability model. Level 4 is at most one choice between actions the review already lists. Confidence is high, medium, or low. There is no numeric score. Save, Mark completed, and Dismiss stay in this browser for this folder and this pair. Ask a follow-up searches the words of these items and says that the search is not an AI answer. If no item met the rules, the list is left empty.

Explore opens the map. Physical groups the code by folder. Logical groups it by recorded calls. Conceptual is marked experimental. Its topics are guessed from calls and from common words, and they are often wrong. Sure links, maybe links, and test code can be shown or hidden. Review a change marks what the current comparison changed. Search matches words. It is not an AI answer. File list opens folders, then files, then functions. A missing connection is recorded as missing.

Settings offers twelve themes. Pointing at a card previews it. Clicking saves it on this computer. Integrations shows the only Git connection, which is the folder that was opened. Refresh local Git reads the branch, the dirty flag, HEAD, and the recent commit count again. Export review JSON and Export review CSV download the review already on screen. The file is built in the browser. GitHub, GitLab, Bitbucket, Slack, and the other hosted services named on that screen are not connected.
''')
    h2(story, 'A.6 Errors and help')
    prose(story, '''
The system reports a problem on the page that was in use. It does not send the message anywhere else. Table A.2 is the short list. The full manual's table is the longer form of the same list [5].
''')
    add_table(
        story,
        'Table A.2 What the screen reports',
        ['Situation', 'What to do'],
        [
            ['The folder path is empty or cannot be opened', 'Type a folder that exists on this computer, or use Browse.'],
            ['The same commit is chosen twice', 'Pick another version, or explore the map only.'],
            ['The analysis cannot finish', 'Read the message, then start again from Open a project.'],
            ['The person stops a read', 'No repair is required. The repository was not changed.'],
            ['The folder is not a Git repository', 'Explore without comparing. A comparison needs saved commits.'],
            ['There is no review to export', 'Run a comparison first.'],
            ['A test command cannot be copied', 'Select the command on the page and copy it.'],
            ['A screen cannot be drawn', 'Use Back, or go to Start. The project was not changed.'],
            ['A comparison cannot be reversed from this page', 'Open a live review that still has the chosen pair.'],
        ],
        (0.48, 0.52),
    )
    prose(story, '''
Help is on the screens. There is no separate help site. The dialog opened from the status line explains that a sure link is written in the code, that a maybe link depends on an assumption, that commands are copied and are not executed, and that a missing link is not proof of anything about the change. The sentence under Reverse states the direction and that Git will not be modified. The reversed banner repeats that the repository was not changed. The note on Recommendations explains the levels and that dismiss, save, and completed stay in this browser. The conceptual control is marked experimental. The last paragraph of Integrations states that hosted services are not connected.

The marks on the screen are the grades from Chapter 4, plus a few that belong only to a comparison. Old version only means the link was recorded in the older version and not in the newer one. A plus at the start of a diff line is added text, and a minus is removed text. Connected only before is a test path that can be followed in the older version and not in the newer one. Untraced calls are calls inside a changed definition that could not be followed. When a page is quiet, read Limits and history before deciding what to do next. Then run the tests that were chosen. RepoTrace does not run them.
''')

    chapter(story, 'Annex B. Milestone Sheet')
    prose(story, '''
Project title. RepoTrace: A Local System for Exploring Python Code and Reviewing the Impact of a Change.
''', 'mile')
    prose(story, 'Team. Hana Mesfin, Israel Hayalsew, Jaffer Hussien, Kal Tsegaye.', 'mile')
    prose(story, 'Advisor. Dr. Hassen.', 'mile')
    prose(story, 'Report. Senior Project Final Report. November 2026.', 'mile')
    story.append(P('Tasks accomplished', 'mileb'))
    for item in (
        'The engine: read Python with ast, build a graded call map, and compare two Git versions without running the project.',
        'The guided lab: open a local folder, explore without Git, and review a comparison on 127.0.0.1.',
        'Reverse comparison: swap the two commits in the analysis only, and leave the repository unchanged.',
        'Recommendations drawn from the review, with no probability model and no language model.',
        'The user manual, attached as Annex A, with the full manual kept as docs/RepoTrace_User_Manual.pdf.',
    ):
        bullet(story, item)
    story.append(Spacer(1, 14))
    story.append(P('Signatures', 'mileb'))
    story.append(SignRow('Advisor:', 'Signature:'))
    story.append(SignRow('Examiner:', 'Signature:'))
    story.append(Spacer(1, 8))
    story.append(SignRow('Team:', 'Signature:'))


def make_frame():
    return Frame(MARGIN, MARGIN, CONTENT_W, CONTENT_H, id='main', showBoundary=0)


def check(path, body_first):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or '') for page in reader.pages]
    print('pages', len(pages), 'body_first', body_first)
    cover = pages[0]
    if 'SENIOR PROJECT FINAL DOCUMENT' not in cover:
        raise SystemExit('Cover is missing SENIOR PROJECT FINAL DOCUMENT')
    if 'PROPOSAL' in cover.upper():
        raise SystemExit('Cover mentions a proposal')
    if 'USER MANUAL' in cover.upper():
        raise SystemExit('Cover mentions a user manual')
    exec_pages = [i for i, text in enumerate(pages) if 'The hard part is what a static reading' in text]
    if len(exec_pages) != 1:
        raise SystemExit('Executive summary body appears on %s pages' % len(exec_pages))
    if 'Executive Summary' not in pages[exec_pages[0]][:500]:
        raise SystemExit('Executive summary body is not on its heading page')
    nxt = pages[exec_pages[0] + 1]
    if 'Chapter 1' not in nxt[:800]:
        raise SystemExit('The page after the executive summary does not start Chapter 1')
    last = pages[-1]
    if 'Annex B' not in last or 'Milestone' not in last:
        raise SystemExit('The last page is not the milestone sheet')
    for index, text in enumerate(pages, 1):
        if len(text.strip()) < 40:
            print('SHORT PAGE', index, repr(text[:120]))
    print('cover ok, exec on page', exec_pages[0] + 1, 'chapter 1 on', exec_pages[0] + 2)


def main():
    story = []
    assemble(story)
    doc = Report(
        str(OUT),
        pagesize=A4,
        title='RepoTrace Senior Project Final Report',
        author='Hana Mesfin, Israel Hayalsew, Jaffer Hussien, Kal Tsegaye',
    )
    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[make_frame()], onPage=on_blank),
        PageTemplate(id='front', frames=[make_frame()], onPage=on_blank),
        PageTemplate(id='body', frames=[make_frame()], onPage=on_body),
    ])
    passes = doc.multiBuild(story)
    print('passes', passes, 'physical_pages', doc.page, 'body_first', doc.body_first)
    COPY_TO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT, COPY_TO)
    print(OUT)
    print(COPY_TO)
    check(OUT, doc.body_first)


if __name__ == '__main__':
    main()
