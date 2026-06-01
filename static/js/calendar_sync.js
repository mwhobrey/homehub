/**
 * Google Calendar connect UI, manager panel, and write-target dropdown.
 */
(function () {
  if (!window.calendarSyncApi) return;

  const banner = document.getElementById('calendarConnectBanner');
  const writeRow = document.getElementById('writeCalendarRow');
  const writeSelect = document.getElementById('writeCalendarSelect');
  const writeHint = document.getElementById('writeCalendarHint');
  const defaultSelect = document.getElementById('defaultWriteCalendarSelect');
  const ownList = document.getElementById('calendarOwnList');
  const visibleList = document.getElementById('calendarVisibleList');
  const lastSyncEl = document.getElementById('calendarLastSync');
  const syncBtn = document.getElementById('calendarSyncNow');

  let writableCalendars = [];

  function updateWriteHint() {
    if (!writeHint || !writeSelect) return;
    const opt = writeSelect.selectedOptions[0];
    writeHint.textContent = opt ? `Saving to: ${opt.textContent}` : '';
  }

  function populateWriteSelect(selectedId) {
    if (!writeSelect) return;
    writeSelect.innerHTML = '';
    writableCalendars.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.summary || `Calendar ${c.id}`;
      if (selectedId && c.id === selectedId) opt.selected = true;
      else if (!selectedId && c.is_default) opt.selected = true;
      writeSelect.appendChild(opt);
    });
    if (writeRow) writeRow.classList.toggle('hidden', !writableCalendars.length);
    updateWriteHint();
  }

  async function loadWritable() {
    const res = await window.calendarSyncApi.writableCalendars();
    if (res.ok) writableCalendars = res.calendars || [];
    populateWriteSelect();
    if (defaultSelect) {
      defaultSelect.innerHTML = '';
      writableCalendars.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.summary || `Calendar ${c.id}`;
        if (c.is_default) opt.selected = true;
        defaultSelect.appendChild(opt);
      });
    }
  }

  function renderCalendarRow(cal, isOwner) {
    const div = document.createElement('div');
    div.className = 'border rounded p-2 space-y-1';
    const color = cal.background_color || '#2563eb';
    div.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-full flex-shrink-0" style="background:${color}"></span>
        <strong>${escapeHtml(cal.summary || '')}</strong>
      </div>`;
    if (isOwner) {
      const vis = document.createElement('select');
      vis.className = 'text-xs border rounded p-1';
      ['private', 'household', 'custom'].forEach((v) => {
        const o = document.createElement('option');
        o.value = v;
        o.textContent = v;
        if ((cal.visibility || 'household') === v) o.selected = true;
        vis.appendChild(o);
      });
      vis.addEventListener('change', () => {
        window.calendarSyncApi.patchCalendar(cal.id, { visibility: vis.value }).then(loadManager);
      });
      const syncLbl = document.createElement('label');
      syncLbl.className = 'text-xs inline-flex items-center gap-1';
      syncLbl.innerHTML = `<input type="checkbox" ${cal.sync_enabled ? 'checked' : ''}> Sync`;
      syncLbl.querySelector('input').addEventListener('change', (e) => {
        window.calendarSyncApi.patchCalendar(cal.id, { sync_enabled: e.target.checked }).then(loadManager);
      });
      const defBtn = document.createElement('button');
      defBtn.type = 'button';
      defBtn.className = 'text-xs text-blue-600';
      defBtn.textContent = cal.is_default ? 'Default write' : 'Set as default write';
      defBtn.addEventListener('click', () => {
        window.calendarSyncApi.patchCalendar(cal.id, { set_default: true }).then(() => {
          loadWritable();
          loadManager();
        });
      });
      div.appendChild(vis);
      div.appendChild(syncLbl);
      div.appendChild(defBtn);
    } else {
      const prefLbl = document.createElement('label');
      prefLbl.className = 'text-xs inline-flex items-center gap-1';
      prefLbl.innerHTML = `<input type="checkbox" ${cal.visible !== false ? 'checked' : ''}> Show on my calendar`;
      prefLbl.querySelector('input').addEventListener('change', (e) => {
        window.calendarSyncApi.displayPrefs([
          { linked_calendar_id: cal.id, visible: e.target.checked },
        ]);
      });
      div.appendChild(prefLbl);
    }
    return div;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  async function loadManager() {
    const st = await window.calendarSyncApi.status();
    if (banner) {
      banner.classList.toggle('hidden', !!st.connected);
    }
    if (!st.connected) return;
    if (lastSyncEl && st.last_sync_at) {
      lastSyncEl.textContent = 'Last sync: ' + new Date(st.last_sync_at).toLocaleString();
    }
    const data = await window.calendarSyncApi.calendars();
    if (!data.ok) return;
    if (ownList) {
      ownList.innerHTML = '<div class="text-xs font-semibold text-gray-600">Your calendars</div>';
      (data.own || []).forEach((c) => ownList.appendChild(renderCalendarRow(c, true)));
    }
    if (visibleList) {
      visibleList.innerHTML = '<div class="text-xs font-semibold text-gray-600 mt-2">Shared with you</div>';
      (data.visible || []).forEach((c) => visibleList.appendChild(renderCalendarRow(c, false)));
    }
    await loadWritable();
  }

  if (writeSelect) {
    writeSelect.addEventListener('change', updateWriteHint);
  }
  if (defaultSelect) {
    defaultSelect.addEventListener('change', () => {
      const id = parseInt(defaultSelect.value, 10);
      if (!id) return;
      window.calendarSyncApi.patchCalendar(id, { set_default: true }).then(loadWritable);
    });
  }
  if (syncBtn) {
    syncBtn.addEventListener('click', async () => {
      syncBtn.disabled = true;
      await window.calendarSyncApi.syncNow();
      await loadManager();
      if (typeof fetchMonth === 'function' && typeof getSelectedDate === 'function') {
        await fetchMonth(getSelectedDate(), true);
        if (typeof updateCalendarBadges === 'function') updateCalendarBadges();
        if (typeof renderList === 'function') renderList();
      }
      syncBtn.disabled = false;
    });
  }

  window.homehubCalendarSync = {
    getWriteCalendarId() {
      if (!writeSelect || writeRow.classList.contains('hidden')) return null;
      const v = parseInt(writeSelect.value, 10);
      return Number.isFinite(v) ? v : null;
    },
    setWriteCalendarId(id) {
      populateWriteSelect(id);
    },
    refresh: loadManager,
  };

  const params = new URLSearchParams(window.location.search);
  if (params.get('connect_calendar') === '1' && banner) {
    banner.classList.remove('hidden');
  }
  if (params.get('calendar_connected') === '1') {
    window.history.replaceState({}, '', window.location.pathname);
  }

  loadManager().catch((e) => console.error('calendar sync init', e));
})();
