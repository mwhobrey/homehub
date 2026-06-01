"""School module: classes, assignments, submissions, grading, attendance, analytics."""

from __future__ import annotations

import json
import os
from datetime import date, datetime

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from ..blueprints import main_bp
from ..models import (
    Assignment,
    AssignmentCategory,
    AttendanceRecord,
    Enrollment,
    File,
    GradeEntry,
    SchoolClass,
    Submission,
    SubmissionArtifact,
    db,
)
from ..school_permissions import (
    actor_name,
    can_manage_class,
    can_view_class,
    can_view_student_work,
    is_school_admin,
    school_role_label,
    visible_class_ids,
)
from ..school_services import (
    ASSIGNMENT_STATUSES,
    ATTENDANCE_STATUSES,
    SUBMISSION_STATUSES,
    audit_log,
    class_analytics,
    compute_is_late,
    dashboard_summary,
    get_or_create_submission,
    parse_due_at,
    sanitize_assignment_html,
    school_feature_enabled,
    serialize_assignment,
    serialize_class,
    serialize_submission,
    validate_submission_url,
    weighted_gradebook,
)
from ..security import safe_basename_filename, sanitize_text
from ..user_context import resolve_actor

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')


def _api_err(code: str, status: int = 400):
    return jsonify({'ok': False, 'error': code}), status


def _api_ok(**payload):
    out = {'ok': True}
    out.update(payload)
    return jsonify(out)


def _require_school():
    if not school_feature_enabled():
        abort(404)
    name = actor_name()
    if not name:
        return None
    return name


@main_bp.route('/school')
def school_index():
    if not school_feature_enabled():
        abort(404)
    actor = actor_name()
    if not actor:
        flash('Select or sign in as a user to use School.', 'error')
        return redirect(url_for('main.index'))
    config = current_app.config['HOMEHUB_CONFIG']
    class_ids = visible_class_ids(actor)
    classes = SchoolClass.query.filter(SchoolClass.id.in_(class_ids)).order_by(SchoolClass.name).all() if class_ids else []
    summary = dashboard_summary(actor, class_ids)
    role = school_role_label(actor)
    family = config.get('family_members') or []
    school_cfg = config.get('school') or {}
    return render_template(
        'school/index.html',
        config=config,
        classes=classes,
        summary=summary,
        school_role=role,
        family_members=family,
        school_cfg=school_cfg,
        is_school_admin=is_school_admin(actor),
    )


@main_bp.route('/school/class/<int:class_id>')
def school_class_detail(class_id):
    if not school_feature_enabled():
        abort(404)
    actor = actor_name()
    if not actor or not can_view_class(class_id, actor):
        abort(403)
    cls = SchoolClass.query.get_or_404(class_id)
    assignments = Assignment.query.filter_by(class_id=class_id).order_by(Assignment.due_at.desc()).all()
    enrollments = Enrollment.query.filter_by(class_id=class_id).all()
    categories = AssignmentCategory.query.filter_by(class_id=class_id).all()
    can_manage = can_manage_class(class_id, actor)
    config = current_app.config['HOMEHUB_CONFIG']
    return render_template(
        'school/class_detail.html',
        config=config,
        school_class=cls,
        assignments=assignments,
        enrollments=enrollments,
        categories=categories,
        can_manage=can_manage,
        school_role=school_role_label(actor),
        family_members=config.get('family_members') or [],
        today=date.today().isoformat(),
    )


