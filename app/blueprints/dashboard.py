from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from datetime import datetime, date, timedelta
from ..models import db, HomeStatus, MemberStatus, Notice, Reminder, RecurringReminder, Chore, LinkedCalendar
from ..blueprints import main_bp
from ..user_context import (
    resolve_actor,
    resolve_user,
    can_modify_record,
    can_modify_reminder,
    is_admin_for,
    current_firebase_uid,
)
from ..security import sanitize_html, sanitize_text, normalize_hex_color
from sqlalchemy import func
import json


def _parse_date_param(value, default=None):
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except Exception:
        return default


def _calendar_week_start_day() -> str:
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    rem = cfg.get('reminders') or {}
    raw = (rem.get('calendar_start_day') or 'sunday')
    return str(raw).lower()


def _week_range(base_date: date) -> tuple[date, date]:
    """Week window using configured start day (default Sunday)."""
    name_to_py = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    start_name = _calendar_week_start_day()
    start_py = name_to_py.get(start_name, 6)
    delta = (base_date.weekday() - start_py) % 7
    start = base_date - timedelta(days=delta)
    return start, start + timedelta(days=6)


def _show_chores_on_homepage() -> bool:
    try:
        row = db.session.execute(db.text("SELECT value FROM app_setting WHERE key='show_chores_on_homepage'"))
        val = row.scalar()
        if val is None:
            cfg = current_app.config.get('HOMEHUB_CONFIG', {})
            return bool((cfg.get('feature_toggles') or {}).get('show_chores_on_homepage', False))
        return str(val).strip().lower() in ('1', 'true', 'yes', 'on')
    except Exception:
        return False


@main_bp.route('/')
def index():
    config = current_app.config['HOMEHUB_CONFIG']
    notice = Notice.query.order_by(Notice.updated_at.desc()).first()
    show_chores_on_homepage = _show_chores_on_homepage()
    # Calendar: gather reminders grouped by date
    try:
        rows = Reminder.query.with_entities(
            Reminder.id,
            Reminder.title,
            Reminder.description,
            Reminder.creator,
            Reminder.date,
            Reminder.time,
            Reminder.category,
        ).all()
    except Exception:
        rows = []
    by_date = {}
    for rid, title, description, creator, rdate, rtime, rcat in rows:
        try:
            key = rdate.strftime('%Y-%m-%d')
        except Exception:
            key = str(rdate) if rdate else ''
        by_date.setdefault(key, []).append({
            'id': int(rid),
            'title': title or '',
            'description': description or '',
            'creator': creator or '',
            'time': rtime or None,
            'category': rcat or None,
        })
    # Who is Home summary
    family = list(dict.fromkeys(config.get('family_members', [])))
    who_statuses = {s.name: s.status for s in HomeStatus.query.all() if s.name in family}
    member_statuses = {ms.name: ms.text for ms in MemberStatus.query.all() if ms.name in family and (ms.text or '').strip()}
    # Extract reminder categories
    reminder_categories = []
    try:
        rcfg = (config.get('reminders') or {}).get('categories') or []
        if isinstance(rcfg, list):
            for entry in rcfg:
                if not isinstance(entry, dict):
                    continue
                key = entry.get('key')
                if not key:
                    continue
                reminder_categories.append({
                    'key': key,
                    'label': entry.get('label') or key,
                    'color': entry.get('color') or None,
                })
    except Exception:
        reminder_categories = []
    # Backward compatibility: provide both Python object and pre-serialized JSON
    try:
        reminders_json = json.dumps(by_date)
    except Exception:
        reminders_json = '{}'
    home_chores = []
    if show_chores_on_homepage and config.get('feature_toggles', {}).get('chores', True):
        try:
            home_chores = (
                Chore.query
                .filter(Chore.done == False)  # noqa: E712
                .order_by(Chore.due_date.asc(), Chore.timestamp.desc())
                .limit(8)
                .all()
            )
        except Exception:
            home_chores = []
    try:
        from ..google_calendar.acl import google_calendar_enabled, get_connection_for_uid
        from ..google_calendar.sync import sync_connection_for_uid
        if google_calendar_enabled():
            uid = current_firebase_uid()
            if uid and get_connection_for_uid(uid):
                import threading
                app_obj = current_app._get_current_object()
                def _bg_sync(u=uid, app=app_obj):
                    with app.app_context():
                        sync_connection_for_uid(u)
                threading.Thread(target=_bg_sync, daemon=True).start()
    except Exception:
        pass
    # Pass Python object; template will use |tojson safely
    return render_template(
        'index.html',
        config=config,
        notice=notice,
        reminders_data=by_date,
        reminders_json=reminders_json,
        who_statuses=who_statuses,
        member_statuses=member_statuses,
        reminder_categories=reminder_categories,
        home_chores=home_chores,
        show_chores_on_homepage=show_chores_on_homepage,
    )


def _household_timezone() -> str:
    cfg = current_app.config.get('HOMEHUB_CONFIG', {}) or {}
    rem = cfg.get('reminders') or {}
    gcal = cfg.get('google_calendar') or {}
    return rem.get('default_timezone') or gcal.get('default_timezone') or 'UTC'


