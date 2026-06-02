/**
 * Full calendar: month / week time-grid / agenda, lanes, drag-reschedule, recurring, colors.
 */
(function () {
  function uiError(msg) {
    if (window.globalToast) window.globalToast(msg, 'error');
    else if (window.homehubDialog?.alert) window.homehubDialog.alert(msg, { title: 'Error' });
    else window.alert(msg);
  }

  async function uiConfirm(msg, opts) {
    if (window.homehubDialog?.confirm) return window.homehubDialog.confirm(msg, opts || {});
    return window.confirm(msg);
  }
  const START_DAY = (window.REMINDERS_CAL_START || 'sunday').toLowerCase();
  const TIME_FMT = window.REMINDERS_TIME_FORMAT || '12h';
  const HOUR_PX = 48;
  const HOURS = 24;
  const LOCAL_LANE_KEY = '__local__';
  const HOUSEHOLD_TZ = window.HOUSEHOLD_TZ || 'UTC';

  let categories = [];
  try {
    const el = document.getElementById('reminderCategoriesData');
    if (el) categories = JSON.parse(el.textContent || '[]');
  } catch (_) {
    categories = [];
  }
  let catMap = {};
  categories.forEach((c) => {
    catMap[c.key] = c;
  });

  function applyCategories(cats) {
    categories = cats || [];
    catMap = {};
    categories.forEach((c) => {
      catMap[c.key] = c;
    });
    if (window.homehubReminderCategories) {
      window.homehubReminderCategories.applyStyles(categories);
      const sel = $('calCategorySelect');
      const current = form?.querySelector('[name=category]')?.value || '';
      window.homehubReminderCategories.populateSelect(sel, categories, current || null);
    }
    renderFilters();
  }

  async function loadCategories() {
    if (window.homehubReminderCategories) {
      try {
        const res = await window.homehubReminderCategories.fetchList();
        if (res.ok) {
          applyCategories(res.categories);
          return;
        }
      } catch (e) {
        console.warn('load categories', e);
      }
    }
    applyCategories(categories);
  }

  let view = 'month';
  let anchor = new Date();
  anchor.setHours(0, 0, 0, 0);
  let selectedYmd = fmtYmd(anchor);
  let events = [];
  let recurringRules = [];
  let linkedCalendars = [];
  const hiddenCats = new Set();
  const hiddenCals = new Set();
  let editingId = null;
  let editingRuleId = null;
  let dragEventId = null;
  let eventColorPicker = null;
  let pendingMove = null;
  let resizeState = null;

  const $ = (id) => document.getElementById(id);
  const scopeModal = $('calRecurringScopeModal');
  const conflictPanel = $('calConflictPanel');
  const monthView = $('calMonthView');
  const weekView = $('calWeekView');
  const agendaView = $('calAgendaView');
  const monthGrid = $('calMonthGrid');
  const weekTimeGrid = $('calWeekTimeGrid');
  const weekdayRow = $('calWeekdayRow');
  const periodLabel = $('calPeriodLabel');
  const filterBar = $('calFilterBar');
  const form = $('calEventForm');
  const dayList = $('calDayList');
  const selectedLabel = $('calSelectedLabel');
  const recurrenceBox = $('calRecurrenceControls');
  const recurChk = $('calIsRecurring');

  function fmtYmd(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function parseYmd(s) {
    const [y, m, d] = String(s).split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  function weekStart(d) {
    const x = new Date(d);
    const dow = x.getDay();
    const offset = START_DAY === 'monday' ? (dow + 6) % 7 : dow;
    x.setDate(x.getDate() - offset);
    return x;
  }

  function addDays(d, n) {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
  }

  function fmtTime(t) {
    if (!t) return '';
    const [h, m] = t.split(':').map(Number);
    if (TIME_FMT === '24h') return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    const ap = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${h12}:${String(m).padStart(2, '0')} ${ap}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function normHex(v) {
    return window.homehubColorPicker ? window.homehubColorPicker.normalizeHex(v) : null;
  }

  function eventColor(ev) {
    const custom = normHex(ev.color);
    if (custom) return custom;
    const cal = normHex(ev.calendar_color);
    if (cal) return cal;
    const cat = ev.category && catMap[ev.category];
    if (cat && cat.color) return normHex(cat.color) || cat.color;
    return '#2563eb';
  }

  function eventTextColor(ev) {
    return window.homehubColorPicker
      ? window.homehubColorPicker.textColorForBg(eventColor(ev))
      : '#ffffff';
  }

  function laneKey(ev) {
    return ev.linked_calendar_id ? String(ev.linked_calendar_id) : LOCAL_LANE_KEY;
  }

  function passesFilters(e) {
    if (e.category && hiddenCats.has(e.category)) return false;
    if (hiddenCals.has(laneKey(e))) return false;
    return true;
  }

  function filteredEvents() {
    return events.filter(passesFilters);
  }

  function eventsOn(ymd) {
    return filteredEvents().filter((e) => {
      const end = e.end_date || e.date;
      return ymd >= e.date && ymd <= end;
    });
  }

  function minutesFromTime(t) {
    if (!t) return 0;
    const [h, m] = t.split(':').map(Number);
    return h * 60 + m;
  }

  function durationMinutes(ev) {
    if (ev.all_day) return HOURS * 60;
    const start = minutesFromTime(ev.time);
    if (ev.end_time && (!ev.end_date || ev.end_date === ev.date)) {
      const end = minutesFromTime(ev.end_time);
      return Math.max(30, end - start);
    }
    return 60;
  }

  function monthRange() {
    const y = anchor.getFullYear();
    const m = anchor.getMonth();
    const start = new Date(y, m, 1);
    const end = new Date(y, m + 1, 0);
    const gridStart = weekStart(start);
    const gridEnd = addDays(weekStart(end), 6);
    return { start, end, gridStart, gridEnd };
  }

  function weekRange() {
    const ws = weekStart(anchor);
    return { start: ws, end: addDays(ws, 6) };
  }

  async function loadLinkedCalendars() {
    linkedCalendars = [];
    if (!window.calendarSyncApi) return;
    try {
      const data = await window.calendarSyncApi.calendars();
      if (data.ok) {
        linkedCalendars = [...(data.own || []), ...(data.visible || [])].filter(
          (c) => c.sync_enabled !== false
        );
        const syncedIds = new Set(linkedCalendars.map((c) => String(c.id)));
        for (const key of hiddenCals) {
          if (key !== LOCAL_LANE_KEY && !syncedIds.has(key)) hiddenCals.delete(key);
        }
      }
    } catch (e) {
      console.warn('calendar lanes', e);
    }
  }

  async function loadEvents() {
    let scope = 'month';
    let dateStr = fmtYmd(anchor);
    if (view === 'week') {
      scope = 'week';
      dateStr = fmtYmd(weekStart(anchor));
    }
    const res = await window.remindersApi.list(scope, dateStr);
    events = (res && res.reminders) || [];
    recurringRules = (res && res.recurring_rules) || [];
    render();
  }

  function parseAttendeesText(raw) {
    if (!raw || !String(raw).trim()) return [];
    return String(raw)
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((email) => ({ email }));
  }

  function formatAttendeesField(list) {
    if (!list || !list.length) return '';
    return list
      .map((a) => (typeof a === 'string' ? a : a.email || ''))
      .filter(Boolean)
      .join(', ');
  }

  function eventTzLabel(ev) {
    const tz = ev.time_zone || HOUSEHOLD_TZ;
    if (!tz || tz === HOUSEHOLD_TZ) return '';
    return ` (${tz})`;
  }

  function showRecurringScopeModal(onPick) {
    if (!scopeModal) {
      onPick('this');
      return;
    }
    scopeModal.showModal();
    const finish = (scope) => {
      scopeModal.close();
      cleanup();
      onPick(scope);
    };
    const cleanup = () => {
      $('calScopeThis')?.removeEventListener('click', onThis);
      $('calScopeSeries')?.removeEventListener('click', onSeries);
      $('calScopeCancel')?.removeEventListener('click', onCancel);
    };
    const onThis = () => finish('this');
    const onSeries = () => finish('series');
    const onCancel = () => finish(null);
    $('calScopeThis')?.addEventListener('click', onThis);
    $('calScopeSeries')?.addEventListener('click', onSeries);
    $('calScopeCancel')?.addEventListener('click', onCancel);
  }

  async function applyMove(ev, patch, scope) {
    const creator = localStorage.getItem('username') || '';
    if (ev.id < 0 && ev.recurring_id) {
      const res = await window.remindersApi.patchOccurrence(ev.recurring_id, {
        occurrence_date: ev.date,
        scope: scope || 'this',
        patch,
        creator,
      });
      if (!res.ok) {
        uiError(res.error || 'Could not move occurrence');
        return false;
      }
      await loadEvents();
      return true;
    }
    const payload = { ...patch, creator, occurrence_scope: scope || undefined };
    const res = await window.remindersApi.update(ev.id, payload);
    if (!res.ok) {
      uiError(res.error || 'Could not move event');
      return false;
    }
    await loadEvents();
    return true;
  }

  async function rescheduleEvent(ev, patch) {
    if (ev.recurring_id) {
      return new Promise((resolve) => {
        showRecurringScopeModal(async (scope) => {
          if (!scope) {
            resolve(false);
            return;
          }
          resolve(await applyMove(ev, patch, scope));
        });
      });
    }
    const creator = localStorage.getItem('username') || '';
    const res = await window.remindersApi.update(ev.id, { ...patch, creator });
    if (!res.ok) {
      uiError(res.error || 'Could not move event');
      return false;
    }
    await loadEvents();
    return true;
  }

  function bindDragChip(chip, ev) {
    if (ev.can_edit === false) {
      chip.draggable = false;
      return;
    }
    if (!ev.id) {
      chip.draggable = false;
      return;
    }
    chip.draggable = true;
    chip.addEventListener('dragstart', (e) => {
      dragEventId = ev.id;
      pendingMove = { ev };
      e.dataTransfer.setData('text/plain', String(ev.id));
      e.dataTransfer.effectAllowed = 'move';
    });
    chip.addEventListener('dragend', () => {
      dragEventId = null;
      document.querySelectorAll('.cal-drop-target').forEach((n) => n.classList.remove('cal-drop-target'));
    });
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      openForm('edit', ev);
    });
  }

  function bindDropTarget(el, onDrop) {
    el.addEventListener('dragover', (e) => {
      if (!dragEventId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      el.classList.add('cal-drop-target');
    });
    el.addEventListener('dragleave', () => el.classList.remove('cal-drop-target'));
    el.addEventListener('drop', async (e) => {
      e.preventDefault();
      el.classList.remove('cal-drop-target');
      const id = dragEventId || parseInt(e.dataTransfer.getData('text/plain'), 10);
      dragEventId = null;
      if (!id) return;
      await onDrop(id);
    });
  }

  function renderWeekdayHeaders() {
    if (!weekdayRow) return;
    const labels =
      START_DAY === 'monday'
        ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    weekdayRow.innerHTML = labels.map((l) => `<div class="text-center py-1">${l}</div>`).join('');
  }

  function renderFilters() {
    if (!filterBar) return;
    const parts = [];
    const hasLocal = events.some((e) => !e.linked_calendar_id);
    if (hasLocal) {
      const off = hiddenCals.has(LOCAL_LANE_KEY);
      parts.push(
        `<button type="button" class="cal-lane-filter px-2 py-0.5 rounded border ${off ? 'opacity-40' : ''}" data-lane="${LOCAL_LANE_KEY}"><span class="inline-block w-2 h-2 rounded-full mr-1 bg-gray-500"></span>Local</button>`
      );
    }
    linkedCalendars.forEach((c) => {
      const key = String(c.id);
      const off = hiddenCals.has(key);
      const bg = normHex(c.background_color) || '#2563eb';
      parts.push(
        `<button type="button" class="cal-lane-filter px-2 py-0.5 rounded border ${off ? 'opacity-40' : ''}" data-lane="${key}" style="border-color:${bg}"><span class="inline-block w-2 h-2 rounded-full mr-1" style="background:${bg}"></span>${escapeHtml(c.summary || 'Calendar')}</button>`
      );
    });
    if (categories.length) {
      parts.push('<span class="text-gray-400 px-1">|</span>');
      categories.forEach((c) => {
        const off = hiddenCats.has(c.key);
        const bg = c.color || '#6b7280';
        parts.push(
          `<button type="button" class="cal-cat-filter px-2 py-0.5 rounded border ${off ? 'opacity-40' : ''}" data-cat="${escapeHtml(c.key)}" style="border-color:${bg}"><span class="inline-block w-2 h-2 rounded-full mr-1" style="background:${bg}"></span>${escapeHtml(c.label || c.key)}</button>`
        );
      });
    }
    filterBar.innerHTML = parts.join('') || '<span class="text-gray-500 text-xs">No filters</span>';
    filterBar.querySelectorAll('.cal-cat-filter').forEach((btn) => {
      btn.addEventListener('click', () => {
        const k = btn.getAttribute('data-cat');
        if (hiddenCats.has(k)) hiddenCats.delete(k);
        else hiddenCats.add(k);
        render();
      });
    });
    filterBar.querySelectorAll('.cal-lane-filter').forEach((btn) => {
      btn.addEventListener('click', () => {
        const k = btn.getAttribute('data-lane');
        if (hiddenCals.has(k)) hiddenCals.delete(k);
        else hiddenCals.add(k);
        render();
      });
    });
  }

  function renderPeriodLabel() {
    if (!periodLabel) return;
    if (view === 'month') {
      periodLabel.textContent = anchor.toLocaleString(undefined, { month: 'long', year: 'numeric' });
    } else if (view === 'week') {
      const { start, end } = weekRange();
      periodLabel.textContent = `${start.toLocaleDateString()} – ${end.toLocaleDateString()}`;
    } else {
      periodLabel.textContent = 'Upcoming';
    }
  }

  function chipHtml(e, extraClass) {
    const col = eventColor(e);
    const tc = eventTextColor(e);
    const conflict = e.sync_status === 'conflict' ? ' ring-2 ring-amber-400' : '';
    const importedBadge = e.source === 'google' ? ' <span class="text-[9px] opacity-90">(imported)</span>' : '';
    return `<div class="cal-event-chip ${extraClass || ''}${conflict}" data-ev-id="${e.id}" style="background:${col};color:${tc}" title="${escapeHtml(e.title)}">${escapeHtml(e.title)}${importedBadge}</div>`;
  }

  function renderMonth() {
    if (!monthGrid) return;
    const { start, gridStart, gridEnd } = monthRange();
    const cells = [];
    let d = new Date(gridStart);
    const today = fmtYmd(new Date());
    while (d <= gridEnd) {
      const ymd = fmtYmd(d);
      const inMonth = d.getMonth() === start.getMonth();
      const evs = eventsOn(ymd).slice(0, 5);
      const more = eventsOn(ymd).length - evs.length;
      const sel = ymd === selectedYmd;
      cells.push(`
        <div data-ymd="${ymd}" class="cal-day-cell text-left min-h-[80px] p-1 rounded border text-xs ${inMonth ? 'bg-white dark:bg-slate-800' : 'bg-gray-50 dark:bg-slate-900 opacity-60'} ${sel ? 'ring-2 ring-blue-500' : ''}">
          <button type="button" class="font-semibold w-full text-left ${ymd === today ? 'text-blue-600' : ''}" data-select-day="${ymd}">${d.getDate()}</button>
          <div class="space-y-0.5">${evs.map((e) => chipHtml(e)).join('')}</div>
          ${more > 0 ? `<div class="text-[10px] text-gray-500">+${more} more</div>` : ''}
        </div>`);
      d = addDays(d, 1);
    }
    monthGrid.innerHTML = cells.join('');
    monthGrid.querySelectorAll('.cal-day-cell').forEach((cell) => {
      const ymd = cell.getAttribute('data-ymd');
      cell.querySelector('[data-select-day]')?.addEventListener('click', () => selectDay(ymd));
      cell.querySelectorAll('.cal-event-chip').forEach((chip) => {
        const id = parseInt(chip.getAttribute('data-ev-id'), 10);
        const ev = events.find((x) => x.id === id);
        if (ev) bindDragChip(chip, ev);
      });
      bindDropTarget(cell, async () => {
        const ev = pendingMove?.ev || events.find((x) => x.id === dragEventId);
        if (!ev || ev.date === ymd) return;
        await rescheduleEvent(ev, { date: ymd });
        pendingMove = null;
      });
    });
  }

  function renderWeekTimeGrid() {
    if (!weekTimeGrid) return;
    const { start } = weekRange();
    const days = [];
    for (let i = 0; i < 7; i++) days.push(addDays(start, i));

    let html = '<div class="cal-week-time-grid text-xs">';
    html += '<div></div>';
    days.forEach((d) => {
      const ymd = fmtYmd(d);
      html += `<div class="text-center font-semibold py-1 border-b"><button type="button" data-select-day="${ymd}" class="hover:underline">${d.toLocaleDateString(undefined, { weekday: 'short', month: 'numeric', day: 'numeric' })}</button></div>`;
    });
    html += '</div>';

    html += '<div class="cal-week-allday"><div class="text-[10px] text-gray-500 pr-1 text-right">All day</div>';
    days.forEach((d) => {
      const ymd = fmtYmd(d);
      const allDay = eventsOn(ymd).filter((e) => e.all_day || !e.time);
      html += `<div class="p-1 border-l space-y-0.5 min-h-[2rem]" data-allday-col="${ymd}">${allDay.map((e) => chipHtml(e)).join('')}</div>`;
    });
    html += '</div>';

    html += '<div class="cal-week-time-grid" style="grid-template-rows: auto;">';
    html += '<div class="relative" style="height:' + HOURS * HOUR_PX + 'px">';
    for (let h = 0; h < HOURS; h++) {
      html += `<div class="cal-week-hour-label" style="position:absolute;top:${h * HOUR_PX}px;width:100%">${h === 0 ? '12a' : h < 12 ? h + 'a' : h === 12 ? '12p' : h - 12 + 'p'}</div>`;
    }
    html += '</div>';

    days.forEach((d) => {
      const ymd = fmtYmd(d);
      html += `<div class="cal-week-day-col" data-week-col="${ymd}" style="height:${HOURS * HOUR_PX}px">`;
      for (let h = 0; h < HOURS; h++) {
        html += `<div class="cal-week-slot-drop" data-drop-ymd="${ymd}" data-drop-hour="${h}" style="top:${h * HOUR_PX}px;height:${HOUR_PX}px"></div>`;
        html += `<div class="cal-week-hour-line" style="top:${h * HOUR_PX}px"></div>`;
      }
      const timed = eventsOn(ymd).filter((e) => !e.all_day && e.time);
      timed.forEach((e) => {
        const top = (minutesFromTime(e.time) / 60) * HOUR_PX;
        const hpx = Math.max(22, (durationMinutes(e) / 60) * HOUR_PX - 2);
        const col = eventColor(e);
        const tc = eventTextColor(e);
        const conflict = e.sync_status === 'conflict' ? ' conflict' : '';
        html += `<div class="cal-week-event${conflict}" data-ev-id="${e.id}" style="top:${top}px;height:${hpx}px;background:${col};color:${tc}">${escapeHtml(fmtTime(e.time))}${escapeHtml(eventTzLabel(e))} ${escapeHtml(e.title)}<span class="cal-resize-handle" data-resize="${e.id}"></span></div>`;
      });
      html += '</div>';
    });
    html += '</div>';

    weekTimeGrid.innerHTML = html;

    weekTimeGrid.querySelectorAll('[data-select-day]').forEach((b) => {
      b.addEventListener('click', () => selectDay(b.getAttribute('data-select-day')));
    });

    weekTimeGrid.querySelectorAll('.cal-event-chip, .cal-week-event').forEach((chip) => {
      const id = parseInt(chip.getAttribute('data-ev-id'), 10);
      const ev = events.find((x) => x.id === id);
      if (ev) bindDragChip(chip, ev);
    });

    weekTimeGrid.querySelectorAll('.cal-resize-handle').forEach((handle) => {
      handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const id = parseInt(handle.getAttribute('data-resize'), 10);
        const ev = events.find((x) => x.id === id);
        if (!ev || ev.all_day || !ev.time) return;
        const block = handle.closest('.cal-week-event');
        resizeState = {
          ev,
          block,
          startY: e.clientY,
          startMin: minutesFromTime(ev.time),
          startHeight: block.offsetHeight,
        };
        document.body.style.cursor = 'ns-resize';
      });
    });

    weekTimeGrid.querySelectorAll('[data-allday-col]').forEach((col) => {
      bindDropTarget(col, async () => {
        const ev = pendingMove?.ev || events.find((x) => x.id === dragEventId);
        if (!ev) return;
        const ymd = col.getAttribute('data-allday-col');
        await rescheduleEvent(ev, { date: ymd, all_day: true, time: null, end_time: null });
        pendingMove = null;
      });
    });

    weekTimeGrid.querySelectorAll('.cal-week-slot-drop').forEach((slot) => {
      bindDropTarget(slot, async () => {
        const ev = pendingMove?.ev || events.find((x) => x.id === dragEventId);
        if (!ev) return;
        const ymd = slot.getAttribute('data-drop-ymd');
        const hour = parseInt(slot.getAttribute('data-drop-hour'), 10);
        const time = `${String(hour).padStart(2, '0')}:00`;
        await rescheduleEvent(ev, { date: ymd, all_day: false, time });
        pendingMove = null;
      });
    });
  }

  function renderAgenda() {
    if (!agendaView) return;
    const list = filteredEvents()
      .slice()
      .sort((a, b) => (a.date + (a.time || '')).localeCompare(b.date + (b.time || '')));
    if (!list.length) {
      agendaView.innerHTML = '<p class="text-sm text-gray-500">No events in this range.</p>';
      return;
    }
    let lastDate = '';
    let html = '';
    list.forEach((e) => {
      if (e.date !== lastDate) {
        lastDate = e.date;
        html += `<div class="text-xs font-bold text-gray-600 mt-2">${parseYmd(e.date).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</div>`;
      }
      const range =
        e.end_date && e.end_date !== e.date
          ? `${e.date} → ${e.end_date}`
          : e.all_day
            ? 'All day'
            : e.time
              ? fmtTime(e.time) + (e.end_time ? ' – ' + fmtTime(e.end_time) : '')
              : '';
      const col = eventColor(e);
      html += `<button type="button" class="w-full text-left flex gap-2 items-start p-2 rounded border hover:bg-gray-50 dark:hover:bg-slate-800" data-edit="${e.id}">
        <span class="w-2 h-2 rounded-full mt-1 flex-shrink-0" style="background:${col}"></span>
        <span><span class="font-semibold text-sm">${escapeHtml(e.title)}</span>${e.source === 'google' ? ' <span class="text-[10px] text-blue-600">imported</span>' : ''}${e.sync_status === 'conflict' ? ' <span class="text-amber-600 text-[10px]">sync conflict</span>' : ''}<br><span class="text-xs text-gray-500">${escapeHtml(range)}</span></span>
      </button>`;
    });
    agendaView.innerHTML = html;
    agendaView.querySelectorAll('[data-edit]').forEach((b) => {
      b.addEventListener('click', () => {
        const id = parseInt(b.getAttribute('data-edit'), 10);
        const item = events.find((x) => x.id === id);
        if (item) openForm('edit', item);
      });
    });
  }

  function renderDayList() {
    if (!dayList) return;
    const evs = eventsOn(selectedYmd);
    if (!evs.length) {
      dayList.innerHTML = '<p class="text-xs text-gray-500">No events this day.</p>';
      return;
    }
    dayList.innerHTML = evs
      .map((e) => {
        const meta = e.all_day ? 'All day' : e.time ? fmtTime(e.time) : 'No time';
        const col = eventColor(e);
        return `<div class="flex items-center justify-between gap-2 p-2 rounded border text-xs">
          <button type="button" class="text-left flex-1 flex gap-2 items-start" data-edit="${e.id}">
            <span class="w-2 h-2 rounded-full mt-1 flex-shrink-0" style="background:${col}"></span>
            <span><strong>${escapeHtml(e.title)}</strong>${e.source === 'google' ? ' <span class="text-[10px] text-blue-600">imported</span>' : ''}<br><span class="text-gray-500">${escapeHtml(meta)}</span></span>
          </button>
          <button type="button" class="text-red-600" data-del="${e.id}" title="Delete">✕</button>
        </div>`;
      })
      .join('');
    dayList.querySelectorAll('[data-edit]').forEach((b) => {
      b.addEventListener('click', () => {
        const id = parseInt(b.getAttribute('data-edit'), 10);
        const item = events.find((x) => x.id === id);
        if (item) openForm('edit', item);
      });
    });
    dayList.querySelectorAll('[data-del]').forEach((b) => {
      b.addEventListener('click', async () => {
        const id = parseInt(b.getAttribute('data-del'), 10);
        if (!id || id < 0 || !(await uiConfirm('Delete this event?', { title: 'Delete Event', okText: 'Delete', cancelText: 'Cancel' }))) return;
        await window.remindersApi.removeMany([id], localStorage.getItem('username') || '');
        await loadEvents();
      });
    });
  }

  function setView(v) {
    view = v;
    document.querySelectorAll('.cal-view-btn').forEach((btn) => {
      const on = btn.getAttribute('data-view') === v;
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (monthView) monthView.classList.toggle('hidden', v !== 'month');
    if (weekView) weekView.classList.toggle('hidden', v !== 'week');
    if (agendaView) agendaView.classList.toggle('hidden', v !== 'agenda');
    loadEvents();
  }

  function render() {
    renderPeriodLabel();
    renderFilters();
    if (view === 'month') renderMonth();
    else if (view === 'week') renderWeekTimeGrid();
    else renderAgenda();
    renderDayList();
  }

  function selectDay(ymd) {
    selectedYmd = ymd;
    if (selectedLabel) selectedLabel.textContent = `Selected: ${parseYmd(ymd).toLocaleDateString()}`;
    renderDayList();
    if (view === 'month') renderMonth();
  }

  function toggleTimedFields(allDay) {
    document.querySelectorAll('.cal-timed-only').forEach((el) => {
      el.classList.toggle('hidden', !!allDay);
    });
  }

  function toggleRecurrence(show) {
    if (recurrenceBox) recurrenceBox.classList.toggle('hidden', !show);
    if (show && editingId) {
      recurChk.checked = false;
      recurrenceBox.classList.add('hidden');
    }
    if (show && form && window.homehubRecurrence) {
      window.homehubRecurrence.bind(form);
    }
  }

  function openForm(mode, data) {
    if (!form) return;
    form.classList.remove('hidden');
    form.reset();
    editingId = null;
    editingRuleId = null;
    conflictPanel?.classList.add('hidden');
    form.querySelector('[name=id]').value = '';
    const dateInput = form.querySelector('[name=date]');
    const tzSel = $('calTimeZoneSelect');
    const attInput = $('calAttendeesInput');
    if (form && window.homehubRecurrence) window.homehubRecurrence.bind(form);
    if (mode === 'edit' && data) {
      if (data.isRule && data.id) {
        editingRuleId = data.id;
        form.querySelector('[name=title]').value = data.title || '';
        form.querySelector('[name=description]').value = data.description || '';
        recurChk.checked = true;
        toggleRecurrence(true);
        form.querySelector('[name=rec_interval]').value = data.interval || 1;
        form.querySelector('[name=rec_unit]').value = data.unit || 'week';
        if (window.homehubRecurrence) {
          window.homehubRecurrence.applyRuleEndDate(form, data.end_date || null);
        } else if (data.end_date) {
          form.querySelector('[name=rec_end_date]').value = data.end_date;
        }
        if (data.time) form.querySelector('[name=time]').value = data.time;
        if (data.category) form.querySelector('[name=category]').value = data.category;
        if (eventColorPicker) eventColorPicker.setValue(data.color || null);
        return;
      }
      editingId = data.id > 0 ? data.id : null;
      if (!editingId) return;
      form.querySelector('[name=id]').value = data.id;
      form.querySelector('[name=title]').value = data.title || '';
      form.querySelector('[name=description]').value = data.description || '';
      dateInput.value = data.date || selectedYmd;
      if (data.time) form.querySelector('[name=time]').value = data.time;
      if (data.end_date) form.querySelector('[name=end_date]').value = data.end_date;
      if (data.end_time) form.querySelector('[name=end_time]').value = data.end_time;
      const ad = form.querySelector('[name=all_day]');
      if (ad) ad.checked = !!data.all_day;
      if (data.category && form.querySelector('[name=category]')) {
        form.querySelector('[name=category]').value = data.category;
      }
      if (eventColorPicker) eventColorPicker.setValue(data.color || eventColor(data));
      if (data.linked_calendar_id && window.homehubCalendarSync) {
        window.homehubCalendarSync.setWriteCalendarId(data.linked_calendar_id);
      }
      if (tzSel) tzSel.value = data.time_zone || '';
      if (attInput) attInput.value = formatAttendeesField(data.attendees);
      if (data.sync_status === 'conflict' && conflictPanel) {
        conflictPanel.classList.remove('hidden');
        conflictPanel.dataset.conflictId = String(data.id);
      }
    } else {
      dateInput.value = selectedYmd;
      if (eventColorPicker) {
        const catSel = form.querySelector('[name=category]');
        const opt = catSel && catSel.selectedOptions[0];
        const dc = opt && opt.getAttribute('data-color');
        eventColorPicker.setValue(dc || '#2563eb');
      }
    }
    const allDay = form.querySelector('[name=all_day]').checked;
    toggleTimedFields(allDay);
    toggleRecurrence(recurChk && recurChk.checked);
  }

  function hideForm() {
    if (form) {
      form.classList.add('hidden');
    }
    conflictPanel?.classList.add('hidden');
    editingId = null;
    editingRuleId = null;
  }

  document.querySelectorAll('.cal-view-btn').forEach((btn) => {
    btn.addEventListener('click', () => setView(btn.getAttribute('data-view')));
  });

  $('calPrev')?.addEventListener('click', () => {
    if (view === 'month') anchor.setMonth(anchor.getMonth() - 1);
    else if (view === 'week') anchor = addDays(anchor, -7);
    else anchor = addDays(anchor, -14);
    loadEvents();
  });
  $('calNext')?.addEventListener('click', () => {
    if (view === 'month') anchor.setMonth(anchor.getMonth() + 1);
    else if (view === 'week') anchor = addDays(anchor, 7);
    else anchor = addDays(anchor, 14);
    loadEvents();
  });
  $('calToday')?.addEventListener('click', () => {
    anchor = new Date();
    anchor.setHours(0, 0, 0, 0);
    selectedYmd = fmtYmd(anchor);
    loadEvents();
  });

  $('calAddEvent')?.addEventListener('click', () => openForm('add'));
  $('calFormCancel')?.addEventListener('click', hideForm);

  form?.querySelector('[name=all_day]')?.addEventListener('change', (e) => {
    toggleTimedFields(e.target.checked);
  });

  recurChk?.addEventListener('change', (e) => toggleRecurrence(e.target.checked));

  const catSel = $('calCategorySelect');
  catSel?.addEventListener('change', () => {
    if (!eventColorPicker) return;
    const opt = catSel.selectedOptions[0];
    const dc = opt && opt.getAttribute('data-color');
    if (dc) eventColorPicker.setValue(dc);
  });

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const allDay = !!fd.get('all_day');
    const colorVal = eventColorPicker ? eventColorPicker.getValue() : null;
    const creator = localStorage.getItem('username') || '';

    if (recurChk && recurChk.checked && !editingId) {
      let interval = parseInt(fd.get('rec_interval'), 10);
      if (!Number.isFinite(interval) || interval < 1) interval = 1;
      const payload = {
        title: fd.get('title'),
        description: fd.get('description') || '',
        date: fd.get('date'),
        time: allDay ? undefined : fd.get('time') || undefined,
        creator,
        category: fd.get('category') || undefined,
        color: colorVal || undefined,
        time_zone: fd.get('time_zone') || undefined,
        attendees: parseAttendeesText(fd.get('attendees')),
        recurring: {
          interval,
          unit: fd.get('rec_unit') || 'week',
          end_date: window.homehubRecurrence
            ? window.homehubRecurrence.endDateForPayload(form)
            : (fd.get('rec_end_date') || null),
        },
      };
      if (window.homehubCalendarSync) {
        const wcid = window.homehubCalendarSync.getWriteCalendarId();
        if (wcid) payload.linked_calendar_id = wcid;
        const pcid = window.homehubCalendarSync.getPersonalCalendarId
          ? window.homehubCalendarSync.getPersonalCalendarId()
          : null;
        if (pcid) payload.personal_calendar_id = pcid;
      }
      const res = await window.remindersApi.create(payload);
      if (!res.ok) {
        uiError(res.error || 'Save failed');
        return;
      }
      hideForm();
      await loadEvents();
      return;
    }

    if (editingRuleId) {
      let interval = parseInt(fd.get('rec_interval'), 10);
      if (!Number.isFinite(interval) || interval < 1) interval = 1;
      const res = await window.remindersApi.updateRule(editingRuleId, {
        creator,
        title: fd.get('title'),
        description: fd.get('description') || '',
        time: fd.get('time') || undefined,
        category: fd.get('category') || undefined,
        color: colorVal || undefined,
        interval,
        unit: fd.get('rec_unit') || 'week',
        end_date: window.homehubRecurrence
          ? window.homehubRecurrence.endDateForPayload(form)
          : (fd.get('rec_end_date') || null),
      });
      if (!res.ok) {
        uiError(res.error || 'Save failed');
        return;
      }
      hideForm();
      await loadEvents();
      return;
    }

    const payload = {
      title: fd.get('title'),
      description: fd.get('description') || '',
      date: fd.get('date'),
      all_day: allDay,
      category: fd.get('category') || undefined,
      color: colorVal || undefined,
      time_zone: fd.get('time_zone') || undefined,
      attendees: parseAttendeesText(fd.get('attendees')),
    };
    if (!allDay) {
      if (fd.get('time')) payload.time = fd.get('time');
      if (fd.get('end_date')) payload.end_date = fd.get('end_date');
      if (fd.get('end_time')) payload.end_time = fd.get('end_time');
    } else if (fd.get('end_date')) {
      payload.end_date = fd.get('end_date');
    }
    if (window.homehubCalendarSync) {
      const wcid = window.homehubCalendarSync.getWriteCalendarId();
      if (wcid) payload.linked_calendar_id = wcid;
      const pcid = window.homehubCalendarSync.getPersonalCalendarId
        ? window.homehubCalendarSync.getPersonalCalendarId()
        : null;
      if (pcid) payload.personal_calendar_id = pcid;
    }
    let res;
    if (editingId) res = await window.remindersApi.update(editingId, { ...payload, creator });
    else res = await window.remindersApi.create({ ...payload, creator });
    if (!res.ok) {
      uiError(res.error || 'Save failed');
      return;
    }
    hideForm();
    await loadEvents();
  });

  $('calSyncNow')?.addEventListener('click', async () => {
    const btn = $('calSyncNow');
    if (!window.calendarSyncApi) return;
    btn.disabled = true;
    await window.calendarSyncApi.syncNow();
    if (window.homehubCalendarSync) await window.homehubCalendarSync.refresh();
    await loadLinkedCalendars();
    await loadEvents();
    btn.disabled = false;
  });

  document.querySelectorAll('.cal-side-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      const t = tab.getAttribute('data-tab');
      document.querySelectorAll('.cal-side-tab').forEach((x) => {
        const on = x.getAttribute('data-tab') === t;
        x.classList.toggle('border-b-2', on);
        x.classList.toggle('border-blue-600', on);
        x.classList.toggle('text-blue-600', on);
        x.classList.toggle('text-gray-500', !on);
      });
      $('calSideEvent')?.classList.toggle('hidden', t !== 'event');
      $('calSideSetup')?.classList.toggle('hidden', t !== 'setup');
    });
  });

  function activateSideTab(tabName) {
    const tab = document.querySelector(`.cal-side-tab[data-tab="${tabName}"]`);
    if (tab) tab.click();
  }

  $('calConflictLocal')?.addEventListener('click', async () => {
    const id = parseInt(conflictPanel?.dataset.conflictId || '0', 10);
    if (!id) return;
    const res = await window.remindersApi.resolveConflict(id, 'local');
    if (!res.ok) uiError(res.error || 'Resolve failed');
    else {
      hideForm();
      await loadEvents();
    }
  });
  $('calConflictGoogle')?.addEventListener('click', async () => {
    const id = parseInt(conflictPanel?.dataset.conflictId || '0', 10);
    if (!id) return;
    const res = await window.remindersApi.resolveConflict(id, 'google');
    if (!res.ok) uiError(res.error || 'Resolve failed');
    else {
      hideForm();
      await loadEvents();
    }
  });

  document.addEventListener('mousemove', (e) => {
    if (!resizeState) return;
    const deltaPx = e.clientY - resizeState.startY;
    const newHeight = Math.max(22, resizeState.startHeight + deltaPx);
    resizeState.block.style.height = `${newHeight}px`;
  });

  document.addEventListener('mouseup', async () => {
    if (!resizeState) return;
    const { ev, block, startMin, startHeight } = resizeState;
    const deltaMin = Math.round(((block.offsetHeight - startHeight) / HOUR_PX) * 60);
    const endMin = Math.max(startMin + 15, startMin + Math.max(30, deltaMin));
    const eh = Math.floor(endMin / 60);
    const em = endMin % 60;
    const end_time = `${String(eh).padStart(2, '0')}:${String(em).padStart(2, '0')}`;
    resizeState = null;
    document.body.style.cursor = '';
    if (ev.recurring_id) {
      showRecurringScopeModal(async (scope) => {
        if (!scope) {
          render();
          return;
        }
        await applyMove(ev, { end_time, end_date: ev.date }, scope);
      });
    } else {
      const creator = localStorage.getItem('username') || '';
      await window.remindersApi.update(ev.id, { end_time, end_date: ev.date, creator });
      await loadEvents();
    }
  });

  if (window.homehubColorPicker && $('calEventColorPicker')) {
    eventColorPicker = window.homehubColorPicker.mount($('calEventColorPicker'), {
      value: '#2563eb',
      allowClear: true,
    });
  }

  window.homehubCalendarApp = {
    reload: async () => {
      await loadLinkedCalendars();
      await loadEvents();
    },
    onCalendarsUpdated: loadLinkedCalendars,
    setCategories: applyCategories,
  };

  if (window.homehubReminderCategories && $('calCategoryManager')) {
    window.__calCategoryMgr = window.homehubReminderCategories.mountManager($('calCategoryManager'), {
      initial: categories.slice(),
      onChange: applyCategories,
    });
  }

  renderWeekdayHeaders();
  try {
    const params = new URLSearchParams(window.location.search);
    const shouldOpenSetup =
      params.get('calendar_connected') === '1' ||
      params.get('calendar_error') !== null ||
      params.get('connect_calendar') === '1' ||
      sessionStorage.getItem('calendar:openSetupTab') === '1';
    if (shouldOpenSetup) {
      activateSideTab('setup');
      sessionStorage.removeItem('calendar:openSetupTab');
    }
  } catch (_) {
    // no-op
  }
  selectDay(selectedYmd);
  (async () => {
    await loadCategories();
    await loadLinkedCalendars();
    await loadEvents();
  })();
})();