@main_bp.route('/school/assignment/<int:assignment_id>')
def school_assignment_detail(assignment_id):
    if not school_feature_enabled():
        abort(404)
    actor = actor_name()
    assignment = Assignment.query.get_or_404(assignment_id)
    if not can_view_class(assignment.class_id, actor):
        abort(403)
    cls = SchoolClass.query.get_or_404(assignment.class_id)
    can_manage = can_manage_class(assignment.class_id, actor)
    student_id = actor
    if can_manage and request.args.get('student'):
        student_id = sanitize_text(request.args.get('student'))
    elif not can_manage:
        student_id = actor
    if not can_view_student_work(assignment.class_id, student_id, actor):
        abort(403)
    submission = get_or_create_submission(assignment, student_id)
    db.session.commit()
    artifacts = SubmissionArtifact.query.filter_by(submission_id=submission.id).all()
    students = [e.student_id for e in Enrollment.query.filter_by(class_id=assignment.class_id, role='student').all()]
    config = current_app.config['HOMEHUB_CONFIG']
    return render_template(
        'school/assignment_detail.html',
        config=config,
        school_class=cls,
        assignment=assignment,
        submission=submission,
        artifacts=artifacts,
        can_manage=can_manage,
        students=students,
        viewing_student=student_id,
        school_role=school_role_label(actor),
    )


@main_bp.route('/school/class/<int:class_id>/gradebook')
def school_gradebook_page(class_id):
    if not school_feature_enabled():
        abort(404)
    actor = actor_name()
    if not actor or not can_view_class(class_id, actor):
        abort(403)
    cls = SchoolClass.query.get_or_404(class_id)
    book = weighted_gradebook(class_id)
    config = current_app.config['HOMEHUB_CONFIG']
    return render_template(
        'school/gradebook.html',
        config=config,
        school_class=cls,
        gradebook=book,
        can_manage=can_manage_class(class_id, actor),
    )


# --- JSON API ---


@main_bp.route('/api/school/classes', methods=['GET', 'POST'])
def api_school_classes():
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if request.method == 'GET':
        ids = visible_class_ids(actor)
        rows = SchoolClass.query.filter(SchoolClass.id.in_(ids)).order_by(SchoolClass.name).all() if ids else []
        return _api_ok(classes=[serialize_class(c) for c in rows])
    from ..school_permissions import is_configured_teacher, teaches_any
    if not (is_school_admin(actor) or is_configured_teacher(actor) or teaches_any(actor)):
        return _api_err('forbidden', 403)
    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name', '')).strip()
    if not name:
        return _api_err('name_required')
    cls = SchoolClass(
        name=name,
        subject=sanitize_text(data.get('subject', '')),
        term=sanitize_text(data.get('term', '')),
        teacher_id=sanitize_text(data.get('teacher_id') or actor),
        schedule_json=json.dumps(data.get('schedule') or {}),
        creator=resolve_actor(json_payload=data),
    )
    db.session.add(cls)
    db.session.flush()
    audit_log(actor, 'create', 'school_class', cls.id, after=serialize_class(cls))
    db.session.commit()
    return _api_ok(class_=serialize_class(cls))