def _exception_dates(rr: RecurringReminder) -> list[str]:
    try:
        data = json.loads(rr.exception_dates_json or '[]')
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _add_exception_date(rr: RecurringReminder, d: date) -> None:
    dates = _exception_dates(rr)
    key = d.strftime('%Y-%m-%d')
    if key not in dates:
        dates.append(key)
    rr.exception_dates_json = json.dumps(sorted(dates))


def _parse_attendees_field(raw):
    from ..google_calendar.mapper import parse_attendees_payload
    return parse_attendees_payload(raw)


def _serialize_attendees_list(r: Reminder) -> list:
    raw = getattr(r, 'attendees_json', None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _calendar_meta(r: Reminder) -> dict:
    lc_id = getattr(r, 'linked_calendar_id', None)
    if not lc_id:
        return {}
    lc = LinkedCalendar.query.get(lc_id)
    if not lc:
        return {'linked_calendar_id': lc_id}
    return {
        'linked_calendar_id': lc_id,
        'calendar_summary': lc.summary,
        'calendar_color': lc.background_color,
    }


def _reminders_in_range(q, start: date, end: date):
    """Include events whose span overlaps [start, end] (multi-day aware)."""
    event_end = func.coalesce(Reminder.end_date, Reminder.date)
    return q.filter(Reminder.date <= end, event_end >= start)


def _reminder_visible(r: Reminder, visible_ids: set[int]) -> bool:
    if getattr(r, 'source', None) == 'google' or getattr(r, 'linked_calendar_id', None):
        lid = getattr(r, 'linked_calendar_id', None)
        return lid in visible_ids if lid else False
    return True


def _serialize_reminder(r: Reminder):
    data = {
        'id': r.id,
        'date': r.date.strftime('%Y-%m-%d') if r.date else None,
        'time': getattr(r, 'time', None) or None,
        'title': r.title,
        'description': r.description or '',
        'creator': r.creator or '',
        'category': getattr(r, 'category', None),
        'color': getattr(r, 'color', None),
        'recurring_id': getattr(r, 'recurring_id', None),
        'timestamp': r.timestamp.isoformat() if r.timestamp else None,
        'updated_at': getattr(r, 'updated_at', None).isoformat() if getattr(r, 'updated_at', None) else None,
        'source': getattr(r, 'source', None) or 'local',
        'sync_status': getattr(r, 'sync_status', None) or 'synced',
        'all_day': bool(getattr(r, 'all_day', False)),
        'end_date': r.end_date.strftime('%Y-%m-%d') if getattr(r, 'end_date', None) else None,
        'end_time': getattr(r, 'end_time', None) or None,
        'time_zone': getattr(r, 'time_zone', None) or None,
        'attendees': _serialize_attendees_list(r),
    }
    data.update(_calendar_meta(r))
    try:
        data['can_edit'] = can_modify_reminder(r)
    except Exception:
        data['can_edit'] = can_modify_record(r.creator or '')
    return data

def _serialize_recurring_rule(rr: RecurringReminder):
    interval = getattr(rr, 'interval', None) or 1
    unit = (getattr(rr, 'unit', None) or '').lower()
    if not unit:
        if rr.frequency == 'daily': unit = 'day'
        elif rr.frequency == 'weekly': unit = 'week'
        else: unit = 'month'
    return {
        'id': rr.id,
        'title': rr.title,
        'description': rr.description or '',
        'creator': rr.creator or '',
        'interval': int(interval),
        'unit': unit,
        'time': rr.time,
        'category': rr.category,
        'color': rr.color,
        'start_date': rr.start_date.strftime('%Y-%m-%d') if rr.start_date else None,
        'end_date': rr.end_date.strftime('%Y-%m-%d') if rr.end_date else None,
        'google_recurring_event_id': getattr(rr, 'google_recurring_event_id', None),
        'linked_calendar_id': getattr(rr, 'linked_calendar_id', None),
        'exception_dates': _exception_dates(rr),
    }


@main_bp.route('/api/reminders')
def api_reminders_list():
    from ..google_calendar.acl import visible_linked_calendar_ids
    visible_ids = set(visible_linked_calendar_ids())
    scope = (request.args.get('scope', 'day') or 'day').lower()
    base_date = _parse_date_param(request.args.get('date'), date.today())
    q = Reminder.query
    if scope == 'month':
        start = base_date.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1, day=1)
        else:
            next_month = start.replace(month=start.month + 1, day=1)
        end = next_month - timedelta(days=1)
        q = _reminders_in_range(q, start, end)
    elif scope == 'week':
        start, end = _week_range(base_date)
        q = _reminders_in_range(q, start, end)
    else:
        q = q.filter(Reminder.date == base_date)
    try:
        from sqlalchemy import case
        rows = q.order_by(
            Reminder.date.asc(),
            case((Reminder.time.is_(None), 1), (Reminder.time == '', 1), else_=0).asc(),
            Reminder.time.asc(),
            Reminder.id.asc(),
        ).all()
    except Exception:
        rows = q.order_by(Reminder.date.asc(), Reminder.id.asc()).all()
    rows = [r for r in rows if _reminder_visible(r, visible_ids)]
    # Generate from recurring rules within scope window (without altering past)
    try:
        rules = RecurringReminder.query.all()
    except Exception:
        rules = []
    gen_rows = []
    rule_dates = {}  # rr.id -> list of dates within window
    if scope == 'month':
        window_start = start
        window_end = end
    elif scope == 'week':
        window_start = start
        window_end = end
    else:
        window_start = base_date
        window_end = base_date
    def add_months(dt: date, months: int) -> date:
        y = dt.year + (dt.month - 1 + months) // 12
        m = (dt.month - 1 + months) % 12 + 1
        # clamp to last day of target month
        last = (date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1) - timedelta(days=1)).day
        d = min(dt.day, last)
        return date(y, m, d)
    def add_years(dt: date, years: int) -> date:
        try:
            return date(dt.year + years, dt.month, dt.day)
        except ValueError:
            # Feb 29 -> Feb 28 fallback
            if dt.month == 2 and dt.day == 29:
                return date(dt.year + years, 2, 28)
            # else clamp to last valid day of month
            return add_months(dt, years * 12)
    def next_date_rule(rr, d):
        # Prefer new interval/unit if present
        interval = getattr(rr, 'interval', None) or 1
        unit = (getattr(rr, 'unit', None) or '').lower() or None
        if not unit:
            # legacy mapping
            if rr.frequency == 'daily':
                unit = 'day'; interval = 1
            elif rr.frequency == 'weekly':
                unit = 'week'; interval = 1
            else:
                unit = 'month'; interval = 1
        if unit == 'day':
            return d + timedelta(days=interval)
        if unit == 'week':
            return d + timedelta(weeks=interval)
        if unit == 'month':
            return add_months(d, interval)
        if unit == 'year':
            return add_years(d, interval)
        # default safety
        return d + timedelta(days=interval)
    for rr in rules:
        if getattr(rr, 'google_recurring_event_id', None):
            continue
        exc_set = set(_exception_dates(rr))
        rs = rr.start_date or window_start
        d = rs
        # advance d to window_start if needed
        while d < window_start:
            nd = next_date_rule(rr, d)
            if nd == d:
                break
            d = nd
        while d <= window_end and (not rr.end_date or d <= rr.end_date):
            if d.strftime('%Y-%m-%d') in exc_set:
                d = next_date_rule(rr, d)
                continue
            # ensure not already present in DB rows for that date/title
            if not any((r.date == d and r.title == rr.title and r.recurring_id == rr.id) for r in rows):
                temp = Reminder(date=d, title=rr.title, description=rr.description or '', creator=rr.creator or '', time=rr.time, category=rr.category, color=rr.color)
                temp.id = -(1000000 + rr.id)  # ephemeral negative ID
                temp.recurring_id = rr.id
                gen_rows.append(temp)
            rule_dates.setdefault(rr.id, []).append(d)
            d = next_date_rule(rr, d)
    combined = rows + gen_rows
    # Sort combined
    try:
        combined.sort(key=lambda r: (r.date, (r.time is None or r.time == ''), r.time or '', r.id))
    except Exception:
        pass
    data = [_serialize_reminder(r) for r in combined]
    counts = {}
    categories_counts = {}
    if scope == 'month':
        # Include stored and synthesized rows in counts for calendar dots
        for r in (rows + gen_rows):
            k = r.date.strftime('%Y-%m-%d')
            counts[k] = counts.get(k, 0) + 1
            cat = getattr(r, 'category', None) or '_uncategorized'
            if k not in categories_counts:
                categories_counts[k] = {}
            categories_counts[k][cat] = categories_counts[k].get(cat, 0) + 1

    # Build recurring rules summary for UI compression
    recurring_rules = []
    for rr in rules:
        # Determine interval/unit from new fields or legacy frequency
        interval = getattr(rr, 'interval', None) or 1
        unit = (getattr(rr, 'unit', None) or '').lower()
        if not unit:
            if rr.frequency == 'daily': unit = 'day'
            elif rr.frequency == 'weekly': unit = 'week'
            else: unit = 'month'
        recurring_rules.append({
            'id': rr.id,
            'title': rr.title,
            'description': rr.description or '',
            'creator': rr.creator or '',
            'interval': int(interval),
            'unit': unit,
            'time': rr.time,
            'category': rr.category,
            'color': rr.color,
            'end_date': rr.end_date.strftime('%Y-%m-%d') if rr.end_date else None,
            'dates': [d.strftime('%Y-%m-%d') for d in rule_dates.get(rr.id, [])],
        })
    return jsonify({
        'ok': True,
        'scope': scope,
        'date': base_date.strftime('%Y-%m-%d'),
        'reminders': data,
        'counts': counts,
        'categories_counts': categories_counts,
        'recurring_rules': recurring_rules,
    })


