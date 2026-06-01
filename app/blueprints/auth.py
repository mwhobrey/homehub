from __future__ import annotations

import hashlib
from datetime import timedelta

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)

from ..blueprints import main_bp
from ..config import load_config
from ..extensions import limiter
from ..user_context import is_logged_in, uses_firebase
from ..security import safe_local_redirect_path
import bleach


def _redirect_after_login():
    nxt = safe_local_redirect_path(request.args.get('next'))
    return redirect(nxt or url_for('main.index'))


def _public_endpoints() -> set[str]:
    base = {
        'static',
        'main.login',
        'main.auth_config',
        'main.auth_session',
        'main.auth_logout',
        'main.google_calendar_oauth_callback',
        'main.privacy',
        'main.terms',
    }
    return base


@main_bp.before_app_request
def reload_config_and_require_auth():
    if not current_app.config.get('TESTING'):
        try:
            current_app.config['HOMEHUB_CONFIG'] = load_config()
        except Exception:
            pass
    endpoint = request.endpoint or ''
    if endpoint.startswith('static') or endpoint in _public_endpoints():
        return None

    cfg = current_app.config.get('HOMEHUB_CONFIG', {})

    if uses_firebase():
        if not is_logged_in():
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'ok': False, 'error': 'unauthorized'}), 401
            return redirect(url_for('main.login', next=request.path))
        return None

    # Legacy shared-password gate
    if cfg.get('password_hash'):
        if not session.get('authed'):
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'unauthorized'}), 401
            return redirect(url_for('main.login', next=request.path))
    elif endpoint == 'main.login':
        return redirect(url_for('main.index'))


@main_bp.route('/privacy')
def privacy():
    config = current_app.config['HOMEHUB_CONFIG']
    legal = config.get('legal') or {}
    admin_emails = (config.get('auth') or {}).get('admin_emails') or []
    contact = legal.get('contact_email') or (admin_emails[0] if admin_emails else '')
    return render_template(
        'privacy.html',
        config=config,
        operator_contact=contact,
        policy_updated=legal.get('policy_updated', '2026-06-01'),
        hide_user_ui=True,
    )


@main_bp.route('/terms')
def terms():
    config = current_app.config['HOMEHUB_CONFIG']
    legal = config.get('legal') or {}
    return render_template(
        'terms.html',
        config=config,
        policy_updated=legal.get('policy_updated', '2026-06-01'),
        hide_user_ui=True,
    )


@main_bp.route('/login', methods=['GET'])
def login():
    config = current_app.config['HOMEHUB_CONFIG']
    if uses_firebase():
        if is_logged_in():
            return _redirect_after_login()
        return render_template(
            'login.html',
            config=config,
            hide_user_ui=True,
            auth_mode='firebase',
        )
    if not config.get('password_hash'):
        return redirect(url_for('main.index'))
    if session.get('authed'):
        return redirect(url_for('main.index'))
    return render_template('login.html', config=config, hide_user_ui=True, auth_mode='legacy')


@main_bp.route('/login', methods=['POST'])
@limiter.limit('15 per minute')
def login_post():
    """Legacy password form only."""
    config = current_app.config['HOMEHUB_CONFIG']
    if uses_firebase() or not config.get('password_hash'):
        return redirect(url_for('main.index'))
    supplied = bleach.clean(request.form.get('password', ''))
    if hashlib.sha256(supplied.encode()).hexdigest() == config.get('password_hash'):
        session.permanent = True
        session['authed'] = True
        flash('Logged in successfully.', 'success')
        return _redirect_after_login()
    flash('Invalid password', 'error')
    return render_template('login.html', config=config, hide_user_ui=True, auth_mode='legacy')


@main_bp.route('/auth/config')
@limiter.limit('30 per minute')
def auth_config():
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    auth = cfg.get('auth') or {}
    if auth.get('mode') != 'firebase':
        return jsonify({'mode': 'legacy'})
    fb = auth.get('firebase') or {}
    return jsonify({
        'mode': 'firebase',
        'apiKey': fb.get('api_key', ''),
        'authDomain': fb.get('auth_domain', ''),
        'projectId': fb.get('project_id', ''),
        'appId': fb.get('app_id', ''),
    })


@main_bp.route('/auth/session', methods=['POST'])
@limiter.limit('10 per minute')
def auth_session():
    if not uses_firebase():
        return jsonify({'ok': False, 'error': 'firebase_disabled'}), 400
    payload = request.get_json(silent=True) or {}
    id_token = (payload.get('idToken') or '').strip()
    if not id_token:
        return jsonify({'ok': False, 'error': 'missing_token'}), 400

    try:
        from ..firebase_auth import verify_id_token

        decoded = verify_id_token(id_token)
    except Exception as exc:
        current_app.logger.warning('Firebase token verification failed: %s', exc)
        return jsonify({'ok': False, 'error': 'invalid_token'}), 401

    email = (decoded.get('email') or '').lower()
    if not email:
        return jsonify({'ok': False, 'error': 'email_required'}), 401

    cfg = current_app.config['HOMEHUB_CONFIG']
    allowed = {e.lower() for e in (cfg.get('auth') or {}).get('allowed_emails', []) if e}
    if allowed and email not in allowed:
        return jsonify({'ok': False, 'error': 'not_allowed'}), 403

    display_names = (cfg.get('auth') or {}).get('display_names') or {}
    display_name = display_names.get(email) or decoded.get('name') or email.split('@')[0]

    session.permanent = True
    session['firebase_uid'] = decoded.get('uid')
    session['firebase_email'] = email
    session['display_name'] = display_name
    session.pop('authed', None)

    return jsonify({
        'ok': True,
        'email': email,
        'displayName': display_name,
        'isAdmin': email in {e.lower() for e in (cfg.get('auth') or {}).get('admin_emails', []) if e},
    })


@main_bp.route('/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'ok': True})


@main_bp.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('main.login'))
