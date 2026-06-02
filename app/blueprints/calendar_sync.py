"""Google Calendar OAuth and management API."""

from __future__ import annotations

import os
import secrets
from datetime import datetime

from flask import (
    current_app,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from google_auth_oauthlib.flow import Flow

from ..extensions import limiter
from ..google_calendar.acl import (
    calendar_connection_active,
    can_view_linked_calendar,
    get_connection_for_uid,
    google_calendar_enabled,
    owns_linked_calendar,
    resolve_writable_calendar,
)
from ..google_calendar.client import list_calendar_list
from ..google_calendar.mapper import infer_source_category
from ..google_calendar.sync import ensure_display_prefs_for_viewer, sync_connection
from ..google_calendar.imports import (
    ImportSelection,
    ensure_default_personal_calendar,
    set_connection_sync_mode,
    upsert_category_mappings,
    upsert_import_mapping,
)
from ..models import (
    CalendarConnection,
    CalendarDisplayPref,
    CalendarImportMapping,
    CalendarImportProfile,
    CalendarShare,
    CategoryImportMapping,
    LinkedCalendar,
    PersonalCalendar,
    Reminder,
    db,
)
from ..sensitive_store import encrypt_sensitive
from ..security import normalize_hex_color
from ..user_context import current_email, uses_firebase
from . import main_bp

OAUTH_CALLBACK = 'main.google_calendar_oauth_callback'
SESSION_OAUTH_STATE = 'google_calendar_oauth_state'
SESSION_OAUTH_CODE_VERIFIER = 'google_calendar_oauth_code_verifier'
OAUTH_SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/calendar',
]
ALLOWED_VISIBILITY = {'private', 'household', 'custom'}


def _clear_oauth_session() -> None:
    session.pop(SESSION_OAUTH_STATE, None)
    session.pop(SESSION_OAUTH_CODE_VERIFIER, None)


def _gcal_cfg() -> dict:
    return (current_app.config.get('HOMEHUB_CONFIG') or {}).get('google_calendar') or {}


def _oauth_redirect_uri() -> str:
    callback_path = url_for(OAUTH_CALLBACK, _external=False)
    base = (_gcal_cfg().get('redirect_base_url') or '').strip()
    if base:
        return base.rstrip('/') + callback_path
    return url_for(OAUTH_CALLBACK, _external=True)


def _allow_insecure_oauth_transport(redirect_uri: str) -> None:
    # Local dev OAuth callbacks are commonly http://localhost. Allow them explicitly.
    low = (redirect_uri or '').lower()
    if low.startswith('http://localhost') or low.startswith('http://127.0.0.1') or low.startswith('http://10.'):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


def _require_firebase_calendar():
    if not uses_firebase():
        return jsonify({'ok': False, 'error': 'firebase_required'}), 400
    if not google_calendar_enabled():
        return jsonify({'ok': False, 'error': 'google_calendar_disabled'}), 400
    return None


