"""Build the HiLCoE user-manual PDF.

A4, 1 inch margins, Times New Roman 12 pt, 1.5 line spacing.
Page numbers start at the introduction and sit at the bottom centre.
"""
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Preformatted, Spacer, Table, TableStyle, KeepTogether,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'RepoTrace_User_Manual.pdf'
SUP = Path('/System/Library/Fonts/Supplemental')
LIB = Path('/Library/Fonts')
USER = Path.home() / 'Library' / 'Fonts'


def find_font(*names):
    for base in (SUP, LIB, USER, Path('/System/Library/Fonts')):
        for name in names:
            path = base / name
            if path.exists():
                return str(path)
    return None


def register():
    pairs = {
        'TNR': ['Times New Roman.ttf', 'Times.ttf'],
        'TNR-B': ['Times New Roman Bold.ttf', 'Times Bold.ttf'],
        'TNR-I': ['Times New Roman Italic.ttf', 'Times Italic.ttf'],
        'TNR-BI': ['Times New Roman Bold Italic.ttf', 'Times Bold Italic.ttf'],
        'Cal': ['Calibri.ttf'],
        'Cal-B': ['Calibri Bold.ttf'],
        'Cooper': ['CooperBlack.ttf', 'Cooper Black.ttf'],
        'Cour': ['Courier New.ttf'],
        'Cour-B': ['Courier New Bold.ttf'],
    }
    found = {key: find_font(*names) for key, names in pairs.items()}
    if found['TNR'] and found['TNR-B']:
        pdfmetrics.registerFont(TTFont('TNR', found['TNR']))
        pdfmetrics.registerFont(TTFont('TNR-B', found['TNR-B']))
        if found['TNR-I']:
            pdfmetrics.registerFont(TTFont('TNR-I', found['TNR-I']))
        if found['TNR-BI']:
            pdfmetrics.registerFont(TTFont('TNR-BI', found['TNR-BI']))
        body, bold, italic = 'TNR', 'TNR-B', 'TNR-I' if found['TNR-I'] else 'TNR'
    else:
        body, bold, italic = 'Times-Roman', 'Times-Bold', 'Times-Italic'
    if found['Cal'] and found['Cal-B']:
        pdfmetrics.registerFont(TTFont('Cal', found['Cal']))
        pdfmetrics.registerFont(TTFont('Cal-B', found['Cal-B']))
        cover, cover_b = 'Cal', 'Cal-B'
    else:
        cover, cover_b = body, bold
    if found['Cooper']:
        pdfmetrics.registerFont(TTFont('Cooper', found['Cooper']))
        school = 'Cooper'
    else:
        school = cover_b
    if found['Cour']:
        pdfmetrics.registerFont(TTFont('Cour', found['Cour']))
        mono = 'Cour'
    else:
        mono = 'Courier'
    return body, bold, italic, cover, cover_b, school, mono


BODY, BOLD, ITAL, COVER, COVER_B, SCHOOL, MONO = register()
INK = colors.HexColor('#1c1915')
MUTED = colors.HexColor('#5c564c')
RULE = colors.HexColor('#0c6b52')
RULE_SOFT = colors.HexColor('#e5f4ee')
LINE = colors.HexColor('#d9d1c5')
PAPER = colors.HexColor('#f7f4ee')
W, H = A4
MARGIN = 1 * inch

S = {
    'school': ParagraphStyle('school', fontName=SCHOOL, fontSize=14, leading=18, alignment=TA_CENTER, textColor=INK),
    'cover': ParagraphStyle('cover', fontName=COVER_B, fontSize=16, leading=22, alignment=TA_CENTER, textColor=INK),
    'h1': ParagraphStyle('h1', fontName=BOLD, fontSize=15, leading=22, textColor=INK, spaceBefore=14, spaceAfter=8, borderPadding=0),
    'h2': ParagraphStyle('h2', fontName=BOLD, fontSize=14, leading=21, textColor=INK, spaceBefore=12, spaceAfter=6),
    'body': ParagraphStyle('body', fontName=BODY, fontSize=12, leading=18, alignment=TA_JUSTIFY, textColor=INK, spaceAfter=8),
    'toc': ParagraphStyle('toc', fontName=BODY, fontSize=12, leading=18, textColor=INK, spaceAfter=1),
    'toc2': ParagraphStyle('toc2', fontName=BODY, fontSize=12, leading=18, textColor=INK, leftIndent=16, spaceAfter=1),
    'cap': ParagraphStyle('cap', fontName=ITAL if ITAL != BODY else BODY, fontSize=12, leading=16, textColor=INK, spaceBefore=8, spaceAfter=4),
    'cell': ParagraphStyle('cell', fontName=BODY, fontSize=11, leading=15, textColor=INK),
    'cellb': ParagraphStyle('cellb', fontName=BOLD, fontSize=11, leading=15, textColor=colors.HexColor('#083d30')),
    'code': ParagraphStyle('code', fontName=MONO, fontSize=11, leading=15, textColor=INK, leftIndent=8),
    'ref': ParagraphStyle('ref', fontName=BODY, fontSize=12, leading=18, alignment=TA_LEFT, textColor=INK, spaceAfter=8, firstLineIndent=-18, leftIndent=18),
}


