import base64
import os
from io import BytesIO

from flask import abort, current_app, render_template, request, redirect, send_from_directory, url_for, flash
import qrcode

from ..models import db, QRCode
from ..blueprints import main_bp
from ..extensions import limiter
from ..user_context import resolve_actor, resolve_user, can_modify_record, is_admin
from ..security import sanitize_text
from ..qr_guard import (
    is_wifi_payload,
    prepare_qr_storage,
    purge_expired_qr_history,
    qr_settings,
    qr_storage_dir,
    safe_qr_filename,
    wifi_to_qrtext,
)


@main_bp.route('/qr', methods=['GET', 'POST'])
@limiter.limit('20 per hour', methods=['POST'])
def qr_view():
    settings = qr_settings()
    purge_expired_qr_history()
    qr_img = None
    ephemeral_wifi = False

    if request.method == 'POST':
        text = sanitize_text(request.form.get('qrtext', ''))
        if not text:
            return redirect(url_for('main.qr_view'))
        if len(text) > settings['max_payload_length']:
            flash('QR text is too long.', 'error')
            return redirect(url_for('main.qr_view'))

        wifi_text = wifi_to_qrtext(text)
        payload = wifi_text or text
        is_wifi = is_wifi_payload(payload)

        if is_wifi and settings['admin_only_wifi'] and not is_admin():
            flash('Only admins can generate WiFi QR codes.', 'error')
            return redirect(url_for('main.qr_view'))

        img = qrcode.make(payload)
        buf = BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        qr_img = b64

        stored_text, display, safe_original = prepare_qr_storage(payload, text, is_wifi)
        if is_wifi and not settings['store_wifi_history']:
            ephemeral_wifi = True
            flash(
                'WiFi QR generated. It is not saved to history (passwords are not stored). '
                'Save the image now if you need it later.',
                'info',
            )
        else:
            rec = QRCode(
                text=stored_text or ' ',
                original_input=safe_original,
                display_label=display,
                is_wifi=is_wifi,
                creator=resolve_actor(),
                filename='pending',
            )
            db.session.add(rec)
            db.session.flush()
            fname = safe_qr_filename(rec.id)
            rec.filename = fname
            out_path = os.path.join(qr_storage_dir(), fname)
            img.save(out_path)
            db.session.commit()
            flash('QR code saved.', 'success')

    history = QRCode.query.order_by(QRCode.timestamp.desc()).limit(50).all()
    config = current_app.config['HOMEHUB_CONFIG']
    return render_template(
        'qr.html',
        qr_img=qr_img,
        history=history,
        config=config,
        ephemeral_wifi=ephemeral_wifi,
        store_wifi_history=settings['store_wifi_history'],
    )


@main_bp.route('/qr/image/<int:qr_id>')
def qr_image(qr_id: int):
    rec = QRCode.query.get_or_404(qr_id)
    fname = safe_qr_filename(qr_id)
    if rec.filename != fname:
        abort(404)
    directory = qr_storage_dir()
    path = os.path.join(directory, fname)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(directory, fname, mimetype='image/png', as_attachment=False)


@main_bp.route('/qr/image/<int:qr_id>/download')
def qr_image_download(qr_id: int):
    rec = QRCode.query.get_or_404(qr_id)
    fname = safe_qr_filename(qr_id)
    if rec.filename != fname:
        abort(404)
    directory = qr_storage_dir()
    if not os.path.isfile(os.path.join(directory, fname)):
        abort(404)
    return send_from_directory(directory, fname, mimetype='image/png', as_attachment=True)


@main_bp.route('/qr/delete/<int:qr_id>', methods=['POST'])
def qr_delete(qr_id: int):
    rec = QRCode.query.get_or_404(qr_id)
    user = resolve_user()
    if can_modify_record(rec.creator, user):
        try:
            path = os.path.join(qr_storage_dir(), rec.filename)
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        db.session.delete(rec)
        db.session.commit()
    return redirect(url_for('main.qr_view'))
