"""Media downloader hardening helpers."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from flask import current_app

from .models import Media
from .security import is_url_safe_for_fetch

DEFAULT_ALLOWED_MEDIA_DOMAINS = (
    'youtube.com',
    'www.youtube.com',
    'm.youtube.com',
    'music.youtube.com',
    'youtu.be',
    'vimeo.com',
    'www.vimeo.com',
)


def media_settings() -> dict:
    cfg = current_app.config.get('HOMEHUB_CONFIG', {})
    hard = cfg.get('hardening') or {}
    media = hard.get('media_downloader') or {}
    domains = media.get('allowed_domains')
    if domains is None:
        domains = list(DEFAULT_ALLOWED_MEDIA_DOMAINS)
    return {
        'allowed_domains': [d.lower().strip() for d in domains if d],
        'max_filesize_mb': int(media.get('max_filesize_mb', 500)),
        'max_concurrent_per_user': int(media.get('max_concurrent_per_user', 2)),
        'download_timeout_minutes': int(media.get('download_timeout_minutes', 45)),
        'admin_only': bool(media.get('admin_only', False)),
        'rate_limit': str(media.get('rate_limit', '8 per hour')),
    }


def _host_allowed(hostname: str, allowed: list[str]) -> bool:
    host = (hostname or '').lower().rstrip('.')
    if not host or not allowed:
        return False
    for domain in allowed:
        if host == domain or host.endswith('.' + domain):
            return True
    return False


def is_media_url_allowed(url: str) -> bool:
    if not is_url_safe_for_fetch(url):
        return False
    allowed = media_settings()['allowed_domains']
    if not allowed:
        return False
    try:
        host = urlparse(url).hostname or ''
    except Exception:
        return False
    return _host_allowed(host, allowed)


def count_pending_media(creator: str) -> int:
    if not creator:
        creator = ''
    return Media.query.filter_by(creator=creator, status='pending').count()


def validate_media_format(fmt: str) -> str:
    fmt = (fmt or 'mp4').lower()
    return fmt if fmt in ('mp4', 'mp3') else 'mp4'


def validate_media_quality(quality: str, fmt: str) -> str:
    if fmt == 'mp3':
        return 'best'
    allowed = {
        'best',
        'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        'bestvideo[height<=720]+bestaudio/best[height<=720]',
    }
    q = (quality or 'best').strip()
    return q if q in allowed else 'best'


def build_ytdlp_command(url: str, output_tmpl: str, fmt: str, quality: str) -> list[str]:
    settings = media_settings()
    fmt = validate_media_format(fmt)
    quality = validate_media_quality(quality, fmt)
    cmd = [
        'yt-dlp',
        '--no-playlist',
        '--no-warnings',
        '--max-filesize',
        f"{max(1, settings['max_filesize_mb'])}M",
        '--socket-timeout',
        '30',
        '-o',
        output_tmpl,
    ]
    if fmt == 'mp3':
        cmd += ['-x', '--audio-format', 'mp3']
    else:
        if quality == 'best':
            fmt_string = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        else:
            fmt_string = f'{quality}/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
        cmd += ['-f', fmt_string, '--merge-output-format', 'mp4']
    cmd.append(url)
    return cmd


def safe_media_filename(filename: str) -> str | None:
    if not filename:
        return None
    name = os.path.basename(filename)
    if name != filename or '..' in filename or name.startswith('.'):
        return None
    return name
