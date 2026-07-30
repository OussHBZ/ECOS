import os
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime
from io import BytesIO

from flask import flash, jsonify, redirect, render_template, request, send_file, session, url_for

from auth import teacher_required
from models import Exam, PathologyFolder, PatientCase, SimulationSession, Student, db
from progression_tracker import ProgressionTracker
from simple_pdf_generator import create_simple_consultation_pdf, export_kine_dashboard_csv, export_kine_dashboard_excel
from timeline_logger import append_timeline_event, format_timeline

from . import kine_bp
from .common import error, kine_staff_required, wants_json


def _dashboard_query():
    query = db.session.query(SimulationSession, Student, PatientCase, PathologyFolder).join(
        Student, SimulationSession.student_id == Student.id
    ).join(PatientCase, SimulationSession.clinical_case_id == PatientCase.id).outerjoin(
        PathologyFolder, PatientCase.folder_id == PathologyFolder.id
    ).filter(PatientCase.specialty == 'kine', Student.ecos_type == 'kine')
    if request.args.get('q'):
        term = f"%{request.args['q'].strip()}%"
        query = query.filter(db.or_(
            Student.name.ilike(term), Student.student_code.ilike(term),
            Student.group_name.ilike(term), Student.class_name.ilike(term),
        ))
    if request.args.get('folder_id'):
        query = query.filter(PatientCase.folder_id == int(request.args['folder_id']))
    if request.args.get('case_id'):
        query = query.filter(PatientCase.id == int(request.args['case_id']))
    if request.args.get('mode') in ('training', 'exam'):
        query = query.filter(SimulationSession.mode == request.args['mode'])
    if request.args.get('group'):
        query = query.filter(Student.group_name == request.args['group'])
    if request.args.get('class_name'):
        query = query.filter(Student.class_name == request.args['class_name'])
    if request.args.get('from'):
        query = query.filter(SimulationSession.started_at >= datetime.fromisoformat(request.args['from']))
    if request.args.get('to'):
        query = query.filter(SimulationSession.started_at < datetime.fromisoformat(request.args['to']).replace(hour=23, minute=59, second=59))
    return query.order_by(SimulationSession.started_at.desc())


def _export_row(simulation, student, case, folder):
    result = simulation.evaluation_results or {}
    duration = max(0, ((simulation.completed_at or datetime.utcnow()) - simulation.started_at).total_seconds()
                   - (simulation.total_paused_seconds or 0)) / 60
    return {
        'student_name': student.name, 'student_code': student.student_code,
        'student_level': student.level, 'group': student.group_name or '',
        'class_name': student.class_name or '',
        'folder_name': folder.name if folder else '', 'case_number': case.case_number,
        'mode': simulation.mode, 'started_at': simulation.started_at,
        'completed_at': simulation.completed_at, 'duration_minutes': round(duration, 1),
        'phase_timings': simulation.phase_timings or {},
        'vital_measurements': result.get(
            'vital_measurements',
            (simulation.runtime_state or {}).get('obtained_vital_parameters', []),
        ),
        'raw_score': result.get('raw_points_earned', ''), 'score': result.get('points_earned', ''),
        'passed': result.get('passed', ''),
        'eliminatory_error_triggered': simulation.eliminatory_error_triggered or result.get('eliminatory_error_triggered', False),
        'eliminatory_errors': result.get('eliminatory_errors', []), 'status': simulation.status,
    }


def _student_report_identity(student):
    """Return a stable, French-labelled identity block for Kiné reports."""
    return {
        'name': (student.name or '').strip() or f"Étudiant {student.student_code}",
        'student_code': student.student_code,
        'level': {'licence': 'Licence', 'master': 'Master'}.get(
            student.level, student.level or 'Non renseigné'
        ),
        'group_name': student.group_name or '',
        'class_name': student.class_name or '',
    }


def _report_evaluation(simulation):
    report = dict(simulation.evaluation_results or {})
    report.update({
        'student': _student_report_identity(simulation.student),
        'supplementary_score': simulation.supplementary_score,
        'teacher_comments': simulation.teacher_comments,
        'vital_measurements': report.get(
            'vital_measurements',
            (simulation.runtime_state or {}).get('obtained_vital_parameters', []),
        ),
    })
    return report


