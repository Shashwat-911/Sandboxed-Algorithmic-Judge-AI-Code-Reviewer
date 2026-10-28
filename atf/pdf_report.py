"""Self-contained, paginated PDF report. User text is escaped, never HTML-rendered."""
import io
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('ATF', str(FONT_DIR / 'Vera.ttf')))
pdfmetrics.registerFont(TTFont('ATF-Bold', str(FONT_DIR / 'VeraBd.ttf')))
INK = colors.HexColor('#19202d')
ACCENT = colors.HexColor('#5044df')
MUTED = colors.HexColor('#6e7787')


def plain(value):
    text = str(value if value is not None else '').replace('\u2014','-').replace('\u2013','-').replace('\u2011','-')
    glyphs = pdfmetrics.getFont('ATF').face.charToGlyph
    # Keep unsupported characters legible as codepoints rather than missing-glyph squares.
    return ''.join(c if c in '\n\t' or ord(c) in glyphs else f'[U+{ord(c):04X}]' for c in text)


def render_report(result):
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=42, leftMargin=42,
                           topMargin=56, bottomMargin=48, title=plain(result['name']) + ' - ATF report', author='ATF')
    styles = {
        'title': ParagraphStyle('title', fontName='ATF-Bold', fontSize=21, leading=27, textColor=INK, spaceAfter=13),
        'heading': ParagraphStyle('heading', fontName='ATF-Bold', fontSize=13, leading=18, textColor=ACCENT, spaceBefore=17, spaceAfter=8, keepWithNext=True),
        'body': ParagraphStyle('body', fontName='ATF', fontSize=9, leading=14, textColor=INK, spaceAfter=6, splitLongWords=True),
        'small': ParagraphStyle('small', fontName='ATF', fontSize=8, leading=12, textColor=MUTED, spaceAfter=5, splitLongWords=True),
    }
    story = []
    def paragraph(value, style='body'):
        return Paragraph(escape(plain(value)).replace('\n','<br/>').replace('\t','    '), styles[style])
    def add(value, style='body'):
        # Bound each flowable so very long logs/model responses can paginate.
        for line in str(value if value is not None else '').splitlines() or ['']:
            story.append(paragraph(line or ' ', style))
    def section(title): add(title, 'heading')
    def items(values):
        for value in values: add('- ' + str(value))

    r = result['report']
    add('PROJECT INTELLIGENCE / ATF', 'small')
    add(result['name'], 'title')
    add('Created: ' + result['created_at'], 'small')
    add('Report ID: ' + result['id'], 'small')
    source = r.get('source', {'kind':'zip'})
    add('Source: ' + source.get('kind','zip') + (' | ' + source['url'] if source.get('url') else ''), 'small')
    if source.get('ref'): add('Requested ref: ' + source['ref'], 'small')
    summary = r['summary']
    cells = [paragraph(f'{value}\n{label}') for value, label in [
        (summary['files'],'Files reviewed'),(summary['lines'],'Lines of source'),
        (len(r['findings']),'Review findings'),(len(r['test_plan']),'Proposed cases')]]
    story.append(Spacer(1,12))
    metrics=Table([cells], colWidths=[doc.width/4]*4)
    metrics.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f0effe')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story.append(metrics)
    add('Evidence-based static review with optional execution and AI suggestions. Proposed cases are not executed tests.', 'small')
    from atf.verification import verification
    v=verification(r)
    section('Verification status')
    add(v['status'] + ': ' + v['headline'])
    items(v['gaps'])
    add(v['note'],'small')
    if r.get('planning_coverage'): add(str(r['planning_coverage']),'small')
    section('1. Summary')
    quality=r.get('quality_review',{})
    add(quality.get('headline','No browser execution evidence recorded.'))
    add('Measured test outcomes: '+str(quality.get('measured_tests',{})))
    items(quality.get('actions',[]))
    items(quality.get('boundaries',[]))
    for run in r.get('browser_evidence',[]):
        add(f"Browser run {run['id']} | {run['status']} | {run.get('browser')} | {run.get('counts',{})}")
        for test in run.get('tests',[]):
            add(f"{test['status']} | {test['file']}:{test['line']} | {test['title']} | {test['duration_ms']} ms", 'small')
            for error in test.get('errors',[]): add(error.get('message',''), 'small')
    add('Languages: ' + ', '.join(f'{k}: {v}' for k,v in summary.get('languages',{}).items()))
    add('Conventional test files: ' + str(summary.get('test_files',0)))
    add('Finding severity: ' + (', '.join(f'{k}: {v}' for k,v in summary.get('severity',{}).items()) or 'No findings'))
    section('2. Findings')
    if not r['findings']: add('No findings from the implemented rules. This does not establish correctness.')
    add(f"Showing up to 20 of {len(r['findings'])} findings. Full details are retained in JSON.", 'small')
    for f in r['findings'][:20]:
        add(f"[{f['severity'].upper()}] {f['title']} ({f['rule']})")
        add(f"{f['file'] or 'Project'}:{f['line']}", 'small')
        add(f.get('context','unknown') + ' | ' + f.get('evidence','Legacy finding; evidence context not recorded.'),'small')
        add(f['recommendation'])
    section('3. Execution and static validation')
    execution = r['execution']
    add('Execution status: ' + execution['status'])
    add(execution['detail'])
    if execution.get('duration_ms') is not None: add(f"Wall time: {execution['duration_ms']} ms")
    add(execution.get('output') or 'No execution output.', 'small')
    add(f"Static syntax checks: {len(r.get('checks',[]))}; individual checks retained in JSON.", 'small')
    for check in [c for c in r.get('checks',[]) if c['status']!='passed'][:20]: add(f"{check['status']} | {check['file']} | {check['check']}", 'small')
    section('4. Proposed test cases and edge cases')
    add('These scenarios require domain-specific assertions. They are not evidence of passing tests.', 'small')
    add(f"Showing up to 20 of {len(r['test_plan'])} proposed scenarios. Download JSON for the complete plan.", 'small')
    for t in r['test_plan'][:20]:
        add(f"{t['id']} | {t['target']} | {t['category']}")
        add(f"{t['file']}:{t['line']}", 'small')
        add(t['scenario'])
        add('Expected: ' + t['expected'])
        add(t['status'], 'small')
    section('5. Local AI review')
    ai = r['ai']
    add('AI status: ' + ai['status'])
    add(ai['text'])
    if ai.get('note'): add(ai['note'],'small')
    if ai.get('files_in_context'):
        add(f"Context: {ai.get('characters_in_context',0)} characters", 'small')
        items(ai['files_in_context'])
    section('6. Architecture')
    a = r.get('architecture',{})
    add(a.get('note','No architecture inventory recorded.'),'small')
    add('Entry points'); items(a.get('entrypoints',[]))
    add('API routes')
    items(f"{x['method']} {x['path']} | {x['file']}:{x['line']}" for x in a.get('routes',[])[:30])
    add('Declared dependencies')
    items(f"{x['declaration']} | {x['manifest']}" for x in a.get('dependencies',[])[:30])
    add('Python imports (first 30; full inventory in JSON)')
    items(f"{x['file']}:{x['line']} | {x['module']}" for x in a.get('imports',[])[:30])
    section('7. Suggestions and future scope')
    items(r.get('suggestions',[]));items(r.get('future_scope',[]))
    section('8. File inventory')
    add('First 30 files shown; complete file and exclusion inventories are in JSON.', 'small')
    for f in r.get('inventory',[])[:30]: add(f"{f['path']} | {f['language']} | {f['lines']} lines | {f['bytes']} bytes",'small')
    add('Skipped files: ' + str(len(r.get('skipped_files',[]))))
    items(r.get('skipped_files',[])[:15])
    section('9. Limitations')
    items(r.get('limitations',[]))
    add('Unsupported font characters are represented as [U+XXXX]. AI Markdown and execution logs are included as plain text. This PDF is a snapshot of the stored report.', 'small')

    def page(canvas, document):
        canvas.saveState()
        canvas.setFont('ATF',8);canvas.setFillColor(MUTED)
        canvas.drawString(42,A4[1]-30,'ATF / PROJECT REVIEW')
        canvas.drawRightString(A4[0]-42,26,f'Page {document.page}')
        canvas.drawString(42,26,'Evidence first. AI assisted.')
        canvas.restoreState()
    doc.build(story,onFirstPage=page,onLaterPages=page)
    return output.getvalue()
