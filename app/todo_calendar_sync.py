"""Sync to-do list due dates into HomeHub calendar reminders (personal calendars)."""

from __future__ import annotations

from .models import db, TodoList, TodoItem, Reminder, PersonalCalendar
from .security import sanitize_text, sanitize_html
from .google_calendar.acl import can_write_personal_calendar
from .user_context import current_firebase_uid

TODO_REMINDER_CATEGORY = 'todo'


def _parse_personal_calendar_id(value) -> int | None:
    if value is None or value == '':
        return None
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def resolve_personal_calendar_for_todo_list(data: dict, owner_uid: str | None = None) -> tuple[str | None, int | None]:
    """Returns (error_code, personal_calendar_id). error_code: invalid | forbidden."""
    if 'personal_calendar_id' not in data:
        return None, None
    raw = data.get('personal_calendar_id')
    if raw is None or raw == '' or raw is False:
        return None, 0
    pid = _parse_personal_calendar_id(raw)
    if pid is None:
        return 'invalid', None
    pc = PersonalCalendar.query.get(pid)
    if not pc or pc.archived:
        return 'invalid', None
    uid = current_firebase_uid() or owner_uid
    if uid and not can_write_personal_calendar(pc, uid):
        return 'forbidden', None
    return None, pid


def _reminder_title_for_item(item: TodoItem, tl: TodoList) -> str:
    prefix = f'[{tl.name}] ' if tl.name else ''
    title = prefix + (item.description or 'To-do item')
    return title[:256]


def _reminder_title_for_list(tl: TodoList) -> str:
    return sanitize_text(f'[{tl.name}] List due' if tl.name else 'To-do list due')[:256]


def _reminder_body_for_item(item: TodoItem, tl: TodoList) -> str:
    lines = [f'To-do list: {tl.name or "Untitled"}']
    if item.assignees:
        try:
            import json
            assignees = json.loads(item.assignees) if isinstance(item.assignees, str) else item.assignees
            if assignees:
                lines.append('Assignees: ' + ', '.join(assignees))
        except Exception:
            pass
    return sanitize_html('\n'.join(lines))


def _reminder_body_for_list(tl: TodoList) -> str:
    desc = (tl.description or '').strip()
    base = f'To-do list: {tl.name or "Untitled"}'
    if desc:
        base += '\n' + desc
    return sanitize_html(base)


def _delete_reminder_by_id(reminder_id: int | None) -> None:
    if not reminder_id:
        return
    r = Reminder.query.get(reminder_id)
    if r:
        db.session.delete(r)


def delete_item_reminder(item: TodoItem) -> None:
    if item.reminder_id:
        _delete_reminder_by_id(item.reminder_id)
        item.reminder_id = None


def delete_list_reminder(tl: TodoList) -> None:
    if tl.list_reminder_id:
        _delete_reminder_by_id(tl.list_reminder_id)
        tl.list_reminder_id = None


def purge_todo_list_calendar_reminders(tl: TodoList) -> None:
    for item in TodoItem.query.filter_by(todo_list_id=tl.id).all():
        delete_item_reminder(item)
    delete_list_reminder(tl)


def sync_item_reminder(item: TodoItem, tl: TodoList) -> None:
    pc_id = getattr(tl, 'personal_calendar_id', None)
    if not pc_id:
        delete_item_reminder(item)
        return
    should_show = bool(item.due_date) and not item.done
    if not should_show:
        delete_item_reminder(item)
        return
    if item.reminder_id:
        r = Reminder.query.get(item.reminder_id)
        if not r:
            item.reminder_id = None
        else:
            r.date = item.due_date
            r.title = _reminder_title_for_item(item, tl)
            r.description = _reminder_body_for_item(item, tl)
            r.personal_calendar_id = pc_id
            r.all_day = True
            r.category = TODO_REMINDER_CATEGORY
            return
    r = Reminder(
        date=item.due_date,
        title=_reminder_title_for_item(item, tl),
        description=_reminder_body_for_item(item, tl),
        creator=item.creator or tl.creator,
        all_day=True,
        personal_calendar_id=pc_id,
        category=TODO_REMINDER_CATEGORY,
    )
    db.session.add(r)
    db.session.flush()
    item.reminder_id = r.id


def sync_list_reminder(tl: TodoList) -> None:
    pc_id = getattr(tl, 'personal_calendar_id', None)
    if not pc_id:
        delete_list_reminder(tl)
        return
    if not tl.due_date:
        delete_list_reminder(tl)
        return
    if tl.list_reminder_id:
        r = Reminder.query.get(tl.list_reminder_id)
        if not r:
            tl.list_reminder_id = None
        else:
            r.date = tl.due_date
            r.title = _reminder_title_for_list(tl)
            r.description = _reminder_body_for_list(tl)
            r.personal_calendar_id = pc_id
            r.all_day = True
            r.category = TODO_REMINDER_CATEGORY
            return
    r = Reminder(
        date=tl.due_date,
        title=_reminder_title_for_list(tl),
        description=_reminder_body_for_list(tl),
        creator=tl.creator,
        all_day=True,
        personal_calendar_id=pc_id,
        category=TODO_REMINDER_CATEGORY,
    )
    db.session.add(r)
    db.session.flush()
    tl.list_reminder_id = r.id


def sync_todo_list_calendar(tl: TodoList) -> None:
    sync_list_reminder(tl)
    for item in TodoItem.query.filter_by(todo_list_id=tl.id).all():
        sync_item_reminder(item, tl)


def apply_todo_list_personal_calendar(tl: TodoList, data: dict) -> str | None:
    """Set personal_calendar_id from payload; returns error code or None."""
    if 'personal_calendar_id' not in data:
        return None
    err, pid = resolve_personal_calendar_for_todo_list(data, tl.owner_uid)
    if err:
        return err
    if pid == 0:
        if tl.personal_calendar_id:
            purge_todo_list_calendar_reminders(tl)
        tl.personal_calendar_id = None
        return None
    if pid is None:
        return None
    old = tl.personal_calendar_id
    tl.personal_calendar_id = pid
    if old and old != pid:
        purge_todo_list_calendar_reminders(tl)
    return None
