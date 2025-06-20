import os
import tempfile
import logging
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, BaseDocTemplate, PageTemplate

logger = logging.getLogger(__name__)



class SimpleConsultationPDF(BaseDocTemplate):
    """Simplified PDF document template for OSCE consultation reports without renderPM dependency"""
    
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

def create_simple_consultation_pdf(conversation, case_number, evaluation_results, recommendations=None):
    """Create a simplified PDF document with enhanced error handling"""
    
    # STEP 1: Debug and fix conversation format
    logger.info(f"=== PDF CONVERSATION DEBUG ===")
    logger.info(f"Conversation type: {type(conversation)}")
    logger.info(f"Conversation length: {len(conversation) if conversation else 0}")
    
    if conversation:
        logger.info(f"First item type: {type(conversation[0])}")
        logger.info(f"First item content: {str(conversation[0])[:100]}...")
    
    # STEP 2: Convert conversation to proper format
    def fix_conversation_format(conv):
        """Convert conversation to proper dict format"""
        fixed_conv = []
        
        if not conv:
            return [{'role': 'system', 'content': 'Aucune conversation enregistrée'}]
        
        for i, item in enumerate(conv):
            try:
                if isinstance(item, dict):
                    # Check if it has the required keys
                    if 'role' in item and 'content' in item:
                        fixed_conv.append(item)
                    else:
                        # Dict but missing keys - try to fix
                        logger.warning(f"Dict missing keys at {i}: {item}")
                        content = item.get('content') or str(item)
                        role = item.get('role', 'system')
                        fixed_conv.append({'role': role, 'content': content})
                
                elif isinstance(item, str):
                    # String format - need to parse
                    logger.info(f"Converting string at {i}: {item[:50]}...")
                    
                    # Try to detect role from content
                    if any(word in item.lower() for word in ['médecin:', 'doctor:', 'vous:']):
                        role = 'human'
                        content = item
                    elif any(word in item.lower() for word in ['patient:', 'je ', 'j\'ai', 'bonjour docteur']):
                        role = 'assistant'
                        content = item
                    else:
                        role = 'system'
                        content = item
                    
                    fixed_conv.append({'role': role, 'content': content})
                
                else:
                    # Other type - convert to string
                    logger.warning(f"Unknown type at {i}: {type(item)} - {item}")
                    fixed_conv.append({'role': 'system', 'content': str(item)})
                    
            except Exception as e:
                logger.error(f"Error processing conversation item {i}: {e}")
                fixed_conv.append({'role': 'system', 'content': f"Error: {str(item)}"})
        
        return fixed_conv
    
    # Apply the fix
    conversation = fix_conversation_format(conversation)
    logger.info(f"Fixed conversation length: {len(conversation)}")
    
    # STEP 3: Input validation
    if not evaluation_results:
        logger.warning("Empty evaluation results provided to PDF generator")
        evaluation_results = {
            'checklist': [],
            'feedback': 'Aucune évaluation disponible',
            'points_total': 0,
            'points_earned': 0,
            'percentage': 0
        }
    
    if not case_number:
        case_number = 'UNKNOWN'
    
    try:
        # STEP 4: Create PDF file
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"consultation_case{case_number}_{timestamp}.pdf"
        filepath = os.path.join(temp_dir, filename)
        
        logger.info(f"Creating PDF at: {filepath}")
        logger.info(f"Temp directory: {temp_dir}")
        logger.info(f"Temp directory exists: {os.path.exists(temp_dir)}")
        logger.info(f"Temp directory writable: {os.access(temp_dir, os.W_OK)}")
        
        # Create the PDF document
        doc = SimpleConsultationPDF(filepath)
        
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
            leading=14
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
        current_date = datetime.now().strftime('%d/%m/%Y %H:%M')
        elements.append(Paragraph(f"Date: {current_date}", normal_style))
        elements.append(Spacer(1, 20))
        
        # Add score summary at the top
        total_points = evaluation_results.get('points_total', 0)
        earned_points = evaluation_results.get('points_earned', 0)
        percentage = evaluation_results.get('percentage', 0)
        
        # Determine score color based on percentage
        score_color = "#dc3545"  # Red for low scores
        if percentage >= 80:
            score_color = "#28a745"  # Green for high scores
        elif percentage >= 60:
            score_color = "#ffc107"  # Yellow for medium scores
        
        score_text = f"<b>Score:</b> <font color='{score_color}'>{earned_points}/{total_points} points ({percentage}%)</font>"
        
        # Create score summary table
        score_table_data = [
            [Paragraph("<b>Résumé de l'évaluation</b>", subtitle_style)],
            [Paragraph(score_text, normal_style)]
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
        
        # Add recommendations if available - ENSURE THEY ARE IN FRENCH
        if recommendations and len(recommendations) > 0:
            # Verify recommendations are in French
            translated_recommendations = []
            english_indicators = ['here are', 'practice', 'review', 'improve', 'make sure', 'remember to']
            
            for rec in recommendations:
                if rec and len(rec.strip()) > 0:
                    # Check if the recommendation seems to be in English
                    if any(indicator in rec.lower() for indicator in english_indicators):
                        # This is likely in English, add an error message
                        translated_recommendations.append(f"[ERREUR: Cette recommandation devrait être en français: '{rec}']")
                    else:
                        translated_recommendations.append(rec)
                        
            rec_data = [[Paragraph("<b>Recommandations personnalisées</b>", subtitle_style)]]
            
            for rec in translated_recommendations:
                rec_data.append([Paragraph(f"• {rec}", normal_style)])
            
            if len(rec_data) > 1:  # Only add table if we have recommendations
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
        
        # STEP 5: Process conversation messages - NOW SAFE!
        elements.append(Paragraph("Dialogue de la consultation", subtitle_style))
        
        # Process only non-system messages and preserve the chronological order
        conversation_messages = []
        
        # Now we can safely access dict keys because we fixed the format
        for msg in conversation:
            if msg.get('role') != 'system':  # Safe to use dict access
                role = "Médecin" if msg['role'] == 'human' else "Patient"
                content = msg.get('content', '')
                if content:
                    # Limit content length for PDF to prevent issues
                    if len(content) > 500:
                        content = content[:500] + "..."
                    conversation_messages.append({
                        'role': role,
                        'content': content
                    })
        
        logger.info(f"Processed {len(conversation_messages)} conversation messages for PDF")
        
        # Create conversation table
        if conversation_messages:
            conversation_data = []
            
            for msg in conversation_messages:
                role = msg['role']
                content = msg['content']
                
                # Use different colors for different roles
                role_color = "#5B9BD5" if role == "Médecin" else "#70AD47"  # Blue for doctor, green for patient
                
                # Format message with role and content
                conversation_data.append([
                    Paragraph(f"<font color='{role_color}'><b>{role}:</b></font>", normal_style),
                    Paragraph(content, normal_style)
                ])
            
            conversation_table = Table(conversation_data, colWidths=[100, 350])
            conversation_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke)
            ]))
            
            elements.append(conversation_table)
        else:
            elements.append(Paragraph("Aucun message de conversation enregistré.", normal_style))
        
        # Add consultation end info
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"Nombre total de messages: {len(conversation_messages)}", normal_style))
        
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
                        description = item.get('description', 'Item')
                        
                        # Limit description length
                        if len(description) > 100:
                            description = description[:100] + "..."
                        
                        row = [
                            Paragraph(status, normal_style),
                            Paragraph(description, normal_style),
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
                    description = item.get('description', 'Item')
                    
                    # Limit description length
                    if len(description) > 100:
                        description = description[:100] + "..."
                    
                    row = [
                        Paragraph(status, normal_style),
                        Paragraph(description, normal_style),
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
        
        # STEP 6: Build PDF
        logger.info("Building PDF document...")
        doc.build(elements)
        
        # STEP 7: Verify file was created
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f"✅ PDF created successfully: {filename} ({file_size} bytes)")
            
            if file_size > 1000:  # At least 1KB - a reasonable PDF should be larger
                return filename
            else:
                logger.error(f"PDF file too small ({file_size} bytes), likely corrupted")
                return None
        else:
            logger.error("PDF file was not created at expected location")
            return None
            
    except Exception as e:
        logger.error(f"Error creating PDF: {str(e)}")
        import traceback
        logger.error(f"PDF creation traceback:\n{traceback.format_exc()}")
        return None

def create_competition_report_pdf(report_data):
    """Create a PDF report for competition results"""
    import os
    import tempfile
    from datetime import datetime
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    
    # Create a temporary file
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"competition_report_{report_data['student_code']}_{timestamp}.pdf"
    filepath = os.path.join(temp_dir, filename)
    
    # Create PDF document
    doc = SimpleDocTemplate(filepath, pagesize=A4, rightMargin=72, leftMargin=72,
                          topMargin=72, bottomMargin=72)
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=12
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceBefore=6,
        spaceAfter=6
    )
    
    # Content elements
    elements = []
    
    # Title
    elements.append(Paragraph("Rapport de Compétition OSCE", title_style))
    elements.append(Spacer(1, 20))
    
    # Student info
    student_info = [
        ["Étudiant:", report_data['student_name']],
        ["Code étudiant:", report_data['student_code']],
        ["Compétition:", report_data['competition_name']],
        ["Date:", report_data['start_time'].strftime('%d/%m/%Y')],
        ["Rapport généré le:", datetime.now().strftime('%d/%m/%Y à %H:%M')]
    ]
    
    info_table = Table(student_info, colWidths=[150, 300])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey)
    ]))
    
    elements.append(info_table)
    elements.append(Spacer(1, 30))
    
    # Summary scores
    elements.append(Paragraph("Résumé des Performances", subtitle_style))
    
    summary_data = [
        ["Score moyen", f"{report_data['average_score']}%"],
        ["Score total", f"{report_data['total_score']} points"],
        ["Stations complétées", f"{report_data['completed_stations']}/{report_data['total_stations']}"],
        ["Taux de réussite", f"{(report_data['completed_stations']/report_data['total_stations']*100):.1f}%"]
    ]
    
    summary_table = Table(summary_data, colWidths=[200, 150])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lavender),
        ('BACKGROUND', (1, 0), (1, -1), colors.white)
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 30))
    
    # Detailed station results
    if report_data['station_results']:
        elements.append(Paragraph("Résultats Détaillés par Station", subtitle_style))
        
        # Create table headers
        station_headers = [
            "Station", "Cas", "Spécialité", "Score", "Statut", "Temps"
        ]
        
        station_data = [station_headers]
        
        for result in report_data['station_results']:
            # Calculate duration if both times are available
            duration = "N/A"
            if result.get('started_at') and result.get('completed_at'):
                start_time = result['started_at']
                end_time = result['completed_at']
                if isinstance(start_time, str):
                    # Parse datetime strings if needed
                    from datetime import datetime
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                
                duration_seconds = (end_time - start_time).total_seconds()
                duration = f"{int(duration_seconds // 60)}:{int(duration_seconds % 60):02d}"
            
            # Determine status display
            status_display = {
                'completed': 'Terminé',
                'active': 'En cours',
                'pending': 'En attente'
            }.get(result['status'], result['status'])
            
            station_data.append([
                str(result['station_order']),
                result['case_number'],
                result['specialty'],
                f"{result['score']}%",
                status_display,
                duration
            ])
        
        # Create and style the table
        station_table = Table(station_data, colWidths=[50, 80, 120, 60, 80, 60])
        station_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ]))
        
        # Add alternating row colors
        for i in range(1, len(station_data)):
            if i % 2 == 0:
                station_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, i), (-1, i), colors.lightgrey)
                ]))
        
        elements.append(station_table)
        elements.append(Spacer(1, 20))
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_text = f"Rapport généré automatiquement par le système OSCE - {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    elements.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(elements)
    
    return filename