@main_bp.route('/api/recurring_rules/<int:rid>', methods=['PATCH', 'DELETE'])
def api_recurring_rules_update_delete(rid):
    rr = RecurringReminder.query.get_or_404(rid)
    if request.method == 'DELETE':
        payload = request.get_json(silent=True) or {}
        user = resolve_user(json_payload=payload, json_key='creator')
        if not can_modify_record(rr.creator or '', user):
            return jsonify({'ok': False, 'error': 'Not allowed'}), 403
        if getattr(rr, 'linked_calendar_id', None) and getattr(rr, 'google_recurring_event_id', None):
            from ..google_calendar.writes import push_recurring_delete
            lc = LinkedCalendar.query.get(rr.linked_calendar_id)
            if lc:
                push_recurring_delete(rr, lc)
        db.session.delete(rr)
        db.session.commit()
        return jsonify({'ok': True})
    # PATCH
    payload = request.get_json(silent=True) or {}
    user = resolve_user(json_payload=payload, json_key='creator')
    if not can_modify_record(rr.creator or '', user):
        return jsonify({'ok': False, 'error': 'Not allowed'}), 403
    # Updatable fields
    if 'title' in payload: rr.title = sanitize_text(payload.get('title') or rr.title)
    if 'description' in payload: rr.description = sanitize_html(payload.get('description') or '')
    if 'time' in payload:
        time_raw = payload.get('time')
        tval = None
        if isinstance(time_raw, str) and len(time_raw) == 5 and time_raw[2] == ':':
            hh, mm = time_raw.split(':', 1)
            if hh.isdigit() and mm.isdigit():
                hhi, mmi = int(hh), int(mm)
                if 0 <= hhi < 24 and 0 <= mmi < 60:
                    tval = f"{hhi:02d}:{mmi:02d}"
        rr.time = tval
    if 'category' in payload: rr.category = sanitize_text(payload.get('category')) or None
    if 'color' in payload:
        raw = payload.get('color')
        rr.color = normalize_hex_color(raw) if raw else None
    # interval/unit/end_date/start_date
    interval = payload.get('interval')
    try:
        interval = int(interval) if interval is not None else None
    except Exception:
        interval = None
    if interval and interval >= 1: rr.interval = interval
    unit = (payload.get('unit') or '').lower()
    if unit in {'day','week','month','year'}: rr.unit = unit
    def _pd(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except Exception:
            return None
    if 'start_date' in payload:
        sd = _pd(payload.get('start_date'))
        if sd: rr.start_date = sd
    if 'end_date' in payload:
        rr.end_date = _pd(payload.get('end_date'))
    db.session.commit()
    if getattr(rr, 'linked_calendar_id', None) and getattr(rr, 'google_recurring_event_id', None):
        from ..google_calendar.writes import push_recurring_update
        lc = LinkedCalendar.query.get(rr.linked_calendar_id)
        if lc:
            push_recurring_update(rr, lc)
    elif getattr(rr, 'linked_calendar_id', None):
        from ..google_calendar.acl import resolve_writable_calendar
        from ..google_calendar.writes import push_recurring_create
        lc = resolve_writable_calendar(rr.linked_calendar_id)
        if lc:
            push_recurring_create(rr, lc)
    return jsonify({'ok': True, 'rule': _serialize_recurring_rule(rr)})


@main_bp.route('/api/recurring_rules/<int:rid>/occurrence', methods=['PATCH'])
def api_recurring_occurrence(rid):
    from ..google_calendar.acl import google_calendar_enabled, resolve_writable_calendar
    from ..google_calendar.writes import push_reminder_create, push_recurring_update

    rr = RecurringReminder.query.get_or_404(rid)
    payload = request.get_json(silent=True) or {}
    user = resolve_user(json_payload=payload, json_key='creator')
    if not can_modify_record(rr.creator or '', user):
        return jsonify({'ok': False, 'error': 'Not allowed'}), 403
    occ_date = _parse_date_param(payload.get('occurrence_date'), None)
    if not occ_date:
        return jsonify({'ok': False, 'error': 'occurrence_date required'}), 400
    scope = (payload.get('scope') or 'this').lower()
    patch = payload.get('patch') or {}
    if scope == 'series':
        if 'date' in patch:
            sd = _parse_date_param(patch.get('date'), None)
            if sd:
                rr.start_date = sd
        if 'time' in patch:
            rr.time = _parse_time_field(patch.get('time'))
        if 'title' in patch:
            rr.title = sanitize_text(patch.get('title') or rr.title)
        db.session.commit()
        if rr.linked_calendar_id:
            lc = LinkedCalendar.query.get(rr.linked_calendar_id)
            if lc:
                push_recurring_update(rr, lc)
        return jsonify({'ok': True, 'rule': _serialize_recurring_rule(rr)})
    _add_exception_date(rr, occ_date)
    db.session.commit()
    new_date = _parse_date_param(patch.get('date'), occ_date)
    r = Reminder(
        date=new_date,
        title=sanitize_text(patch.get('title') or rr.title),
        description=rr.description or '',
        creator=resolve_actor(json_payload=payload),
        time=_parse_time_field(patch.get('time')) if patch.get('time') else rr.time,
        category=rr.category,
        color=rr.color,
        all_day=not bool(patch.get('time') or rr.time),
    )
    if patch.get('end_date'):
        r.end_date = _parse_date_param(patch.get('end_date'), None)
    if patch.get('end_time'):
        r.end_time = _parse_time_field(patch.get('end_time'))
    db.session.add(r)
    db.session.commit()
    lc = None
    if google_calendar_enabled() and rr.linked_calendar_id:
        lc = resolve_writable_calendar(rr.linked_calendar_id)
        if lc:
            r.source = 'google'
            r.linked_calendar_id = lc.id
            r.owner_uid = current_firebase_uid()
            db.session.commit()
            push_reminder_create(r, lc)
    return jsonify({'ok': True, 'reminder': _serialize_reminder(r)})


def _parse_time_field(time_raw):
    tval = None
    if isinstance(time_raw, str) and len(time_raw) == 5 and time_raw[2] == ':':
        hh, mm = time_raw.split(':', 1)
        if hh.isdigit() and mm.isdigit():
            hhi, mmi = int(hh), int(mm)
            if 0 <= hhi < 24 and 0 <= mmi < 60:
                tval = f"{hhi:02d}:{mmi:02d}"
    return tval


def _apply_schedule_fields(reminder: Reminder, payload: dict) -> None:
    if 'all_day' in payload:
        reminder.all_day = bool(payload.get('all_day'))
    if 'date' in payload:
        nd = _parse_date_param(payload.get('date'), None)
        if nd:
            reminder.date = nd
    if 'end_date' in payload:
        reminder.end_date = _parse_date_param(payload.get('end_date'), None)
    if 'time' in payload:
        raw = payload.get('time')
        reminder.time = _parse_time_field(raw) if raw else None
    if 'end_time' in payload:
        raw = payload.get('end_time')
        reminder.end_time = _parse_time_field(raw) if raw else None
    if reminder.all_day:
        reminder.time = None
        reminder.end_time = None
        if not reminder.end_date:
            reminder.end_date = reminder.date


@main_bp.route('/api/reminders', methods=['POST'])
def api_reminders_create():
    from ..google_calendar.acl import google_calendar_enabled, resolve_writable_calendar
    from ..google_calendar.writes import push_reminder_create

    payload = request.get_json(silent=True) or {}
    title = sanitize_text(payload.get('title', ''))
    creator = resolve_actor(json_payload=payload)
    description = sanitize_html(payload.get('description', ''))
    if not title:
        return jsonify({'ok': False, 'error': 'Title required'}), 400
    d = _parse_date_param(payload.get('date'), None)
    if not d:
        return jsonify({'ok': False, 'error': 'Invalid date'}), 400
    tval = _parse_time_field(payload.get('time'))
    # Recurring support (optional)
    recur = payload.get('recurring')
    if recur and isinstance(recur, dict):
        # New shape: interval+unit; support legacy 'frequency' for compatibility
        interval = recur.get('interval')
        try:
            interval = int(interval)
        except Exception:
            interval = None
        if not interval or interval < 1:
            interval = 1
        unit = (recur.get('unit') or '').lower()
        if unit not in {'day','week','month','year'}:
            # legacy path
            freq = sanitize_text(recur.get('frequency') or 'daily')
            unit = 'day' if freq == 'daily' else ('week' if freq == 'weekly' else 'month')
        end_s = recur.get('end_date'); end_d = _parse_date_param(end_s, None)
        rr = RecurringReminder(title=title, description=description, creator=creator,
                               interval=interval, unit=unit,
                               frequency=None, monthly_mode=None,
                               time=tval, category=payload.get('category'),
                               color=normalize_hex_color(payload.get('color')) if payload.get('color') else None,
                               start_date=d, end_date=end_d, effective_from=d)
        lc = None
        if google_calendar_enabled():
            lc_id = payload.get('linked_calendar_id')
            try:
                lc_id = int(lc_id) if lc_id is not None else None
            except (TypeError, ValueError):
                return jsonify({'ok': False, 'error': 'Invalid calendar'}), 400
            lc = resolve_writable_calendar(lc_id)
            if lc_id is not None and not lc:
                return jsonify({'ok': False, 'error': 'Invalid calendar'}), 400
            if lc:
                rr.linked_calendar_id = lc.id
                rr.owner_uid = current_firebase_uid()
                rr.source = 'google'
        db.session.add(rr)
        db.session.commit()
        if lc:
            from ..google_calendar.writes import push_recurring_create
            push_recurring_create(rr, lc)
        return jsonify({'ok': True, 'recurring_id': rr.id, 'rule': _serialize_recurring_rule(rr)})
    all_day = bool(payload.get('all_day'))
    if all_day:
        tval = None
    r = Reminder(
        date=d, title=title, description=description, creator=creator, time=tval,
        all_day=all_day,
        end_date=_parse_date_param(payload.get('end_date'), None) or (d if all_day else None),
        end_time=_parse_time_field(payload.get('end_time')) if not all_day else None,
    )
    cat = payload.get('category'); col = payload.get('color')
    if hasattr(r, 'category'):
        r.category = sanitize_text(cat) if cat else None
    if hasattr(r, 'color'):
        r.color = normalize_hex_color(col) if col else None
    tz = sanitize_text(payload.get('time_zone') or '')
    if hasattr(r, 'time_zone'):
        r.time_zone = tz if tz else None
    if 'attendees' in payload and hasattr(r, 'attendees_json'):
        att = _parse_attendees_field(payload.get('attendees'))
        r.attendees_json = json.dumps(att) if att else None
    lc = None
    if google_calendar_enabled():
        lc_id = payload.get('linked_calendar_id')
        try:
            lc_id = int(lc_id) if lc_id is not None else None
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid calendar'}), 400
        lc = resolve_writable_calendar(lc_id)
        if lc_id is not None and not lc:
            return jsonify({'ok': False, 'error': 'Invalid calendar'}), 400
        if lc:
            r.source = 'google'
            r.linked_calendar_id = lc.id
            r.owner_uid = current_firebase_uid()
            if 'all_day' not in payload:
                r.all_day = not tval
    db.session.add(r)
    db.session.commit()
    if lc:
        push_reminder_create(r, lc)
    return jsonify({'ok': True, 'reminder': _serialize_reminder(r)})


@main_bp.route('/api/reminders/<int:rid>', methods=['PATCH'])
def api_reminders_update(rid):
    from ..google_calendar.acl import google_calendar_enabled, resolve_writable_calendar
    from ..google_calendar.writes import push_reminder_move, push_reminder_update

    r = Reminder.query.get_or_404(rid)
    payload = request.get_json(silent=True) or {}
    user = resolve_user(json_payload=payload, json_key='creator')
    if not can_modify_reminder(r):
        return jsonify({'ok': False, 'error': 'Not allowed'}), 403
    if 'title' in payload:
        title = sanitize_text(payload['title'])
        if title:
            r.title = title
    if 'description' in payload:
        r.description = sanitize_html(payload['description'])
    _apply_schedule_fields(r, payload)
    if hasattr(r, 'category') and 'category' in payload:
        r.category = sanitize_text(payload.get('category')) if payload.get('category') else None
    if hasattr(r, 'color') and 'color' in payload:
        raw = payload.get('color')
        r.color = normalize_hex_color(raw) if raw else None
    if hasattr(r, 'time_zone') and 'time_zone' in payload:
        tz = sanitize_text(payload.get('time_zone') or '')
        r.time_zone = tz if tz else None
    if 'attendees' in payload and hasattr(r, 'attendees_json'):
        att = _parse_attendees_field(payload.get('attendees'))
        r.attendees_json = json.dumps(att) if att else None
    occ_scope = (payload.get('occurrence_scope') or '').lower()
    if occ_scope == 'this' and r.recurring_id:
        rr = RecurringReminder.query.get(r.recurring_id)
        if rr:
            _add_exception_date(rr, r.date)
        r.recurring_id = None
    elif occ_scope == 'series' and r.recurring_id:
        rr = RecurringReminder.query.get(r.recurring_id)
        if rr:
            if 'date' in payload:
                sd = _parse_date_param(payload.get('date'), None)
                if sd:
                    rr.start_date = sd
            if 'time' in payload:
                rr.time = _parse_time_field(payload.get('time'))
            if 'title' in payload and payload.get('title'):
                rr.title = sanitize_text(payload['title'])
            from ..google_calendar.writes import push_recurring_update
            if rr.linked_calendar_id:
                lc_rr = LinkedCalendar.query.get(rr.linked_calendar_id)
                if lc_rr:
                    push_recurring_update(rr, lc_rr)
        r.recurring_id = None
    new_lc = None
    if google_calendar_enabled() and 'linked_calendar_id' in payload:
        try:
            new_lc_id = int(payload.get('linked_calendar_id')) if payload.get('linked_calendar_id') is not None else None
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Invalid calendar'}), 400
        new_lc = resolve_writable_calendar(new_lc_id) if new_lc_id else None
        if new_lc_id is not None and not new_lc:
            return jsonify({'ok': False, 'error': 'Invalid calendar'}), 400
    db.session.commit()
    if google_calendar_enabled():
        if new_lc and r.linked_calendar_id and new_lc.id != r.linked_calendar_id:
            old_lc = LinkedCalendar.query.get(r.linked_calendar_id)
            if old_lc and r.google_event_id:
                push_reminder_move(r, old_lc, new_lc)
            else:
                r.linked_calendar_id = new_lc.id
                push_reminder_create(r, new_lc) if not r.google_event_id else push_reminder_update(r, new_lc)
        elif new_lc and not r.linked_calendar_id:
            r.linked_calendar_id = new_lc.id
            r.source = 'google'
            r.owner_uid = current_firebase_uid()
            push_reminder_create(r, new_lc)
        elif r.linked_calendar_id and (r.source == 'google' or r.google_event_id):
            lc = LinkedCalendar.query.get(r.linked_calendar_id)
            if lc:
                push_reminder_update(r, lc)
    return jsonify({'ok': True, 'reminder': _serialize_reminder(r)})


@main_bp.route('/api/reminders/<int:rid>/resolve-conflict', methods=['PATCH'])
def api_reminders_resolve_conflict(rid):
    from ..google_calendar.writes import apply_google_event_to_reminder, push_reminder_update

    r = Reminder.query.get_or_404(rid)
    if not can_modify_reminder(r):
        return jsonify({'ok': False, 'error': 'Not allowed'}), 403
    payload = request.get_json(silent=True) or {}
    choice = (payload.get('resolution') or '').lower()
    if choice == 'google':
        if r.linked_calendar_id:
            lc = LinkedCalendar.query.get(r.linked_calendar_id)
            if lc and not apply_google_event_to_reminder(r, lc):
                return jsonify({'ok': False, 'error': 'Could not load Google version'}), 502
        else:
            r.sync_status = 'synced'
            db.session.commit()
        return jsonify({'ok': True, 'reminder': _serialize_reminder(r)})
    if choice == 'local':
        r.sync_status = 'synced'
        db.session.commit()
        if r.linked_calendar_id:
            lc = LinkedCalendar.query.get(r.linked_calendar_id)
            if lc:
                push_reminder_update(r, lc)
        return jsonify({'ok': True, 'reminder': _serialize_reminder(r)})
    return jsonify({'ok': False, 'error': 'resolution required (google|local)'}), 400


@main_bp.route('/api/reminders', methods=['DELETE'])
def api_reminders_delete_bulk():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids') or []
    user = resolve_user(json_payload=payload, json_key='creator')
    if not isinstance(ids, list) or not ids:
        return jsonify({'ok': False, 'error': 'No ids provided'}), 400
    deleted = 0
    dates = set()
    for rid in ids:
        if not isinstance(rid, int):
            continue
        r = Reminder.query.get(rid)
        if not r:
            continue
        if can_modify_reminder(r):
            if r.date:
                dates.add(r.date.strftime('%Y-%m-%d'))
            if r.linked_calendar_id and r.google_event_id:
                from ..google_calendar.writes import push_reminder_delete
                lc = LinkedCalendar.query.get(r.linked_calendar_id)
                if lc:
                    push_reminder_delete(r, lc)
            db.session.delete(r)
            deleted += 1
    if deleted:
        db.session.commit()
    return jsonify({'ok': True, 'deleted': deleted, 'dates': list(dates)})


@main_bp.route('/calendar/add', methods=['POST'])
def add_reminder():
    date_s = sanitize_text(request.form.get('date'))
    title = sanitize_text(request.form.get('title'))
    description = sanitize_html(request.form.get('description'))
    creator = resolve_actor()
    if not (date_s and title):
        flash('Date and title are required for reminders.', 'error')
        return redirect(url_for('main.index'))
    try:
        d = datetime.strptime(date_s, '%Y-%m-%d').date()
    except Exception:
        flash('Invalid date.', 'error')
        return redirect(url_for('main.index'))
    r = Reminder(date=d, title=title, description=description, creator=creator)
    db.session.add(r)
    db.session.commit()
    flash('Reminder added.', 'success')
    return redirect(url_for('main.index', date=date_s))


@main_bp.route('/calendar/delete/<int:reminder_id>', methods=['POST'])
def delete_reminder(reminder_id):
    r = Reminder.query.get_or_404(reminder_id)
    user = resolve_user()
    if can_modify_record(r.creator, user):
        db.session.delete(r)
        db.session.commit()
        flash('Reminder deleted.', 'success')
    else:
        flash('Not allowed to delete this reminder.', 'error')
    date_s = None
    try:
        if r.date:
            date_s = r.date.strftime('%Y-%m-%d')
    except Exception:
        date_s = None
    return redirect(url_for('main.index', date=date_s) if date_s else url_for('main.index'))


@main_bp.route('/calendar/delete_bulk', methods=['POST'])
def delete_reminders_bulk():
    ids_raw = sanitize_text(request.form.get('ids', ''))
    user = resolve_user()
    if not ids_raw:
        return redirect(url_for('main.index'))
    id_list = []
    for part in ids_raw.split(','):
        part = part.strip()
        if part.isdigit():
            id_list.append(int(part))
    if not id_list:
        return redirect(url_for('main.index'))
    kept_date = None
    deleted = 0
    for rid in id_list:
        r = Reminder.query.get(rid)
        if not r:
            continue
        if kept_date is None and getattr(r, 'date', None):
            try:
                kept_date = r.date.strftime('%Y-%m-%d')
            except Exception:
                kept_date = None
        if can_modify_record(r.creator, user):
            db.session.delete(r)
            deleted += 1
    if deleted:
        db.session.commit()
        flash(f'Deleted {deleted} reminder(s).', 'success')
    else:
        flash('No reminders deleted (permission?).', 'error')
    return redirect(url_for('main.index', date=kept_date) if kept_date else url_for('main.index'))


@main_bp.route('/notice', methods=['POST'])
def update_notice():
    content = sanitize_html(request.form.get('content', ''))
    from ..user_context import is_admin, current_display_name
    if not is_admin():
        flash('Only admin can update the notice.', 'error')
        return redirect(url_for('main.index'))
    user = current_display_name()
    n = Notice.query.order_by(Notice.updated_at.desc()).first()
    now = datetime.utcnow()
    if n:
        n.content = content
        n.updated_by = user
        n.updated_at = now
    else:
        db.session.add(Notice(content=content, updated_by=user, updated_at=now))
    db.session.commit()
    flash('Notice updated.', 'success')
    return redirect(url_for('main.index'))


@main_bp.route('/whoishome', methods=['POST'])
def who_is_home_action():
    action = sanitize_text(request.form.get('action', 'update'))
    config = current_app.config['HOMEHUB_CONFIG']
    family = set(config.get('family_members', []))
    name = sanitize_text(request.form.get('name', ''))
    if not name or name not in family:
        if request.headers.get('X-Requested-With') != 'fetch':
            flash('Invalid user for status.', 'error')
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': False, 'error': 'Invalid user'}), 400
        return redirect(url_for('main.index'))
    result = None
    if action == 'clear':
        hs = HomeStatus.query.filter_by(name=name).first()
        if hs:
            db.session.delete(hs)
            db.session.commit()
            result = 'cleared'
            if request.headers.get('X-Requested-With') != 'fetch':
                flash('Status cleared.', 'success')
        else:
            result = 'none'
            if request.headers.get('X-Requested-With') != 'fetch':
                flash('No status to clear.', 'info')
    else:
        status = sanitize_text(request.form.get('status', '')) or 'Away'
        hs = HomeStatus.query.filter_by(name=name).first()
        if hs:
            hs.status = status
        else:
            db.session.add(HomeStatus(name=name, status=status))
        db.session.commit()
        result = 'updated'
        if request.headers.get('X-Requested-With') != 'fetch':
            flash('Status updated.', 'success')
    if request.headers.get('X-Requested-With') == 'fetch':
        who_statuses = {s.name: s.status for s in HomeStatus.query.all() if s.name in family}
        member_statuses = {ms.name: ms.text for ms in MemberStatus.query.all() if ms.name in family and (ms.text or '').strip()}
        result = result or 'updated'
        return jsonify({'ok': True, 'who_statuses': who_statuses, 'member_statuses': member_statuses, 'result': result})
    date_q = request.args.get('date') or request.form.get('date')
    return redirect(url_for('main.index', date=date_q) if date_q else url_for('main.index'))


@main_bp.route('/status/update', methods=['POST'])
def member_status_update():
    config = current_app.config['HOMEHUB_CONFIG']
    family = set(config.get('family_members', []))
    name = sanitize_text(request.form.get('name', ''))
    raw_text = request.form.get('text', '') or ''
    text = sanitize_text(raw_text)
    if not name or name not in family:
        if request.headers.get('X-Requested-With') != 'fetch':
            flash('Invalid user for status.', 'error')
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': False, 'error': 'Invalid user'}), 400
        return redirect(url_for('main.index'))
    if not text:
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': False, 'error': 'Empty status'}), 400
        else:
            flash('Status cannot be empty.', 'error')
            return redirect(url_for('main.index'))
    ms = MemberStatus.query.filter_by(name=name).first()
    now = datetime.utcnow()
    if ms:
        ms.text = text
        ms.updated_at = now
    else:
        db.session.add(MemberStatus(name=name, text=text, updated_at=now))
    db.session.commit()
    if request.headers.get('X-Requested-With') != 'fetch':
        flash('Status saved.', 'success')
    if request.headers.get('X-Requested-With') == 'fetch':
        who_statuses = {s.name: s.status for s in HomeStatus.query.all() if s.name in family}
        member_statuses = {ms.name: ms.text for ms in MemberStatus.query.all() if ms.name in family and (ms.text or '').strip()}
        return jsonify({'ok': True, 'who_statuses': who_statuses, 'member_statuses': member_statuses, 'result': 'saved'})
    return redirect(url_for('main.index'))


@main_bp.route('/status/delete', methods=['POST'])
def member_status_delete():
    config = current_app.config['HOMEHUB_CONFIG']
    family = set(config.get('family_members', []))
    name = sanitize_text(request.form.get('name', ''))
    if not name or name not in family:
        if request.headers.get('X-Requested-With') != 'fetch':
            flash('Invalid user for status removal.', 'error')
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': False, 'error': 'Invalid user'}), 400
        return redirect(url_for('main.index'))
    ms = MemberStatus.query.filter_by(name=name).first()
    removed = False
    if ms:
        db.session.delete(ms)
        db.session.commit()
        removed = True
        if request.headers.get('X-Requested-With') != 'fetch':
            flash('Status removed.', 'success')
    if request.headers.get('X-Requested-With') == 'fetch':
        who_statuses = {s.name: s.status for s in HomeStatus.query.all() if s.name in family}
        member_statuses = {ms.name: ms.text for ms in MemberStatus.query.all() if ms.name in family and (ms.text or '').strip()}
        return jsonify({'ok': True, 'who_statuses': who_statuses, 'member_statuses': member_statuses, 'result': 'removed' if removed else 'none'})
    return redirect(url_for('main.index'))
