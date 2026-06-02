"""Google Calendar API client built from stored OAuth tokens."""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import current_app
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..models import CalendarConnection, db
from ..sensitive_store import SensitiveDecryptError, decrypt_sensitive, encrypt_sensitive


class CalendarCredentialsError(RuntimeError):
    """OAuth tokens missing or unreadable (re-connect Google Calendar)."""


SCOPES = ['https://www.googleapis.com/auth/calendar']


def _gcal_config() -> dict:
    return (current_app.config.get('HOMEHUB_CONFIG') or {}).get('google_calendar') or {}


def _credentials_from_connection(conn: CalendarConnection) -> Credentials:
    cfg = _gcal_config()
    try:
        refresh = decrypt_sensitive(conn.refresh_token_enc or '')
        access = decrypt_sensitive(conn.access_token_enc or '') if conn.access_token_enc else None
    except SensitiveDecryptError as exc:
        raise CalendarCredentialsError(str(exc)) from exc
    creds = Credentials(
        token=access,
        refresh_token=refresh or None,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=cfg.get('client_id'),
        client_secret=cfg.get('client_secret'),
        scopes=SCOPES,
    )
    if conn.token_expiry and creds.token:
        creds.expiry = conn.token_expiry
    return creds


def _persist_credentials(conn: CalendarConnection, creds: Credentials) -> None:
    if creds.token:
        conn.access_token_enc = encrypt_sensitive(creds.token)
    if creds.expiry:
        conn.token_expiry = creds.expiry
    elif creds.token:
        conn.token_expiry = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()


def get_calendar_service(conn: CalendarConnection):
    factory = current_app.config.get('GOOGLE_CALENDAR_CLIENT_FACTORY')
    if factory:
        return factory(conn)

    creds = _credentials_from_connection(conn)
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        _persist_credentials(conn, creds)
    service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
    return service


def list_calendar_list(service) -> list[dict]:
    items = []
    page_token = None
    while True:
        resp = service.calendarList().list(pageToken=page_token).execute()
        items.extend(resp.get('items') or [])
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return items
