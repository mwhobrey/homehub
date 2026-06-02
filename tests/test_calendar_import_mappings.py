from unittest.mock import patch

from app import create_app, db
from app.models import CalendarConnection, LinkedCalendar, PersonalCalendar, CalendarImportMapping


def make_app():
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "HOMEHUB_CONFIG": {
            "google_calendar": {"enabled": True, "default_sync_mode": "import_only"},
            "auth": {"mode": "firebase", "display_names": {}},
        },
        "SECRET_KEY": "test",
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


def _login(client, uid="u1"):
    with client.session_transaction() as sess:
        sess["firebase_uid"] = uid
        sess["firebase_email"] = "u1@example.com"


def test_import_options_preview_and_commit():
    app = make_app()
    client = app.test_client()
    _login(client)
    with app.app_context():
        conn = CalendarConnection(firebase_uid="u1", firebase_email="u1@example.com", refresh_token_enc="x")
        db.session.add(conn)
        db.session.flush()
        lc = LinkedCalendar(connection_id=conn.id, google_calendar_id="g1", summary="Work", sync_enabled=True)
        db.session.add(lc)
        pc = PersonalCalendar(owner_uid="u1", name="Home", color="#2563eb")
        db.session.add(pc)
        db.session.commit()
        linked_id = lc.id
        personal_id = pc.id

    options = client.get("/api/calendar/import/options").get_json()
    assert options["ok"] is True
    assert len(options["linked_calendars"]) == 1
    for cat in options["linked_calendars"][0]["source_categories"]:
        assert cat.get("color")

    selections = [
        {
            "linked_calendar_id": linked_id,
            "personal_calendar_id": personal_id,
            "import_enabled": True,
            "import_color": "#123456",
            "categories": [
                {
                    "source_key": "default",
                    "source_label": "Default",
                    "target_key": "family",
                    "target_label": "Family",
                    "target_color": "#00aa00",
                }
            ],
        }
    ]
    preview = client.post("/api/calendar/import/preview", json={"selections": selections}).get_json()
    assert preview["ok"] is True
    assert preview["summary"]["selected_calendars"] == 1

    commit = client.post("/api/calendar/import/commit", json={"selections": selections}).get_json()
    assert commit["ok"] is True
    with app.app_context():
        row = CalendarImportMapping.query.filter_by(linked_calendar_id=linked_id).first()
        assert row is not None
        assert row.personal_calendar_id == personal_id
        assert row.import_color == "#123456"
        from app.reminder_categories import load_reminder_categories
        cats = {c["key"]: c for c in load_reminder_categories()}
        assert "family" in cats
        assert cats["family"]["label"] == "Family"
        assert cats["family"]["color"] == "#00aa00"


def test_import_reuses_personal_calendar_by_name():
    app = make_app()
    client = app.test_client()
    _login(client)
    with app.app_context():
        conn = CalendarConnection(firebase_uid="u1", firebase_email="u1@example.com", refresh_token_enc="x")
        db.session.add(conn)
        db.session.flush()
        lc = LinkedCalendar(connection_id=conn.id, google_calendar_id="g1", summary="Work", sync_enabled=True)
        db.session.add(lc)
        pc = PersonalCalendar(owner_uid="u1", name="Work Hub", color="#2563eb")
        db.session.add(pc)
        db.session.commit()
        linked_id = lc.id
        existing_pc_id = pc.id

    selections = [
        {
            "linked_calendar_id": linked_id,
            "new_personal_calendar_name": "Work Hub",
            "import_enabled": True,
            "categories": [],
        }
    ]
    with patch("app.blueprints.calendar_sync.sync_connection"):
        res = client.post("/api/calendar/import/commit", json={"selections": selections}).get_json()
    assert res["ok"] is True
    with app.app_context():
        count = PersonalCalendar.query.filter_by(owner_uid="u1", archived=False).count()
        row = CalendarImportMapping.query.filter_by(linked_calendar_id=linked_id).first()
        assert row.personal_calendar_id == existing_pc_id
        assert count == 1


def test_sync_mode_manual():
    app = make_app()
    client = app.test_client()
    _login(client)
    with app.app_context():
        conn = CalendarConnection(firebase_uid="u1", firebase_email="u1@example.com", refresh_token_enc="x")
        db.session.add(conn)
        db.session.commit()
    res = client.patch("/api/calendar/sync-mode", json={"mode": "manual"}).get_json()
    assert res["ok"] is True
    assert res["mode"] == "manual"


def test_sync_mode_patch():
    app = make_app()
    client = app.test_client()
    _login(client)
    with app.app_context():
        conn = CalendarConnection(firebase_uid="u1", firebase_email="u1@example.com", refresh_token_enc="x")
        db.session.add(conn)
        db.session.commit()
    res = client.patch("/api/calendar/sync-mode", json={"mode": "bidirectional"}).get_json()
    assert res["ok"] is True
    assert res["mode"] == "bidirectional"


def test_sync_mode_patch_respects_config_disable():
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "HOMEHUB_CONFIG": {
            "google_calendar": {
                "enabled": True,
                "default_sync_mode": "import_only",
                "allow_bidirectional_opt_in": False,
            },
            "auth": {"mode": "firebase", "display_names": {}},
        },
        "SECRET_KEY": "test",
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
        conn = CalendarConnection(firebase_uid="u1", firebase_email="u1@example.com", refresh_token_enc="x")
        db.session.add(conn)
        db.session.commit()
    client = app.test_client()
    _login(client)
    res = client.patch("/api/calendar/sync-mode", json={"mode": "bidirectional"})
    assert res.status_code == 403
    data = res.get_json()
    assert data["ok"] is False
    assert data["error"] == "bidirectional_disabled"
