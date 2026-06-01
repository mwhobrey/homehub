import os, re, shutil, subprocess
from threading import Thread
from flask import render_template, request, redirect, url_for, send_from_directory, jsonify, current_app, flash, abort
from datetime import datetime
from ..models import db, Media, PDF
from ..blueprints import main_bp
from ..extensions import limiter
from ..user_context import resolve_actor, resolve_user, can_modify_record, is_admin
from ..security import sanitize_text, safe_basename_filename
from ..media_guard import (
    build_ytdlp_command,
    count_pending_media,
    is_media_url_allowed,
    media_settings,
    safe_media_filename,
    validate_media_format,
    validate_media_quality,
)
from werkzeug.utils import secure_filename


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MEDIA_FOLDER = os.path.join(BASE_DIR, 'media')
PDF_FOLDER = os.path.join(BASE_DIR, 'pdfs')


@main_bp.route('/media', methods=['GET', 'POST'])
@limiter.limit('8 per hour', methods=['POST'])
def media():
    if request.method == 'POST':
        settings = media_settings()
        if settings['admin_only'] and not is_admin():
            flash('Only admins can queue media downloads.', 'error')
            return redirect(url_for('main.media'))

        url = sanitize_text(request.form['url'])
        creator = resolve_actor()
        if not is_media_url_allowed(url):
            flash(
                'URL not allowed. Use a supported public video host (see config hardening.media_downloader.allowed_domains).',
                'error',
            )
            return redirect(url_for('main.media'))

        pending = count_pending_media(creator)
        if pending >= settings['max_concurrent_per_user']:
            flash(
                f'You already have {pending} download(s) in progress. Wait for them to finish before starting another.',
                'error',
            )
            return redirect(url_for('main.media'))

        fmt = validate_media_format(sanitize_text(request.form.get('format', 'mp4')))
        quality = validate_media_quality(sanitize_text(request.form.get('quality', 'best')), fmt)
        base = f"media_{int(datetime.utcnow().timestamp())}_{os.getpid()}"
        output_tmpl = os.path.join(MEDIA_FOLDER, base + ".%(ext)s")
        media_obj = Media(title=url, url=url, creator=creator, filepath='', status='pending')
        db.session.add(media_obj)
        db.session.commit()
        flash('Download queued. You can switch tabs; refresh to check status.', 'info')
        cmd = build_ytdlp_command(url, output_tmpl, fmt, quality)
        timeout_sec = max(60, settings['download_timeout_minutes'] * 60)

        app_obj = current_app._get_current_object()

        def worker(app, mid: int, base_prefix: str, command: list, timeout: int):
            with app.app_context():
                m = Media.query.get(mid)
                proc = None
                try:
                    proc = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        start_new_session=True,
                    )
                    last_percent = -1
                    for line in proc.stdout:
                        try:
                            m = Media.query.get(mid)
                            if not m:
                                continue
                            match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
                            if match:
                                p = int(float(match.group(1)))
                                if p != last_percent and p % 5 == 0:
                                    m.progress = f"{p}%"
                                    db.session.commit()
                                    last_percent = p
                        except Exception:
                            pass
                    ret = proc.wait(timeout=timeout)
                    if ret != 0:
                        raise RuntimeError(f"yt-dlp exited with {ret}")
                    saved = None
                    for fname in os.listdir(MEDIA_FOLDER):
                        if fname.startswith(base_prefix):
                            saved = fname
                            break
                    m.filepath = saved or ''
                    m.status = 'done'
                except subprocess.TimeoutExpired:
                    if proc is not None:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    m.status = 'error'
                    m.progress = 'Timed out'
                except Exception:
                    m.status = 'error'
                finally:
                    if m.progress != 'Timed out':
                        m.progress = None
                    db.session.commit()

        Thread(target=worker, args=(app_obj, media_obj.id, base, cmd, timeout_sec), daemon=True).start()
        return redirect(url_for('main.media'))
    media_list = Media.query.order_by(Media.download_time.desc()).all()
    config = current_app.config['HOMEHUB_CONFIG']
    return render_template('media.html', media_list=media_list, config=config)