def _flow(redirect_uri: str) -> Flow:
    cfg = _gcal_cfg()
    client_config = {
        'web': {
            'client_id': cfg.get('client_id'),
            'client_secret': cfg.get('client_secret'),
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )


def _serialize_linked(lc: LinkedCalendar, viewer_uid: str, conn: CalendarConnection) -> dict:
    pref = CalendarDisplayPref.query.filter_by(
        viewer_uid=viewer_uid, linked_calendar_id=lc.id
    ).first()
    shares = [
        {'grantee_uid': s.grantee_uid, 'can_write': bool(s.can_write)}
        for s in CalendarShare.query.filter_by(linked_calendar_id=lc.id).all()
    ]
    return {
        'id': lc.id,
        'google_calendar_id': lc.google_calendar_id,
        'summary': lc.summary,
        'background_color': lc.background_color,
        'sync_enabled': bool(lc.sync_enabled),
        'visibility': lc.visibility,
        'visible': pref.visible if pref is not None else True,
        'writable': owns_linked_calendar(lc, viewer_uid),
        'is_default': conn.default_linked_calendar_id == lc.id,
        'last_sync_at': lc.last_sync_at.isoformat() if lc.last_sync_at else None,
        'last_sync_error': lc.last_sync_error,
        'shares': shares,
    }


def _serialize_personal_calendar(pc: PersonalCalendar) -> dict:
    return {
        'id': pc.id,
        'owner_uid': pc.owner_uid,
        'name': pc.name,
        'color': pc.color,
        'visibility': pc.visibility,
        'archived': bool(pc.archived),
    }


def _allow_bidirectional_opt_in() -> bool:
    return bool(_gcal_cfg().get('allow_bidirectional_opt_in', True))


def _infer_google_categories(conn: CalendarConnection, google_calendar_id: str, limit: int = 100) -> list[dict]:
    common: dict[str, str] = {
        'default': 'Default',
        'focusTime': 'Focus Time',
        'outOfOffice': 'Out of Office',
        'workingLocation': 'Working Location',
        'birthday': 'Birthday',
        'fromGmail': 'From Gmail',
    }
    for i in range(1, 12):
        common[f'google_color_{i}'] = f'Google Color {i}'
    if not google_calendar_id:
        return [{'key': k, 'label': v} for k, v in sorted(common.items(), key=lambda item: item[1].lower())]
    try:
        from ..google_calendar.client import get_calendar_service

        service = get_calendar_service(conn)
        resp = service.events().list(
            calendarId=google_calendar_id,
            maxResults=max(1, min(limit, 250)),
            singleEvents=False,
            showDeleted=False,
        ).execute()
        events = resp.get('items') or []
    except Exception:
        current_app.logger.exception('calendar import options: category inference failed')
        return [{'key': k, 'label': v} for k, v in sorted(common.items(), key=lambda item: item[1].lower())]
    seen: dict[str, str] = dict(common)
    for event in events:
        key, label = infer_source_category(event)
        if not key or key in seen:
            continue
        seen[key] = label
    return [{'key': k, 'label': v} for k, v in sorted(seen.items(), key=lambda item: item[1].lower())]


@main_bp.route('/auth/google/calendar/start')
@limiter.limit('10 per hour')
def google_calendar_oauth_start():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    if not uid:
        return redirect(url_for('main.login', next=request.path))
    nonce = secrets.token_urlsafe(16)
    session[SESSION_OAUTH_STATE] = nonce
    redirect_uri = _oauth_redirect_uri()
    _allow_insecure_oauth_transport(redirect_uri)
    flow = _flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=nonce,
    )
    if not flow.code_verifier:
        current_app.logger.error('google calendar oauth: missing PKCE code_verifier after authorization_url')
        return redirect(url_for('main.calendar_page', calendar_error='oauth_failed'))
    session[SESSION_OAUTH_CODE_VERIFIER] = flow.code_verifier
    conn = CalendarConnection.query.filter_by(firebase_uid=uid).first()
    if not conn:
        conn = CalendarConnection(
            firebase_uid=uid,
            firebase_email=current_email(),
            oauth_state_nonce=nonce,
            time_zone=_gcal_cfg().get('default_timezone', 'UTC'),
        )
        db.session.add(conn)
    else:
        conn.oauth_state_nonce = nonce
    db.session.commit()
    return redirect(auth_url)


