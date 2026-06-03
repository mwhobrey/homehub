from flask import render_template, request, current_app, jsonify, session
from datetime import datetime, date, timedelta
import json
from sqlalchemy import func, case

from ..models import (
    db,
    TodoList,
    TodoListShare,
    TodoItem,
    RecurringTodoList,
    RecurringTodoItem,
    PersonalCalendar,
)
from ..todo_calendar_sync import (
    apply_todo_list_personal_calendar,
    sync_todo_list_calendar,
    sync_item_reminder,
    purge_todo_list_calendar_reminders,
    delete_item_reminder,
)
from ..blueprints import main_bp
from ..user_context import (
    resolve_actor,
    resolve_user,
    can_modify_record,
    is_admin,
    uses_firebase,
    current_firebase_uid,
    current_display_name,
)
from ..security import sanitize_text
from ..todo_acl import (
    can_view_todo_list,
    can_write_todo_list,
    visible_todo_list_ids,
    apply_todo_list_shares,
    list_owner_key,
)
from ..google_calendar.acl import (
    household_member_roster,
    visible_personal_calendar_ids,
    can_write_personal_calendar,
    is_household_personal_calendar,
)
from ..google_calendar.imports import ensure_household_calendar


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _add_months(dt: date, months: int) -> date:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    last = (date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1) - timedelta(days=1)).day
    d = min(dt.day, last)
    return date(y, m, d)


def _add_years(dt: date, years: int) -> date:
    try:
        return date(dt.year + years, dt.month, dt.day)
    except Exception:
        if dt.month == 2 and dt.day == 29:
            return date(dt.year + years, 2, 28)
        return _add_months(dt, years * 12)


def _next_occurrence(interval: int, unit: str, d: date) -> date:
    interval = max(1, int(interval or 1))
    unit = (unit or 'day').lower()
    if unit == 'day':
        return d + timedelta(days=interval)
    if unit == 'week':
        return d + timedelta(weeks=interval)
    if unit == 'month':
        return _add_months(d, interval)
    if unit == 'year':
        return _add_years(d, interval)
    return d + timedelta(days=interval)


def _next_due_on_or_after(start: date, end: date | None, interval: int, unit: str, target: date) -> date | None:
    d = start or target
    if end and d > end:
        return None
    if d >= target:
        return d
    while d < target:
        nd = _next_occurrence(interval, unit, d)
        if nd == d:
            break
        d = nd
        if end and d > end:
            return None
    return d if (not end or d <= end) else None