@kine_bp.route('/dashboard')
@teacher_required
def teacher_dashboard():
    try:
        records = _dashboard_query().all()
    except (TypeError, ValueError):
        return error('Filtre du tableau de bord invalide.')
    export_rows = [_export_row(*record) for record in records]
    unique_students = {record[1].id: record[1] for record in records}
    scored = [row['score'] for row in export_rows if isinstance(row['score'], (int, float))]
    stats = {
        'student_count': len(unique_students), 'simulation_count': len(records),
        'average_score': round(sum(scored) / len(scored), 1) if scored else 0,
        'average_duration': round(sum(row['duration_minutes'] for row in export_rows) / len(export_rows), 1) if export_rows else 0,
    }
    if wants_json():
        return jsonify({'stats': stats, 'sessions': export_rows})

    student_rows = []
    total_cases = PatientCase.query.filter_by(specialty='kine').count()
    for student in unique_students.values():
        own = [record for record in records if record[1].id == student.id]
        completed_case_ids = {record[0].clinical_case_id for record in own if record[0].status == 'completed'}
        folders_for_student = sorted({record[3].name for record in own if record[3]})
        own_durations = [_export_row(*record)['duration_minutes'] for record in own]
        attempts_by_case = defaultdict(int)
        for record in own:
            attempts_by_case[record[2].case_number] += 1
        student_rows.append({
            'name': student.name, 'student_code': student.student_code, 'level': student.level,
            'group': student.group_name or '—', 'class_name': student.class_name or '—',
            'folder_name': ', '.join(folders_for_student) or '—',
            'completed_cases': len(completed_case_ids), 'total_cases': total_cases,
            'in_progress_cases': sum(record[0].status == 'in_progress' for record in own),
            'attempt_count': len(own),
            'total_time': f"{round(sum(own_durations), 1)} min",
            'average_time': round(sum(own_durations) / len(own_durations), 1) if own_durations else 0,
            'attempts_by_case': dict(attempts_by_case),
            'last_login': student.last_login, 'progress': round(len(completed_case_ids) / total_cases * 100) if total_cases else 0,
            'detail_url': url_for('kine.dashboard_student', student_id=student.id),
        })
    session_rows = [{
        'id': simulation.id,
        'student_name': student.name, 'case_number': case.case_number, 'mode': simulation.mode,
        'started_at': simulation.started_at, 'duration': f"{_export_row(simulation, student, case, folder)['duration_minutes']} min",
        'phase_summary': ', '.join((simulation.phase_timings or {}).keys()),
        'score': (simulation.evaluation_results or {}).get('points_earned'), 'status': simulation.status,
        'passed': (simulation.evaluation_results or {}).get('passed'),
        'message_count': len(simulation.conversation or []),
        'supplementary_score': simulation.supplementary_score,
        'teacher_comments': simulation.teacher_comments,
        'reviewed_at': simulation.reviewed_at,
        'detail_url': url_for('kine.dashboard_simulation', session_id=simulation.id),
        'pdf_url': url_for('kine.dashboard_simulation_pdf', session_id=simulation.id),
    } for simulation, student, case, folder in records]
    chronological = list(reversed(records))
    score_series = [
        {'label': f"{student.name} · {case.case_number}",
         'value': (simulation.evaluation_results or {}).get('points_earned'),
         'date': simulation.started_at.isoformat()}
        for simulation, student, case, folder in chronological
        if isinstance((simulation.evaluation_results or {}).get('points_earned'), (int, float))
    ]
    duration_series = [
        {'label': f"{student.name} · {case.case_number}",
         'value': _export_row(simulation, student, case, folder)['duration_minutes'],
         'date': simulation.started_at.isoformat()}
        for simulation, student, case, folder in chronological
    ]
    competency_totals = defaultdict(lambda: [0.0, 0.0])
    for simulation, _, _, _ in records:
        for section in (simulation.evaluation_results or {}).get('section_scores', []):
            key = section.get('title') or section.get('criterion') or section.get('id', 'Competency')
            competency_totals[key][0] += float(section.get('points_earned') or 0)
            competency_totals[key][1] += float(section.get('points_possible') or 0)
    competencies = [
        {'name': name, 'percentage': round(earned / possible * 100) if possible else 0}
        for name, (earned, possible) in competency_totals.items()
    ]
    comparisons = []
    for student in unique_students.values():
        own_scores = [(record[0].evaluation_results or {}).get('points_earned') for record in records if record[1].id == student.id]
        own_scores = [score for score in own_scores if isinstance(score, (int, float))]
        comparisons.append({'name': student.name, 'average_score': round(sum(own_scores) / len(own_scores), 1) if own_scores else 0,
                            'simulations': sum(record[1].id == student.id for record in records)})
    export_args = {key: value for key, value in request.args.items() if key != 'format'}
    return render_template(
        'teacher_dashboard_kine.html', stats=stats, students=student_rows, sessions=session_rows,
        folders=PathologyFolder.query.filter_by(specialty='kine').all(),
        cases=PatientCase.query.filter_by(specialty='kine').order_by(PatientCase.is_archived, PatientCase.case_number).all(),
        active_cases=PatientCase.query.filter(
            PatientCase.specialty == 'kine', PatientCase.is_archived.is_(False),
            PatientCase.mode_availability.in_(['exam', 'both']),
        ).order_by(PatientCase.case_number).all(),
        all_students=Student.query.filter_by(ecos_type='kine').order_by(Student.name).all(),
        exams=Exam.query.order_by(Exam.start_at.desc()).all(),
        groups=[value[0] for value in db.session.query(Student.group_name).filter(Student.ecos_type == 'kine', Student.group_name.isnot(None)).distinct().all()],
        classes=[value[0] for value in db.session.query(Student.class_name).filter(Student.ecos_type == 'kine', Student.class_name.isnot(None)).distinct().all()],
        competencies=competencies, comparisons=comparisons,
        score_series=score_series, duration_series=duration_series, filters=request.args,
        export_csv_url=url_for('kine.dashboard_export', format='csv', **export_args),
        export_excel_url=url_for('kine.dashboard_export', format='xlsx', **export_args),
    )


