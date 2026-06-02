from app import create_app, db
from app.models import PersonalCalendar


def make_app():
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "HOMEHUB_CONFIG": {
            "google_calendar": {"enabled": True},
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
        sess["firebase_email"] = f"{uid}@example.com"


def test_create_reminder_rejects_other_users_personal_calendar():
    app = make_app()
    client = app.test_client()
    _login(client, "u1")
    with app.app_context():
        other_pc = PersonalCalendar(owner_uid="u2", name="Other User", color="#2563eb")
        db.session.add(other_pc)
        db.session.commit()
        other_pc_id = other_pc.id
    res = client.post(
        "/api/reminders",
        json={
            "title": "Test",
            "date": "2026-06-03",
            "personal_calendar_id": other_pc_id,
        },
    )
    assert res.status_code == 403
    assert res.get_json()["error"] == "Not allowed"