def P(text, style='body'):
    return Paragraph(text, S[style])


def rule():
    data = [['']]
    t = Table(data, colWidths=[W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 1.25, RULE),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


def code(text):
    block = Table([[Preformatted(text, S['code'])]], colWidths=[W - 2 * MARGIN - 8])
    block.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PAPER),
        ('BOX', (0, 0), (-1, -1), 0.4, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return KeepTogether([Spacer(1, 4), block, Spacer(1, 8)])


def table(caption, header, rows, widths):
    head = [Paragraph(c, S['cellb']) for c in header]
    body = [[Paragraph(c, S['cell']) for c in row] for row in rows]
    col = [w * (W - 2 * MARGIN) for w in widths]
    t = Table([head] + body, colWidths=col, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), RULE_SOFT),
        ('LINEBELOW', (0, 0), (-1, 0), 1, RULE),
        ('LINEBELOW', (0, 1), (-1, -2), 0.3, LINE),
        ('LINEBELOW', (0, -1), (-1, -1), 0.6, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return KeepTogether([P(caption, 'cap'), t, Spacer(1, 8)])


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(2)
    canvas.line(MARGIN, H - 0.72 * inch, W - MARGIN, H - 0.72 * inch)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 0.72 * inch, W - MARGIN, 0.72 * inch)
    canvas.setFillColor(RULE)
    canvas.setFont(BODY, 9)
    canvas.drawCentredString(W / 2, 0.48 * inch, 'Annex to the final project report')
    canvas.restoreState()