@kine_bp.route('/dashboard/conversations/pdf', methods=['POST'])
@teacher_required
def dashboard_conversations_pdf():
    values = request.form.getlist('session_ids') if not request.is_json else (request.get_json(silent=True) or {}).get('session_ids', [])
    try:
        session_ids = [int(value) for value in values]
    except (TypeError, ValueError):
        return error('Sélection de conversations invalide.')
    simulations = SimulationSession.query.filter(
        SimulationSession.id.in_(session_ids), SimulationSession.evaluation_results.isnot(None)
    ).all() if session_ids else []
    if not simulations:
        return error('Sélectionnez au moins une conversation évaluée.', 400)
    archive = BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for simulation in simulations:
            report_evaluation = _report_evaluation(simulation)
            filename = create_simple_consultation_pdf(
                simulation.conversation or [], simulation.clinical_case.case_number,
                report_evaluation,
            )
            path = os.path.join(tempfile.gettempdir(), filename)
            if filename and os.path.exists(path):
                bundle.write(path, f"{simulation.student.student_code}_{filename}")
    archive.seek(0)
    return send_file(archive, mimetype='application/zip', as_attachment=True,
                     download_name=f"conversations_kine_{datetime.now().strftime('%Y%m%d_%H%M')}.zip")


@kine_bp.route('/dashboard/simulation/<int:session_id>/review', methods=['POST'])
@teacher_required
def dashboard_simulation_review(session_id):
    simulation = SimulationSession.query.get_or_404(session_id)
    if simulation.clinical_case.specialty != 'kine':
        return error('Simulation Kiné introuvable.', 404)
    data = request.get_json(silent=True) or request.form
    score = data.get('supplementary_score')
    if score not in (None, ''):
        try:
            score = float(score)
        except (TypeError, ValueError):
            return error("La note complémentaire doit être un nombre entre 0 et 20.")
        if not 0 <= score <= 20:
            return error("La note complémentaire doit être comprise entre 0 et 20.")
        simulation.supplementary_score = score
    else:
        simulation.supplementary_score = None
    simulation.teacher_comments = str(data.get('teacher_comments') or '').strip() or None
    simulation.reviewed_by = session.get('teacher_id')
    simulation.reviewed_at = datetime.utcnow()
    append_timeline_event(
        simulation, 'teacher_feedback_saved', actor='teacher',
        phase=simulation.current_phase,
        details={'supplementary_score': simulation.supplementary_score,
                 'has_comment': bool(simulation.teacher_comments)},
        timestamp=simulation.reviewed_at,
    )
    db.session.commit()
    if wants_json():
        return jsonify({'id': simulation.id, 'supplementary_score': simulation.supplementary_score,
                        'teacher_comments': simulation.teacher_comments,
                        'reviewed_at': simulation.reviewed_at.isoformat() + 'Z'})
    flash('L’évaluation complémentaire a bien été enregistrée et est maintenant visible par l’étudiant.', 'success')
    return redirect(url_for('kine.dashboard_simulation', session_id=simulation.id) + '#evaluation-enseignant')


