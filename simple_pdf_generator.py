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
