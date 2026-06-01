"""Google Calendar OAuth and management API."""

from __future__ import annotations

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
from ..google_calendar.sync import ensure_display_prefs_for_viewer, sync_connection
from ..models import (
    CalendarConnection,
    CalendarDisplayPref,
    CalendarShare,
    LinkedCalendar,
    Reminder,
    db,
)
from ..sensitive_store import encrypt_sensitive
from ..user_context import current_email, uses_firebase
from . import main_bp

OAUTH_CALLBACK = 'main.google_calendar_oauth_callback'
ALLOWED_VISIBILITY = {'private', 'household', 'custom'}


def _gcal_cfg() -> dict:
    return (current_app.config.get('HOMEHUB_CONFIG') or {}).get('google_calendar') or {}


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
        scopes=['https://www.googleapis.com/auth/calendar'],
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
    session['google_calendar_oauth_state'] = nonce
    redirect_uri = url_for(OAUTH_CALLBACK, _external=True)
    flow = _flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=nonce,
    )
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
    if not state or state != session.get('google_calendar_oauth_state'):
        return redirect(url_for('main.index', calendar_error='invalid_state'))
    redirect_uri = url_for(OAUTH_CALLBACK, _external=True)
    flow = _flow(redirect_uri)
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception:
        current_app.logger.exception('google calendar oauth token exchange failed')
        session.pop('google_calendar_oauth_state', None)
        return redirect(url_for('main.calendar_page', calendar_error='oauth_failed'))
    creds = flow.credentials
    conn = CalendarConnection.query.filter_by(firebase_uid=uid).first()
    if not conn:
        conn = CalendarConnection(firebase_uid=uid, firebase_email=current_email())
        db.session.add(conn)
    conn.refresh_token_enc = encrypt_sensitive(creds.refresh_token or '')
    conn.access_token_enc = encrypt_sensitive(creds.token or '')
    conn.token_expiry = creds.expiry
    conn.connected_at = datetime.utcnow()
    db.session.commit()

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
    if primary_lc:
        conn.default_linked_calendar_id = primary_lc.id
    elif not conn.default_linked_calendar_id:
        first = LinkedCalendar.query.filter_by(connection_id=conn.id).first()
        if first:
            conn.default_linked_calendar_id = first.id
    db.session.commit()
    try:
        sync_connection(conn)
    except Exception:
        current_app.logger.exception('initial calendar sync failed')
    return redirect(url_for('main.calendar_page', calendar_connected='1'))


@main_bp.route('/api/calendar/status')
def api_calendar_status():
    err = _require_firebase_calendar()
    if err:
        return err
    uid = session.get('firebase_uid')
    conn = get_connection_for_uid(uid)
    if not conn:
        return jsonify({'ok': True, 'connected': False})
    if not calendar_connection_active(conn):
        return jsonify({
            'ok': True,
            'connected': False,
            'connection_incomplete': True,
        })
    cals = LinkedCalendar.query.filter_by(connection_id=conn.id).count()
    return jsonify({
        'ok': True,
        'connected': True,
        'last_sync_at': conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        'calendar_count': cals,
        'default_linked_calendar_id': conn.default_linked_calendar_id,
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
    return jsonify({'ok': True, 'calendars': out})


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
    return jsonify({'ok': True, 'own': own, 'visible': visible})


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
    if remove_events:
        Reminder.query.filter_by(owner_uid=uid, source='google').delete(synchronize_session=False)
    for lc in LinkedCalendar.query.filter_by(connection_id=conn.id).all():
        CalendarDisplayPref.query.filter_by(linked_calendar_id=lc.id).delete()
        CalendarShare.query.filter_by(linked_calendar_id=lc.id).delete()
        Reminder.query.filter_by(linked_calendar_id=lc.id).delete(synchronize_session=False)
    LinkedCalendar.query.filter_by(connection_id=conn.id).delete()
    db.session.delete(conn)
    db.session.commit()
    session.pop('google_calendar_oauth_state', None)
    return jsonify({'ok': True})
