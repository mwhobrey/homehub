"""School module: permissions, lifecycle, submissions, gradebook."""

from datetime import datetime, timedelta

import pytest

from app import create_app, db
from app.models import (
    Assignment,
    AssignmentCategory,
    Enrollment,
    GradeEntry,
    SchoolClass,
    Submission,
    SubmissionArtifact,
)


def make_app(**school_overrides):
    school_cfg = {
        'teachers': ['Teacher'],
        'students': ['Student'],
        'parent_observers': {'Parent': ['Student']},
    }
    school_cfg.update(school_overrides)
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'admin_name': 'Administrator',
            'family_members': ['Teacher', 'Student', 'Parent', 'Stranger'],
            'feature_toggles': {'school': True},
            'school': school_cfg,
        },
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-school',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


class _SchoolClient:
    def __init__(self, raw, default_creator='Teacher'):
        self._c = raw
        self._creator = default_creator
        self.application = raw.application

    def get(self, path, **kwargs):
        if 'query_string' not in kwargs and '?' not in path:
            kwargs['query_string'] = f'creator={self._creator}'
        return self._c.get(path, **kwargs)

    def post(self, path, **kwargs):
        if kwargs.get('json') is not None:
            kwargs['json'] = {**kwargs['json'], 'creator': kwargs['json'].get('creator', self._creator)}
        return self._c.post(path, **kwargs)

    def patch(self, path, **kwargs):
        if kwargs.get('json') is not None:
            kwargs['json'] = {**kwargs['json'], 'creator': kwargs['json'].get('creator', self._creator)}
        return self._c.patch(path, **kwargs)

    def delete(self, path, **kwargs):
        if 'query_string' not in kwargs:
            kwargs['query_string'] = f'creator={self._creator}'
        return self._c.delete(path, **kwargs)


def _wrap(app, creator='Teacher'):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['authed'] = True
    return _SchoolClient(c, creator)


@pytest.fixture()
def app():
    return make_app()


@pytest.fixture()
def client(app):
    return _wrap(app, 'Teacher')


@pytest.fixture()
def student_client(app):
    return _wrap(app, 'Student')


def _create_class(client, teacher='Teacher'):
    r = client.post('/api/school/classes', json={
        'name': 'Math 101',
        'subject': 'Math',
        'teacher_id': teacher,
        'creator': teacher,
    })
    assert r.status_code == 200
    return r.get_json()['class_']['id']


def _enroll(client, class_id, student_id='Student'):
    r = client.post(f'/api/school/classes/{class_id}/enrollments', json={
        'student_ids': [student_id],
        'role': 'student',
        'creator': 'Teacher',
    })
    assert r.status_code == 200