@main_bp.route('/auth/google/calendar/callback')
@limiter.limit('20 per hour')
def google_calendar_oauth_callback():
    if not uses_firebase() or not google_calendar_enabled():
        return redirect(url_for('main.index'))
    uid = session.get('firebase_uid')
    if not uid:
        return redirect(url_for('main.login'))
    state = request.args.get('state')
    if not state or state != session.get(SESSION_OAUTH_STATE):
        return redirect(url_for('main.index', calendar_error='invalid_state'))
    code_verifier = session.pop(SESSION_OAUTH_CODE_VERIFIER, None)
    if not code_verifier:
        current_app.logger.error('google calendar oauth callback: missing PKCE code_verifier in session')
        _clear_oauth_session()
        return redirect(url_for('main.calendar_page', calendar_error='oauth_failed'))
    redirect_uri = _oauth_redirect_uri()
    _allow_insecure_oauth_transport(redirect_uri)
    flow = _flow(redirect_uri)
    flow.code_verifier = code_verifier
    flow.autogenerate_code_verifier = False
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as exc:
        current_app.logger.exception('google calendar oauth token exchange failed')
        _clear_oauth_session()
        code = 'oauth_failed'
        if 'insecure_transport' in str(exc).lower():
            code = 'oauth_insecure_transport'
        return redirect(url_for('main.calendar_page', calendar_error=code))
    creds = flow.credentials
    conn = CalendarConnection.query.filter_by(firebase_uid=uid).first()
    if not conn:
        conn = CalendarConnection(firebase_uid=uid, firebase_email=current_email())
        db.session.add(conn)
    conn.refresh_token_enc = encrypt_sensitive(creds.refresh_token or '')
    conn.access_token_enc = encrypt_sensitive(creds.token or '')
    conn.token_expiry = creds.expiry
    conn.connected_at = datetime.utcnow()
    set_connection_sync_mode(conn, _gcal_cfg().get('default_sync_mode'))
    db.session.commit()
    _clear_oauth_session()

    from ..google_calendar.client import get_calendar_service
    service = get_calendar_service(conn)
    items = list_calendar_list(service)
    enable_all = _gcal_cfg().get('onboarding_all_calendars_enabled', True)
    primary_lc = None
    existing_ids = {
        lc.google_calendar_id: lc
        for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all()
    }
    for item in items:
        gid = item.get('id')
        if not gid:
            continue
        lc = existing_ids.get(gid)
        if not lc:
            lc = LinkedCalendar(
                connection_id=conn.id,
                google_calendar_id=gid,
                summary=item.get('summary') or gid,
                background_color=item.get('backgroundColor'),
                sync_enabled=bool(enable_all),
                visibility='household',
            )
            db.session.add(lc)
            db.session.flush()
        else:
            lc.summary = item.get('summary') or lc.summary
            lc.background_color = item.get('backgroundColor') or lc.background_color
        if item.get('primary'):
            primary_lc = lc
        for other_conn in CalendarConnection.query.all():
            ensure_display_prefs_for_viewer(other_conn.firebase_uid, lc)
    default_pc = ensure_default_personal_calendar(uid)
    for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all():
        mapping = CalendarImportMapping.query.filter_by(
            connection_id=conn.id,
            linked_calendar_id=lc.id,
        ).first()
        if not mapping:
            db.session.add(
                CalendarImportMapping(
                    connection_id=conn.id,
                    linked_calendar_id=lc.id,
                    personal_calendar_id=default_pc.id,
                    import_enabled=bool(lc.sync_enabled),
                    import_color=lc.background_color,
                )
            )
    if primary_lc:
        conn.default_linked_calendar_id = primary_lc.id
    elif not conn.default_linked_calendar_id:
        first = LinkedCalendar.query.filter_by(connection_id=conn.id).first()
        if first:
            conn.default_linked_calendar_id = first.id
    db.session.commit()
    # Do not auto-import on connect. User should review and run import wizard explicitly.
    return redirect(url_for('main.calendar_page', calendar_connected='1', connect_calendar='1'))


@main_bp.route('/api/calendar/status')
def api_calendar_status():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': True, 'connected': False, 'oauth_redirect_uri': _oauth_redirect_uri()})
    if not calendar_connection_active(conn):
        return jsonify({
            'ok': True,
            'connected': False,
            'connection_incomplete': True,
            'oauth_redirect_uri': _oauth_redirect_uri(),
        })
    cals = LinkedCalendar.query.filter_by(connection_id=conn.id).count()
    return jsonify({
        'ok': True,
        'connected': True,
        'last_sync_at': conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        'calendar_count': cals,
        'default_linked_calendar_id': conn.default_linked_calendar_id,
        'sync_mode': conn.sync_mode or 'import_only',
        'allow_bidirectional_opt_in': _allow_bidirectional_opt_in(),
        'oauth_redirect_uri': _oauth_redirect_uri(),
    })


@main_bp.route('/api/calendar/writable-calendars')
def api_calendar_writable():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn or not calendar_connection_active(conn):
        return jsonify({'ok': True, 'calendars': []})
    out = []
    for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all():
        out.append({
            'id': lc.id,
            'summary': lc.summary,
            'background_color': lc.background_color,
            'is_default': conn.default_linked_calendar_id == lc.id,
        })
    personal = [
        _serialize_personal_calendar(pc)
        for pc in PersonalCalendar.query.filter_by(owner_uid=uid, archived=False).order_by(PersonalCalendar.name.asc()).all()
    ]
    return jsonify({'ok': True, 'calendars': out, 'personal_calendars': personal})


