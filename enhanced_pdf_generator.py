import os
import tempfile
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, BaseDocTemplate, PageTemplate

class EnhancedConsultationPDF(BaseDocTemplate):
    """Enhanced PDF document template for OSCE consultation reports"""
    
    def __init__(self, filename):
        super().__init__(
            filename,
            pagesize=A4,
            rightMargin=72,  # 1 inch in points
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Store page count
        self._page_count = 0
        
        def add_header_footer(canvas, doc):
            canvas.saveState()
            
            # Header
            canvas.setFont('Helvetica-Bold', 12)
            header_text = f"Consultation OSCE - Rapport d'Évaluation"
            canvas.drawString(doc.leftMargin, doc.pagesize[1] - doc.topMargin + 40, header_text)
            
            # Date in header
            canvas.setFont('Helvetica', 10)
            date_text = f"Date: {datetime.now().strftime('%d/%m/%Y')}"
            canvas.drawString(doc.pagesize[0] - doc.rightMargin - 100, doc.pagesize[1] - doc.topMargin + 40, date_text)
            
            # Horizontal line under header
            canvas.line(doc.leftMargin, doc.pagesize[1] - doc.topMargin + 25,
                       doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - doc.topMargin + 25)
            
            # Footer with page numbers
            canvas.setFont('Helvetica', 9)
            current_page = canvas.getPageNumber()
            self._page_count = max(self._page_count, current_page)
            page_text = f"Page {current_page}"
            canvas.drawString(doc.leftMargin, doc.bottomMargin - 40, page_text)
            
            # Horizontal line above footer
            canvas.line(doc.leftMargin, doc.bottomMargin - 20,
                       doc.pagesize[0] - doc.rightMargin, doc.bottomMargin - 20)
            
            canvas.restoreState()
        
        # Create frame for the content
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.pagesize[0] - self.leftMargin - self.rightMargin,
            self.pagesize[1] - self.topMargin - self.bottomMargin - 40,  # Extra space for header/footer
            id='normal',
            showBoundary=0
        )
        
        template = PageTemplate(
            id='consultation_template',
            frames=frame,
            onPage=add_header_footer
        )
        self.addPageTemplates([template])
        
    def handle_nextPage(self):
        self._page_count += 1
        super().handle_nextPage()


