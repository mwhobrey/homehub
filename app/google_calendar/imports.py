from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import (
    CalendarConnection,
    CalendarImportMapping,
    CategoryImportMapping,
    PersonalCalendar,
    db,
)
from ..security import normalize_hex_color


SYNC_MODE_IMPORT_ONLY = "import_only"
SYNC_MODE_BIDIRECTIONAL = "bidirectional"
SYNC_MODE_MANUAL = "manual"
ALLOWED_SYNC_MODES = {SYNC_MODE_IMPORT_ONLY, SYNC_MODE_BIDIRECTIONAL, SYNC_MODE_MANUAL}

HOUSEHOLD_OWNER_UID = "__household__"
DEFAULT_HOUSEHOLD_NAME = "Household"
DEFAULT_HOUSEHOLD_COLOR = "#2563eb"


@dataclass
class ImportSelection:
    linked_calendar_id: int
    personal_calendar_id: int
    import_enabled: bool
    import_color: str | None
    categories: list[dict]


def normalize_sync_mode(raw: str | None) -> str:
    candidate = (raw or "").strip().lower()
    if candidate in ALLOWED_SYNC_MODES:
        return candidate
    return SYNC_MODE_IMPORT_ONLY


def ensure_household_calendar(name: str | None = None) -> PersonalCalendar:
    """Single shared calendar visible to every household member."""
    row = PersonalCalendar.query.filter_by(
        owner_uid=HOUSEHOLD_OWNER_UID,
        visibility="household",
        archived=False,
    ).first()
    if row:
        return row
    row = PersonalCalendar(
        owner_uid=HOUSEHOLD_OWNER_UID,
        name=(name or DEFAULT_HOUSEHOLD_NAME)[:128],
        color=DEFAULT_HOUSEHOLD_COLOR,
        visibility="household",
        archived=False,
    )
    db.session.add(row)
    db.session.flush()
    return row


def default_event_personal_calendar_id() -> int:
    """Default bucket for new local events (household-shared)."""
    return ensure_household_calendar().id


def ensure_default_personal_calendar(uid: str, name: str = "My Calendar") -> PersonalCalendar:
    """Per-user private calendar (legacy helper — prefer household for new events)."""
    row = (
        PersonalCalendar.query.filter_by(owner_uid=uid, archived=False)
        .order_by(PersonalCalendar.id.asc())
        .first()
    )
    if row:
        return row
    row = PersonalCalendar(
        owner_uid=uid,
        name=name,
        color="#2563eb",
        visibility="private",
        archived=False,
    )
    db.session.add(row)
    db.session.flush()
    return row


def get_connection_sync_mode(conn: CalendarConnection) -> str:
    return normalize_sync_mode(getattr(conn, "sync_mode", None))


def set_connection_sync_mode(conn: CalendarConnection, mode: str) -> str:
    normalized = normalize_sync_mode(mode)
    conn.sync_mode = normalized
    return normalized


def get_import_mapping_for_linked_calendar(connection_id: int, linked_calendar_id: int) -> CalendarImportMapping | None:
    return CalendarImportMapping.query.filter_by(
        connection_id=connection_id,
        linked_calendar_id=linked_calendar_id,
    ).first()


def get_category_mapping(connection_id: int, linked_calendar_id: int, source_key: str) -> CategoryImportMapping | None:
    if not source_key:
        return None
    return CategoryImportMapping.query.filter_by(
        connection_id=connection_id,
        linked_calendar_id=linked_calendar_id,
        source_key=source_key,
    ).first()


def upsert_import_mapping(selection: ImportSelection, connection_id: int) -> CalendarImportMapping:
    row = get_import_mapping_for_linked_calendar(connection_id, selection.linked_calendar_id)
    if not row:
        row = CalendarImportMapping(
            connection_id=connection_id,
            linked_calendar_id=selection.linked_calendar_id,
        )
        db.session.add(row)
    row.personal_calendar_id = selection.personal_calendar_id
    row.import_enabled = bool(selection.import_enabled)
    row.import_color = normalize_hex_color(selection.import_color) if selection.import_color else None
    row.updated_at = datetime.utcnow()
    return row


def resolve_personal_calendar_for_import(
    uid: str,
    pc_id: int | None,
    new_name: str | None,
    new_color: str | None,
) -> PersonalCalendar:
    """Reuse an existing personal calendar by id or name; create only when needed."""
    from sqlalchemy import func

    pc: PersonalCalendar | None = None
    if pc_id:
        pc = PersonalCalendar.query.filter_by(id=pc_id, archived=False).first()
    if not pc:
        name = (new_name or "").strip()[:128]
        if name:
            pc = PersonalCalendar.query.filter(
                PersonalCalendar.owner_uid == uid,
                PersonalCalendar.archived.is_(False),
                func.lower(PersonalCalendar.name) == name.lower(),
            ).first()
            if not pc:
                pc = PersonalCalendar(
                    owner_uid=uid,
                    name=name,
                    color=normalize_hex_color(new_color) or "#2563eb",
                    visibility="private",
                    archived=False,
                )
                db.session.add(pc)
                db.session.flush()
    if not pc:
        pc = ensure_household_calendar()
    return pc


def upsert_category_mappings(connection_id: int, linked_calendar_id: int, categories: list[dict]) -> None:
    for c in categories:
        source_key = str((c.get("source_key") or "")).strip().lower()
        if not source_key:
            continue
        row = CategoryImportMapping.query.filter_by(
            connection_id=connection_id,
            linked_calendar_id=linked_calendar_id,
            source_key=source_key,
        ).first()
        if not row:
            row = CategoryImportMapping(
                connection_id=connection_id,
                linked_calendar_id=linked_calendar_id,
                source_key=source_key,
            )
            db.session.add(row)
        row.source_label = (c.get("source_label") or "")[:128] or None
        row.target_key = (c.get("target_key") or "")[:64] or None
        row.target_label = (c.get("target_label") or "")[:128] or None
        row.target_color = normalize_hex_color(c.get("target_color")) if c.get("target_color") else None
        row.updated_at = datetime.utcnow()