@main_bp.route('/api/calendar/calendars')
def api_calendar_list():
    err = _require_firebase_calendar()
    if err:
        return err
    viewer_uid = session.get('firebase_uid')
    conn = get_connection_for_uid(viewer_uid)
    own = []
    if conn and calendar_connection_active(conn):
        own = [_serialize_linked(lc, viewer_uid, conn) for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all()]
    visible = []
    for lc in LinkedCalendar.query.all():
        if conn and lc.connection_id == conn.id:
            continue
        if can_view_linked_calendar(lc, viewer_uid):
            c = lc.connection
            if c:
                visible.append(_serialize_linked(lc, viewer_uid, c))
    personal = []
    if viewer_uid:
        personal = [
            _serialize_personal_calendar(pc)
            for pc in PersonalCalendar.query.filter_by(owner_uid=viewer_uid, archived=False).order_by(PersonalCalendar.name.asc()).all()
        ]
    return jsonify({'ok': True, 'own': own, 'visible': visible, 'personal_calendars': personal})


@main_bp.route('/api/calendar/calendars/<int:lc_id>', methods=['PATCH'])
def api_calendar_patch(lc_id):
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    lc = LinkedCalendar.query.get_or_404(lc_id)
    if not owns_linked_calendar(lc, uid):
        return jsonify({'ok': False, 'error': 'Not allowed'}), 403
    conn = lc.connection
    payload = request.get_json(silent=True) or {}
    if 'sync_enabled' in payload:
        lc.sync_enabled = bool(payload['sync_enabled'])
    if 'visibility' in payload:
        vis = (payload.get('visibility') or '').lower()
        if vis in ALLOWED_VISIBILITY:
            lc.visibility = vis
    if payload.get('set_default'):
        conn.default_linked_calendar_id = lc.id
    if 'background_color' in payload:
        from ..security import normalize_hex_color

        hc = normalize_hex_color(payload.get('background_color'))
        if hc:
            lc.background_color = hc
        elif payload.get('background_color') in (None, ''):
            pass
        else:
            return jsonify({'ok': False, 'error': 'Invalid color'}), 400
    db.session.commit()
    return jsonify({'ok': True, 'calendar': _serialize_linked(lc, uid, conn)})


@main_bp.route('/api/calendar/calendars/<int:lc_id>/shares', methods=['PUT'])
def api_calendar_shares(lc_id):
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    lc = LinkedCalendar.query.get_or_404(lc_id)
    if not owns_linked_calendar(lc, uid):
        return jsonify({'ok': False, 'error': 'Not allowed'}), 403
    payload = request.get_json(silent=True) or {}
    shares = payload.get('shares') or []
    CalendarShare.query.filter_by(linked_calendar_id=lc.id).delete()
    for s in shares:
        grantee = (s.get('grantee_uid') or '').strip()
        if not grantee:
            continue
        db.session.add(
            CalendarShare(
                linked_calendar_id=lc.id,
                grantee_uid=grantee,
                can_write=bool(s.get('can_write')),
            )
        )
    lc.visibility = 'custom'
    db.session.commit()
    return jsonify({'ok': True})


@main_bp.route('/api/calendar/display-prefs', methods=['PATCH'])
def api_calendar_display_prefs():
    err = _require_firebase_calendar()
    if err:
        return err
    viewer_uid = session.get('firebase_uid')
    payload = request.get_json(silent=True) or {}
    prefs = payload.get('prefs') or []
    for p in prefs:
        lc_id = p.get('linked_calendar_id')
        if lc_id is None:
            continue
        lc = LinkedCalendar.query.get(lc_id)
        if not lc or not can_view_linked_calendar(lc, viewer_uid):
            continue
        row = CalendarDisplayPref.query.filter_by(
            viewer_uid=viewer_uid, linked_calendar_id=lc_id
        ).first()
        if not row:
            row = CalendarDisplayPref(viewer_uid=viewer_uid, linked_calendar_id=lc_id)
            db.session.add(row)
        row.visible = bool(p.get('visible', True))
    db.session.commit()
    return jsonify({'ok': True})