@kine_bp.route('/dashboard/export')
@teacher_required
def dashboard_export():
    try:
        rows = [_export_row(*record) for record in _dashboard_query().all()]
    except (TypeError, ValueError):
        return error('Filtre du tableau de bord invalide.')
    export_format = request.args.get('format', 'csv').lower()
    if export_format == 'csv':
        path = export_kine_dashboard_csv(rows)
        mimetype = 'text/csv'
    elif export_format in ('xlsx', 'excel'):
        path = export_kine_dashboard_excel(rows)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        return error("Export format must be 'csv' or 'xlsx'")
    return send_file(path, mimetype=mimetype, as_attachment=True, download_name=path.rsplit('\\', 1)[-1].rsplit('/', 1)[-1])


@kine_bp.route('/dashboard/student/<int:student_id>')
@teacher_required
def dashboard_student(student_id):
    student = Student.query.get_or_404(student_id)
    sessions = SimulationSession.query.filter_by(student_id=student.id).order_by(SimulationSession.started_at.desc()).all()
    return jsonify({'student': {'id': student.id, 'name': student.name, 'level': student.level},
                    'sessions': [{'id': item.id, 'case_number': item.clinical_case.case_number,
                                  'mode': item.mode, 'status': item.status,
                                  'score': (item.evaluation_results or {}).get('points_earned')} for item in sessions]})


@kine_bp.route('/dashboard/simulation/<int:session_id>')
@kine_staff_required
def dashboard_simulation(session_id):
    simulation = SimulationSession.query.get_or_404(session_id)
    if simulation.clinical_case.specialty != 'kine':
        return error('Not a kine simulation', 404)
    progression = ProgressionTracker(
        simulation, student=simulation.student
    ).to_frontend()
    if wants_json():
        formatted_timeline = format_timeline(simulation.timeline or [], request.args.get('timezone', 'Africa/Casablanca'))
        return jsonify({'id': simulation.id,
                        'student': _student_report_identity(simulation.student),
                        'conversation': simulation.conversation or [],
                        'timeline': formatted_timeline, 'phase_timings': simulation.phase_timings or {},
                        'progression': progression,
                        'evaluation_results': simulation.evaluation_results,
                        'supplementary_score': simulation.supplementary_score,
                        'teacher_comments': simulation.teacher_comments,
                        'reviewed_at': simulation.reviewed_at.isoformat() + 'Z' if simulation.reviewed_at else None})
    return render_template('timeline_view.html', simulation=simulation, student=simulation.student,
                           timeline=format_timeline(simulation.timeline or [], request.args.get('timezone', 'Africa/Casablanca')),
                           progression=progression,
                           pdf_url=url_for('kine.dashboard_simulation_pdf', session_id=simulation.id),
                           review_url=url_for('kine.dashboard_simulation_review', session_id=simulation.id))


@kine_bp.route('/dashboard/simulation/<int:session_id>/pdf')
@kine_staff_required
def dashboard_simulation_pdf(session_id):
    simulation = SimulationSession.query.get_or_404(session_id)
    if simulation.clinical_case.specialty != 'kine' or not simulation.evaluation_results:
        return error('Évaluation Kiné terminée introuvable.', 404)
    report_evaluation = _report_evaluation(simulation)
    filename = create_simple_consultation_pdf(
        simulation.conversation or [], simulation.clinical_case.case_number,
        report_evaluation,
    )
    if not filename:
        return error('La génération du PDF a échoué.', 500)
    return send_file(os.path.join(tempfile.gettempdir(), filename), as_attachment=True,
                     download_name=filename, mimetype='application/pdf')
