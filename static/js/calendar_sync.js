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
      inferred.forEach((c) => {
        merged.set(c.key, {
          source_key: c.key,
          source_label: c.label || c.key,
          target_label: '',
          target_color: source?.background_color || '#2563eb',
          enabled: false,
        });
      });
      existingMappings.forEach((c) => {
        merged.set(c.source_key, {
          source_key: c.source_key,
          source_label: c.source_label || c.source_key,
          target_label: c.target_label || '',
          target_color: c.target_color || source?.background_color || '#2563eb',
          enabled: true,
        });
      });
      if (!merged.size) {
        merged.set('default', {
          source_key: 'default',
          source_label: 'Default',
          target_label: '',
          target_color: source?.background_color || '#2563eb',
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
    importOptions.forEach((cal) => {
      const row = document.createElement('label');
      row.className = 'flex items-center justify-between gap-3 p-3.5 border border-slate-200 dark:border-slate-700 rounded-xl bg-white dark:bg-slate-800 cursor-pointer hover:border-blue-400 transition-colors';
      row.innerHTML = `
        <span class="flex items-center gap-2 min-w-0">
          <span class="w-3 h-3 rounded-full flex-shrink-0" style="background:${cal.background_color || '#2563eb'}"></span>
          <span class="min-w-0">
            <span class="font-medium text-sm block truncate text-slate-900 dark:text-slate-100">${escapeHtml(cal.summary || '')}</span>
            <span class="text-[11px] text-slate-500 dark:text-slate-400 block">${(cal.source_categories || []).length} Google categories detected</span>
          </span>
        </span>
        <input type="checkbox" class="h-4 w-4" data-source-id="${cal.id}" ${selectedSourceIds.has(cal.id) ? 'checked' : ''}>
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

  function renderMapSubstepPills() {
    if (!wizardSubstepPills) return;
    const selected = selectedImportOptions();
    wizardSubstepPills.innerHTML = '';
    selected.forEach((cal, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      const active = idx === wizardMapIndex;
      btn.className = `px-3 py-1.5 rounded-full text-xs border transition-colors ${active ? 'bg-blue-600 text-white border-blue-600 shadow-sm' : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-700 hover:border-blue-400'}`;
      btn.textContent = `${idx + 1}. ${cal.summary || `Calendar ${cal.id}`}`;
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
        ? `Mapping ${wizardMapIndex + 1} of ${selected.length}`
        : 'No calendars selected';
    }
  }

  function renderImportWizardRows() {
    if (!wizardRows) return;
    wizardRows.innerHTML = '';
    const selected = selectedImportOptions();
    if (!selected.length) {
      wizardRows.innerHTML = '<p class="text-xs text-slate-500 dark:text-slate-400">Select at least one source calendar in step 1.</p>';
      return;
    }
    const cal = selected[Math.max(0, Math.min(wizardMapIndex, selected.length - 1))];
    const state = getWizardState(cal.id);
    const categoryTotal = (state.categories || []).length;
    const categoryMapped = (state.categories || []).filter((c) => c.enabled && (c.target_label || '').trim()).length;
    const row = document.createElement('div');
    row.className = 'border border-slate-200 dark:border-slate-700 rounded-2xl p-4 md:p-5 space-y-4 bg-white dark:bg-slate-800 shadow-sm';
    const datalistId = `calendarImportPersonalSuggestions-${cal.id}`;
    const datalistOptions = personalCalendars
      .map((pc) => `<option value="${escapeHtml(pc.name || `Calendar ${pc.id}`)}"></option>`)
      .join('');
    row.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-base font-semibold leading-tight text-slate-900 dark:text-slate-100">${escapeHtml(cal.summary || '')}</p>
          <p class="text-[11px] text-slate-500 dark:text-slate-400">${categoryTotal} Google categories · ${categoryMapped} mapped for import</p>
          <p class="text-[10px] text-slate-400 dark:text-slate-500 truncate" title="${escapeHtml(cal.google_calendar_id || '')}">${escapeHtml(cal.google_calendar_id || '')}</p>
        </div>
        <label class="text-xs inline-flex items-center gap-2 bg-slate-50 dark:bg-slate-900 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200">
          <input type="checkbox" data-field="import_enabled" ${state.import_enabled ? 'checked' : ''}>
          Import this calendar
        </label>
      </div>
      <div class="grid md:grid-cols-2 gap-3.5">
        <label class="text-xs font-medium text-slate-700 dark:text-slate-200">Destination HomeHub calendar
          <input class="w-full h-10 border border-slate-300 dark:border-slate-700 rounded-lg px-3 mt-1.5 bg-white dark:bg-slate-900" data-field="personal_calendar_name" list="${datalistId}" value="${escapeHtml(state.personal_calendar_name || '')}" placeholder="Type to search or create new">
          <datalist id="${datalistId}">${datalistOptions}</datalist>
          <p class="text-[10px] text-gray-500 dark:text-gray-400 mt-1">Pick existing or type a new name to create it on import.</p>
        </label>
        <label class="text-xs font-medium text-slate-700 dark:text-slate-200">Imported event color
          <input class="w-full h-10 border border-slate-300 dark:border-slate-700 rounded-lg px-2 mt-1.5" type="color" data-field="import_color" value="${state.import_color || '#2563eb'}">
        </label>
      </div>
      <div class="space-y-2.5">
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Category mappings</p>
        <p class="text-[11px] text-slate-500 dark:text-slate-400">Choose which Google categories to map and what HomeHub category each one should become.</p>
        <div class="space-y-2 max-h-72 overflow-auto pr-1" data-category-rows></div>
      </div>
    `;
    const catWrap = row.querySelector('[data-category-rows]');
    (state.categories || []).forEach((cat, idx) => {
      const catRow = document.createElement('div');
      catRow.className = 'grid grid-cols-[auto_1fr_1fr_auto] gap-2.5 items-center border border-slate-200 dark:border-slate-700 rounded-xl p-2.5 bg-slate-50/80 dark:bg-slate-900';
      catRow.innerHTML = `
        <input type="checkbox" class="h-4 w-4" data-cat-field="enabled" ${cat.enabled ? 'checked' : ''}>
        <div class="text-xs">
          <p class="font-medium text-slate-900 dark:text-slate-100">${escapeHtml(cat.source_label || cat.source_key)}</p>
          <p class="text-[10px] text-slate-500 dark:text-slate-400">${escapeHtml(cat.source_key)}</p>
        </div>
        <input class="h-8.5 border border-slate-300 dark:border-slate-700 rounded-lg px-2 text-xs bg-white dark:bg-slate-800" data-cat-field="target_label" placeholder="HomeHub category" value="${escapeHtml(cat.target_label || '')}">
        <input class="h-8.5 w-11 border border-slate-300 dark:border-slate-700 rounded-lg p-0" type="color" data-cat-field="target_color" value="${cat.target_color || '#2563eb'}">
      `;
      const enabledEl = catRow.querySelector('[data-cat-field="enabled"]');
      const labelEl = catRow.querySelector('[data-cat-field="target_label"]');
      const colorEl = catRow.querySelector('[data-cat-field="target_color"]');
      enabledEl?.addEventListener('change', (e) => {
        state.categories[idx].enabled = !!e.target.checked;
        renderImportWizardRows();
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
    const onLast = wizardStep === 2 && wizardMapIndex >= selected.length - 1;
    if (!onLast || !selected.length) {
      wizardPreviewSummary.classList.add('hidden');
      return;
    }
    const selections = getWizardSelections();
    const selectedCount = selections.filter((s) => s.import_enabled).length;
    const categoryCount = selections.reduce((sum, s) => sum + ((s.categories || []).length), 0);
    wizardPreviewSummary.textContent = `Ready to import ${selectedCount} calendar(s) with ${categoryCount} category mapping(s).`;
    wizardPreviewSummary.classList.remove('hidden');
  }

  function updateWizardFooter() {
    const selected = selectedImportOptions();
    const onStep2 = wizardStep === 2;
    const lastCal = onStep2 && selected.length > 0 && wizardMapIndex >= selected.length - 1;

    if (wizardBackBtn) {
      wizardBackBtn.classList.toggle('invisible', wizardStep === 1);
      wizardBackBtn.textContent = onStep2 && wizardMapIndex > 0 ? 'Previous calendar' : 'Back';
    }
    if (wizardNextBtn) {
      const showNext = wizardStep === 1 || (onStep2 && !lastCal);
      wizardNextBtn.classList.toggle('hidden', !showNext);
      wizardNextBtn.textContent = wizardStep === 1 ? 'Next' : 'Next calendar';
    }
    if (wizardCommitBtn) {
      wizardCommitBtn.classList.toggle('hidden', !(onStep2 && lastCal && selected.length));
    }
    updatePreviewSummary();
  }

  function setWizardStep(step) {
    wizardStep = Math.min(2, Math.max(1, step));
    if (wizardStepLabel) wizardStepLabel.textContent = `Step ${wizardStep} of 2`;
    [1, 2].forEach((n) => {
      const pill = document.querySelector(`[data-step-pill="${n}"]`);
      if (!pill) return;
      pill.classList.toggle('bg-blue-600', n === wizardStep);
      pill.classList.toggle('text-white', n === wizardStep);
      pill.classList.toggle('border', n !== wizardStep);
    });
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
      wizardCommitBtn.disabled = true;
      const res = await window.calendarSyncApi.importCommit(getWizardSelections());
      wizardCommitBtn.disabled = false;
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
    setWizardStep(1);
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