@main_bp.route('/api/calendar/sync', methods=['POST'])
@limiter.limit('30 per hour')
def api_calendar_sync_now():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn or not calendar_connection_active(conn):
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    sync_connection(conn)
    return jsonify({'ok': True, 'last_sync_at': conn.last_sync_at.isoformat() if conn.last_sync_at else None})


@main_bp.route('/api/calendar/disconnect', methods=['POST'])
def api_calendar_disconnect():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': True})
    payload = request.get_json(silent=True) or {}
    remove_events = bool(payload.get('remove_google_reminders'))
    try:
        if remove_events:
            Reminder.query.filter_by(owner_uid=uid, source='google').delete(synchronize_session=False)
        # Remove import-related rows first to avoid FK NULL updates during connection delete.
        CategoryImportMapping.query.filter_by(connection_id=conn.id).delete(synchronize_session=False)
        CalendarImportMapping.query.filter_by(connection_id=conn.id).delete(synchronize_session=False)
        CalendarImportProfile.query.filter_by(connection_id=conn.id).delete(synchronize_session=False)
        for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all():
            CalendarDisplayPref.query.filter_by(linked_calendar_id=lc.id).delete(synchronize_session=False)
            CalendarShare.query.filter_by(linked_calendar_id=lc.id).delete(synchronize_session=False)
            Reminder.query.filter_by(linked_calendar_id=lc.id).delete(synchronize_session=False)
        LinkedCalendar.query.filter_by(connection_id=conn.id).delete(synchronize_session=False)
        db.session.delete(conn)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('calendar disconnect failed')
        return jsonify({'ok': False, 'error': 'disconnect_failed'}), 500
    _clear_oauth_session()
    return jsonify({'ok': True})


@main_bp.route('/api/calendar/sync-mode', methods=['PATCH'])
def api_calendar_sync_mode():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    payload = request.get_json(silent=True) or {}
    requested = (payload.get('mode') or '').strip().lower()
    if requested == 'bidirectional' and not _allow_bidirectional_opt_in():
        return jsonify({'ok': False, 'error': 'bidirectional_disabled'}), 403
    mode = set_connection_sync_mode(conn, payload.get('mode'))
    db.session.commit()
    return jsonify({'ok': True, 'mode': mode})


@main_bp.route('/api/calendar/import/options')
def api_calendar_import_options():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    ensure_default_personal_calendar(uid)
    personal = [
        _serialize_personal_calendar(pc)
        for pc in PersonalCalendar.query.filter_by(owner_uid=uid, archived=False).order_by(PersonalCalendar.name.asc()).all()
    ]
    linked = []
    for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).order_by(LinkedCalendar.summary.asc()).all():
        mapping = CalendarImportMapping.query.filter_by(connection_id=conn.id, linked_calendar_id=lc.id).first()
        cat_rows = CategoryImportMapping.query.filter_by(connection_id=conn.id, linked_calendar_id=lc.id).all()
        inferred_categories = _infer_google_categories(conn, lc.google_calendar_id)
        known_keys = {c['key'] for c in inferred_categories}
        for row in cat_rows:
            key = (row.source_key or '').strip()
            if key and key not in known_keys:
                inferred_categories.append({
                    'key': key,
                    'label': (row.source_label or key),
                })
                known_keys.add(key)
        linked.append({
            'id': lc.id,
            'google_calendar_id': lc.google_calendar_id,
            'summary': lc.summary,
            'background_color': lc.background_color,
            'sync_enabled': bool(lc.sync_enabled),
            'source_categories': sorted(inferred_categories, key=lambda x: (x.get('label') or '').lower()),
            'import_mapping': {
                'id': mapping.id if mapping else None,
                'personal_calendar_id': mapping.personal_calendar_id if mapping else None,
                'import_enabled': bool(mapping.import_enabled) if mapping else bool(lc.sync_enabled),
                'import_color': mapping.import_color if mapping else lc.background_color,
            },
            'category_mappings': [
                {
                    'id': c.id,
                    'source_key': c.source_key,
                    'source_label': c.source_label,
                    'target_key': c.target_key,
                    'target_label': c.target_label,
                    'target_color': c.target_color,
                }
                for c in cat_rows
            ],
        })
    return jsonify({'ok': True, 'sync_mode': conn.sync_mode or 'import_only', 'linked_calendars': linked, 'personal_calendars': personal})


