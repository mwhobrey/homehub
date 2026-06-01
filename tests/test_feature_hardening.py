import pytest

from app import create_app, db
from app.media_guard import is_media_url_allowed
from app.qr_guard import (
    mask_wifi_payload,
    mask_wifi_shorthand,
    prepare_qr_storage,
    wifi_to_qrtext,
    is_wifi_payload,
)
from app.sensitive_store import decrypt_sensitive, encrypt_sensitive


def make_app():
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'HOMEHUB_CONFIG': {
            'admin_name': 'Administrator',
            'family_members': ['Alice'],
            'hardening': {
                'media_downloader': {
                    'allowed_domains': ['youtube.com', 'youtu.be'],
                },
                'qr_generator': {
                    'store_wifi_history': False,
                    'encrypt_payloads': True,
                },
            },
        },
        'SECRET_KEY': 'test-secret-key-for-encryption',
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def client():
    app = make_app()
    return app.test_client()


def test_media_blocks_non_allowlisted_domain():
    app = make_app()
    with app.app_context():
        assert is_media_url_allowed('https://www.youtube.com/watch?v=abc') is True
        assert is_media_url_allowed('https://evil.example.com/video') is False
        assert is_media_url_allowed('http://127.0.0.1:8000') is False


def test_wifi_shorthand_masking():
    raw = 'ssid:HomeNet pass:supersecret type:wpa hidden:false'
    masked = mask_wifi_shorthand(raw)
    assert 'supersecret' not in masked
    assert 'pass:***' in masked or 'pass:***' in masked.lower()


def test_wifi_payload_masking():
    payload = wifi_to_qrtext('ssid:Home pass:secret type:wpa hidden:false')
    assert is_wifi_payload(payload)
    assert 'secret' not in mask_wifi_payload(payload)


def test_prepare_qr_storage_ephemeral_wifi():
    app = make_app()
    with app.app_context():
        payload = wifi_to_qrtext('ssid:Home pass:secret type:wpa')
        stored, display, original = prepare_qr_storage(payload, 'ssid:Home pass:secret', True)
        assert stored == ''
        assert 'secret' not in original
        assert display.startswith('WiFi:')


def test_encrypt_roundtrip():
    app = make_app()
    with app.app_context():
        enc = encrypt_sensitive('WIFI:T:WPA;S:Home;P:secret;;')
        assert enc.startswith('enc:v1:')
        assert decrypt_sensitive(enc) == 'WIFI:T:WPA;S:Home;P:secret;;'


def test_media_post_rejects_bad_domain(client):
    resp = client.post('/media', data={
        'url': 'https://not-allowed.example.com/vid',
        'creator': 'Alice',
        'format': 'mp4',
        'quality': 'best',
    }, follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert 'not allowed' in body.lower() or 'URL not allowed' in body
