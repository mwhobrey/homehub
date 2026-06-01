from . import db
from datetime import datetime

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    creator = db.Column(db.String(64), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    creator = db.Column(db.String(64), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)

class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256))
    url = db.Column(db.String(512))
    creator = db.Column(db.String(64))
    download_time = db.Column(db.DateTime, default=datetime.utcnow)
    filepath = db.Column(db.String(512))
    status = db.Column(db.String(32), default='done')  # pending, done, error
    progress = db.Column(db.Text)  # latest progress line or JSON

class PDF(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256))
    creator = db.Column(db.String(64))
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    compressed_path = db.Column(db.String(512))

class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(256), nullable=False)
    checked = db.Column(db.Boolean, default=False)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # JSON-encoded list of tags (e.g., ["Costco", "Dairy"]) for filtering/grouping
    tags = db.Column(db.Text, default='[]')

class GroceryHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(256), nullable=False)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class HomeStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(16), default='Away')

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    done = db.Column(db.Boolean, default=False)
    due_date = db.Column(db.Date)
    recurring_id = db.Column(db.Integer)
    # JSON-encoded list of tags (e.g., ["Alice", "Weekend"]) for assignment/filtering
    tags = db.Column(db.Text, default='[]')


class RecurringChore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    creator = db.Column(db.String(64))
    tags = db.Column(db.Text, default='[]')
    interval = db.Column(db.Integer, default=1)
    unit = db.Column(db.String(8), default='day')  # day|week|month|year
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    last_generated_date = db.Column(db.Date)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    link = db.Column(db.String(512))
    ingredients = db.Column(db.Text)
    instructions = db.Column(db.Text)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # JSON-encoded list of tags (e.g., ["Dessert", "Quick", "Vegetarian"]) for filtering/grouping
    tags = db.Column(db.Text, default='[]')

class ExpiryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    expiry_date = db.Column(db.Date)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ShortURL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.String(512), nullable=False)
    short_code = db.Column(db.String(16), unique=True, nullable=False)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)  # encrypted payload when hardening enabled
    filename = db.Column(db.String(256), nullable=False)
    original_input = db.Column(db.Text)  # masked shorthand for WiFi; safe display text otherwise
    display_label = db.Column(db.String(256))  # UI-safe label (never includes WiFi password)
    is_wifi = db.Column(db.Boolean, default=False)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, default='')
    updated_by = db.Column(db.String(64))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(5))  # HH:MM (optional)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # New fields (phase 1) - added via auto-migration if missing
    category = db.Column(db.String(64))  # key referencing configured category
    color = db.Column(db.String(16))     # optional override hex color
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Tie back to a recurring rule (if generated)
    recurring_id = db.Column(db.Integer)
    # Google Calendar sync
    source = db.Column(db.String(16), default='local')  # local | google
    linked_calendar_id = db.Column(db.Integer, db.ForeignKey('linked_calendar.id'))
    google_event_id = db.Column(db.String(256))
    google_recurring_event_id = db.Column(db.String(256))
    google_etag = db.Column(db.String(128))
    google_updated = db.Column(db.String(64))
    owner_uid = db.Column(db.String(128))
    sync_status = db.Column(db.String(32), default='synced')
    all_day = db.Column(db.Boolean, default=False)
    end_date = db.Column(db.Date)
    end_time = db.Column(db.String(5))
    time_zone = db.Column(db.String(64))
    attendees_json = db.Column(db.Text)


class CalendarConnection(db.Model):
    __tablename__ = 'calendar_connection'
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    firebase_email = db.Column(db.String(256))
    refresh_token_enc = db.Column(db.Text)
    access_token_enc = db.Column(db.Text)
    token_expiry = db.Column(db.DateTime)
    default_linked_calendar_id = db.Column(db.Integer, nullable=True)
    time_zone = db.Column(db.String(64), default='UTC')
    oauth_state_nonce = db.Column(db.String(64))
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_sync_at = db.Column(db.DateTime)


