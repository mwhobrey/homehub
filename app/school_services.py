"""School domain services: audit, gradebook, analytics, submission helpers."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from flask import current_app

from .models import (
    Assignment,
    AssignmentCategory,
    AttendanceRecord,
    Enrollment,
    GradeEntry,
    SchoolAuditLog,
    SchoolClass,
    Submission,
    db,
)
from .school_permissions import configured_teachers
from .security import sanitize_html, sanitize_text


ASSIGNMENT_STATUSES = ('draft', 'assigned', 'closed')
SUBMISSION_STATUSES = (
    'not_started', 'in_progress', 'submitted', 'needs_revision',
    'graded', 'completed',
)
ATTENDANCE_STATUSES = ('present', 'absent', 'late', 'excused')


def school_feature_enabled() -> bool:
    toggles = (current_app.config.get('HOMEHUB_CONFIG') or {}).get('feature_toggles') or {}
    return bool(toggles.get('school', True))


def parse_due_at(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == '%Y-%m-%d':
                return dt.replace(hour=23, minute=59)
            return dt
        except ValueError:
            continue
    return None


def validate_submission_url(url: str) -> str | None:
    url = sanitize_text(url).strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return None
    if not parsed.netloc:
        return None
    return url


def audit_log(actor: str, action: str, entity_type: str, entity_id: int | None,
              before: dict | None = None, after: dict | None = None) -> None:
    row = SchoolAuditLog(
        actor=actor or '',
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=json.dumps(before) if before is not None else None,
        after_json=json.dumps(after) if after is not None else None,
    )
    db.session.add(row)


def get_or_create_submission(assignment: Assignment, student_id: str) -> Submission:
    sub = Submission.query.filter_by(
        assignment_id=assignment.id,
        student_id=student_id,
        attempt_number=1,
    ).first()
    if sub:
        return sub
    sub = Submission(assignment_id=assignment.id, student_id=student_id, status='not_started')
    db.session.add(sub)
    db.session.flush()
    return sub


def compute_is_late(assignment: Assignment, submitted_at: datetime | None) -> bool:
    if not submitted_at or not assignment.due_at:
        return False
    return submitted_at > assignment.due_at


def compute_missing_flag(assignment: Assignment, submission: Submission | None) -> bool:
    if assignment.status != 'assigned' and assignment.visibility != 'assigned':
        return False
    if not assignment.due_at:
        return False
    if submission and submission.status in ('submitted', 'graded', 'completed', 'needs_revision'):
        return False
    return datetime.utcnow() > assignment.due_at


def class_teacher_ids(cls: SchoolClass) -> list[str]:
    """All teachers for a class (primary + teacher/assistant enrollments)."""
    names: list[str] = []
    if cls.teacher_id:
        names.append(cls.teacher_id)
    rows = Enrollment.query.filter_by(class_id=cls.id).filter(
        Enrollment.role.in_(('teacher', 'assistant'))
    ).all()
    for row in rows:
        if row.student_id and row.student_id not in names:
            names.append(row.student_id)
    return names


def sync_class_teachers(cls: SchoolClass, teacher_ids: list[str], *, actor: str = '') -> None:
    """Set primary teacher_id and teacher enrollments from a multi-select list."""
    cleaned: list[str] = []
    for raw in teacher_ids or []:
        name = sanitize_text(str(raw)).strip()
        if name and name not in cleaned:
            cleaned.append(name)
    if not cleaned and actor:
        cleaned = [actor]
    if not cleaned:
        raise ValueError('teachers_required')
    cls.teacher_id = cleaned[0]
    want = set(cleaned)
    existing = Enrollment.query.filter_by(class_id=cls.id).filter(
        Enrollment.role.in_(('teacher', 'assistant'))
    ).all()
    existing_by_name = {e.student_id: e for e in existing}
    for name in want:
        if name not in existing_by_name:
            db.session.add(Enrollment(class_id=cls.id, student_id=name, role='teacher'))
    for enr in existing:
        if enr.student_id not in want:
            db.session.delete(enr)


def parse_student_ids_payload(data: dict) -> list[str]:
    if 'student_ids' in data and data['student_ids'] is not None:
        raw = data['student_ids']
        if isinstance(raw, str):
            return [sanitize_text(raw).strip()] if sanitize_text(raw).strip() else []
        if isinstance(raw, (list, tuple)):
            return [sanitize_text(str(x)).strip() for x in raw if sanitize_text(str(x)).strip()]
    if data.get('student_id'):
        name = sanitize_text(data['student_id']).strip()
        return [name] if name else []
    return []


def sync_class_students(class_id: int, student_ids: list[str]) -> list[str]:
    """Enroll students (role=student); skip duplicates. Returns newly enrolled ids."""
    cleaned: list[str] = []
    for raw in student_ids or []:
        name = sanitize_text(str(raw)).strip()
        if name and name not in cleaned:
            cleaned.append(name)
    if not cleaned:
        return []
    enrolled: list[str] = []
    for name in cleaned:
        existing = Enrollment.query.filter_by(class_id=class_id, student_id=name, role='student').first()
        if existing:
            continue
        db.session.add(Enrollment(class_id=class_id, student_id=name, role='student'))
        enrolled.append(name)
    return enrolled


def parse_teacher_ids_payload(data: dict, *, actor: str = '') -> list[str]:
    if 'teacher_ids' in data and data['teacher_ids'] is not None:
        raw = data['teacher_ids']
        if isinstance(raw, str):
            return [sanitize_text(raw).strip()] if sanitize_text(raw).strip() else []
        if isinstance(raw, (list, tuple)):
            return [sanitize_text(str(x)).strip() for x in raw if sanitize_text(str(x)).strip()]
    if data.get('teacher_id'):
        name = sanitize_text(data['teacher_id']).strip()
        return [name] if name else []
    configured = sorted(configured_teachers())
    if configured:
        return configured
    return [actor] if actor else []


def serialize_class(cls: SchoolClass) -> dict[str, Any]:
    teachers = class_teacher_ids(cls)
    return {
        'id': cls.id,
        'name': cls.name,
        'subject': cls.subject or '',
        'term': cls.term or '',
        'teacher_id': cls.teacher_id,
        'teacher_ids': teachers,
        'archived': bool(cls.archived),
        'schedule': json.loads(cls.schedule_json or '{}'),
    }


def serialize_assignment(a: Assignment) -> dict[str, Any]:
    return {
        'id': a.id,
        'class_id': a.class_id,
        'category_id': a.category_id,
        'title': a.title,
        'instructions_html': a.instructions_html or '',
        'due_at': a.due_at.isoformat() if a.due_at else None,
        'assigned_at': a.assigned_at.isoformat() if a.assigned_at else None,
        'points_possible': a.points_possible,
        'allow_late': bool(a.allow_late),
        'visibility': a.visibility,
        'status': a.status,
        'creator': a.creator,
    }


def serialize_submission(s: Submission, assignment: Assignment | None = None) -> dict[str, Any]:
    assignment = assignment or Assignment.query.get(s.assignment_id)
    missing = compute_missing_flag(assignment, s) if assignment else False
    grade = s.grade
    return {
        'id': s.id,
        'assignment_id': s.assignment_id,
        'student_id': s.student_id,
        'status': s.status,
        'submitted_at': s.submitted_at.isoformat() if s.submitted_at else None,
        'is_late': bool(s.is_late),
        'is_missing': missing,
        'attempt_number': s.attempt_number,
        'student_note': s.student_note or '',
        'grade': {
            'score': grade.score if grade else None,
            'feedback_html': grade.feedback_html if grade else '',
            'revision_requested': bool(grade.revision_requested) if grade else False,
            'completed': bool(grade.completed) if grade else False,
            'graded_at': grade.graded_at.isoformat() if grade and grade.graded_at else None,
        } if grade else None,
    }


def weighted_gradebook(class_id: int) -> dict[str, Any]:
    """Per-student weighted average by assignment category."""
    categories = AssignmentCategory.query.filter_by(class_id=class_id).all()
    cat_weights = {c.id: float(c.weight_percent or 0) for c in categories}
    total_weight = sum(cat_weights.values()) or 0.0

    students = [
        e.student_id for e in Enrollment.query.filter_by(class_id=class_id, role='student').all()
    ]
    assignments = Assignment.query.filter_by(class_id=class_id).filter(
        Assignment.status.in_(('assigned', 'closed'))
    ).all()

    rows: dict[str, dict[str, Any]] = {}
    for sid in students:
        rows[sid] = {'student_id': sid, 'categories': {}, 'overall_percent': None}

    for a in assignments:
        for sid in students:
            sub = Submission.query.filter_by(assignment_id=a.id, student_id=sid, attempt_number=1).first()
            if not sub or not sub.grade or sub.grade.score is None:
                continue
            cat_id = a.category_id or 0
            bucket = rows[sid]['categories'].setdefault(str(cat_id), {'scores': [], 'weight': cat_weights.get(cat_id, 0)})
            pct = (sub.grade.score / a.points_possible * 100.0) if a.points_possible else sub.grade.score
            bucket['scores'].append(pct)

    for sid, row in rows.items():
        weighted_sum = 0.0
        weight_used = 0.0
        flat_scores: list[float] = []
        for _cat_id, bucket in row['categories'].items():
            if not bucket['scores']:
                continue
            avg = sum(bucket['scores']) / len(bucket['scores'])
            flat_scores.append(avg)
            w = float(bucket['weight'] or 0)
            if total_weight > 0 and w > 0:
                weighted_sum += avg * (w / total_weight)
                weight_used += w
        if weight_used > 0:
            row['overall_percent'] = round(weighted_sum, 2)
        elif flat_scores:
            row['overall_percent'] = round(sum(flat_scores) / len(flat_scores), 2)

    return {
        'class_id': class_id,
        'categories': [{'id': c.id, 'name': c.name, 'weight_percent': c.weight_percent} for c in categories],
        'students': list(rows.values()),
    }


def class_analytics(class_id: int) -> dict[str, Any]:
    assignments = Assignment.query.filter_by(class_id=class_id).filter(
        Assignment.status.in_(('assigned', 'closed'))
    ).all()
    students = Enrollment.query.filter_by(class_id=class_id, role='student').count()
    total_assignments = len(assignments)
    submitted = 0
    late = 0
    missing = 0
    graded = 0
    for a in assignments:
        for enr in Enrollment.query.filter_by(class_id=class_id, role='student').all():
            sub = Submission.query.filter_by(
                assignment_id=a.id, student_id=enr.student_id, attempt_number=1
            ).first()
            if sub and sub.status in ('submitted', 'graded', 'completed', 'needs_revision'):
                submitted += 1
                if sub.is_late:
                    late += 1
            elif compute_missing_flag(a, sub):
                missing += 1
            if sub and sub.grade and sub.grade.score is not None:
                graded += 1

    denom = max(1, total_assignments * max(1, students))
    attendance = AttendanceRecord.query.filter_by(class_id=class_id).all()
    present = sum(1 for r in attendance if r.status == 'present')
    att_total = len(attendance) or 1

    return {
        'class_id': class_id,
        'students': students,
        'assignments': total_assignments,
        'submission_rate': round(submitted / denom, 3),
        'late_count': late,
        'missing_count': missing,
        'graded_count': graded,
        'attendance_present_rate': round(present / att_total, 3),
    }


def dashboard_summary(actor: str, class_ids: list[int]) -> dict[str, Any]:
    due_soon = []
    missing = []
    needs_grading = []
    now = datetime.utcnow()
    for cid in class_ids:
        cls = SchoolClass.query.get(cid)
        if not cls:
            continue
        q = Assignment.query.filter_by(class_id=cid, status='assigned')
        for a in q.all():
            subs = Submission.query.filter_by(assignment_id=a.id).all()
            for sub in subs:
                if sub.status == 'submitted' and (not sub.grade or sub.grade.score is None):
                    needs_grading.append({'class': cls.name, 'assignment_id': a.id, 'title': a.title, 'student_id': sub.student_id})
            for enr in Enrollment.query.filter_by(class_id=cid, role='student').all():
                if enr.student_id != actor and actor not in (cls.teacher_id,):
                    pass
                sub = Submission.query.filter_by(assignment_id=a.id, student_id=enr.student_id, attempt_number=1).first()
                if compute_missing_flag(a, sub):
                    missing.append({'class': cls.name, 'assignment_id': a.id, 'title': a.title})
                if a.due_at and a.due_at >= now and (a.due_at - now).days <= 7:
                    if enr.student_id == actor or actor == cls.teacher_id:
                        due_soon.append({'class': cls.name, 'assignment_id': a.id, 'title': a.title, 'due_at': a.due_at.isoformat()})
    return {
        'due_soon': due_soon[:20],
        'missing': missing[:20],
        'needs_grading': needs_grading[:20],
    }


def sanitize_assignment_html(html: str) -> str:
    return sanitize_html(html or '')