@main_bp.route('/api/school/classes/<int:class_id>', methods=['GET', 'PATCH', 'DELETE'])
def api_school_class(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    cls = SchoolClass.query.get_or_404(class_id)
    if request.method == 'GET':
        if not can_view_class(class_id, actor):
            return _api_err('forbidden', 403)
        return _api_ok(class_=serialize_class(cls))
    if not can_manage_class(class_id, actor):
        return _api_err('forbidden', 403)
    if request.method == 'DELETE':
        before = serialize_class(cls)
        db.session.delete(cls)
        audit_log(actor, 'delete', 'school_class', class_id, before=before)
        db.session.commit()
        return _api_ok()
    data = request.get_json(silent=True) or {}
    before = serialize_class(cls)
    if 'name' in data:
        cls.name = sanitize_text(data['name']).strip() or cls.name
    if 'subject' in data:
        cls.subject = sanitize_text(data.get('subject', ''))
    if 'term' in data:
        cls.term = sanitize_text(data.get('term', ''))
    if 'teacher_id' in data:
        cls.teacher_id = sanitize_text(data['teacher_id'])
    if 'archived' in data:
        cls.archived = bool(data['archived'])
    if 'schedule' in data:
        cls.schedule_json = json.dumps(data['schedule'] or {})
    audit_log(actor, 'update', 'school_class', class_id, before=before, after=serialize_class(cls))
    db.session.commit()
    return _api_ok(class_=serialize_class(cls))


@main_bp.route('/api/school/classes/<int:class_id>/enrollments', methods=['GET', 'POST'])
def api_school_enrollments(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if not can_view_class(class_id, actor):
        return _api_err('forbidden', 403)
    if request.method == 'GET':
        rows = Enrollment.query.filter_by(class_id=class_id).all()
        return _api_ok(enrollments=[{
            'id': r.id, 'student_id': r.student_id, 'role': r.role,
            'active_from': r.active_from.isoformat() if r.active_from else None,
            'active_to': r.active_to.isoformat() if r.active_to else None,
        } for r in rows])
    if not can_manage_class(class_id, actor):
        return _api_err('forbidden', 403)
    data = request.get_json(silent=True) or {}
    student_id = sanitize_text(data.get('student_id', '')).strip()
    if not student_id:
        return _api_err('student_required')
    role = sanitize_text(data.get('role', 'student')).strip() or 'student'
    if role not in ('student', 'teacher', 'assistant'):
        return _api_err('invalid_role')
    existing = Enrollment.query.filter_by(class_id=class_id, student_id=student_id).first()
    if existing:
        return _api_err('already_enrolled')
    enr = Enrollment(class_id=class_id, student_id=student_id, role=role)
    db.session.add(enr)
    audit_log(actor, 'enroll', 'school_enrollment', None, after={'class_id': class_id, 'student_id': student_id})
    db.session.commit()
    return _api_ok(enrollment={'id': enr.id, 'student_id': student_id, 'role': role})


@main_bp.route('/api/school/enrollments/<int:enrollment_id>', methods=['DELETE'])
def api_school_enrollment_delete(enrollment_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    enr = Enrollment.query.get_or_404(enrollment_id)
    if not can_manage_class(enr.class_id, actor):
        return _api_err('forbidden', 403)
    db.session.delete(enr)
    db.session.commit()
    return _api_ok()


@main_bp.route('/api/school/classes/<int:class_id>/categories', methods=['GET', 'POST'])
def api_school_categories(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if not can_view_class(class_id, actor):
        return _api_err('forbidden', 403)
    if request.method == 'GET':
        cats = AssignmentCategory.query.filter_by(class_id=class_id).all()
        return _api_ok(categories=[{
            'id': c.id, 'name': c.name, 'weight_percent': c.weight_percent, 'grading_policy': c.grading_policy,
        } for c in cats])
    if not can_manage_class(class_id, actor):
        return _api_err('forbidden', 403)
    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name', '')).strip()
    if not name:
        return _api_err('name_required')
    cat = AssignmentCategory(
        class_id=class_id,
        name=name,
        weight_percent=float(data.get('weight_percent') or 0),
        grading_policy=sanitize_text(data.get('grading_policy', 'points')),
    )
    db.session.add(cat)
    db.session.commit()
    return _api_ok(category={'id': cat.id, 'name': cat.name, 'weight_percent': cat.weight_percent})


@main_bp.route('/api/school/classes/<int:class_id>/assignments', methods=['GET', 'POST'])
def api_school_assignments(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if not can_view_class(class_id, actor):
        return _api_err('forbidden', 403)
    if request.method == 'GET':
        rows = Assignment.query.filter_by(class_id=class_id).order_by(Assignment.due_at.desc()).all()
        return _api_ok(assignments=[serialize_assignment(a) for a in rows])
    if not can_manage_class(class_id, actor):
        return _api_err('forbidden', 403)
    data = request.get_json(silent=True) or {}
    title = sanitize_text(data.get('title', '')).strip()
    if not title:
        return _api_err('title_required')
    status = sanitize_text(data.get('status', 'draft'))
    if status not in ASSIGNMENT_STATUSES:
        return _api_err('invalid_status')
    due_at = parse_due_at(data.get('due_at'))
    a = Assignment(
        class_id=class_id,
        category_id=data.get('category_id'),
        title=title,
        instructions_html=sanitize_assignment_html(data.get('instructions_html', '')),
        due_at=due_at,
        assigned_at=datetime.utcnow() if status == 'assigned' else None,
        points_possible=float(data.get('points_possible') or 100),
        allow_late=bool(data.get('allow_late', True)),
        visibility=status,
        status=status,
        creator=resolve_actor(json_payload=data),
    )
    db.session.add(a)
    db.session.flush()
    if status == 'assigned':
        for enr in Enrollment.query.filter_by(class_id=class_id, role='student').all():
            get_or_create_submission(a, enr.student_id)
    audit_log(actor, 'create', 'assignment', a.id, after=serialize_assignment(a))
    db.session.commit()
    return _api_ok(assignment=serialize_assignment(a))


@main_bp.route('/api/school/assignments/<int:assignment_id>', methods=['GET', 'PATCH', 'DELETE'])
def api_school_assignment(assignment_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    a = Assignment.query.get_or_404(assignment_id)
    if request.method == 'GET':
        if not can_view_class(a.class_id, actor):
            return _api_err('forbidden', 403)
        return _api_ok(assignment=serialize_assignment(a))
    if not can_manage_class(a.class_id, actor):
        return _api_err('forbidden', 403)
    if request.method == 'DELETE':
        audit_log(actor, 'delete', 'assignment', assignment_id)
        db.session.delete(a)
        db.session.commit()
        return _api_ok()
    data = request.get_json(silent=True) or {}
    before = serialize_assignment(a)
    if 'title' in data:
        a.title = sanitize_text(data['title']).strip() or a.title
    if 'instructions_html' in data:
        a.instructions_html = sanitize_assignment_html(data['instructions_html'])
    if 'due_at' in data:
        a.due_at = parse_due_at(data['due_at'])
        audit_log(actor, 'deadline_change', 'assignment', assignment_id, before={'due_at': before.get('due_at')}, after={'due_at': a.due_at.isoformat() if a.due_at else None})
    if 'points_possible' in data:
        a.points_possible = float(data['points_possible'])
    if 'allow_late' in data:
        a.allow_late = bool(data['allow_late'])
    if 'category_id' in data:
        a.category_id = data['category_id'] or None
    if 'status' in data:
        st = sanitize_text(data['status'])
        if st in ASSIGNMENT_STATUSES:
            a.status = st
            a.visibility = st
            if st == 'assigned' and not a.assigned_at:
                a.assigned_at = datetime.utcnow()
                for enr in Enrollment.query.filter_by(class_id=a.class_id, role='student').all():
                    get_or_create_submission(a, enr.student_id)
    audit_log(actor, 'update', 'assignment', assignment_id, before=before, after=serialize_assignment(a))
    db.session.commit()
    return _api_ok(assignment=serialize_assignment(a))


@main_bp.route('/api/school/assignments/<int:assignment_id>/submissions', methods=['GET'])
def api_school_submissions_list(assignment_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    a = Assignment.query.get_or_404(assignment_id)
    if not can_manage_class(a.class_id, actor):
        return _api_err('forbidden', 403)
    subs = Submission.query.filter_by(assignment_id=assignment_id).all()
    return _api_ok(submissions=[serialize_submission(s, a) for s in subs])


@main_bp.route('/api/school/assignments/<int:assignment_id>/submit', methods=['POST'])
def api_school_submit(assignment_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    a = Assignment.query.get_or_404(assignment_id)
    if a.status not in ('assigned',) and a.visibility != 'assigned':
        return _api_err('assignment_not_open')
    student_id = actor
    data = request.get_json(silent=True) or {}
    if data.get('student_id') and can_manage_class(a.class_id, actor):
        student_id = sanitize_text(data['student_id'])
    if not can_view_student_work(a.class_id, student_id, actor):
        return _api_err('forbidden', 403)
    if not Enrollment.query.filter_by(class_id=a.class_id, student_id=student_id, role='student').first():
        if student_id == actor and not can_manage_class(a.class_id, actor):
            return _api_err('not_enrolled')
    sub = get_or_create_submission(a, student_id)
    sub.student_note = sanitize_text(data.get('student_note', sub.student_note or ''))
    if data.get('status') == 'in_progress':
        sub.status = 'in_progress'
        db.session.commit()
        return _api_ok(submission=serialize_submission(sub, a))
    now = datetime.utcnow()
    if a.due_at and now > a.due_at and not a.allow_late:
        return _api_err('deadline_passed')
    sub.status = 'submitted'
    sub.submitted_at = now
    sub.is_late = compute_is_late(a, now)
    audit_log(actor, 'submit', 'submission', sub.id, after=serialize_submission(sub, a))
    db.session.commit()
    return _api_ok(submission=serialize_submission(sub, a))


@main_bp.route('/api/school/submissions/<int:submission_id>/artifacts', methods=['POST'])
def api_school_add_artifact(submission_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    sub = Submission.query.get_or_404(submission_id)
    a = Assignment.query.get_or_404(sub.assignment_id)
    if not can_view_student_work(a.class_id, sub.student_id, actor):
        return _api_err('forbidden', 403)
    if sub.student_id != actor and not can_manage_class(a.class_id, actor):
        return _api_err('forbidden', 403)

    if request.content_type and 'multipart/form-data' in request.content_type:
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return _api_err('file_required')
        filename = secure_filename(upload.filename)
        upload.save(os.path.join(UPLOAD_FOLDER, filename))
        db_file = File(filename=filename, creator=resolve_actor())
        db.session.add(db_file)
        db.session.flush()
        art = SubmissionArtifact(
            submission_id=sub.id,
            artifact_type='file',
            file_id=db_file.id,
            note=sanitize_text(request.form.get('note', '')),
        )
        db.session.add(art)
        if sub.status == 'not_started':
            sub.status = 'in_progress'
        db.session.commit()
        return _api_ok(artifact={'id': art.id, 'type': 'file', 'filename': filename, 'file_id': db_file.id})

    data = request.get_json(silent=True) or {}
    atype = sanitize_text(data.get('artifact_type', 'link'))
    if atype == 'link':
        url = validate_submission_url(data.get('url', ''))
        if not url:
            return _api_err('invalid_url')
        art = SubmissionArtifact(submission_id=sub.id, artifact_type='link', url=url, note=sanitize_text(data.get('note', '')))
    elif atype == 'text':
        art = SubmissionArtifact(
            submission_id=sub.id, artifact_type='text',
            note=sanitize_text(data.get('note', data.get('text', ''))),
        )
    else:
        return _api_err('invalid_artifact_type')
    db.session.add(art)
    if sub.status == 'not_started':
        sub.status = 'in_progress'
    db.session.commit()
    return _api_ok(artifact={'id': art.id, 'type': art.artifact_type})


@main_bp.route('/api/school/artifacts/<int:artifact_id>', methods=['DELETE'])
def api_school_delete_artifact(artifact_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    art = SubmissionArtifact.query.get_or_404(artifact_id)
    sub = Submission.query.get_or_404(art.submission_id)
    a = Assignment.query.get_or_404(sub.assignment_id)
    if sub.student_id != actor and not can_manage_class(a.class_id, actor):
        return _api_err('forbidden', 403)
    db.session.delete(art)
    db.session.commit()
    return _api_ok()


@main_bp.route('/api/school/submissions/<int:submission_id>/grade', methods=['POST', 'PATCH'])
def api_school_grade(submission_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    sub = Submission.query.get_or_404(submission_id)
    a = Assignment.query.get_or_404(sub.assignment_id)
    if not can_manage_class(a.class_id, actor):
        return _api_err('forbidden', 403)
    data = request.get_json(silent=True) or {}
    grade = sub.grade
    if not grade:
        grade = GradeEntry(submission_id=sub.id)
        db.session.add(grade)
    before = {'score': grade.score, 'revision_requested': grade.revision_requested}
    if 'score' in data:
        grade.score = float(data['score']) if data['score'] is not None else None
    if 'feedback_html' in data:
        grade.feedback_html = sanitize_assignment_html(data['feedback_html'])
    if 'revision_requested' in data:
        grade.revision_requested = bool(data['revision_requested'])
        if grade.revision_requested:
            sub.status = 'needs_revision'
    if 'completed' in data:
        grade.completed = bool(data['completed'])
        if grade.completed:
            sub.status = 'completed'
    if 'rubric' in data:
        grade.rubric_json = json.dumps(data['rubric'] or {})
    grade.graded_by = actor
    grade.graded_at = datetime.utcnow()
    if sub.status == 'submitted' or sub.status == 'needs_revision':
        sub.status = 'graded'
    audit_log(actor, 'grade', 'submission', sub.id, before=before, after={'score': grade.score})
    db.session.commit()
    return _api_ok(submission=serialize_submission(sub, a))


@main_bp.route('/api/school/classes/<int:class_id>/attendance', methods=['GET', 'POST'])
def api_school_attendance(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if not can_view_class(class_id, actor):
        return _api_err('forbidden', 403)
    if request.method == 'GET':
        day = request.args.get('date')
        q = AttendanceRecord.query.filter_by(class_id=class_id)
        if day:
            try:
                d = datetime.strptime(day, '%Y-%m-%d').date()
                q = q.filter_by(attendance_date=d)
            except ValueError:
                return _api_err('invalid_date')
        rows = q.all()
        return _api_ok(records=[{
            'id': r.id, 'student_id': r.student_id, 'date': r.attendance_date.isoformat(),
            'status': r.status, 'note': r.note or '',
        } for r in rows])
    if not can_manage_class(class_id, actor):
        return _api_err('forbidden', 403)
    data = request.get_json(silent=True) or {}
    records = data.get('records') or [data]
    out = []
    for rec in records:
        student_id = sanitize_text(rec.get('student_id', '')).strip()
        if not student_id:
            continue
        try:
            d = datetime.strptime(rec.get('date', ''), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return _api_err('invalid_date')
        status = sanitize_text(rec.get('status', 'present'))
        if status not in ATTENDANCE_STATUSES:
            return _api_err('invalid_status')
        row = AttendanceRecord.query.filter_by(
            class_id=class_id, student_id=student_id, attendance_date=d
        ).first()
        before = {'status': row.status} if row else None
        if not row:
            row = AttendanceRecord(class_id=class_id, student_id=student_id, attendance_date=d)
            db.session.add(row)
        row.status = status
        row.note = sanitize_text(rec.get('note', ''))
        row.marked_by = actor
        audit_log(actor, 'attendance', 'attendance', row.id, before=before, after={'status': status})
        out.append(row)
    db.session.commit()
    return _api_ok(count=len(out))


@main_bp.route('/api/school/classes/<int:class_id>/gradebook', methods=['GET'])
def api_school_gradebook(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if not can_view_class(class_id, actor):
        return _api_err('forbidden', 403)
    return _api_ok(gradebook=weighted_gradebook(class_id))


@main_bp.route('/api/school/classes/<int:class_id>/analytics', methods=['GET'])
def api_school_analytics(class_id):
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    if not can_view_class(class_id, actor):
        return _api_err('forbidden', 403)
    return _api_ok(analytics=class_analytics(class_id))


@main_bp.route('/api/school/dashboard', methods=['GET'])
def api_school_dashboard():
    actor = _require_school()
    if not actor:
        return _api_err('unauthorized', 401)
    ids = visible_class_ids(actor)
    return _api_ok(
        role=school_role_label(actor),
        class_ids=ids,
        summary=dashboard_summary(actor, ids),
    )
