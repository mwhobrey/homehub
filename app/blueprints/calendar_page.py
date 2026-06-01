"""Dedicated family calendar page (schedules + Google setup)."""

from flask import current_app, render_template

from ..blueprints import main_bp
from ..blueprints.dashboard import _household_timezone
from ..google_calendar.acl import google_calendar_enabled

# Common IANA zones for household calendar UI (extend as needed)
TIMEZONE_OPTIONS = [
    'UTC',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Phoenix',
    'America/Anchorage',
    'Pacific/Honolulu',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'Asia/Tokyo',
    'Asia/Shanghai',
    'Australia/Sydney',
]


@main_bp.route('/calendar')
def calendar_page():
    config = current_app.config['HOMEHUB_CONFIG']
    if not (config.get('feature_toggles') or {}).get('calendar', True):
        from flask import redirect, url_for
        return redirect(url_for('main.index'))
    rem = config.get('reminders') or {}
    start_day = rem.get('calendar_start_day') or 'sunday'
    time_fmt = rem.get('time_format') or '12h'
    household_tz = _household_timezone()
    tz_options = list(TIMEZONE_OPTIONS)
    if household_tz and household_tz not in tz_options:
        tz_options.insert(1, household_tz)
    categories = []
    for entry in rem.get('categories') or []:
        if isinstance(entry, dict) and entry.get('key'):
            categories.append({
                'key': entry['key'],
                'label': entry.get('label') or entry['key'],
                'color': entry.get('color'),
            })
    return render_template(
        'calendar.html',
        config=config,
        calendar_start_day=start_day,
        time_format=time_fmt,
        household_timezone=household_tz,
        timezone_options=tz_options,
        reminder_categories=categories,
        google_calendar_enabled=google_calendar_enabled(),
    )