@main_bp.route('/media/status/<int:media_id>')
def media_status(media_id):
    m = Media.query.get_or_404(media_id)
    return jsonify({'status': m.status, 'progress': m.progress, 'filepath': m.filepath})


@main_bp.route('/media/<filename>')
def serve_media(filename):
    safe = safe_media_filename(filename)
    if not safe:
        abort(404)
    return send_from_directory(MEDIA_FOLDER, safe, as_attachment=True)


@main_bp.route('/media/preview/<filename>')
def preview_media(filename):
    """Serve media file for preview (inline) with security headers"""
    safe = safe_media_filename(filename)
    if not safe:
        abort(404)
    from flask import make_response
    response = make_response(send_from_directory(MEDIA_FOLDER, safe, as_attachment=False))
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; media-src 'self'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@main_bp.route('/media/delete/<int:media_id>', methods=['POST'])
def delete_media(media_id):
    m = Media.query.get_or_404(media_id)
    user = resolve_user()
    if can_modify_record(m.creator, user):
        try:
            if m.filepath:
                base = m.filepath.rsplit('.', 1)[0]
                for fname in os.listdir(MEDIA_FOLDER):
                    if fname.startswith(base):
                        os.remove(os.path.join(MEDIA_FOLDER, fname))
        except Exception:
            pass
        db.session.delete(m)
        db.session.commit()
    return redirect(url_for('main.media'))


@main_bp.route('/pdfs', methods=['GET', 'POST'])
def pdfs():
    if request.method == 'POST':
        pdf_file = request.files['pdf']
        creator = resolve_actor()
        filename = pdf_file.filename
        if not filename:
            return redirect(url_for('main.pdfs'))
        # Only allow .pdf uploads
        if not filename.lower().endswith('.pdf'):
            flash('Only PDF files are allowed.', 'error')
            return redirect(url_for('main.pdfs'))
        # Normalize and secure the user-provided filename to avoid traversal or odd chars
        safe_name = secure_filename(os.path.basename(filename))
        if not safe_name:
            flash('Invalid filename.', 'error')
            return redirect(url_for('main.pdfs'))
        input_path = os.path.join(PDF_FOLDER, safe_name)
        pdf_file.save(input_path)
        compressed_path = f"compressed_{safe_name}"
        output_path = os.path.join(PDF_FOLDER, compressed_path)
        try:
            gs_cmd = [
                'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                '-dPDFSETTINGS=/ebook', '-dNOPAUSE', '-dQUIET', '-dBATCH',
                f'-sOutputFile={output_path}', input_path
            ]
            subprocess.run(gs_cmd, check=True)
        except Exception:
            shutil.copy(input_path, output_path)
        pdf_obj = PDF(filename=safe_name, creator=creator, compressed_path=compressed_path)
        db.session.add(pdf_obj)
        db.session.commit()
        return redirect(url_for('main.pdfs'))
    pdfs = PDF.query.order_by(PDF.upload_time.desc()).all()
    config = current_app.config['HOMEHUB_CONFIG']
    return render_template('pdfs.html', pdfs=pdfs, config=config)


@main_bp.route('/pdfs/<filename>')
def serve_pdf(filename):
    safe = safe_basename_filename(filename)
    if not safe:
        abort(404)
    return send_from_directory(PDF_FOLDER, safe, as_attachment=True)


@main_bp.route('/pdfs/preview/<filename>')
def preview_pdf(filename):
    """Serve PDF file for preview (inline) with security headers"""
    safe = safe_basename_filename(filename)
    if not safe:
        abort(404)
    from flask import make_response
    response = make_response(send_from_directory(PDF_FOLDER, safe, as_attachment=False))
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@main_bp.route('/pdfs/delete/<int:pdf_id>', methods=['POST'])
def delete_pdf(pdf_id):
    p = PDF.query.get_or_404(pdf_id)
    user = resolve_user()
    if can_modify_record(p.creator, user):
        try:
            if p.compressed_path:
                os.remove(os.path.join(PDF_FOLDER, p.compressed_path))
        except Exception:
            pass
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for('main.pdfs'))
