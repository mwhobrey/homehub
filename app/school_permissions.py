"""School module role resolution and class-scoped authorization."""

from __future__ import annotations

from flask import current_app, request

from .models import Enrollment, SchoolClass
from .user_context import current_display_name, is_admin, resolve_actor, resolve_user_from_args


def _school_cfg() -> dict:
    return (current_app.config.get('HOMEHUB_CONFIG') or {}).get('school') or {}


def actor_name() -> str:
    data = request.get_json(silent=True) if request else None
    if data:
        name = resolve_actor(json_payload=data)
        if name:
            return name
    name = resolve_user_from_args()
    if name:
        return name
    name = resolve_actor()
    if name:
        return name
    return current_display_name() or ''


def configured_teachers() -> set[str]:
    return {str(x).strip() for x in (_school_cfg().get('teachers') or []) if str(x).strip()}


def configured_students() -> set[str]:
    return {str(x).strip() for x in (_school_cfg().get('students') or []) if str(x).strip()}


def parent_child_map() -> dict[str, set[str]]:
    raw = _school_cfg().get('parent_observers') or {}
    out: dict[str, set[str]] = {}
    for parent, children in raw.items():
        parent_name = str(parent).strip()
        if not parent_name:
            continue
        if isinstance(children, (list, tuple)):
            out[parent_name] = {str(c).strip() for c in children if str(c).strip()}
        elif children:
            out[parent_name] = {str(children).strip()}
    return out


def is_school_admin(actor: str | None = None) -> bool:
    if is_admin(actor):
        return True
    return False


def is_configured_teacher(actor: str | None = None) -> bool:
    name = actor or actor_name()
    return bool(name) and name in configured_teachers()


def is_configured_student(actor: str | None = None) -> bool:
    name = actor or actor_name()
    return bool(name) and name in configured_students()


def is_parent_observer(actor: str | None = None) -> bool:
    name = actor or actor_name()
    return bool(name) and name in parent_child_map()


def observed_children(actor: str | None = None) -> set[str]:
    name = actor or actor_name()
    return parent_child_map().get(name, set())


def teaches_class(class_id: int, actor: str | None = None) -> bool:
    name = actor or actor_name()
    if not name:
        return False
    cls = SchoolClass.query.get(class_id)
    if not cls:
        return False
    if cls.teacher_id == name:
        return True
    enr = Enrollment.query.filter_by(class_id=class_id, student_id=name).filter(
        Enrollment.role.in_(('teacher', 'assistant'))
    ).first()
    return enr is not None


def enrolled_in_class(class_id: int, actor: str | None = None) -> bool:
    name = actor or actor_name()
    if not name:
        return False
    return Enrollment.query.filter_by(class_id=class_id, student_id=name, role='student').first() is not None


def can_manage_class(class_id: int, actor: str | None = None) -> bool:
    if is_school_admin(actor):
        return True
    if is_configured_teacher(actor) and teaches_class(class_id, actor):
        return True
    return teaches_class(class_id, actor)


def can_view_class(class_id: int, actor: str | None = None) -> bool:
    name = actor or actor_name()
    if not name:
        return False
    if can_manage_class(class_id, name):
        return True
    if enrolled_in_class(class_id, name):
        return True
    # Parent can view if any enrolled child is in class
    children = observed_children(name)
    if children:
        rows = Enrollment.query.filter_by(class_id=class_id, role='student').all()
        return any(r.student_id in children for r in rows)
    return False


def can_view_student_work(class_id: int, student_id: str, actor: str | None = None) -> bool:
    name = actor or actor_name()
    if not name:
        return False
    if can_manage_class(class_id, name):
        return True
    if name == student_id and enrolled_in_class(class_id, name):
        return True
    if student_id in observed_children(name) and enrolled_in_class(class_id, student_id):
        return True
    return False


def visible_class_ids(actor: str | None = None) -> list[int]:
    name = actor or actor_name()
    if not name:
        return []
    if is_school_admin(name):
        return [c.id for c in SchoolClass.query.filter_by(archived=False).all()]
    ids: set[int] = set()
    for cls in SchoolClass.query.filter_by(archived=False).all():
        if cls.teacher_id == name or teaches_class(cls.id, name):
            ids.add(cls.id)
    for enr in Enrollment.query.filter_by(student_id=name).all():
        ids.add(enr.class_id)
    children = observed_children(name)
    if children:
        for enr in Enrollment.query.filter(Enrollment.student_id.in_(list(children))).all():
            ids.add(enr.class_id)
    return sorted(ids)


def school_role_label(actor: str | None = None) -> str:
    name = actor or actor_name()
    if is_school_admin(name):
        return 'school_admin'
    if is_parent_observer(name) and not (is_configured_teacher(name) or teaches_any(name)):
        return 'parent_observer'
    if is_configured_teacher(name) or teaches_any(name):
        return 'teacher'
    if is_configured_student(name) or student_any(name):
        return 'student'
    return 'guest'


def teaches_any(actor: str | None = None) -> bool:
    name = actor or actor_name()
    if not name:
        return False
    if SchoolClass.query.filter_by(teacher_id=name, archived=False).first():
        return True
    return Enrollment.query.filter_by(student_id=name).filter(
        Enrollment.role.in_(('teacher', 'assistant'))
    ).first() is not None


def student_any(actor: str | None = None) -> bool:
    name = actor or actor_name()
    if not name:
        return False
    return Enrollment.query.filter_by(student_id=name, role='student').first() is not None