@main_bp.route('/api/calendar/import/preview', methods=['POST'])
def api_calendar_import_preview():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    payload = request.get_json(silent=True) or {}
    selections = payload.get('selections') or []
    if not isinstance(selections, list):
        return jsonify({'ok': False, 'error': 'invalid_payload'}), 400
    selected = 0
    category_mappings = 0
    for s in selections:
        if not isinstance(s, dict):
            continue
        if s.get('import_enabled', True):
            selected += 1
        category_mappings += len(s.get('categories') or [])
    return jsonify({
        'ok': True,
        'summary': {
            'selected_calendars': selected,
            'category_mapping_rows': category_mappings,
            'mode': conn.sync_mode or 'import_only',
        },
    })


@main_bp.route('/api/calendar/import/commit', methods=['POST'])
def api_calendar_import_commit():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    payload = request.get_json(silent=True) or {}
    selections = payload.get('selections') or []
    if not isinstance(selections, list):
        return jsonify({'ok': False, 'error': 'invalid_payload'}), 400
    saved = 0
    for s in selections:
        if not isinstance(s, dict):
            continue
        lc_id = s.get('linked_calendar_id')
        try:
            lc_id = int(lc_id)
        except (TypeError, ValueError):
            continue
        lc = LinkedCalendar.query.filter_by(id=lc_id, connection_id=conn.id).first()
        if not lc:
            continue
        pc_id = s.get('personal_calendar_id')
        pc = None
        if pc_id is not None:
            try:
                pc_id = int(pc_id)
            except (TypeError, ValueError):
                pc_id = None
        if pc_id:
            pc = PersonalCalendar.query.filter_by(id=pc_id, owner_uid=uid).first()
        if not pc:
            pc_name = (s.get('new_personal_calendar_name') or '').strip()
            if pc_name:
                pc_color = normalize_hex_color(s.get('new_personal_calendar_color')) or '#2563eb'
                pc = PersonalCalendar(
                    owner_uid=uid,
                    name=pc_name[:128],
                    color=pc_color,
                    visibility='private',
                    archived=False,
                )
                db.session.add(pc)
                db.session.flush()
            else:
                pc = ensure_default_personal_calendar(uid)
        selection = ImportSelection(
            linked_calendar_id=lc.id,
            personal_calendar_id=pc.id,
            import_enabled=bool(s.get('import_enabled', True)),
            import_color=s.get('import_color'),
            categories=s.get('categories') or [],
        )
        upsert_import_mapping(selection, conn.id)
        upsert_category_mappings(conn.id, lc.id, selection.categories)
        lc.sync_enabled = bool(selection.import_enabled)
        saved += 1
    db.session.commit()
    try:
        sync_connection(conn)
    except Exception:
        current_app.logger.exception('import commit sync failed')
    return jsonify({'ok': True, 'saved': saved})


@main_bp.route('/api/calendar/import/mappings/<int:mapping_id>', methods=['PATCH'])
def api_calendar_import_mapping_patch(mapping_id):
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    row = CalendarImportMapping.query.get_or_404(mapping_id)
    if row.connection_id != conn.id:
        return jsonify({'ok': False, 'error': 'not_allowed'}), 403
    payload = request.get_json(silent=True) or {}
    if 'import_enabled' in payload:
        row.import_enabled = bool(payload.get('import_enabled'))
    if 'import_color' in payload:
        from ..security import normalize_hex_color

        row.import_color = normalize_hex_color(payload.get('import_color')) if payload.get('import_color') else None
    if 'personal_calendar_id' in payload:
        pc_id = payload.get('personal_calendar_id')
        try:
            pc_id = int(pc_id)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'invalid_personal_calendar'}), 400
        pc = PersonalCalendar.query.filter_by(id=pc_id, owner_uid=uid).first()
        if not pc:
            return jsonify({'ok': False, 'error': 'invalid_personal_calendar'}), 400
        row.personal_calendar_id = pc.id
    db.session.commit()
    return jsonify({'ok': True})
