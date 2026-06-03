from flask import current_app, flash, redirect, render_template, request, url_for



from ..blueprints import main_bp

from ..settings_service import (

    build_settings_form_context,

    clear_runtime_overrides,

    reload_merged_config,

    save_settings_from_form,

)

from ..user_context import is_admin, is_logged_in, resolve_user, resolve_user_from_args, uses_firebase

from ..user_preferences_service import (

    build_user_preferences_form_context,

    clear_user_preferences,

    migrate_legacy_system_theme_to_user,

    save_user_preferences_from_form,

    user_storage_key,

)





def _legacy_actor():

    if uses_firebase():

        return None

    return resolve_user_from_args() or resolve_user() or None





def _require_admin():

    if not is_admin(_legacy_actor()):

        flash('Only administrators can change system settings.', 'error')

        return redirect(url_for('main.index'))

    return None





def _require_user_preferences_access():

    if uses_firebase() and not is_logged_in():

        flash('Sign in to manage your preferences.', 'error')

        return redirect(url_for('main.login', next=request.path))

    return None





def _legacy_redirect(endpoint: str, **kwargs):

    actor = _legacy_actor()

    if actor and not uses_firebase():

        return redirect(url_for(endpoint, user=actor, **kwargs))

    return redirect(url_for(endpoint, **kwargs))





@main_bp.route('/settings', methods=['GET', 'POST'])

def settings_user_page():

    denied = _require_user_preferences_access()

    if denied:

        return denied

    config = current_app.config['HOMEHUB_CONFIG']

    actor = _legacy_actor()

    if request.method == 'GET':

        ctx = build_user_preferences_form_context(config, actor=actor)

        if not ctx.get('storage_key') and not uses_firebase():

            return render_template(

                'settings_user.html',

                config=config,

                user_prefs_form=ctx,

                needs_legacy_user=True,

            )

        return render_template(

            'settings_user.html',

            config=config,

            user_prefs_form=ctx,

            needs_legacy_user=False,

        )

    if not uses_firebase() and not actor:

        flash('Choose your name in the header switcher, then save again.', 'error')

        return redirect(url_for('main.settings_user_page'))

    try:

        sk = user_storage_key(actor=actor)
        if sk and migrate_legacy_system_theme_to_user(sk):

            flash('Moved a previous hub-wide theme into your personal preferences.', 'info')

        save_user_preferences_from_form(

            request.form,

            base_config=current_app.config.get('HOMEHUB_CONFIG'),

        )

        flash('Your preferences were saved.', 'success')

    except ValueError:

        flash('Could not save preferences — sign in or select your user.', 'error')

    except Exception:

        current_app.logger.exception('Failed to save user preferences')

        flash('Failed to save preferences.', 'error')

    return _legacy_redirect('main.settings_user_page')





@main_bp.route('/settings/reset-user', methods=['POST'])

def settings_reset_user_preferences():

    denied = _require_user_preferences_access()

    if denied:

        return denied

    actor = _legacy_actor()

    if not uses_firebase() and not actor:

        flash('Choose your name in the header switcher first.', 'error')

        return redirect(url_for('main.settings_user_page'))

    try:

        clear_user_preferences(actor=actor)

        flash('Your personal theme and appearance were reset.', 'success')

    except Exception:

        current_app.logger.exception('Failed to clear user preferences')

        flash('Failed to reset preferences.', 'error')

    return _legacy_redirect('main.settings_user_page')





@main_bp.route('/settings/system', methods=['GET', 'POST'])

def settings_system_page():

    denied = _require_admin()

    if denied:

        return denied

    if request.method == 'GET':

        config = current_app.config['HOMEHUB_CONFIG']

        ctx = build_settings_form_context(config)

        return render_template('settings_system.html', config=config, settings_form=ctx)



    try:

        save_settings_from_form(request.form, base_config=current_app.config.get('HOMEHUB_CONFIG'))

        flash('System settings saved.', 'success')

    except Exception:

        current_app.logger.exception('Failed to save system settings')

        flash('Failed to save system settings.', 'error')

    current_app.config['HOMEHUB_CONFIG'] = reload_merged_config()

    return _legacy_redirect('main.settings_system_page')





@main_bp.route('/settings/reset', methods=['POST'])

@main_bp.route('/settings/system/reset', methods=['POST'])

def settings_reset_overrides():

    denied = _require_admin()

    if denied:

        return denied

    try:

        clear_runtime_overrides()

        flash('Reverted to config.yml defaults (system overrides cleared).', 'success')

    except Exception:

        current_app.logger.exception('Failed to clear system settings overrides')

        flash('Failed to reset system settings.', 'error')

    current_app.config['HOMEHUB_CONFIG'] = reload_merged_config()

    return _legacy_redirect('main.settings_system_page')


