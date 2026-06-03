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

    var search = document.getElementById('settingsFeatureSearch');
    if (search) {
        search.addEventListener('input', function () {
            var q = search.value.trim().toLowerCase();
            root.querySelectorAll('.settings-feature-card').forEach(function (card) {
                var label = (card.getAttribute('data-feature-label') || '').toLowerCase();
                var match = !q || label.indexOf(q) !== -1;
                card.classList.toggle('is-hidden', !match);
            });
            root.querySelectorAll('.settings-feature-group').forEach(function (group) {
                var visible = group.querySelectorAll('.settings-feature-card:not(.is-hidden)').length > 0;
                group.hidden = !visible;
            });
        });
    }

    root.querySelectorAll('.settings-feature-card').forEach(function (card) {
        var input = card.querySelector('input[type="checkbox"]');
        if (!input) return;
        function sync() {
            card.classList.toggle('is-off', !input.checked);
        }
        input.addEventListener('change', sync);
        sync();
        card.addEventListener('click', function (e) {
            if (e.target === input || e.target.closest('.settings-switch')) return;
            input.checked = !input.checked;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            markDirty();
        });
    });

    var weatherEnabled = document.getElementById('weather_enabled');
    var weatherFields = document.getElementById('settingsWeatherFields');
    function syncWeatherFields() {
        if (!weatherFields || !weatherEnabled) return;
        weatherFields.style.opacity = weatherEnabled.checked ? '1' : '0.55';
        weatherFields.querySelectorAll('input, select').forEach(function (el) {
            el.disabled = !weatherEnabled.checked;
        });
    }
    if (weatherEnabled) {
        weatherEnabled.addEventListener('change', syncWeatherFields);
        syncWeatherFields();
    }

    var legacyUser = document.getElementById('settings-user');
    var legacyReset = document.getElementById('settings-reset-user');
    if (legacyUser || legacyReset) {
        var name = localStorage.getItem('username') || '';
        if (legacyUser) legacyUser.value = name;
        if (legacyReset) legacyReset.value = name;
    }
})();