def create_enhanced_consultation_pdf(conversation, case_number, evaluation_results, recommendations=None):
    """Create an enhanced PDF document from consultation with improved evaluation visualization"""
    # Create a temporary file
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"consultation_case{case_number}_{timestamp}.pdf"
    filepath = os.path.join(temp_dir, filename)
    
    # Create the PDF document using the custom template
    doc = EnhancedConsultationPDF(filepath)
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        keepWithNext=True
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=12,
        keepWithNext=True
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceBefore=6,
        spaceAfter=6,
        leading=14  # Line spacing
    )
    
    highlight_style = ParagraphStyle(
        'CustomHighlight',
        parent=styles['Normal'],
        fontSize=11,
        spaceBefore=6,
        spaceAfter=6,
        leading=14,
        backColor=colors.lightgrey,
        borderPadding=5,
        borderWidth=1,
        borderColor=colors.grey
    )
    
    # Content elements
    elements = []
    
    # Add title
    elements.append(Paragraph(f"Consultation OSCE - Cas {case_number}", title_style))
    elements.append(Spacer(1, 20))
    
    # Add date
    current_date = datetime.now().strftime('%d/%m/%Y')
    elements.append(Paragraph(f"Date: {current_date}", normal_style))
    elements.append(Spacer(1, 20))
    
    # Add score summary at the top
    total_points = evaluation_results.get('points_total', 0)
    earned_points = evaluation_results.get('points_earned', 0)
    percentage = evaluation_results.get('percentage', 0)
    
    # Create score gauge
    score_table_data = [
        [Paragraph("<b>Résumé de l'évaluation</b>", subtitle_style)],
        [create_score_gauge(percentage)],
        [Paragraph(f"<b>Score:</b> {earned_points}/{total_points} points ({percentage}%)", normal_style)]
    ]
    
    score_table = Table(score_table_data, colWidths=[450])
    score_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lavender)
    ]))
    
    elements.append(score_table)
    elements.append(Spacer(1, 15))
    
    # Add smart recommendations if available
    if recommendations and len(recommendations) > 0:
        rec_data = [[Paragraph("<b>Recommandations personnalisées</b>", subtitle_style)]]
        
        for rec in recommendations:
            rec_data.append([Paragraph(f"• {rec}", normal_style)])
        
        rec_table = Table(rec_data, colWidths=[450])
        rec_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lavender)
        ]))
        
        elements.append(rec_table)
        elements.append(Spacer(1, 15))
    
    # Add general feedback
    if evaluation_results.get('feedback'):
        feedback_data = [
            [Paragraph("<b>Feedback général</b>", subtitle_style)],
            [Paragraph(evaluation_results['feedback'], normal_style)]
        ]
        
        feedback_table = Table(feedback_data, colWidths=[450])
        feedback_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lavender)
        ]))
        
        elements.append(feedback_table)
        elements.append(Spacer(1, 15))
    
    # Process messages
    elements.append(Paragraph("Dialogue de la consultation", subtitle_style))
    
    # Process only non-system messages and preserve the chronological order
    conversation_messages = []
    
    for msg in conversation:
        if msg['role'] != 'system':  # Skip system messages
            role = "Médecin" if msg['role'] == 'human' else "Patient"
            conversation_messages.append({
                'role': role,
                'content': msg['content']
            })
    
    # Now add the messages to the PDF in their original order
    message_count = 0
    
    # Create a table for the conversation
    conversation_data = []
    
    for msg in conversation_messages:
        message_count += 1
        role = msg['role']
        content = msg['content']
        
        # Use different colors for different roles
        role_color = "#5B9BD5" if role == "Médecin" else "#70AD47"  # Blue for doctor, green for patient
        
        # Format message with role and content
        conversation_data.append([
            Paragraph(f"<font color='{role_color}'><b>{role}:</b></font>", normal_style),
            Paragraph(content, normal_style)
        ])
    
    # Create the conversation table
    if conversation_data:
        conversation_table = Table(conversation_data, colWidths=[100, 350])
        conversation_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke)
        ]))
        
        elements.append(conversation_table)
    
    # Add consultation end info
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Nombre total de messages: {message_count}", normal_style))
    
    # Add evaluation section
    elements.append(PageBreak())
    elements.append(Paragraph("Évaluation détaillée", title_style))
    elements.append(Spacer(1, 10))
    
    # Add checklist items with categories
    if evaluation_results.get('checklist'):
        # Group by category if available
        categories = {}
        has_categories = False
        
        for item in evaluation_results['checklist']:
            cat = item.get('category')
            if cat:
                has_categories = True
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)
            else:
                if 'Général' not in categories:
                    categories['Général'] = []
                categories['Général'].append(item)
        
        if has_categories:
            # Display by category
            for cat, items in categories.items():
                elements.append(Paragraph(f"<b>{cat}</b>", subtitle_style))
                
                # Create table for checklist items
                checklist_data = []
                
                for item in items:
                    status = "✅" if item.get('completed', False) else "❌"
                    points = item.get('points', 1)
                    earned = points if item.get('completed', False) else 0
                    
                    row = [
                        Paragraph(status, normal_style),
                        Paragraph(item.get('description', 'Item'), normal_style),
                        Paragraph(f"{earned}/{points}", normal_style)
                    ]
                    
                    checklist_data.append(row)
                    
                    # Add justification if available
                    if item.get('justification'):
                        justification_style = ParagraphStyle(
                            'JustificationStyle',
                            parent=normal_style,
                            fontSize=10,
                            leftIndent=20,
                            textColor=colors.darkgrey
                        )
                        checklist_data.append([
                            Paragraph("", normal_style),
                            Paragraph(f"<i>{item['justification']}</i>", justification_style),
                            Paragraph("", normal_style)
                        ])
                
                if checklist_data:
                    checklist_table = Table(checklist_data, colWidths=[30, 370, 50])
                    checklist_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                        # Add alternating row colors
                        *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke) for i in range(0, len(checklist_data), 2)]
                    ]))
                    
                    elements.append(checklist_table)
                    elements.append(Spacer(1, 10))
        else:
            # Just list all items in one table
            elements.append(Paragraph("<b>Éléments évalués</b>", subtitle_style))
            
            checklist_data = []
            
            for item in evaluation_results['checklist']:
                status = "✅" if item.get('completed', False) else "❌"
                points = item.get('points', 1)
                earned = points if item.get('completed', False) else 0
                
                row = [
                    Paragraph(status, normal_style),
                    Paragraph(item.get('description', 'Item'), normal_style),
                    Paragraph(f"{earned}/{points}", normal_style)
                ]
                
                checklist_data.append(row)
                
                # Add justification if available
                if item.get('justification'):
                    justification_style = ParagraphStyle(
                        'JustificationStyle',
                        parent=normal_style,
                        fontSize=10,
                        leftIndent=20,
                        textColor=colors.darkgrey
                    )
                    checklist_data.append([
                        Paragraph("", normal_style),
                        Paragraph(f"<i>{item['justification']}</i>", justification_style),
                        Paragraph("", normal_style)
                    ])
            
            if checklist_data:
                checklist_table = Table(checklist_data, colWidths=[30, 370, 50])
                checklist_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                    # Add alternating row colors
                    *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke) for i in range(0, len(checklist_data), 2)]
                ]))
                
                elements.append(checklist_table)
                elements.append(Spacer(1, 20))
    
    # Build PDF
    doc.build(elements)
    
    return filename


