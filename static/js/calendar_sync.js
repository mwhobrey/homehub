/**
 * Google Calendar connect UI, manager panel, and write-target dropdown.
 */
(function () {
  if (!window.calendarSyncApi) return;

  const banner = document.getElementById('calendarConnectBanner');
  const bannerText = document.getElementById('calendarConnectBannerText');
  const connectedPanel = document.getElementById('calendarConnectedPanel');
  const disconnectBtn = document.getElementById('calDisconnect');
  const disconnectConnectedBtn = document.getElementById('calDisconnectConnected');
  const writeRow = document.getElementById('writeCalendarRow');
  const writeSelect = document.getElementById('writeCalendarSelect');
  const writeHint = document.getElementById('writeCalendarHint');
  const defaultSelect = document.getElementById('defaultWriteCalendarSelect');
  const ownList = document.getElementById('calendarOwnList');
  const visibleList = document.getElementById('calendarVisibleList');
  const lastSyncEl = document.getElementById('calendarLastSync');
  const syncBtn = document.getElementById('calendarSyncNow') || document.getElementById('calSyncNow');
  const syncModeSelect = document.getElementById('calendarSyncModeSelect');
  const personalCalendarSelect = document.getElementById('personalCalendarSelect');
  const wizardRows = document.getElementById('calendarImportWizardRows');
  const wizardOpenBtn = document.getElementById('calendarImportOpen');
  const wizardModal = document.getElementById('calendarImportModal');
  const wizardCloseBtn = document.getElementById('calendarImportClose');
  const wizardStepLabel = document.getElementById('calendarImportStepLabel');
  const wizardStep1 = document.getElementById('calendarImportStep1');
  const wizardStep2 = document.getElementById('calendarImportStep2');
  const wizardSourceList = document.getElementById('calendarImportSourceList');
  const wizardPreviewSummary = document.getElementById('calendarImportPreviewSummary');
  const wizardBackBtn = document.getElementById('calendarImportBack');
  const wizardNextBtn = document.getElementById('calendarImportNext');
  const wizardCommitBtn = document.getElementById('calendarImportCommit');
  const wizardSummary = document.getElementById('calendarImportSummary');
  const wizardSubstepLabel = document.getElementById('calendarImportSubstepLabel');
  const wizardSubstepPills = document.getElementById('calendarImportSubstepPills');

  let writableCalendars = [];
  let personalCalendars = [];
  let importOptions = [];
  let allowBidirectional = true;
  let wizardStep = 1;
  const selectedSourceIds = new Set();
  const wizardStateBySource = new Map();
  let wizardMapIndex = 0;

  const WIZARD_STEP_META = [
    { title: 'Select sources' },
    { title: 'Map & import' },
  ];

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
    if (res.ok) {
      writableCalendars = res.calendars || [];
      personalCalendars = res.personal_calendars || personalCalendars;
    }
    populateWriteSelect();
    if (personalCalendarSelect) {
      personalCalendarSelect.innerHTML = '';
      personalCalendars.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name || `Calendar ${c.id}`;
        personalCalendarSelect.appendChild(opt);
      });
    }
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
      if (window.homehubColorPicker) {
        const colorMount = document.createElement('div');
        colorMount.className = 'mt-1';
        window.homehubColorPicker.mount(colorMount, {
          value: cal.background_color || '#2563eb',
          label: 'Lane color',
          onChange(hex) {
            if (!hex) return;
            window.calendarSyncApi.patchCalendar(cal.id, { background_color: hex }).then(() => {
              loadManager();
              if (window.homehubCalendarApp && window.homehubCalendarApp.onCalendarsUpdated) {
                window.homehubCalendarApp.onCalendarsUpdated();
              }
            });
          },
        });
        div.appendChild(colorMount);
      }
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
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function showConnectBanner(message, showDisconnect) {
    if (bannerText && message) bannerText.textContent = message;
    if (banner) banner.classList.remove('hidden');
    if (connectedPanel) connectedPanel.classList.add('hidden');
    if (disconnectBtn) disconnectBtn.classList.toggle('hidden', !showDisconnect);
  }

  function showConnectedPanel() {
    if (banner) banner.classList.add('hidden');
    if (connectedPanel) connectedPanel.classList.remove('hidden');
    if (disconnectBtn) disconnectBtn.classList.add('hidden');
  }

  async function loadManager() {
    const st = await window.calendarSyncApi.status();
    if (!st.connected) {
      const msg = st.connection_incomplete
        ? 'Google sign-in did not finish. Disconnect to clear the partial link, then connect again.'
        : 'Connect Google Calendar to sync household schedules.';
      const withUri = st.oauth_redirect_uri ? `${msg} Expected OAuth callback: ${st.oauth_redirect_uri}` : msg;
      showConnectBanner(withUri, !!st.connection_incomplete);
      if (ownList) ownList.innerHTML = '';
      if (visibleList) visibleList.innerHTML = '';
      writableCalendars = [];
      populateWriteSelect();
      return;
    }
    showConnectedPanel();
    if (lastSyncEl && st.last_sync_at) {
      lastSyncEl.textContent = 'Last sync: ' + new Date(st.last_sync_at).toLocaleString();
    } else if (lastSyncEl) {
      lastSyncEl.textContent = '';
    }
    allowBidirectional = st.allow_bidirectional_opt_in !== false;
    if (syncModeSelect) {
      const bidirectionalOpt = syncModeSelect.querySelector('option[value="bidirectional"]');
      if (bidirectionalOpt) bidirectionalOpt.disabled = !allowBidirectional;
      syncModeSelect.value = st.sync_mode || 'import_only';
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
    if (data.personal_calendars) personalCalendars = data.personal_calendars;
    await loadWritable();
    await loadImportWizard();
    if (window.homehubCalendarApp && window.homehubCalendarApp.onCalendarsUpdated) {
      await window.homehubCalendarApp.onCalendarsUpdated();
    }
  }

  function selectedImportOptions() {
    return importOptions.filter((c) => selectedSourceIds.has(c.id));
  }

  function normalizedName(v) {
    return String(v || '').trim().toLowerCase();
  }

  function getWizardState(sourceId) {
    const id = Number(sourceId);
    if (!wizardStateBySource.has(id)) {
      const source = importOptions.find((c) => c.id === id);
      const existingMappings = source?.category_mappings || [];
      const inferred = source?.source_categories || [];
      const merged = new Map();
      const fallbackColor = source?.background_color || '#2563eb';
      inferred.forEach((c) => {
        const label = c.label || c.key;
        merged.set(c.key, {
          source_key: c.key,
          source_label: label,
          target_label: label,
          target_color: c.color || fallbackColor,
          enabled: true,
        });
      });
      existingMappings.forEach((c) => {
        const label = c.source_label || c.source_key;
        merged.set(c.source_key, {
          source_key: c.source_key,
          source_label: label,
          target_label: c.target_label || label,
          target_color: c.target_color || fallbackColor,
          enabled: true,
        });
      });
      if (!merged.size) {
        merged.set('default', {
          source_key: 'default',
          source_label: 'Default',
          target_label: 'Default',
          target_color: fallbackColor,
          enabled: true,
        });
      }
      const defaultPcId = source?.import_mapping?.personal_calendar_id || personalCalendars[0]?.id || null;
      const defaultPcName = personalCalendars.find((pc) => pc.id === defaultPcId)?.name || personalCalendars[0]?.name || 'My Calendar';
      wizardStateBySource.set(id, {
        linked_calendar_id: id,
        import_enabled: source?.import_mapping?.import_enabled !== false,
        personal_calendar_name: defaultPcName,
        import_color: source?.import_mapping?.import_color || source?.background_color || '#2563eb',
        categories: Array.from(merged.values()),
      });
    }
    return wizardStateBySource.get(id);
  }

  function getWizardSelections() {
    return selectedImportOptions().map((source) => {
      const state = getWizardState(source.id);
      const enabledCats = (state.categories || []).filter((c) => c.enabled && (c.target_label || '').trim());
      const calendarName = (state.personal_calendar_name || '').trim();
      const match = personalCalendars.find((pc) => normalizedName(pc.name) === normalizedName(calendarName));
      return {
        linked_calendar_id: state.linked_calendar_id,
        import_enabled: !!state.import_enabled,
        personal_calendar_id: match ? match.id : null,
        new_personal_calendar_name: match ? '' : calendarName,
        new_personal_calendar_color: state.import_color || '#2563eb',
        import_color: state.import_color || null,
        categories: enabledCats.map((c) => ({
          source_key: c.source_key,
          source_label: c.source_label || c.source_key,
          target_key: (c.target_label || '').trim().toLowerCase().replace(/\s+/g, '_'),
          target_label: (c.target_label || '').trim(),
          target_color: c.target_color || null,
        })),
      };
    });
  }

  function renderSourceList() {
    if (!wizardSourceList) return;
    wizardSourceList.innerHTML = '';
    if (!importOptions.length) {
      wizardSourceList.innerHTML = '<p class="text-sm text-gray-500 py-4 text-center">No Google calendars available. Connect Google in Setup first.</p>';
      return;
    }
    importOptions.forEach((cal) => {
      const catCount = (cal.source_categories || []).length;
      const row = document.createElement('label');
      row.className = 'cal-source-card';
      row.innerHTML = `
        <input type="checkbox" data-source-id="${cal.id}" ${selectedSourceIds.has(cal.id) ? 'checked' : ''} aria-label="Import ${escapeHtml(cal.summary || 'calendar')}">
        <span class="min-w-0 flex-1">
          <span class="flex items-center gap-2 min-w-0">
            <span class="w-3 h-3 rounded-full shrink-0" style="background:${cal.background_color || '#2563eb'}" aria-hidden="true"></span>
            <span class="font-semibold text-sm truncate block">${escapeHtml(cal.summary || 'Untitled calendar')}</span>
          </span>
          <span class="text-xs text-gray-500 mt-1 block">${catCount ? `${catCount} categor${catCount === 1 ? 'y' : 'ies'} detected` : 'No category labels detected — default mapping will be used'}</span>
        </span>
      `;
      row.querySelector('input')?.addEventListener('change', (e) => {
        if (e.target.checked) selectedSourceIds.add(cal.id);
        else {
          selectedSourceIds.delete(cal.id);
          if (wizardMapIndex >= selectedImportOptions().length) {
            wizardMapIndex = Math.max(0, selectedImportOptions().length - 1);
          }
        }
        renderMapSubstepPills();
        renderImportWizardRows();
        updateWizardFooter();
      });
      wizardSourceList.appendChild(row);
    });
  }

  function setAllSourceSelection(selectAll) {
    if (selectAll) importOptions.forEach((c) => selectedSourceIds.add(c.id));
    else {
      selectedSourceIds.clear();
      wizardMapIndex = 0;
    }
    renderSourceList();
    renderMapSubstepPills();
    renderImportWizardRows();
    updateWizardFooter();
  }

  function renderMapSubstepPills() {
    if (!wizardSubstepPills) return;
    const selected = selectedImportOptions();
    wizardSubstepPills.innerHTML = '';
    selected.forEach((cal, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      const active = idx === wizardMapIndex;
      btn.className = `cal-map-pill${active ? ' is-active' : ''}`;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      btn.title = cal.summary || `Calendar ${cal.id}`;
      btn.textContent = cal.summary || `Calendar ${cal.id}`;
      btn.addEventListener('click', () => {
        wizardMapIndex = idx;
        renderMapSubstepPills();
        renderImportWizardRows();
        updateWizardFooter();
      });
      wizardSubstepPills.appendChild(btn);
    });
    if (wizardSubstepLabel) {
      wizardSubstepLabel.textContent = selected.length
        ? `${wizardMapIndex + 1} / ${selected.length}`
        : '';
    }
  }

  function renderImportWizardRows() {
    if (!wizardRows) return;
    wizardRows.innerHTML = '';
    const selected = selectedImportOptions();
    if (!selected.length) {
      wizardRows.innerHTML = '<p class="text-sm text-gray-500 py-6 text-center">Go back and select at least one Google calendar.</p>';
      return;
    }
    const cal = selected[Math.max(0, Math.min(wizardMapIndex, selected.length - 1))];
    const state = getWizardState(cal.id);
    const categoryTotal = (state.categories || []).length;
    const categoryMapped = (state.categories || []).filter((c) => c.enabled && (c.target_label || '').trim()).length;
    const row = document.createElement('div');
    row.className = 'cal-map-card space-y-4';
    const datalistId = `calendarImportPersonalSuggestions-${cal.id}`;
    const datalistOptions = personalCalendars
      .map((pc) => `<option value="${escapeHtml(pc.name || `Calendar ${pc.id}`)}"></option>`)
      .join('');
    row.innerHTML = `
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-base font-bold leading-tight truncate">${escapeHtml(cal.summary || 'Untitled calendar')}</p>
          <p class="text-xs text-gray-500 mt-1">${categoryMapped} of ${categoryTotal} categories mapped</p>
        </div>
        <label class="inline-flex items-center gap-2 text-sm font-medium shrink-0 cursor-pointer">
          <input type="checkbox" class="h-4 w-4 accent-[var(--primary-color)]" data-field="import_enabled" ${state.import_enabled ? 'checked' : ''}>
          Import events
        </label>
      </div>
      <div class="grid sm:grid-cols-2 gap-4">
        <label class="cal-field">Destination HomeHub calendar
          <input data-field="personal_calendar_name" list="${datalistId}" value="${escapeHtml(state.personal_calendar_name || '')}" placeholder="e.g. Family, Work…" autocomplete="off">
          <datalist id="${datalistId}">${datalistOptions}</datalist>
          <span class="cal-field-hint">Pick an existing calendar or type a new name to create one on import.</span>
        </label>
        <label class="cal-field">Default event color
          <input type="color" data-field="import_color" value="${state.import_color || '#2563eb'}">
        </label>
      </div>
      <div class="space-y-2">
        <p class="text-sm font-semibold">Category mappings</p>
        <p class="text-xs text-gray-500">Categories are on by default with Google names and colors. Disable a card to skip that label on import.</p>
        <div class="cal-category-grid" data-category-rows></div>
      </div>
    `;
    const catWrap = row.querySelector('[data-category-rows]');
    function syncCatRowUi(catRow, enabled) {
      catRow.classList.toggle('is-disabled', !enabled);
    }
    (state.categories || []).forEach((cat, idx) => {
      const catRow = document.createElement('div');
      catRow.className = `cal-cat-row${cat.enabled ? '' : ' is-disabled'}`;
      catRow.innerHTML = `
        <div class="cal-cat-row__head">
          <input type="checkbox" data-cat-field="enabled" ${cat.enabled ? 'checked' : ''} aria-label="Map ${escapeHtml(cat.source_label || cat.source_key)}">
          <div class="cal-cat-row__title text-xs">
            <p class="font-semibold truncate">${escapeHtml(cat.source_label || cat.source_key)}</p>
            <p class="text-[10px] text-gray-500 truncate">${escapeHtml(cat.source_key)}</p>
          </div>
        </div>
        <input data-cat-field="target_label" placeholder="HomeHub category" value="${escapeHtml(cat.target_label || '')}" aria-label="HomeHub category for ${escapeHtml(cat.source_label || cat.source_key)}">
        <input type="color" data-cat-field="target_color" value="${cat.target_color || '#2563eb'}" aria-label="Color for ${escapeHtml(cat.source_label || cat.source_key)}">
      `;
      const enabledEl = catRow.querySelector('[data-cat-field="enabled"]');
      const labelEl = catRow.querySelector('[data-cat-field="target_label"]');
      const colorEl = catRow.querySelector('[data-cat-field="target_color"]');
      enabledEl?.addEventListener('change', (e) => {
        state.categories[idx].enabled = !!e.target.checked;
        syncCatRowUi(catRow, state.categories[idx].enabled);
        updateWizardFooter();
      });
      labelEl?.addEventListener('input', (e) => {
        state.categories[idx].target_label = e.target.value;
        if (e.target.value && !state.categories[idx].enabled) {
          state.categories[idx].enabled = true;
          if (enabledEl) enabledEl.checked = true;
        }
        updateWizardFooter();
      });
      colorEl?.addEventListener('input', (e) => {
        state.categories[idx].target_color = e.target.value;
      });
      catWrap?.appendChild(catRow);
    });
    const importToggle = row.querySelector('[data-field="import_enabled"]');
    const personalNameInput = row.querySelector('[data-field="personal_calendar_name"]');
    const importColor = row.querySelector('[data-field="import_color"]');
    importToggle?.addEventListener('change', (e) => {
      state.import_enabled = !!e.target.checked;
      updateWizardFooter();
    });
    personalNameInput?.addEventListener('input', (e) => { state.personal_calendar_name = e.target.value; updateWizardFooter(); });
    importColor?.addEventListener('input', (e) => { state.import_color = e.target.value; });
    wizardRows.appendChild(row);
  }

  function updatePreviewSummary() {
    if (!wizardPreviewSummary) return;
    const selected = selectedImportOptions();
    if (wizardStep !== 2 || !selected.length) {
      wizardPreviewSummary.classList.add('hidden');
      return;
    }
    const selections = getWizardSelections();
    const selectedCount = selections.filter((s) => s.import_enabled).length;
    const categoryCount = selections.reduce((sum, s) => sum + ((s.categories || []).length), 0);
    wizardPreviewSummary.textContent = `Ready: ${selectedCount} calendar${selectedCount === 1 ? '' : 's'}, ${categoryCount} category mapping${categoryCount === 1 ? '' : 's'}.`;
    wizardPreviewSummary.classList.remove('hidden');
  }

  function updateWizardFooter() {
    const selected = selectedImportOptions();
    const onStep2 = wizardStep === 2;
    const hasMoreCalendars = onStep2 && selected.length > 0 && wizardMapIndex < selected.length - 1;

    if (wizardBackBtn) {
      wizardBackBtn.classList.toggle('invisible', wizardStep === 1);
      wizardBackBtn.textContent = onStep2 && wizardMapIndex > 0 ? 'Previous' : 'Back';
    }
    if (wizardNextBtn) {
      const showNext = wizardStep === 1 || hasMoreCalendars;
      wizardNextBtn.classList.toggle('hidden', !showNext);
      wizardNextBtn.textContent = wizardStep === 1 ? 'Continue' : 'Next calendar';
    }
    if (wizardCommitBtn) {
      wizardCommitBtn.classList.toggle('hidden', !(onStep2 && selected.length));
    }
    updatePreviewSummary();
  }

  function refreshWizardStepper() {
    const root = wizardModal || document;
    [1, 2].forEach((n) => {
      const pill = root.querySelector(`[data-step-pill="${n}"]`);
      if (!pill) return;
      const isCurrent = n === wizardStep;
      const isComplete = n < wizardStep;
      pill.classList.remove('is-active', 'is-done');
      if (isCurrent) pill.classList.add('is-active');
      else if (isComplete) pill.classList.add('is-done');
      const numEl = pill.querySelector('.cal-import-step__num');
      if (numEl) numEl.textContent = isComplete ? '✓' : String(n);
      pill.setAttribute('aria-current', isCurrent ? 'step' : 'false');
    });
  }

  function setWizardStep(step) {
    wizardStep = Math.min(2, Math.max(1, step));
    const meta = WIZARD_STEP_META[wizardStep - 1];
    if (wizardStepLabel && meta) {
      wizardStepLabel.textContent = `Step ${wizardStep} of 2 — ${meta.title}`;
    }
    refreshWizardStepper();
    wizardModal?.classList.add('cal-import-modal--wide');
    wizardStep1?.classList.toggle('hidden', wizardStep !== 1);
    wizardStep2?.classList.toggle('hidden', wizardStep !== 2);
    if (wizardStep === 2) {
      renderMapSubstepPills();
      renderImportWizardRows();
    }
    updateWizardFooter();
  }

  async function loadImportWizard() {
    if (!window.calendarSyncApi.importOptions || !wizardRows) return;
    if (wizardSourceList) wizardSourceList.innerHTML = '<p class="text-xs text-gray-500">Loading calendars...</p>';
    const res = await window.calendarSyncApi.importOptions();
    if (!res.ok) {
      if (wizardSourceList) wizardSourceList.innerHTML = `<p class="text-xs text-red-600">Could not load import options (${escapeHtml(res.error || 'unknown_error')}).</p>`;
      return;
    }
    importOptions = res.linked_calendars || [];
    if (res.personal_calendars) personalCalendars = res.personal_calendars;
    if (!selectedSourceIds.size) {
      importOptions.forEach((cal) => {
        if (cal.import_mapping?.import_enabled !== false) selectedSourceIds.add(cal.id);
      });
    }
    renderSourceList();
    renderMapSubstepPills();
    renderImportWizardRows();
    updateWizardFooter();
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
  async function runDisconnect(btn) {
    const ask = window.homehubDialog?.confirm
      ? window.homehubDialog.confirm.bind(window.homehubDialog)
      : async (msg) => window.confirm(msg);
    const notify = (msg) => {
      if (window.globalToast) window.globalToast(msg, 'error');
      else if (window.homehubDialog?.alert) window.homehubDialog.alert(msg, { title: 'Error' });
      else window.alert(msg);
    };
    if (!(await ask('Disconnect Google Calendar from HomeHub?', { title: 'Disconnect Google Calendar' }))) return;
    const removeEvents = await ask(
      'Delete events that were imported from Google? (Choose Cancel to keep imported events in HomeHub.)',
      { title: 'Remove Imported Events?', okText: 'Delete Imported Events', cancelText: 'Keep Imported Events' }
    );
    if (btn) btn.disabled = true;
    try {
      await window.calendarSyncApi.disconnect(removeEvents);
      await loadManager();
      if (window.homehubCalendarApp && typeof window.homehubCalendarApp.reload === 'function') {
        await window.homehubCalendarApp.reload();
      }
    } catch (e) {
      console.error('disconnect', e);
      notify('Could not disconnect. Try again or contact the operator.');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  if (disconnectBtn) disconnectBtn.addEventListener('click', () => runDisconnect(disconnectBtn));
  if (disconnectConnectedBtn) {
    disconnectConnectedBtn.addEventListener('click', () => runDisconnect(disconnectConnectedBtn));
  }

  if (syncBtn) {
    syncBtn.addEventListener('click', async () => {
      syncBtn.disabled = true;
      await window.calendarSyncApi.syncNow();
      await loadManager();
      if (window.homehubCalendarApp && typeof window.homehubCalendarApp.reload === 'function') {
        await window.homehubCalendarApp.reload();
      } else if (typeof fetchMonth === 'function' && typeof getSelectedDate === 'function') {
        await fetchMonth(getSelectedDate(), true);
        if (typeof updateCalendarBadges === 'function') updateCalendarBadges();
        if (typeof renderList === 'function') renderList();
      }
      syncBtn.disabled = false;
    });
  }
  if (syncModeSelect) {
    syncModeSelect.addEventListener('change', async () => {
      if (syncModeSelect.value === 'bidirectional' && !allowBidirectional) {
        syncModeSelect.value = 'import_only';
        if (window.globalToast) window.globalToast('Bidirectional sync is disabled by operator configuration.', 'error');
        else if (window.homehubDialog?.alert) window.homehubDialog.alert('Bidirectional sync is disabled by operator configuration.', { title: 'Not Allowed' });
        else window.alert('Bidirectional sync is disabled by operator configuration.');
        return;
      }
      await window.calendarSyncApi.syncMode(syncModeSelect.value);
      await loadManager();
    });
  }
  if (wizardCommitBtn) {
    wizardCommitBtn.addEventListener('click', async () => {
      const prevLabel = wizardCommitBtn.innerHTML;
      wizardCommitBtn.disabled = true;
      wizardCommitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs" aria-hidden="true"></i> Importing…';
      const res = await window.calendarSyncApi.importCommit(getWizardSelections());
      wizardCommitBtn.disabled = false;
      wizardCommitBtn.innerHTML = prevLabel;
      if (!res.ok) {
        if (wizardSummary) wizardSummary.textContent = res.error || 'Import failed';
        return;
      }
      if (wizardSummary) wizardSummary.textContent = `Saved ${res.saved || 0} calendar mappings and started import.`;
      wizardModal?.close();
      await loadManager();
      if (window.homehubCalendarApp && typeof window.homehubCalendarApp.reload === 'function') {
        await window.homehubCalendarApp.reload();
      }
    });
  }

  function openImportWizardModal() {
    wizardMapIndex = 0;
    wizardStateBySource.clear();
    setWizardStep(1);
    wizardModal?.classList.add('cal-import-modal--wide');
    try {
      wizardModal?.showModal();
    } catch (_) {
      if (window.globalToast) window.globalToast('Could not open import wizard modal.', 'error');
    }
    // Load async so the modal opens immediately even if API is slow.
    loadImportWizard().catch((e) => {
      if (wizardSourceList) wizardSourceList.innerHTML = '<p class="text-xs text-red-600">Failed to load import options.</p>';
      console.error('loadImportWizard', e);
    });
  }

  wizardOpenBtn?.addEventListener('click', openImportWizardModal);
  // Delegated fallback in case direct binding is lost due dynamic redraw.
  document.addEventListener('click', (e) => {
    const btn = e.target.closest?.('#calendarImportOpen');
    if (!btn) return;
    e.preventDefault();
    openImportWizardModal();
  });
  wizardCloseBtn?.addEventListener('click', () => wizardModal?.close());
  wizardModal?.addEventListener('click', (e) => {
    if (e.target === wizardModal) wizardModal.close();
  });
  document.getElementById('calendarImportSourceToolbar')?.addEventListener('click', (e) => {
    const btn = e.target.closest?.('[data-import-select]');
    if (!btn) return;
    setAllSourceSelection(btn.getAttribute('data-import-select') === 'all');
  });
  wizardBackBtn?.addEventListener('click', () => {
    if (wizardStep === 2 && wizardMapIndex > 0) {
      wizardMapIndex -= 1;
      renderMapSubstepPills();
      renderImportWizardRows();
      updateWizardFooter();
      return;
    }
    setWizardStep(wizardStep - 1);
  });
  wizardNextBtn?.addEventListener('click', () => {
    if (wizardStep === 1) {
      if (!selectedSourceIds.size) {
        if (window.globalToast) window.globalToast('Select at least one source calendar to continue.', 'error');
        return;
      }
      wizardMapIndex = 0;
      setWizardStep(2);
      return;
    }
    const selected = selectedImportOptions();
    if (wizardStep === 2 && wizardMapIndex < selected.length - 1) {
      wizardMapIndex += 1;
      renderMapSubstepPills();
      renderImportWizardRows();
      updateWizardFooter();
    }
  });

  window.homehubCalendarSync = {
    getWriteCalendarId() {
      if (!writeSelect || writeRow.classList.contains('hidden')) return null;
      const v = parseInt(writeSelect.value, 10);
      return Number.isFinite(v) ? v : null;
    },
    setWriteCalendarId(id) {
      populateWriteSelect(id);
    },
    getPersonalCalendarId() {
      if (!personalCalendarSelect) return null;
      const v = parseInt(personalCalendarSelect.value, 10);
      return Number.isFinite(v) ? v : null;
    },
    refresh: loadManager,
  };

  function openSetupTab() {
    try { sessionStorage.setItem('calendar:openSetupTab', '1'); } catch (_) {}
    document.querySelector('.cal-side-tab[data-tab="setup"]')?.click();
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get('connect_calendar') === '1' && banner) {
    banner.classList.remove('hidden');
    openSetupTab();
  }
  if (params.get('calendar_connected') === '1') {
    openSetupTab();
    if (window.globalToast) window.globalToast('Google Calendar connected. Review mappings in Setup.', 'success');
    window.history.replaceState({}, '', window.location.pathname);
  }
  const calErr = params.get('calendar_error');
  if (calErr) {
    const errMsg =
      calErr === 'oauth_insecure_transport'
        ? 'Google OAuth callback blocked on insecure local HTTP transport. This is now auto-enabled for localhost/127.0.0.1/LAN. Retry Connect Google.'
        :
      calErr === 'oauth_failed'
        ? 'Google authorization failed (often OAuth client mismatch/secret). Disconnect if needed, fix Google Cloud + Firebase settings, then connect again.'
        : 'Calendar connection error. Try disconnecting and connecting again.';
    showConnectBanner(errMsg, true);
    openSetupTab();
    window.history.replaceState({}, '', window.location.pathname);
  }

  loadManager().catch((e) => console.error('calendar sync init', e));
})();
