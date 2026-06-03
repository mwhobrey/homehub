(function () {
    'use strict';

    var root = document.getElementById('settingsApp');
    if (!root) return;

    var form = document.getElementById('settingsForm');
    var dirty = false;
    var initialSnapshot = form ? new FormData(form) : null;

    function markDirty() {
        dirty = true;
        var hint = document.getElementById('settingsDirtyHint');
        if (hint) hint.classList.remove('hidden');
    }

    function formMatchesInitial() {
        if (!form || !initialSnapshot) return true;
        var now = new FormData(form);
        var keys = new Set();
        initialSnapshot.forEach(function (_, k) { keys.add(k); });
        now.forEach(function (_, k) { keys.add(k); });
        var it = keys.values();
        var key;
        while (!(key = it.next()).done) {
            var k = key.value;
            var a = initialSnapshot.getAll(k).sort().join('\0');
            var b = now.getAll(k).sort().join('\0');
            if (a !== b) return false;
        }
        return true;
    }

    if (form) {
        form.addEventListener('input', markDirty);
        form.addEventListener('change', markDirty);
        window.addEventListener('beforeunload', function (e) {
            if (dirty && !formMatchesInitial()) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
        form.addEventListener('submit', function () {
            dirty = false;
        });
    }

    var navButtons = root.querySelectorAll('[data-settings-tab]');
    var panels = root.querySelectorAll('[data-settings-panel]');

    function showPanel(id) {
        panels.forEach(function (panel) {
            var on = panel.getAttribute('data-settings-panel') === id;
            panel.classList.toggle('is-active', on);
            panel.hidden = !on;
        });
        navButtons.forEach(function (btn) {
            var on = btn.getAttribute('data-settings-tab') === id;
            btn.setAttribute('aria-current', on ? 'page' : 'false');
        });
        try { history.replaceState(null, '', '#settings-' + id); } catch (e) { /* ignore */ }
    }

    navButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            showPanel(btn.getAttribute('data-settings-tab'));
        });
    });

    var hash = (location.hash || '').replace(/^#settings-/, '');
    if (hash && root.querySelector('[data-settings-panel="' + hash + '"]')) {
        showPanel(hash);
    } else if (panels.length) {
        showPanel(panels[0].getAttribute('data-settings-panel'));
    }

    root.querySelectorAll('.settings-appearance-modes input[type="radio"]').forEach(function (radio) {
        radio.addEventListener('change', function () {
            root.querySelectorAll('.settings-appearance-modes label').forEach(function (label) {
                var on = label.querySelector('input') && label.querySelector('input').checked;
                label.classList.toggle('is-selected', on);
            });
            markDirty();
        });
        if (radio.checked && radio.closest('label')) {
            radio.closest('label').classList.add('is-selected');
        }
    });

    function normalizeHex(raw) {
        if (!raw) return '';
        var s = String(raw).trim();
        if (!s) return '';
        if (s.charAt(0) !== '#') s = '#' + s;
        if (/^#[0-9A-Fa-f]{6}$/.test(s)) return s.toLowerCase();
        if (/^#[0-9A-Fa-f]{3}$/.test(s)) {
            return ('#' + s[1] + s[1] + s[2] + s[2] + s[3] + s[3]).toLowerCase();
        }
        return '';
    }

    var preview = document.getElementById('settingsThemePreview');
    var themeKeys = [
        'primary_color', 'secondary_color', 'background_color', 'card_background_color', 'text_color',
        'sidebar_background_color', 'sidebar_text_color', 'sidebar_link_color',
        'sidebar_link_border_color', 'sidebar_active_color'
    ];

    function readThemeVar(key) {
        var text = root.querySelector('[name="theme_' + key + '"]');
        var color = root.querySelector('[data-theme-color="' + key + '"]');
        var hex = '';
        if (color && color.value) hex = color.value;
        if (!hex && text && text.value) hex = normalizeHex(text.value);
        if (!hex && text && text.placeholder) hex = normalizeHex(text.placeholder);
        return hex || '';
    }

    function updateThemePreview() {
        if (!preview) return;
        var vars = {};
        themeKeys.forEach(function (key) {
            vars[key] = readThemeVar(key);
        });
        preview.style.setProperty('--preview-bg', vars.background_color || '#f7fafc');
        preview.style.setProperty('--preview-card', vars.card_background_color || '#fff');
        preview.style.setProperty('--preview-text', vars.text_color || '#333');
        preview.style.setProperty('--preview-primary', vars.primary_color || '#2563eb');
        preview.style.setProperty('--preview-sidebar-bg', vars.sidebar_background_color || '#2563eb');
        preview.style.setProperty('--preview-sidebar-text', vars.sidebar_text_color || '#fff');
        preview.style.setProperty('--preview-sidebar-active', vars.sidebar_active_color || '#3b82f6');
    }

    root.querySelectorAll('[data-theme-color]').forEach(function (picker) {
        var key = picker.getAttribute('data-theme-color');
        var text = root.querySelector('[name="theme_' + key + '"]');
        function syncFromPicker() {
            if (text) text.value = picker.value;
            updateThemePreview();
            markDirty();
        }
        function syncFromText() {
            var hex = normalizeHex(text ? text.value : '');
            if (hex && hex.length === 7) picker.value = hex;
            updateThemePreview();
        }
        picker.addEventListener('input', syncFromPicker);
        if (text) {
            text.addEventListener('input', syncFromText);
            text.addEventListener('change', syncFromText);
        }
        syncFromText();
    });
    updateThemePreview();

    var legacyUser = document.getElementById('settings-user');
    var legacyReset = document.getElementById('settings-reset-user');
    if (legacyUser || legacyReset) {
        var name = localStorage.getItem('username') || '';
        if (legacyUser) legacyUser.value = name;
        if (legacyReset) legacyReset.value = name;
        if (name && legacyUser && !legacyUser.value) {
            window.location.href = '/settings?user=' + encodeURIComponent(name);
        }
    }
})();