class LinkedCalendar(db.Model):
    __tablename__ = 'linked_calendar'
    id = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(db.Integer, db.ForeignKey('calendar_connection.id'), nullable=False)
    google_calendar_id = db.Column(db.String(256), nullable=False)
    summary = db.Column(db.String(256))
    background_color = db.Column(db.String(32))
    sync_enabled = db.Column(db.Boolean, default=True)
    visibility = db.Column(db.String(16), default='household')  # private | household | custom
    sync_token = db.Column(db.Text)
    last_sync_at = db.Column(db.DateTime)
    last_sync_error = db.Column(db.Text)
    connection = db.relationship('CalendarConnection', backref=db.backref('calendars', lazy=True))


class CalendarShare(db.Model):
    __tablename__ = 'calendar_share'
    id = db.Column(db.Integer, primary_key=True)
    linked_calendar_id = db.Column(db.Integer, db.ForeignKey('linked_calendar.id'), nullable=False)
    grantee_uid = db.Column(db.String(128), nullable=False)
    can_write = db.Column(db.Boolean, default=False)
    linked_calendar = db.relationship('LinkedCalendar', backref=db.backref('shares', lazy=True))


class CalendarDisplayPref(db.Model):
    __tablename__ = 'calendar_display_pref'
    id = db.Column(db.Integer, primary_key=True)
    viewer_uid = db.Column(db.String(128), nullable=False)
    linked_calendar_id = db.Column(db.Integer, db.ForeignKey('linked_calendar.id'), nullable=False)
    visible = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint('viewer_uid', 'linked_calendar_id', name='uq_calendar_display_pref'),)


class CalendarSyncOutbox(db.Model):
    __tablename__ = 'calendar_sync_outbox'
    id = db.Column(db.Integer, primary_key=True)
    reminder_id = db.Column(db.Integer, db.ForeignKey('reminder.id'))
    operation = db.Column(db.String(16), nullable=False)  # create | update | delete | move
    payload_json = db.Column(db.Text)
    attempts = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MemberStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    text = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class RecurringExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    unit_price = db.Column(db.Float, default=0.0)
    default_quantity = db.Column(db.Float, default=1.0)
    frequency = db.Column(db.String(16), default='daily')  # daily|weekly|monthly
    category = db.Column(db.String(64))
    monthly_mode = db.Column(db.String(16), default='day_of_month')  # calendar|day_of_month
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    last_generated_date = db.Column(db.Date)
    effective_from = db.Column(db.Date)  # apply changes from this date forward
    creator = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class RecurringReminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    creator = db.Column(db.String(64))
    # Legacy fields kept for backward compatibility
    frequency = db.Column(db.String(16), default='daily')  # daily|weekly|monthly (legacy)
    monthly_mode = db.Column(db.String(16), default='day_of_month')  # calendar|day_of_month (legacy)
    # New flexible recurrence
    interval = db.Column(db.Integer, default=1)  # e.g., 1,2,3
    unit = db.Column(db.String(8), default='day')  # 'day'|'week'|'month'|'year'
    time = db.Column(db.String(5))  # optional HH:MM
    category = db.Column(db.String(64))
    color = db.Column(db.String(16))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    last_generated_date = db.Column(db.Date)
    effective_from = db.Column(db.Date)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    exception_dates_json = db.Column(db.Text)
    linked_calendar_id = db.Column(db.Integer, db.ForeignKey('linked_calendar.id'))
    google_recurring_event_id = db.Column(db.String(256))
    google_etag = db.Column(db.String(128))
    owner_uid = db.Column(db.String(128))
    source = db.Column(db.String(16), default='local')
    sync_status = db.Column(db.String(32), default='synced')

class ExpenseEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(256), nullable=False)
    category = db.Column(db.String(64))
    unit_price = db.Column(db.Float)
    quantity = db.Column(db.Float)
    amount = db.Column(db.Float, nullable=False)
    payer = db.Column(db.String(64))
    recurring_id = db.Column(db.Integer, db.ForeignKey('recurring_expense.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# --- School module ---

class SchoolClass(db.Model):
    __tablename__ = 'school_class'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    subject = db.Column(db.String(128))
    term = db.Column(db.String(64))
    teacher_id = db.Column(db.String(64), nullable=False)
    schedule_json = db.Column(db.Text, default='{}')
    archived = db.Column(db.Boolean, default=False)
    creator = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    enrollments = db.relationship('Enrollment', backref='school_class', lazy=True, cascade='all, delete-orphan')
    assignments = db.relationship('Assignment', backref='school_class', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('AssignmentCategory', backref='school_class', lazy=True, cascade='all, delete-orphan')


class Enrollment(db.Model):
    __tablename__ = 'school_enrollment'
    __table_args__ = (
        db.UniqueConstraint('class_id', 'student_id', name='uq_enrollment_class_student'),
    )
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_class.id'), nullable=False, index=True)
    student_id = db.Column(db.String(64), nullable=False, index=True)
    role = db.Column(db.String(16), default='student')  # student|teacher|assistant
    active_from = db.Column(db.Date)
    active_to = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssignmentCategory(db.Model):
    __tablename__ = 'school_assignment_category'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_class.id'), nullable=True, index=True)
    name = db.Column(db.String(128), nullable=False)
    weight_percent = db.Column(db.Float, default=0.0)
    grading_policy = db.Column(db.String(32), default='points')  # points|pass_fail
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Assignment(db.Model):
    __tablename__ = 'school_assignment'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_class.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('school_assignment_category.id'), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    instructions_html = db.Column(db.Text, default='')
    due_at = db.Column(db.DateTime)
    assigned_at = db.Column(db.DateTime)
    points_possible = db.Column(db.Float, default=100.0)
    allow_late = db.Column(db.Boolean, default=True)
    visibility = db.Column(db.String(16), default='assigned')  # draft|assigned|closed
    status = db.Column(db.String(16), default='draft')  # draft|assigned|closed
    creator = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship('AssignmentCategory', backref='assignments')
    submissions = db.relationship('Submission', backref='assignment', lazy=True, cascade='all, delete-orphan')


class Submission(db.Model):
    __tablename__ = 'school_submission'
    __table_args__ = (
        db.UniqueConstraint('assignment_id', 'student_id', 'attempt_number', name='uq_submission_attempt'),
    )
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('school_assignment.id'), nullable=False, index=True)
    student_id = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(24), default='not_started')
    submitted_at = db.Column(db.DateTime)
    is_late = db.Column(db.Boolean, default=False)
    attempt_number = db.Column(db.Integer, default=1)
    student_note = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artifacts = db.relationship('SubmissionArtifact', backref='submission', lazy=True, cascade='all, delete-orphan')
    grade = db.relationship('GradeEntry', backref='submission', uselist=False, cascade='all, delete-orphan')


class SubmissionArtifact(db.Model):
    __tablename__ = 'school_submission_artifact'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('school_submission.id'), nullable=False, index=True)
    artifact_type = db.Column(db.String(16), nullable=False)  # file|link|text
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=True)
    url = db.Column(db.String(1024))
    note = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    file = db.relationship('File', backref='submission_artifacts')


class GradeEntry(db.Model):
    __tablename__ = 'school_grade_entry'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('school_submission.id'), nullable=False, unique=True)
    score = db.Column(db.Float)
    rubric_json = db.Column(db.Text, default='{}')
    feedback_html = db.Column(db.Text, default='')
    graded_by = db.Column(db.String(64))
    graded_at = db.Column(db.DateTime)
    revision_requested = db.Column(db.Boolean, default=False)
    completed = db.Column(db.Boolean, default=False)


class AttendanceRecord(db.Model):
    __tablename__ = 'school_attendance'
    __table_args__ = (
        db.UniqueConstraint('class_id', 'student_id', 'attendance_date', name='uq_attendance_day'),
    )
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_class.id'), nullable=False, index=True)
    student_id = db.Column(db.String(64), nullable=False, index=True)
    attendance_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(16), default='present')  # present|absent|late|excused
    note = db.Column(db.Text, default='')
    marked_by = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SchoolAuditLog(db.Model):
    __tablename__ = 'school_audit_log'
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(64), nullable=False)
    entity_type = db.Column(db.String(64), nullable=False)
    entity_id = db.Column(db.Integer)
    before_json = db.Column(db.Text)
    after_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