def _parse_tags(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        tags = raw
    elif isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            tags = json.loads(raw)
            if not isinstance(tags, list):
                tags = [t.strip() for t in raw.split(',') if t.strip()]
        except Exception:
            tags = [t.strip() for t in raw.split(',') if t.strip()]
    else:
        return []
    cleaned = []
    for t in tags:
        if isinstance(t, str) and t.strip():
            cleaned.append(sanitize_text(t.strip()))
    return cleaned


def _parse_assignees(raw) -> list[str]:
    return _parse_tags(raw)


def _owner_uid_for_write() -> str:
    if uses_firebase():
        return current_firebase_uid()
    return resolve_actor()


def _viewer_uid() -> str:
    if uses_firebase():
        return current_firebase_uid()
    return resolve_user()


def _json_tags_field(value: str | None) -> list:
    try:
        return json.loads(value or '[]')
    except Exception:
        return []


def _ensure_recurring_todo_items(today: date | None = None):
    today = today or date.today()
    rules = RecurringTodoItem.query.all()
    active_rows = (
        TodoItem.query
        .filter(TodoItem.recurring_id.isnot(None))
        .order_by(TodoItem.recurring_id.asc(), TodoItem.due_date.asc(), TodoItem.timestamp.desc())
        .all()
    )
    active_by_rule: dict[int, TodoItem] = {}
    for row in active_rows:
        if row.recurring_id is None or row.recurring_id in active_by_rule:
            continue
        active_by_rule[row.recurring_id] = row
    changed = False
    for rule in rules:
        next_due = _next_due_on_or_after(
            rule.start_date or today,
            rule.end_date,
            rule.interval or 1,
            rule.unit or 'day',
            today,
        )
        active = active_by_rule.get(rule.id)
        if next_due is None:
            if active and not active.done:
                active.done = True
                changed = True
            continue
        if active:
            if active.description != rule.description:
                active.description = rule.description
                changed = True
            if active.creator != rule.creator:
                active.creator = rule.creator
                changed = True
            rule_tags = rule.tags or '[]'
            if active.tags != rule_tags:
                active.tags = rule_tags
                changed = True
            rule_assignees = rule.assignees or '[]'
            if active.assignees != rule_assignees:
                active.assignees = rule_assignees
                changed = True
            if active.due_date != next_due:
                active.due_date = next_due
                changed = True
            if active.done:
                active.done = False
                changed = True
        else:
            db.session.add(TodoItem(
                todo_list_id=rule.todo_list_id,
                description=rule.description,
                creator=rule.creator,
                tags=rule.tags or '[]',
                assignees=rule.assignees or '[]',
                due_date=next_due,
                recurring_id=rule.id,
                done=False,
            ))
            changed = True
        if rule.last_generated_date != next_due:
            rule.last_generated_date = next_due
            changed = True
    if changed:
        db.session.commit()


def _ensure_recurring_todo_lists(today: date | None = None):
    today = today or date.today()
    changed = False
    for rule in RecurringTodoList.query.all():
        tl = TodoList.query.get(rule.todo_list_id)
        if not tl or tl.archived:
            continue
        next_due = _next_due_on_or_after(
            rule.start_date or today,
            rule.end_date,
            rule.interval or 1,
            rule.unit or 'week',
            today,
        )
        if next_due and tl.due_date != next_due:
            tl.due_date = next_due
            changed = True
        if rule.last_generated_date != next_due:
            rule.last_generated_date = next_due
            changed = True
    if changed:
        db.session.commit()


def _serialize_share(s: TodoListShare) -> dict:
    return {'grantee_uid': s.grantee_uid, 'can_write': bool(s.can_write)}


def _item_counts_for_lists(list_ids: list[int]) -> dict[int, dict]:
    if not list_ids:
        return {}
    rows = (
        db.session.query(
            TodoItem.todo_list_id,
            func.count(TodoItem.id),
            func.sum(case((TodoItem.done.is_(True), 1), else_=0)),
        )
        .filter(TodoItem.todo_list_id.in_(list_ids))
        .group_by(TodoItem.todo_list_id)
        .all()
    )
    out = {}
    for lid, total, done in rows:
        out[int(lid)] = {'item_total': int(total or 0), 'item_done': int(done or 0)}
    return out


def _serialize_list(tl: TodoList, viewer_uid: str | None = None, counts: dict | None = None) -> dict:
    viewer_uid = viewer_uid or _viewer_uid()
    shares = []
    owner = list_owner_key(tl)
    is_owner = bool(viewer_uid and (tl.owner_uid == viewer_uid or owner == viewer_uid))
    if is_owner and (tl.visibility or 'private').lower() == 'private':
        for s in TodoListShare.query.filter_by(todo_list_id=tl.id).all():
            shares.append(_serialize_share(s))
    rec = RecurringTodoList.query.filter_by(todo_list_id=tl.id).first()
    recurrence = None
    if rec:
        recurrence = {
            'interval': rec.interval or 1,
            'unit': rec.unit or 'week',
            'start_date': rec.start_date.strftime('%Y-%m-%d') if rec.start_date else None,
            'end_date': rec.end_date.strftime('%Y-%m-%d') if rec.end_date else None,
        }
    return {
        'id': tl.id,
        'name': tl.name,
        'description': tl.description or '',
        'visibility': tl.visibility or 'private',
        'tags': _json_tags_field(tl.tags),
        'assignees': _json_tags_field(tl.assignees),
        'due_date': tl.due_date.strftime('%Y-%m-%d') if tl.due_date else None,
        'creator': tl.creator,
        'owner_uid': tl.owner_uid,
        'archived': bool(tl.archived),
        'is_owner': is_owner,
        'can_edit': can_write_todo_list(tl, viewer_uid),
        'can_share': bool(is_owner and uses_firebase() and (tl.visibility or 'private').lower() == 'private'),
        'shared_with': shares,
        'recurrence': recurrence,
        'item_total': (counts or {}).get('item_total', 0),
        'item_done': (counts or {}).get('item_done', 0),
        'personal_calendar_id': getattr(tl, 'personal_calendar_id', None),
        'personal_calendar_name': _personal_calendar_name(getattr(tl, 'personal_calendar_id', None)),
    }


def _personal_calendar_name(pc_id: int | None) -> str | None:
    if not pc_id:
        return None
    pc = PersonalCalendar.query.get(pc_id)
    return (pc.name or None) if pc and not pc.archived else None


def _serialize_item(item: TodoItem) -> dict:
    rec = None
    if item.recurring_id:
        rule = RecurringTodoItem.query.get(item.recurring_id)
        if rule:
            rec = {
                'interval': rule.interval or 1,
                'unit': rule.unit or 'day',
                'start_date': rule.start_date.strftime('%Y-%m-%d') if rule.start_date else None,
                'end_date': rule.end_date.strftime('%Y-%m-%d') if rule.end_date else None,
            }
    return {
        'id': item.id,
        'todo_list_id': item.todo_list_id,
        'description': item.description,
        'done': bool(item.done),
        'creator': item.creator,
        'due_date': item.due_date.strftime('%Y-%m-%d') if item.due_date else None,
        'tags': _json_tags_field(item.tags),
        'assignees': _json_tags_field(item.assignees),
        'recurring_id': item.recurring_id,
        'recurrence': rec,
        'sort_order': item.sort_order or 0,
        'timestamp': item.timestamp.isoformat() if item.timestamp else None,
    }


def _apply_list_recurrence(tl: TodoList, data: dict) -> None:
    rec = data.get('recurrence')
    existing = RecurringTodoList.query.filter_by(todo_list_id=tl.id).first()
    if not rec:
        if existing:
            db.session.delete(existing)
        return
    try:
        interval = max(1, int(rec.get('interval') or 1))
    except Exception:
        interval = 1
    unit = sanitize_text(rec.get('unit', 'week')).lower()
    if unit not in ('day', 'week', 'month', 'year'):
        unit = 'week'
    start_date = _parse_date(rec.get('start_date')) or date.today()
    end_date = _parse_date(rec.get('end_date'))
    if existing:
        existing.interval = interval
        existing.unit = unit
        existing.start_date = start_date
        existing.end_date = end_date
    else:
        db.session.add(RecurringTodoList(
            todo_list_id=tl.id,
            interval=interval,
            unit=unit,
            start_date=start_date,
            end_date=end_date,
        ))


def _apply_item_recurrence(item: TodoItem, data: dict, list_id: int, creator: str) -> None:
    rec = data.get('recurrence')
    is_recurring = data.get('is_recurring') in (True, 'true', '1', 1, 'on')
    rule_id = data.get('recurring_rule_id')
    if rule_id and not is_recurring:
        rule = RecurringTodoItem.query.get(int(rule_id))
        if rule:
            TodoItem.query.filter_by(recurring_id=rule.id).delete()
            db.session.delete(rule)
        item.recurring_id = None
        return
    if not is_recurring and not rec:
        return
    if not is_recurring:
        return
    try:
        interval = max(1, int((rec or {}).get('interval') or data.get('rec_interval') or 1))
    except Exception:
        interval = 1
    unit = sanitize_text((rec or {}).get('unit') or data.get('rec_unit') or 'day').lower()
    if unit not in ('day', 'week', 'month', 'year'):
        unit = 'day'
    start_date = _parse_date((rec or {}).get('start_date') or data.get('rec_start_date')) or date.today()
    end_date = _parse_date((rec or {}).get('end_date') or data.get('rec_end_date'))
    tags = json.dumps(_parse_tags(data.get('tags', item.tags)))
    assignees = json.dumps(_parse_assignees(data.get('assignees', item.assignees)))
    desc = sanitize_text(data.get('description') or item.description)
    if rule_id:
        rule = RecurringTodoItem.query.get_or_404(int(rule_id))
        rule.description = desc
        rule.tags = tags
        rule.assignees = assignees
        rule.interval = interval
        rule.unit = unit
        rule.start_date = start_date
        rule.end_date = end_date
        item.recurring_id = rule.id
    else:
        rule = RecurringTodoItem(
            todo_list_id=list_id,
            description=desc,
            creator=creator,
            tags=tags,
            assignees=assignees,
            interval=interval,
            unit=unit,
            start_date=start_date,
            end_date=end_date,
        )
        db.session.add(rule)
        db.session.flush()
        item.recurring_id = rule.id


@main_bp.route('/todo-lists')
def todo_lists_page():
    config = current_app.config['HOMEHUB_CONFIG']
    family = config.get('family_members') or []
    return render_template(
        'todos.html',
        config=config,
        family_members=family,
        uses_firebase=uses_firebase(),
        current_user_name=current_display_name(),
        today_date=date.today(),
    )


@main_bp.route('/api/todo-lists', methods=['GET'])
def api_list_todo_lists():
    _ensure_recurring_todo_lists()
    viewer = _viewer_uid()
    visible = visible_todo_list_ids(viewer)
    lists = TodoList.query.filter(
        TodoList.archived.is_(False),
        TodoList.id.in_(visible) if visible else False,
    ).order_by(TodoList.name.asc()).all() if visible else []
    list_ids = [tl.id for tl in lists]
    count_map = _item_counts_for_lists(list_ids)
    return jsonify({
        'ok': True,
        'lists': [
            _serialize_list(tl, viewer, count_map.get(tl.id, {'item_total': 0, 'item_done': 0}))
            for tl in lists
        ],
    })


@main_bp.route('/api/todo-lists', methods=['POST'])
def api_create_todo_list():
    try:
        data = request.get_json(force=True) or {}
        name = sanitize_text(data.get('name', '')).strip()
        if not name:
            return jsonify({'ok': False, 'error': 'name_required'}), 400
        owner = _owner_uid_for_write()
        if uses_firebase() and not owner:
            return jsonify({'ok': False, 'error': 'unauthorized'}), 401
        creator = resolve_actor(json_payload=data)
        visibility = sanitize_text(data.get('visibility', 'private')).lower()
        if visibility not in ('private', 'household'):
            visibility = 'private'
        tl = TodoList(
            owner_uid=owner or creator,
            creator=creator,
            name=name,
            description=sanitize_text(data.get('description', '')),
            visibility=visibility,
            tags=json.dumps(_parse_tags(data.get('tags'))),
            assignees=json.dumps(_parse_assignees(data.get('assignees'))),
            due_date=_parse_date(data.get('due_date')),
        )
        db.session.add(tl)
        db.session.flush()
        if uses_firebase() and visibility == 'private':
            roster = {m['uid'] for m in household_member_roster(owner)}
            apply_todo_list_shares(tl, owner, data.get('shared_with') or data.get('shares'), roster)
        _apply_list_recurrence(tl, data)
        cal_err = apply_todo_list_personal_calendar(tl, data)
        if cal_err:
            db.session.rollback()
            return jsonify({'ok': False, 'error': cal_err}), 400
        db.session.commit()
        _ensure_recurring_todo_lists()
        sync_todo_list_calendar(tl)
        db.session.commit()
        return jsonify({'ok': True, 'list': _serialize_list(tl)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400


@main_bp.route('/api/todo-lists/<int:list_id>', methods=['PUT'])
def api_update_todo_list(list_id):
    tl = TodoList.query.get_or_404(list_id)
    if not can_write_todo_list(tl):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    try:
        data = request.get_json(force=True) or {}
        user = resolve_user(json_payload=data)
        if not uses_firebase() and not can_modify_record(tl.creator, user) and not is_admin(user):
            if list_owner_key(tl) != user and not can_write_todo_list(tl, user):
                return jsonify({'ok': False, 'error': 'not allowed'}), 403
        name = data.get('name')
        if isinstance(name, str) and name.strip():
            tl.name = sanitize_text(name).strip()
        if 'description' in data:
            tl.description = sanitize_text(data.get('description', ''))
        if 'visibility' in data:
            vis = sanitize_text(data.get('visibility', 'private')).lower()
            if vis in ('private', 'household'):
                tl.visibility = vis
        if 'tags' in data:
            tl.tags = json.dumps(_parse_tags(data.get('tags')))
        if 'assignees' in data:
            tl.assignees = json.dumps(_parse_assignees(data.get('assignees')))
        if 'due_date' in data:
            tl.due_date = _parse_date(data.get('due_date'))
        if uses_firebase() and (tl.visibility or 'private') == 'private' and list_owner_key(tl) == _viewer_uid():
            roster = {m['uid'] for m in household_member_roster(tl.owner_uid)}
            apply_todo_list_shares(tl, tl.owner_uid, data.get('shared_with') or data.get('shares'), roster)
        if 'recurrence' in data or data.get('clear_recurrence'):
            if data.get('clear_recurrence'):
                RecurringTodoList.query.filter_by(todo_list_id=tl.id).delete()
            else:
                _apply_list_recurrence(tl, data)
        cal_err = apply_todo_list_personal_calendar(tl, data)
        if cal_err:
            db.session.rollback()
            return jsonify({'ok': False, 'error': cal_err}), 400
        db.session.commit()
        _ensure_recurring_todo_lists()
        sync_todo_list_calendar(tl)
        db.session.commit()
        return jsonify({'ok': True, 'list': _serialize_list(tl)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400


@main_bp.route('/api/todo-lists/<int:list_id>', methods=['DELETE'])
def api_delete_todo_list(list_id):
    tl = TodoList.query.get_or_404(list_id)
    user = resolve_user(json_payload=request.get_json(silent=True) or {})
    if uses_firebase():
        if not can_write_todo_list(tl) or (tl.owner_uid != _viewer_uid() and not is_admin()):
            return jsonify({'ok': False, 'error': 'not allowed'}), 403
    elif not can_modify_record(tl.creator, user) and not is_admin(user):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    purge_todo_list_calendar_reminders(tl)
    TodoItem.query.filter_by(todo_list_id=tl.id).delete()
    RecurringTodoItem.query.filter_by(todo_list_id=tl.id).delete()
    RecurringTodoList.query.filter_by(todo_list_id=tl.id).delete()
    TodoListShare.query.filter_by(todo_list_id=tl.id).delete()
    db.session.delete(tl)
    db.session.commit()
    return jsonify({'ok': True})


@main_bp.route('/api/todo-lists/<int:list_id>/items', methods=['GET'])
def api_list_todo_items(list_id):
    tl = TodoList.query.get_or_404(list_id)
    if not can_view_todo_list(tl):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    _ensure_recurring_todo_items()
    items = (
        TodoItem.query.filter_by(todo_list_id=list_id)
        .order_by(TodoItem.done.asc(), TodoItem.due_date.asc(), TodoItem.sort_order.asc(), TodoItem.id.asc())
        .all()
    )
    return jsonify({'ok': True, 'items': [_serialize_item(i) for i in items]})


@main_bp.route('/api/todo-lists/<int:list_id>/items', methods=['POST'])
def api_create_todo_item(list_id):
    tl = TodoList.query.get_or_404(list_id)
    if not can_write_todo_list(tl):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    try:
        data = request.get_json(force=True) or {}
        desc = sanitize_text(data.get('description', '')).strip()
        if not desc:
            return jsonify({'ok': False, 'error': 'description_required'}), 400
        creator = resolve_actor(json_payload=data)
        item = TodoItem(
            todo_list_id=list_id,
            description=desc,
            creator=creator,
            tags=json.dumps(_parse_tags(data.get('tags'))),
            assignees=json.dumps(_parse_assignees(data.get('assignees'))),
            due_date=_parse_date(data.get('due_date')),
            done=bool(data.get('done')),
        )
        db.session.add(item)
        db.session.flush()
        if data.get('is_recurring') or data.get('recurrence'):
            _apply_item_recurrence(item, data, list_id, creator)
        db.session.commit()
        _ensure_recurring_todo_items()
        sync_item_reminder(item, tl)
        db.session.commit()
        return jsonify({'ok': True, 'item': _serialize_item(item)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400


@main_bp.route('/api/todo-items/<int:item_id>', methods=['PUT'])
def api_update_todo_item(item_id):
    item = TodoItem.query.get_or_404(item_id)
    tl = TodoList.query.get_or_404(item.todo_list_id)
    if not can_write_todo_list(tl):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    try:
        data = request.get_json(force=True) or {}
        user = resolve_user(json_payload=data)
        if not uses_firebase() and not can_modify_record(item.creator, user) and not can_write_todo_list(tl, user):
            return jsonify({'ok': False, 'error': 'not allowed'}), 403
        if 'description' in data and isinstance(data['description'], str):
            item.description = sanitize_text(data['description']).strip()
        if 'tags' in data:
            item.tags = json.dumps(_parse_tags(data.get('tags')))
        if 'assignees' in data:
            item.assignees = json.dumps(_parse_assignees(data.get('assignees')))
        if 'due_date' in data:
            item.due_date = _parse_date(data.get('due_date'))
        if 'done' in data:
            item.done = bool(data.get('done'))
        if 'is_recurring' in data or 'recurrence' in data or 'recurring_rule_id' in data:
            _apply_item_recurrence(item, data, tl.id, item.creator or resolve_actor(json_payload=data))
        db.session.commit()
        _ensure_recurring_todo_items()
        sync_item_reminder(item, tl)
        db.session.commit()
        return jsonify({'ok': True, 'item': _serialize_item(item)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 400


@main_bp.route('/api/todo-items/<int:item_id>/toggle', methods=['POST'])
def api_toggle_todo_item(item_id):
    item = TodoItem.query.get_or_404(item_id)
    tl = TodoList.query.get_or_404(item.todo_list_id)
    if not can_write_todo_list(tl):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    if item.recurring_id:
        rule = RecurringTodoItem.query.get(item.recurring_id)
        if rule and item.due_date:
            next_due = _next_occurrence(rule.interval or 1, rule.unit or 'day', item.due_date)
            if rule.end_date and next_due > rule.end_date:
                item.done = True
            else:
                item.due_date = next_due
                item.done = False
                rule.last_generated_date = next_due
        else:
            item.done = not item.done
    else:
        item.done = not item.done
    db.session.commit()
    sync_item_reminder(item, tl)
    db.session.commit()
    return jsonify({'ok': True, 'item': _serialize_item(item)})


@main_bp.route('/api/todo-items/<int:item_id>', methods=['DELETE'])
def api_delete_todo_item(item_id):
    item = TodoItem.query.get_or_404(item_id)
    tl = TodoList.query.get_or_404(item.todo_list_id)
    if not can_write_todo_list(tl):
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    user = resolve_user(json_payload=request.get_json(silent=True) or {})
    if item.recurring_id:
        rule = RecurringTodoItem.query.get(item.recurring_id)
        if rule and (can_modify_record(rule.creator, user) or can_write_todo_list(tl, _viewer_uid())):
            for row in TodoItem.query.filter_by(recurring_id=rule.id).all():
                delete_item_reminder(row)
            TodoItem.query.filter_by(recurring_id=rule.id).delete()
            db.session.delete(rule)
        elif can_modify_record(item.creator, user) or can_write_todo_list(tl, _viewer_uid()):
            delete_item_reminder(item)
            db.session.delete(item)
        else:
            return jsonify({'ok': False, 'error': 'not allowed'}), 403
    elif can_modify_record(item.creator, user) or can_write_todo_list(tl, _viewer_uid()):
        delete_item_reminder(item)
        db.session.delete(item)
    else:
        return jsonify({'ok': False, 'error': 'not allowed'}), 403
    db.session.commit()
    return jsonify({'ok': True})


@main_bp.route('/api/todo-lists/calendars', methods=['GET'])
def api_todo_list_calendars():
    """Personal calendars the current user may attach to a to-do list."""
    from ..google_calendar.imports import default_event_personal_calendar_id

    household = ensure_household_calendar()
    default_id = default_event_personal_calendar_id()
    db.session.commit()
    viewer = current_firebase_uid() or _viewer_uid() or None
    uid = current_firebase_uid() or viewer
    seen: set[int] = set()
    calendars: list[dict] = []

    def add_calendar(pc: PersonalCalendar | None, *, force_default: bool = False) -> None:
        if not pc or pc.archived or pc.id in seen:
            return
        if uid and not can_write_personal_calendar(pc, uid):
            return
        seen.add(pc.id)
        is_default = force_default or pc.id == default_id
        label = pc.name or 'Calendar'
        if is_household_personal_calendar(pc):
            label = label if label.lower() != 'household' else 'Household'
            if is_default:
                label += ' (default)'
        calendars.append({
            'id': pc.id,
            'name': label,
            'color': pc.color,
            'is_household': is_household_personal_calendar(pc),
            'is_default': is_default,
        })

    add_calendar(household, force_default=True)
    for pc_id in sorted(visible_personal_calendar_ids(viewer)):
        add_calendar(PersonalCalendar.query.get(pc_id))
    calendars.sort(
        key=lambda c: (
            0 if c.get('is_default') else 1,
            0 if c.get('is_household') else 1,
            (c.get('name') or '').lower(),
        )
    )
    return jsonify({
        'ok': True,
        'calendars': calendars,
        'default_calendar_id': default_id,
    })


@main_bp.route('/api/todo-lists/tags', methods=['GET'])
def api_todo_list_tags():
    visible = visible_todo_list_ids(_viewer_uid())
    tag_set = set()
    for tl in TodoList.query.filter(TodoList.id.in_(visible)).all() if visible else []:
        for t in _json_tags_field(tl.tags):
            tag_set.add(t)
    for item in TodoItem.query.filter(TodoItem.todo_list_id.in_(visible)).all() if visible else []:
        for t in _json_tags_field(item.tags):
            tag_set.add(t)
    return jsonify({'ok': True, 'tags': sorted(tag_set)})