def create_score_gauge(percentage):
    """Create a visual score gauge for the PDF"""
    from io import BytesIO
    from reportlab.lib.colors import red, yellow, green, white, black
    from reportlab.graphics.shapes import Drawing, Wedge, String
    from reportlab.graphics.charts.piecharts import Pie
    
    gauge_width = 200
    gauge_height = 100
    
    drawing = Drawing(gauge_width, gauge_height)
    
    # Create gauge background
    background = Wedge(gauge_width/2, 0, 80, -180, 0, fillColor=white)
    drawing.add(background)
    
    # Create colored sections
    drawing.add(Wedge(gauge_width/2, 0, 80, -180, -108, fillColor=red))    # 0-40%
    drawing.add(Wedge(gauge_width/2, 0, 80, -108, -36, fillColor=yellow))  # 40-80%
    drawing.add(Wedge(gauge_width/2, 0, 80, -36, 0, fillColor=green))      # 80-100%
    
    # Create gauge needle
    needle_angle = -180 + (percentage * 1.8)  # Convert percentage to angle (0-100% maps to -180-0 degrees)
    drawing.add(Wedge(gauge_width/2, 0, 80, needle_angle-1, needle_angle+1, fillColor=black))
    
    # Add percentage text
    drawing.add(String(gauge_width/2, 50, f"{percentage}%", fontSize=20, fillColor=black, textAnchor='middle'))
    
    # Convert to an image
    buff = BytesIO()
    drawing.save(formats=['gif'], outDir=None, fnRoot=None, png=None, configPIL={'transparent': None}, gs=None, pdfTitle=None, pdfAuthor=None, pdfSubject=None, pdfCreator=None, pdfProducer=None, pdfKeywords=None, pdfDebug=None, showBoundary=None, verify=None, cache=None, extraContentFile=None)
    
    return drawing