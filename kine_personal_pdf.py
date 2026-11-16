"""Personal report: accepts only the authorized student projection."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def personal_pdf(result, identity, case, metadata, comments=None):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyFR', parent=styles['BodyText'], fontSize=10, leading=15, spaceAfter=7))
    for name in ('Title', 'Heading1', 'Heading2'):
        styles[name].textColor = colors.HexColor('#813d10')
    styles['BodyFR'].textColor = colors.HexColor('#302c28')
    story = []
    def line(text, style='BodyFR'):
        story.append(Paragraph(escape(str(text)), styles[style]))
    line('KardioX | Bilan individuel', 'Title')
    line('Simuler. Raisonner. Rééduquer.')
    line(f"{identity.name} · {identity.student_code} · {str(identity.level or '').capitalize()}")
    line(f"Cas {case.case_number}{(' - ' + case.title) if case.title else ''}", 'Heading2')
    line(f"Tentative {metadata['id']} · {metadata['mode']} · {metadata['date']}")
    provenance = 'reconstruite, version historique non attestée' if metadata.get('case_reference_provenance') == 'reconstructed_current' else 'figée à la réalisation' if metadata.get('case_version_number') else 'historique non versionnée'
    line(f"Version {metadata.get('case_version_number') or 'non renseignée'} · Référence {provenance}")
    line(result.get('status_label') or 'Résultat enregistré', 'Heading2')
    if result.get('points_earned') is not None:
        line(f"Note : {result.get('score_display', result['points_earned'])} / 20", 'Heading1')
    if result.get('rounded_below_threshold'):
        line('La valeur exacte reste sous le seuil malgré la note arrondie affichée.')
    if result.get('validation_threshold') is not None:
        line(f"Seuil appliqué : {result['validation_threshold']} / 20")
    if not metadata['feedback_allowed']:
        line('Le feedback détaillé sera accessible après publication par l’enseignant.')
    summary = result.get('summary')
    if summary:
        line(f"{summary['satisfied']} satisfaits · {summary['partial']} partiels · {summary['failed']} non satisfaits · {summary['pending']} à vérifier")
    for row in result.get('criteria', []):
        line(row['title'], 'Heading2')
        line(row['status_label'])
        if row.get('safety_consequence') != 'none':
            line('Sécurité : ' + {'critical': 'erreur critique', 'eliminatory': 'erreur éliminatoire', 'review': 'à vérifier'}.get(row['safety_consequence'], row['safety_consequence']))
        if row.get('omission'):
            line('Élément attendu non retrouvé dans vos réponses.')
        for evidence in row.get('evidence', []):
            line('Votre réponse : ' + evidence['quote'])
        line('Explication : ' + row.get('justification', ''))
        if row.get('expected'):
            line('Attendu : ' + row['expected'])
        if row.get('alternatives'):
            line('Alternatives acceptées : ' + ' ; '.join(row['alternatives']))
    # Historical authorized feedback keeps its saved wording, without recalculation.
    for section in result.get('section_scores', []):
        line(section.get('title') or section.get('id', 'Compétence'), 'Heading2')
        line(section.get('justification', ''))
    if comments:
        line('Commentaire de l’enseignant', 'Heading2')
        line(comments)
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#68605a'))
        canvas.drawString(42, 25, 'KardioX - Bilan personnel')
        canvas.drawRightString(A4[0] - 42, 25, f'Page {doc.page}')
        canvas.restoreState()
    SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42,
                      topMargin=40, bottomMargin=44, title='Bilan individuel KardioX').build(story, onFirstPage=footer, onLaterPages=footer)
    stream.seek(0)
    return stream