def create_competition_pdf_report(competition_summary, conversations_data):
    """Create a comprehensive PDF report for competition results"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"competition_report_{competition_summary['student_code']}_{timestamp}.pdf"
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        
        # Create PDF document
        doc = SimpleDocTemplate(temp_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.darkblue,
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.darkblue,
            spaceAfter=12
        )
        
        subheader_style = ParagraphStyle(
            'CustomSubHeader',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.darkred,
            spaceAfter=8
        )
        
        # Title
        story.append(Paragraph("RAPPORT DE COMPÉTITION OSCE", title_style))
        story.append(Spacer(1, 20))
        
        # Competition information
        story.append(Paragraph("INFORMATIONS GÉNÉRALES", header_style))
        
        info_data = [
            ["Session de compétition:", competition_summary['session_name']],
            ["Étudiant:", f"{competition_summary['student_name']} ({competition_summary['student_code']})"],
            ["Date de completion:", competition_summary['completed_at']],
            ["Nombre de stations:", str(competition_summary['total_stations'])],
            ["Score total:", f"{competition_summary['total_score']}/{competition_summary['total_possible']} points"],
            ["Pourcentage global:", f"{competition_summary['overall_percentage']}%"],
            ["Score moyen:", f"{competition_summary['average_score']}%"],
            ["Classement:", str(competition_summary['rank'])]
        ]
        
        for label, value in info_data:
            story.append(Paragraph(f"<b>{label}</b> {value}", styles['Normal']))
        
        story.append(Spacer(1, 20))
        
        # Performance summary chart (textual representation)
        story.append(Paragraph("RÉSUMÉ DES PERFORMANCES", header_style))
        
        # Calculate performance grade
        overall_percentage = competition_summary['overall_percentage']
        if overall_percentage >= 90:
            grade = "Excellent (A)"
            grade_color = colors.green
        elif overall_percentage >= 80:
            grade = "Très Bien (B)"
            grade_color = colors.blue
        elif overall_percentage >= 70:
            grade = "Bien (C)"
            grade_color = colors.orange
        elif overall_percentage >= 60:
            grade = "Satisfaisant (D)"
            grade_color = colors.gold
        else:
            grade = "Insuffisant (F)"
            grade_color = colors.red
        
        grade_style = ParagraphStyle(
            'GradeStyle',
            parent=styles['Normal'],
            fontSize=14,
            textColor=grade_color,
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        story.append(Paragraph(f"<b>Note globale: {grade}</b>", grade_style))
        story.append(Spacer(1, 20))
        
        # Detailed station results
        story.append(Paragraph("RÉSULTATS DÉTAILLÉS PAR STATION", header_style))
        
        for i, conv_data in enumerate(conversations_data):
            # Station header
            station_title = f"Station {conv_data['station_number']} - Cas {conv_data['case_number']} ({conv_data['specialty']})"
            story.append(Paragraph(station_title, subheader_style))
            
            # Station score
            score_text = f"Score: {conv_data['score']}% ({conv_data['points_earned']}/{conv_data['points_total']} points)"
            story.append(Paragraph(f"<b>{score_text}</b>", styles['Normal']))
            story.append(Spacer(1, 10))
            
            # Evaluation details if available
            evaluation = conv_data.get('evaluation', {})
            if evaluation and 'checklist' in evaluation:
                story.append(Paragraph("<b>Éléments d'évaluation:</b>", styles['Normal']))
                
                for item in evaluation['checklist']:
                    status_icon = "✅" if item.get('completed') else "❌"
                    item_text = f"{status_icon} {item.get('description', 'N/A')} ({item.get('points', 1)} pts)"
                    story.append(Paragraph(item_text, styles['Normal']))
                    
                    # Add justification if available
                    if item.get('justification'):
                        justification_style = ParagraphStyle(
                            'Justification',
                            parent=styles['Normal'],
                            leftIndent=20,
                            fontSize=9,
                            textColor=colors.grey
                        )
                        story.append(Paragraph(f"<i>{item['justification']}</i>", justification_style))
                
                story.append(Spacer(1, 10))
            
            # Conversation summary (if available and not too long)
            conversation = conv_data.get('conversation', [])
            if conversation and len(conversation) > 0:
                story.append(Paragraph("<b>Résumé de la consultation:</b>", styles['Normal']))
                
                # Show only first few exchanges to keep PDF manageable
                shown_messages = 0
                max_messages = 6  # Show first 6 messages
                
                for msg in conversation:
                    if shown_messages >= max_messages:
                        story.append(Paragraph("<i>[...conversation tronquée...]</i>", styles['Normal']))
                        break
                    
                    if isinstance(msg, dict):
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')
                    else:
                        # Handle string messages
                        content = str(msg)
                        role = 'unknown'
                    
                    # Truncate very long messages
                    if len(content) > 200:
                        content = content[:200] + "..."
                    
                    if role == 'human':
                        story.append(Paragraph(f"<b>Médecin:</b> {content}", styles['Normal']))
                    elif role == 'assistant':
                        story.append(Paragraph(f"<b>Patient:</b> {content}", styles['Normal']))
                    elif role == 'system':
                        story.append(Paragraph(f"<b>Système:</b> {content}", styles['Normal']))
                    
                    shown_messages += 1
            
            # Add page break between stations (except for the last one)
            if i < len(conversations_data) - 1:
                story.append(PageBreak())
            else:
                story.append(Spacer(1, 20))
        
        # Footer with generation info
        story.append(Spacer(1, 30))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        
        generation_time = datetime.now().strftime('%d/%m/%Y à %H:%M')
        story.append(Paragraph(f"Rapport généré le {generation_time} - Simulateur OSCE", footer_style))
        
        # Build PDF
        doc.build(story)
        
        logger.info(f"Competition PDF report generated successfully: {filename}")
        return filename
        
    except Exception as e:
        logger.error(f"Error creating competition PDF report: {str(e)}", exc_info=True)
        return None