def contents_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(1)
    canvas.line(MARGIN, H - 0.62 * inch, W - MARGIN, H - 0.62 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont(BODY, 9)
    canvas.drawString(MARGIN, H - 0.48 * inch, 'RepoTrace')
    canvas.drawRightString(W - MARGIN, H - 0.48 * inch, 'User manual')
    canvas.restoreState()


def body_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(1)
    canvas.line(MARGIN, H - 0.62 * inch, W - MARGIN, H - 0.62 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont(BODY, 9)
    canvas.drawString(MARGIN, H - 0.48 * inch, 'RepoTrace')
    canvas.drawRightString(W - MARGIN, H - 0.48 * inch, 'User manual')
    canvas.setFillColor(INK)
    canvas.setFont(BODY, 12)
    canvas.drawCentredString(W / 2, 0.55 * inch, str(doc.page - 2))
    canvas.restoreState()


def story():
    s = []
    s += [Spacer(1, 1.55 * inch)]
    s += [P('HiLCoE', 'school'), Spacer(1, 6)]
    s += [P('School of Computer Science and Technology', 'cover')]
    s += [Spacer(1, 28)]
    s += [P('REPOTRACE: A LOCAL SYSTEM FOR EXPLORING PYTHON CODE AND REVIEWING THE IMPACT OF A CHANGE', 'cover')]
    s += [Spacer(1, 22)]
    s += [P('SENIOR PROJECT USER MANUAL', 'cover')]
    s += [Spacer(1, 28)]
    s += [P('Prepared by:', 'cover')]
    for name in ('HANA MESFIN', 'ISRAEL HAYALSEW', 'JAFFER HUSSIEN', 'KAL TSEGAYE'):
        s += [P(name, 'cover')]
    s += [Spacer(1, 22)]
    s += [P('NOVEMBER 2026', 'cover')]
    s += [NextPageTemplate('contents'), PageBreak()]

    s += [P('Contents', 'h1'), rule()]
    for line, style in (
        ('1. Introduction', 'toc'),
        ('2. Installation and starting the system', 'toc'),
        ('2.1 What is required', 'toc2'),
        ('2.2 Starting the guided screens', 'toc2'),
        ('2.3 Stopping the system', 'toc2'),
        ('2.4 The earlier screen', 'toc2'),
        ('3. Using the system', 'toc'),
        ('3.1 Open a project', 'toc2'),
        ('3.2 Choose two versions', 'toc2'),
        ('3.3 Reverse a comparison', 'toc2'),
        ('3.4 While the system reads', 'toc2'),
        ('3.5 The workspace', 'toc2'),
        ('3.6 Check a change', 'toc2'),
        ('3.7 Recommendations', 'toc2'),
        ('3.8 Explore the project', 'toc2'),
        ('3.9 Files, search, and the keyboard', 'toc2'),
        ('3.10 Settings, export, and running again', 'toc2'),
        ('4. Error handling and reporting', 'toc'),
        ('5. Help frames', 'toc'),
        ('6. How to read the results', 'toc'),
        ('References', 'toc'),
    ):
        s.append(P(line, style))
    s += [Spacer(1, 12), P('This manual is the user-manual deliverable of the senior project. In the final project report it is attached as an annex, as required by the school documentation guideline [1].')]
    s += [NextPageTemplate('body'), PageBreak()]

    s += [P('1. Introduction', 'h1'), rule()]
    s += [P('This manual explains how an end user installs RepoTrace and uses it. RepoTrace is a local system for a Python project. It reads the source and, when the folder is a Git repository, the saved history. It shows where code lives, which functions call which, what a chosen change could affect, and which existing tests are connected to that change.')]
    s += [P('The system does not upload the project, does not edit the repository, and does not run the project code or its tests. A result that lists nothing found is a report that nothing was found. It is not a statement that a change is safe.')]
    s += [P('The manual is written for a person who has a project folder on their own computer and wants to open it, compare two versions, and read the review. It covers installation, the order of use, the messages shown when something cannot be done, and the help already placed on the screens.')]

    s += [P('2. Installation and starting the system', 'h1'), rule()]
    s += [P('2.1 What is required', 'h2')]
    s += [P('The computer needs Python 3.9 or newer [2]. Git is required only when two versions are compared [3]. No other package is installed. The RepoTrace folder is the folder that contains the <font face="%s">repotrace</font> directory and the file <font face="%s">RepoTrace.command</font>.' % (MONO, MONO))]
    s += [P('2.2 Starting the guided screens', 'h2')]
    s += [P('The guided screens are the screens this manual describes. Open a terminal, move into the RepoTrace folder, and run the following command.')]
    s += [code('python3 -m repotrace --lab')]
    s += [P('The browser opens a page on this computer only. The address looks like <font face="%s">http://127.0.0.1:58510/lab</font>. The port can differ each time the system starts. The first screen is Open a project. To place a folder in the path box before the page opens, pass the folder on the command.' % MONO)]
    s += [code('python3 -m repotrace --lab "/path/to/your/project"')]
    s += [P('2.3 Stopping the system', 'h2')]
    s += [P('Leave the terminal window open while the browser is in use. Press Ctrl+C in that terminal, or close the terminal, to stop RepoTrace. Closing the browser page stops the person from reading the result. The program itself stops when the terminal is stopped.')]
    s += [P('2.4 The earlier screen', 'h2')]
    s += [P('Double-clicking <font face="%s">RepoTrace.command</font>, or running <font face="%s">python3 -m repotrace</font> with no flag, opens the earlier screen rather than the guided screens. That screen has its own example gallery, described in the project guide. Use the flag <font face="%s">--lab</font> when the guided screens are wanted.' % (MONO, MONO, MONO))]

    s += [P('3. Using the system', 'h1'), rule()]
    s += [P('3.1 Open a project', 'h2')]
    s += [P('Type the path of a folder that contains Python files, or press <b>Browse</b> on a Mac, and then press <b>Open</b>. Folders opened before are listed under the form and can be opened from those cards. <b>Explore without comparing</b> reads the working folder and does not ask for two versions. Use it when the folder has no Git history, or when the map of the current files is enough. Git is required only for a comparison of two saved versions.')]
    s += [P('The map and the source on screen are the snapshot that was read. If files are edited after that, open the project again. RepoTrace does not watch the folder.')]
    s += [P('3.2 Choose two versions', 'h2')]
    s += [P('When the folder is a Git repository and at least two commits are found, the next screen is <b>Choose what to compare</b>. Two menus are shown.')]
    s += [table('Table 1. The two version menus', ['Menu', 'Meaning when Reverse is No'], [
        ['Older version, marked Start', 'The version before the change.'],
        ['Newer version, marked End', 'The version after the change.'],
    ], [0.46, 0.54])]
    s += [P('<b>Only explore the map</b> turns the comparison off. <b>Analyse</b> starts the comparison. The two chosen versions must be different. Unsaved edits in the working folder are not part of the comparison. The map can still show the working folder. The comparison uses saved commits only.')]
    s += [P('3.3 Reverse a comparison', 'h2')]
    s += [P('Under the two menus, <b>Reverse this change?</b> has the answers <b>No</b> and <b>Yes</b>. No reads from the older version to the newer version, which is the direction in which the change was made. Yes reads the same two versions in the opposite direction, from the newer version to the older version. Lines that the later version added are then shown as removed, and lines it removed are shown as added. The sentence under the control states the direction before <b>Analyse</b> is pressed. The round swap button switches between No and Yes. The Git repository is not modified.')]
    s += [P('After a review is open, the switch <b>Reverse this change</b> asks for the same pair again with the opposite answer. A banner states when the review on screen is the reversed one. Turning the switch again returns to the first direction. Each direction is a new read of the same two commits.')]
    s += [P('3.4 While the system reads', 'h2')]
    s += [P('The page keeps one list and moves the highlight down it. The steps are: check the project; map the working folder; read the older version; read the newer version; compare the two versions; find what could be affected; prepare the screens. On a reversed run, the reading steps name the newer version as the start and the older version as the end. A commit identifier under a step is a note about the step that is running. It is not another step. The clock shows the time elapsed. A finished step shows how long it took. <b>Cancel</b> stops at the end of the step that is running and returns to the previous screen. Nothing in the repository is changed.')]
    s += [P('3.5 The workspace', 'h2')]
    s += [P('After the read finishes, the workspace has five sections. On a wide window they are listed on the left. On a phone they are a bar along the bottom: Start, Review, Map, Files, and Settings.')]
    s += [table('Table 2. Workspace sections', ['Section', 'Use'], [
        ['Start', 'The comparison in one paragraph, the counts, and the ways into the review, the tests, and the map.'],
        ['Check a change', 'The review. When only one comparison was run, this opens that review.'],
        ['Explore the project', 'The map of folders, files, functions, and recorded calls.'],
        ['File list', 'The same project as folders, then files, then functions, without the graph.'],
        ['Settings', 'Appearance, local Git status, export, and running the comparison again.'],
    ], [0.32, 0.68])]
    s += [P('<b>Back</b>, or Alt together with the Left arrow, returns to the previous view. <b>Find code</b>, or Command+K on a Mac and Ctrl+K on Windows and Linux, opens search. The forward-slash key does the same when the cursor is not in a text field.')]
    s += [P('3.6 Check a change', 'h2')]
    s += [P('The title of the review is the commit message of the change being read. Start and End name the two versions in the direction of this run. The counts are definitions changed, places to inspect, and tests listed. A count of zero connected tests is marked, because a missing test is a gap in the report. <b>Run this comparison again</b> repeats the saved pair on this computer. It does not change Git and it does not run tests.')]
    s += [P('<b>What to check</b> lists the places the comparison flagged, with the line that made each one matter. A comparison can also have changed definitions and no flagged concern. The absence of a flag is not a statement that the change is safe to merge.')]
    s += [P('<b>Changed code</b> lists each changed definition. A line that begins with a plus sign was added. A line that begins with a minus sign was removed. Colour is a second mark, not the only mark. A removed definition is shown from the older version. A rename pairing is evidence from the comparison. It is not a guarantee that the behaviour is unchanged.')]
    s += [P('<b>Related tests</b> lists tests connected to the change by following recorded calls, including unittest setUp hooks. A test connected before the change and not followable after it is reported as a path that was lost. A test that reaches the code only through a pytest fixture can be missing, because those fixtures are not all followed. The command beside a test is copied. It is not executed. The list is a starting point. Tests that sit outside the list are counted. Their absence from the short list is not permission to skip the rest of the suite.')]
    s += [P('<b>Limits and history</b> states what this review cannot establish. History lists files that were edited in the same commits as a changed file. That is a correlation. It is not a call, and it is not a prediction that the files must change together.')]
    s += [P('3.7 Recommendations', 'h2')]
    s += [P('The Recommendations tab reads the review that is already on screen. Each item names a definition, a file, or a test, and gives the recommendation, the reasoning, the evidence, the expected impact, a priority, a confidence, how to carry it out, what is required first, the risks, and a next action.')]
    s += [table('Table 3. Recommendation levels', ['Level', 'Meaning'], [
        ['1, Immediate', 'A concern, a test whose path exists only in the older version, a removed test, or a changed definition with no connected test.'],
        ['2, Analytical', 'Files edited together in the saved history. This is correlation, not a cause.'],
        ['3, Predictive', 'Not shown. The system has no probability model, so it does not invent a forecast.'],
        ['4, Strategic', 'At most one choice between two actions the review already lists.'],
    ], [0.28, 0.72])]
    s += [P('Confidence is high when the link is written in the source, medium when one step is an assumption, and low when the only support is history. There is no numeric score. <b>Evidence</b>, <b>Explain</b>, and <b>Action plan</b> open those fields. The main button follows the next action: another tab of the review, the function on the map, or a copied test command. <b>Compare</b> places two items side by side. <b>Save</b>, <b>Mark completed</b>, and <b>Dismiss</b> are stored in this browser for this folder and this pair of versions. They are not uploaded. <b>Show dismissed</b> brings hidden items back. <b>Ask a follow-up</b> searches the words of these items. The page states that the search is not an AI answer. If no words match, the page says so. If no item met the evidence rules, the list is left empty.')]
    s += [P('3.8 Explore the project', 'h2')]
    s += [P('Explore opens the map. On a wide window the controls, the graph, and the detail sit side by side. When the window is too narrow for three columns, the detail moves under the graph. On a phone the regions stack. <b>Physical</b> groups the code by folder. <b>Logical</b> groups it by recorded calls. <b>Conceptual</b> is marked experimental. Its topics are guessed from calls and from common words, and they are often wrong. Treat that view as a guess.')]
    s += [P('Sure links, maybe links, and test code can be shown or hidden. Test code stays hidden until it is requested. Click a name to read it. The lists beside the graph carry the same connections, so the picture is not the only way through. <b>Explore</b> walks the working folder. <b>Review a change</b> marks what the current comparison changed. Search matches words in names, paths, comments, and code. It is not an AI answer.')]
    s += [P('3.9 Files, search, and the keyboard', 'h2')]
    s += [P('File list opens folders, then files, then the functions in a file. A function page shows its source, what calls it, and what it calls. <b>Possible links</b> and <b>Test code</b> filter that page. A missing connection is recorded as missing. It is not proof that nothing calls the function.')]
    s += [table('Table 4. Keyboard', ['Key', 'Action'], [
        ['Command+K, or Ctrl+K', 'Find code'],
        ['/, when not typing in a field', 'Find code'],
        ['Alt+Left arrow', 'Back'],
        ['Esc', 'Leave a field, then go back'],
    ], [0.48, 0.52])]
    s += [P('3.10 Settings, export, and running again', 'h2')]
    s += [P('Appearance offers twelve editor themes. Pointing at a card previews it. Clicking a card saves it on this computer for the next time the page opens. GitHub Light and Solarized Light are the light themes. The others are dark.')]
    s += [P('Integrations shows the only Git connection, which is the folder that was opened: the branch, whether the working tree has uncommitted changes, HEAD, and how many recent commits were listed. <b>Refresh local Git</b> reads that status again. There is no separate disconnect action. Closing the page is what stops the read.')]
    s += [P('<b>Export review JSON</b> and <b>Export review CSV</b> download the review already on screen, including changed definitions, concerns, tests, and recommendations. The file is built in the browser. Nothing is uploaded. GitHub, GitLab, Bitbucket, Slack, and the other hosted services named on that screen are not connected. The system has no sign-in for them, because sending the repository to those services would take the code off this computer.')]

    s += [P('4. Error handling and reporting', 'h1'), rule()]
    s += [P('RepoTrace reports a problem on the page that was in use. It does not send the message, the path, or the source to another computer. The person corrects the cause and tries again, or goes back. Table 5 lists the situations an end user meets. If the browser shows that the page cannot be reached, the terminal that started RepoTrace has been closed, or the address is from an older run. Start the system again with section 2.2 and use the address printed in the terminal.')]
    s += [table('Table 5. What the screen reports, and what to do', ['Situation', 'What is reported', 'What to do'], [
        ['The folder path is empty or cannot be opened', 'The message returned for that request, on the open screen', 'Type a folder that exists on this computer, or use Browse.'],
        ['The same commit is chosen twice', 'Choose two different versions, or tick Only explore the map.', 'Pick another version, or explore the map only.'],
        ['The analysis cannot finish', 'The analysis failed, with the message, and a way back to choosing a project', 'Read the message, then start again from Open a project.'],
        ['The person stops a read', 'The progress screen closes and the previous screen returns', 'No repair is required. The repository was not changed.'],
        ['The folder is not a Git repository', 'Not a Git repository, on Settings, after Refresh local Git', 'Explore without comparing. A comparison needs saved commits.'],
        ['There is no review to export', 'There is no review to export.', 'Run a comparison first.'],
        ['A test command cannot be copied', 'Copy unavailable here. Select the visible command and copy it.', 'Select the command on the page and copy it.'],
        ['A screen cannot be drawn', 'This page could not be drawn.', 'Use Back, or Go to Start. The project was not changed.'],
        ['A comparison cannot be reversed from this page', 'This comparison cannot be reversed from here.', 'Open a live review that still has the chosen pair.'],
    ], [0.30, 0.38, 0.32])]

    s += [P('5. Help frames', 'h1'), rule()]
    s += [P('Help is placed on the screens themselves. There is no separate help site. Table 6 names each help frame and what the user should take from it.')]
    s += [table('Table 6. Help frames', ['Where', 'What it tells the user'], [
        ['What works here?, and the status line Static analysis, not runtime proof', 'The dialog Real evidence, with its limits. Search is word search. A sure link is written in the code. A maybe link depends on an assumption. Neither proves that the code runs. Commands are copied and are not executed. History is not a dependency. A missing link is not proof of safety.'],
        ['The sentence under Reverse this change?', 'Which direction the next read will use, and that Git will not be modified.'],
        ['The banner This review is reversed.', 'The review runs backwards. Added and removed lines are swapped relative to the later version. The repository was not changed.'],
        ['The note on Recommendations', 'What each level means, that level 3 is omitted because there is no probability model, and that dismiss, save, and completed stay in this browser.'],
        ['Empty recommendation list', 'No recommendation met the evidence rules. The list is not filled with general advice.'],
        ['Conceptual, marked EXPERIMENTAL', 'The topic groups are a guess and are often wrong.'],
        ['Limits and history', 'What the review cannot establish, beside the history counts.'],
        ['Integrations, last paragraph', 'Hosted services are not connected, and the reason is stated on the page.'],
    ], [0.38, 0.62])]

    s += [P('6. How to read the results', 'h1'), rule()]
    s += [table('Table 7. Marks used on the screens', ['Mark', 'Meaning'], [
        ['Sure', 'The call is written in the code.'],
        ['Maybe', 'One step depends on an assumption. A call on self can be overridden by a subclass, so it stays maybe.'],
        ['Old version only', 'The link was recorded in the older version and not in the newer one.'],
        ['Plus and minus at the start of a diff line', 'Added text and removed text.'],
        ['Connected only before', 'A test path that can be followed in the older version and not in the newer one.'],
        ['Untraced calls', 'Calls inside a changed definition that could not be followed. This is a hole in the map, not proof that no call exists.'],
    ], [0.40, 0.60])]
    s += [P('When a page is quiet, read Limits and history before deciding what to do next. Then run the tests that were chosen. RepoTrace does not run them.')]

    s += [P('References', 'h1'), rule()]
    s += [P('[1] HiLCoE, School of Computer Science and Technology, “Senior Project Documentation Guideline,” version 1.4.3, 2024.', 'ref')]
    s += [P('[2] Python Software Foundation, “Python 3 documentation.” [Online]. Available: https://docs.python.org/3/. [Accessed: Nov. 23, 2026].', 'ref')]
    s += [P('[3] Git community, “Git documentation.” [Online]. Available: https://git-scm.com/doc. [Accessed: Nov. 23, 2026].', 'ref')]
    return s


def main():
    frame_cover = Frame(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN, id='cover', showBoundary=0)
    frame_rest = Frame(MARGIN, 0.85 * inch, W - 2 * MARGIN, H - 1.7 * inch, id='rest', showBoundary=0)
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4,
        title='RepoTrace Senior Project User Manual',
        author='Hana Mesfin, Israel Hayalsew, Jaffer Hussien, Kal Tsegaye',
    )
    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[frame_cover], onPage=cover_page),
        PageTemplate(id='contents', frames=[frame_rest], onPage=contents_page),
        PageTemplate(id='body', frames=[frame_rest], onPage=body_page),
    ])
    doc.build(story())
    print(OUT, OUT.stat().st_size)


if __name__ == '__main__':
    main()