def _create_assignment(client, class_id, status='assigned'):
    due = (datetime.utcnow() + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M')
    r = client.post(f'/api/school/classes/{class_id}/assignments', json={
        'title': 'Worksheet 1',
        'due_at': due,
        'status': status,
        'points_possible': 50,
        'creator': 'Teacher',
    })
    assert r.status_code == 200
    return r.get_json()['assignment']['id']


def test_school_page_requires_feature(client):
    r = client.get('/school')
    assert r.status_code == 200


def test_create_class_with_teachers_and_students(client, app):
    r = client.post('/api/school/classes', json={
        'name': 'Homeroom',
        'teacher_ids': ['Teacher'],
        'student_ids': ['Student'],
        'creator': 'Teacher',
    })
    assert r.status_code == 200
    class_id = r.get_json()['class_']['id']
    with app.app_context():
        from app.models import Enrollment
        students = Enrollment.query.filter_by(class_id=class_id, role='student').all()
        assert [s.student_id for s in students] == ['Student']


def test_create_class_with_multiple_teachers(client, app):
    r = client.post('/api/school/classes', json={
        'name': 'Co-taught Science',
        'teacher_ids': ['Teacher', 'Administrator'],
        'creator': 'Teacher',
    })
    assert r.status_code == 200
    body = r.get_json()
    assert set(body['class_']['teacher_ids']) == {'Teacher', 'Administrator'}
    with app.app_context():
        from app.school_services import class_teacher_ids
        from app.models import SchoolClass
        cls = SchoolClass.query.filter_by(name='Co-taught Science').first()
        assert set(class_teacher_ids(cls)) == {'Teacher', 'Administrator'}


def test_class_lifecycle_and_permissions(client):
    class_id = _create_class(client)
    _enroll(client, class_id)

    r = client.get(f'/api/school/classes/{class_id}')
    assert r.status_code == 200

    # Stranger cannot enroll without manage rights — create second client
    stranger = _wrap(client.application, 'Stranger')
    r = stranger.post(f'/api/school/classes/{class_id}/enrollments', json={
        'student_id': 'Stranger',
    })
    assert r.status_code == 403


def test_assignment_submission_link_and_grade(client, student_client):
    class_id = _create_class(client)
    _enroll(client, class_id)
    aid = _create_assignment(client, class_id)

    with client.application.app_context():
        sub = Submission.query.filter_by(assignment_id=aid, student_id='Student').first()
        assert sub is not None

    r = student_client.post(f'/api/school/submissions/{sub.id}/artifacts', json={
        'artifact_type': 'link',
        'url': 'https://docs.google.com/document/d/example',
        'note': 'My worksheet',
    })
    assert r.status_code == 200

    r = student_client.post(f'/api/school/assignments/{aid}/submit', json={
        'student_note': 'Done',
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body['submission']['status'] == 'submitted'

    r = client.post(f'/api/school/submissions/{sub.id}/grade', json={
        'score': 45,
        'feedback_html': '<p>Good work</p>',
        'completed': True,
        'creator': 'Teacher',
    })
    assert r.status_code == 200
    assert r.get_json()['submission']['status'] == 'completed'


def test_invalid_submission_url_rejected(client, student_client):
    class_id = _create_class(client)
    _enroll(client, class_id)
    aid = _create_assignment(client, class_id)
    with client.application.app_context():
        sub = Submission.query.filter_by(assignment_id=aid).first()
    r = student_client.post(f'/api/school/submissions/{sub.id}/artifacts', json={
        'artifact_type': 'link',
        'url': 'javascript:alert(1)',
    })
    assert r.status_code == 400
    assert r.get_json()['error'] == 'invalid_url'


def test_weighted_gradebook(client):
    class_id = _create_class(client)
    _enroll(client, class_id)
    cat = client.post(f'/api/school/classes/{class_id}/categories', json={
        'name': 'Homework',
        'weight_percent': 100,
        'creator': 'Teacher',
    }).get_json()['category']

    aid = _create_assignment(client, class_id)
    with client.application.app_context():
        a = db.session.get(Assignment, aid)
        a.category_id = cat['id']
        sub = Submission.query.filter_by(assignment_id=aid, student_id='Student').first()
        sub.status = 'submitted'
        sub.submitted_at = datetime.utcnow()
        g = GradeEntry(submission_id=sub.id, score=40, graded_by='Teacher', graded_at=datetime.utcnow())
        db.session.add(g)
        db.session.commit()

    r = client.get(f'/api/school/classes/{class_id}/gradebook')
    assert r.status_code == 200
    book = r.get_json()['gradebook']
    assert book['students'][0]['overall_percent'] == 80.0


def test_attendance_api(client):
    class_id = _create_class(client)
    _enroll(client, class_id)
    today = datetime.utcnow().strftime('%Y-%m-%d')
    r = client.post(f'/api/school/classes/{class_id}/attendance', json={
        'records': [{'student_id': 'Student', 'date': today, 'status': 'present'}],
        'creator': 'Teacher',
    })
    assert r.status_code == 200
    r = client.get(f'/api/school/classes/{class_id}/attendance', query_string=f'date={today}&creator=Teacher')
    assert r.status_code == 200
    assert len(r.get_json()['records']) == 1


def test_analytics_endpoint(client):
    class_id = _create_class(client)
    _enroll(client, class_id)
    _create_assignment(client, class_id)
    r = client.get(f'/api/school/classes/{class_id}/analytics')
    assert r.status_code == 200
    assert 'submission_rate' in r.get_json()['analytics']


def test_school_disabled_returns_404(client):
    app = make_app()
    app.config['HOMEHUB_CONFIG']['feature_toggles']['school'] = False
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['authed'] = True
    assert c.get('/school').status_code == 404


def test_parent_cannot_grade(client, app):
    class_id = _create_class(client)
    _enroll(client, class_id)
    aid = _create_assignment(client, class_id)
    with app.app_context():
        sub = Submission.query.filter_by(assignment_id=aid).first()
        sub.status = 'submitted'
        db.session.commit()
        sub_id = sub.id

    parent = _wrap(app, 'Parent')
    r = parent.post(f'/api/school/submissions/{sub_id}/grade', json={
        'score': 100,
    })
    assert r.status_code == 403
