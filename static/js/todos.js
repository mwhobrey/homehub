(function () {
  const root = document.getElementById('todoApp');
  if (!root) return;
  const T = typeof Tags !== 'undefined' ? Tags.scoped('todos') : null;
  const usesFirebase = root.dataset.usesFirebase === 'true';
  const todayStr = root.dataset.today || '';
  let familyMembers = [];
  let currentUser = '';
  try {
    familyMembers = JSON.parse(root.dataset.family || '[]');
  } catch (e) {
    familyMembers = [];
  }
  try {
    currentUser = JSON.parse(root.dataset.currentUser || '""');
  } catch (e) {
    currentUser = '';
  }
  let lists = [];
  let selectedListId = null;
  let currentItems = [];
  let householdMembers = [];
  const tagFilterSelected = new Set();
  let listTagCtrl = null;
  let itemTagCtrl = null;
  let editItemTagCtrl = null;
  let personalCalendars = [];
  const els = {
    listSidebar: document.getElementById('listSidebar'),
    listSidebarEmpty: document.getElementById('listSidebarEmpty'),
    listSearch: document.getElementById('listSearch'),
    showDoneLists: document.getElementById('showDoneLists'),
    emptyState: document.getElementById('emptyState'),
    listDetail: document.getElementById('listDetail'),
    detailListName: document.getElementById('detailListName'),
    detailDescription: document.getElementById('detailDescription'),
    detailVisibilityBadge: document.getElementById('detailVisibilityBadge'),
    detailMeta: document.getElementById('detailMeta'),
    detailTags: document.getElementById('detailTags'),
    detailAssignees: document.getElementById('detailAssignees'),
    detailProgressLabel: document.getElementById('detailProgressLabel'),
    detailProgressPct: document.getElementById('detailProgressPct'),
    detailProgressBar: document.getElementById('detailProgressBar'),
    itemsList: document.getElementById('itemsList'),
    itemsEmpty: document.getElementById('itemsEmpty'),
    itemForm: document.getElementById('itemForm'),
    itemTagFilters: document.getElementById('itemTagFilters'),
    clearItemTagFilters: document.getElementById('clearItemTagFilters'),
    hideCompletedItems: document.getElementById('hideCompletedItems'),
    listDialog: document.getElementById('listDialog'),
    listForm: document.getElementById('listForm'),
    itemDialog: document.getElementById('itemDialog'),
    itemEditForm: document.getElementById('itemEditForm'),
    sharePanel: document.getElementById('sharePanel'),
    shareMembers: document.getElementById('shareMembers'),
  };
  function toast(msg, type) {
    if (window.globalToast) window.globalToast(msg, type || 'error');
    else alert(msg);
  }
  function api(path, opts) {
    return fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {})).then((r) =>
      r.json().then((b) => ({ status: r.status, body: b }))
    );
  }
  function familyNames() {
    const names = new Set(familyMembers || []);
    if (currentUser) names.add(currentUser);
    return [...names].sort((a, b) => a.localeCompare(b));
  }
  function renderAssigneePicker(hostId, selected) {
    const host = document.getElementById(hostId);
    if (!host) return;
    const names = familyNames();
    const sel = new Set(selected || []);
    host.innerHTML = '';
    if (!names.length) {
      const p = document.createElement('p');
      p.className = 'todo-picker-empty';
      p.textContent = 'Add family_members in config.yml to assign people here.';
      host.appendChild(p);
      return;
    }
    names.forEach((name) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.name = name;
      btn.textContent = name;
      btn.className = 'todo-assignee-chip' + (sel.has(name) ? ' is-on' : '');
      btn.addEventListener('click', () => btn.classList.toggle('is-on'));
      host.appendChild(btn);
    });
  }
  function getAssigneePicker(hostId) {
    const host = document.getElementById(hostId);
    if (!host) return [];
    return [...host.querySelectorAll('.todo-assignee-chip.is-on')].map((b) => b.dataset.name);
  }
  function defaultCalendarValueForVisibility(vis) {
    if (vis !== 'household') return '';
    const def = personalCalendars.find((c) => c.is_default) || personalCalendars.find((c) => c.is_household);
    return def ? String(def.id) : '';
  }
  function applyCalendarDefaultForVisibility() {
    const sel = document.getElementById('listPersonalCalendar');
    if (!sel) return;
    const vis = document.getElementById('listVisibility')?.value || 'private';
    sel.value = defaultCalendarValueForVisibility(vis);
  }
  function setListVisibility(vis, opts) {
    const hidden = document.getElementById('listVisibility');
    if (hidden) hidden.value = vis;
    document.querySelectorAll('.todo-segmented button[data-vis]').forEach((btn) => {
      btn.classList.toggle('is-on', btn.dataset.vis === vis);
    });
    const hint = document.getElementById('visibilityHint');
    if (hint) {
      hint.textContent =
        vis === 'household'
          ? 'Everyone in your household can view and edit this list.'
          : 'Only you unless you share with specific people.';
    }
    if (els.sharePanel) {
      els.sharePanel.classList.toggle('hidden', vis === 'household' || !usesFirebase);
    }
    if (!opts || !opts.keepCalendar) {
      applyCalendarDefaultForVisibility();
    }
  }
  function dueDateClass(dueStr, done) {
    if (!dueStr || done) return '';
    if (dueStr < todayStr) return 'text-red-600 font-semibold';
    if (dueStr === todayStr) return 'text-amber-600 font-semibold';
    return 'text-green-700 dark:text-green-400';
  }
  function recurrencePayload(formEl, prefix) {
    const recurring = document.getElementById(prefix + 'Recurring');
    if (!recurring || !recurring.checked) return null;
    const interval = parseInt(document.getElementById(prefix + 'RecInterval').value, 10) || 1;
    const unit = document.getElementById(prefix + 'RecUnit').value;
    const start = document.getElementById(prefix + 'RecStart').value || null;
    let end = null;
    if (window.homehubRecurrence && formEl) {
      end = window.homehubRecurrence.endDateForPayload(formEl);
    } else {
      const endEl = document.getElementById(prefix + 'RecEnd');
      const forever = document.getElementById(prefix + 'RecRepeatForever');
      if (endEl && !(forever && forever.checked)) end = endEl.value || null;
    }
    return { interval, unit, start_date: start, end_date: end };
  }
  function bindRecurrenceToggle(checkboxId, panelId, formEl) {
    const cb = document.getElementById(checkboxId);
    const panel = document.getElementById(panelId);
    if (!cb || !panel) return;
    const sync = () => {
      panel.classList.toggle('hidden', !cb.checked);
      if (cb.checked && formEl && window.homehubRecurrence) window.homehubRecurrence.bind(formEl);
    };
    cb.addEventListener('change', sync);
    sync();
  }
  function fillRecurrenceFields(prefix, rec, formEl) {
    const cb = document.getElementById(prefix + 'Recurring');
    const panel = document.getElementById(prefix + 'RecurrencePanel');
    if (!cb) return;
    cb.checked = !!rec;
    if (panel) panel.classList.toggle('hidden', !rec);
    if (!rec) return;
    document.getElementById(prefix + 'RecInterval').value = rec.interval || 1;
    document.getElementById(prefix + 'RecUnit').value = rec.unit || 'day';
    const startEl = document.getElementById(prefix + 'RecStart');
    if (startEl) startEl.value = rec.start_date || '';
    if (formEl && window.homehubRecurrence) {
      window.homehubRecurrence.applyRuleEndDate(formEl, rec.end_date || null);
      window.homehubRecurrence.bind(formEl);
    }
  }
  async function loadHouseholdMembers() {
    if (!usesFirebase) return;
    const res = await api('/api/calendar/household-members');
    if (res.body && res.body.ok) householdMembers = res.body.members || [];
  }
  function populateCalendarSelect(explicitCalendarId) {
    const sel = document.getElementById('listPersonalCalendar');
    if (!sel) return;
    const vis = document.getElementById('listVisibility')?.value || 'private';
    sel.innerHTML = '<option value="">None — to-dos stay off the calendar</option>';
    personalCalendars.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = String(c.id);
      opt.textContent = c.name || 'Calendar';
      sel.appendChild(opt);
    });
    if (explicitCalendarId !== undefined && explicitCalendarId !== null && explicitCalendarId !== '') {
      sel.value = String(explicitCalendarId);
    } else {
      sel.value = defaultCalendarValueForVisibility(vis);
    }
  }
  async function loadPersonalCalendars() {
    const res = await api('/api/todo-lists/calendars');
    if (res.body && res.body.ok) {
      personalCalendars = res.body.calendars || [];
      populateCalendarSelect();
    }
  }
  function renderShareCheckboxes(sharedWith) {
    if (!els.shareMembers) return;
    els.shareMembers.innerHTML = '';
    const emptyEl = document.getElementById('shareMembersEmpty');
    if (!householdMembers.length) {
      if (emptyEl) emptyEl.classList.remove('hidden');
      return;
    }
    if (emptyEl) emptyEl.classList.add('hidden');
    const map = {};
    (sharedWith || []).forEach((s) => {
      map[s.grantee_uid] = s;
    });
    householdMembers.forEach((m) => {
      const row = document.createElement('div');
      row.className = 'flex items-center justify-between gap-2 py-1 border-b border-gray-100 dark:border-gray-800 last:border-0';
      const left = document.createElement('label');
      left.className = 'flex items-center gap-2 flex-1 min-w-0';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.uid = m.uid;
      cb.className = 'rounded';
      if (map[m.uid]) cb.checked = true;
      const label = document.createElement('span');
      label.className = 'truncate';
      label.textContent = m.email || m.uid;
      left.appendChild(cb);
      left.appendChild(label);
      const write = document.createElement('label');
      write.className = 'inline-flex items-center gap-1 text-xs text-gray-500 shrink-0';
      const writeCb = document.createElement('input');
      writeCb.type = 'checkbox';
      writeCb.title = 'Can edit';
      writeCb.className = 'rounded';
      writeCb.dataset.writeFor = m.uid;
      if (map[m.uid] && map[m.uid].can_write) writeCb.checked = true;
      write.appendChild(writeCb);
      write.appendChild(document.createTextNode('Can edit'));
      row.appendChild(left);
      row.appendChild(write);
      els.shareMembers.appendChild(row);
    });
  }
  function collectShares() {
    const out = [];
    if (!els.shareMembers) return out;
    els.shareMembers.querySelectorAll('input[type=checkbox][data-uid]').forEach((cb) => {
      if (!cb.checked) return;
      const uid = cb.dataset.uid;
      const writeEl = els.shareMembers.querySelector(`input[data-write-for="${uid}"]`);
      out.push({ grantee_uid: uid, can_write: !!(writeEl && writeEl.checked) });
    });
    return out;
  }
  function listSearchQuery() {
    return (els.listSearch && els.listSearch.value || '').trim().toLowerCase();
  }
  function listIsFullyDone(list) {
    const total = list.item_total || 0;
    const done = list.item_done || 0;
    return total > 0 && done >= total;
  }
  function listsForSidebar() {
    const q = listSearchQuery();
    let rows = lists.filter((l) => !q || (l.name || '').toLowerCase().includes(q));
    const showDone = els.showDoneLists && els.showDoneLists.checked;
    if (!showDone) rows = rows.filter((l) => !listIsFullyDone(l));
    return rows;
  }
  function ensureSelectedListVisible() {
    if (!selectedListId) return;
    if (listsForSidebar().some((l) => l.id === selectedListId)) return;
    const visible = listsForSidebar();
    if (visible.length) {
      selectList(visible[0].id);
      return;
    }
    selectedListId = null;
    els.listDetail.classList.add('hidden');
    els.emptyState.classList.remove('hidden');
    syncDetailPanelVisibility();
  }
  function syncDetailPanelVisibility() {
    const panel = document.getElementById('todoMainPanel');
    if (panel) panel.classList.toggle('is-detail', !!selectedListId);
  }
  function renderListSidebar() {
    const filtered = listsForSidebar();
    els.listSidebar.innerHTML = '';
    els.listSidebarEmpty.classList.toggle('hidden', filtered.length > 0);
    if (els.listSidebarEmpty && filtered.length === 0) {
      const showDone = els.showDoneLists && els.showDoneLists.checked;
      const hasAny = lists.length > 0;
      const allDoneHidden = hasAny && !showDone && lists.every((l) => listIsFullyDone(l));
      els.listSidebarEmpty.innerHTML = allDoneHidden
        ? 'All lists are complete. Check <strong>Show done</strong> to view them.'
        : 'No lists yet. Use <strong>New list</strong> in the header.';
    }
    filtered.forEach((l) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      const active = l.id === selectedListId;
      btn.className = 'todo-list-btn' + (active ? ' is-active' : '');
      const row = document.createElement('div');
      row.className = 'flex items-start gap-2';
      const icon = document.createElement('i');
      icon.className =
        'fa-solid mt-0.5 ' +
        (l.visibility === 'household' ? 'fa-users text-green-600' : 'fa-lock text-gray-400');
      const body = document.createElement('div');
      body.className = 'flex-1 min-w-0';
      const title = document.createElement('div');
      title.className = 'font-medium truncate';
      title.textContent = l.name;
      body.appendChild(title);
      const sub = document.createElement('div');
      sub.className = 'text-xs mt-0.5';
      sub.style.color = 'var(--muted-text)';
      const total = l.item_total || 0;
      const done = l.item_done || 0;
      const open = total - done;
      let subText = open ? `${open} open` : total ? 'All done' : 'Empty';
      if (l.due_date) subText += ' · due ' + l.due_date;
      sub.textContent = subText;
      body.appendChild(sub);
      if (total > 0) {
        const barWrap = document.createElement('div');
        barWrap.className = 'todo-progress-track mt-2';
        const bar = document.createElement('div');
        bar.className = 'todo-progress-fill';
        bar.style.width = Math.round((done / total) * 100) + '%';
        barWrap.appendChild(bar);
        body.appendChild(barWrap);
      }
      row.appendChild(icon);
      row.appendChild(body);
      btn.appendChild(row);
      btn.addEventListener('click', () => selectList(l.id));
      els.listSidebar.appendChild(btn);
    });
  }
  function renderDetailHeader(list) {
    els.detailListName.textContent = list.name;
    els.detailDescription.textContent = list.description || '';
    els.detailDescription.classList.toggle('hidden', !list.description);
    const isHouse = list.visibility === 'household';
    els.detailVisibilityBadge.textContent = isHouse ? 'Household' : 'Private';
    els.detailVisibilityBadge.className =
      'todo-vis-badge ' + (isHouse ? 'todo-vis-badge--household' : 'todo-vis-badge--private');
    const meta = [];
    if (list.due_date) {
      const cls = dueDateClass(list.due_date, false);
      meta.push('List due ' + list.due_date);
      els.detailMeta.className = 'text-xs mt-1 ' + (cls || 'text-gray-500');
    } else {
      els.detailMeta.className = 'text-xs text-gray-500 mt-1';
    }
    if (list.recurrence) meta.push('Repeats every ' + list.recurrence.interval + ' ' + list.recurrence.unit);
    if (list.personal_calendar_name) meta.push('Calendar: ' + list.personal_calendar_name);
    els.detailMeta.textContent = meta.join(' · ');
    const total = list.item_total || 0;
    const done = list.item_done || 0;
    els.detailProgressLabel.textContent = total ? `${done} of ${total} completed` : 'No items yet';
    const pct = total ? Math.round((done / total) * 100) : 0;
    els.detailProgressPct.textContent = total ? pct + '%' : '';
    els.detailProgressBar.style.width = pct + '%';
    els.detailTags.innerHTML = '';
    els.detailAssignees.innerHTML = '';
    if (T && list.tags && list.tags.length) {
      list.tags.forEach((t) => els.detailTags.appendChild(T.makeFilledPill(t)));
      T.recordTags(list.tags);
    }
    if (list.assignees && list.assignees.length) {
      list.assignees.forEach((a) => {
        const b = document.createElement('span');
        b.className = 'text-xs px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-900 dark:text-indigo-100';
        b.textContent = a;
        els.detailAssignees.appendChild(b);
      });
    }
  }
  function itemPassesFilters(item) {
    if (els.hideCompletedItems && els.hideCompletedItems.checked && item.done) return false;
    if (!tagFilterSelected.size) return true;
    const tags = item.tags || [];
    return tags.some((t) => tagFilterSelected.has(t));
  }
  function collectItemTags() {
    const set = new Set();
    currentItems.forEach((it) => (it.tags || []).forEach((t) => set.add(t)));
    if (T) T.getAllKnownTags().forEach((t) => set.add(t));
    return [...set].sort((a, b) => a.localeCompare(b));
  }
  function renderItemTagFilters() {
    if (!els.itemTagFilters || !T) return;
    const all = collectItemTags();
    els.itemTagFilters.innerHTML = '';
    all.forEach((t) => {
      els.itemTagFilters.appendChild(
        T.makePill(
          t,
          () => {
            if (tagFilterSelected.has(t)) tagFilterSelected.delete(t);
            else tagFilterSelected.add(t);
            renderItemTagFilters();
            renderItems(currentItems);
          },
          tagFilterSelected.has(t)
        )
      );
    });
    els.clearItemTagFilters.classList.toggle('hidden', tagFilterSelected.size === 0);
  }
  function renderItems(items) {
    currentItems = items || [];
    renderItemTagFilters();
    const visible = currentItems.filter(itemPassesFilters);
    els.itemsList.innerHTML = '';
    els.itemsEmpty.classList.toggle('hidden', visible.length > 0);
    visible.forEach((item) => {
      const li = document.createElement('li');
      li.className = 'card todo-item-card flex flex-col gap-2';
      li.dataset.id = item.id;
      const row = document.createElement('div');
      row.className = 'todo-item-row';
      const title = document.createElement('span');
      title.className = 'todo-item-row__title ' + (item.done ? 'line-through opacity-60' : 'font-medium');
      title.textContent = item.description;
      const actions = document.createElement('div');
      actions.className = 'todo-item-actions';
      const doneBtn = document.createElement('button');
      doneBtn.type = 'button';
      doneBtn.className = 'btn todo-item-done ' + (item.done ? 'btn-secondary' : 'btn-success');
      doneBtn.textContent = item.done ? 'Undo' : 'Done';
      doneBtn.addEventListener('click', async () => {
        const res = await api('/api/todo-items/' + item.id + '/toggle', { method: 'POST', body: '{}' });
        if (res.body.ok) {
          await refreshLists();
          selectList(selectedListId);
        } else toast(res.body.error || 'Could not update item');
      });
      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'todo-icon-btn';
      editBtn.title = 'Edit item';
      editBtn.setAttribute('aria-label', 'Edit item');
      editBtn.innerHTML = '<i class="fa-solid fa-pen" aria-hidden="true"></i>';
      editBtn.addEventListener('click', () => openItemDialog(item));
      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'todo-icon-btn todo-icon-btn--danger';
      delBtn.title = 'Delete item';
      delBtn.setAttribute('aria-label', 'Delete item');
      delBtn.innerHTML = '<i class="fa fa-times" aria-hidden="true"></i>';
      delBtn.addEventListener('click', async () => {
        if (!confirm('Delete this item?')) return;
        const res = await api('/api/todo-items/' + item.id, { method: 'DELETE', body: '{}' });
        if (res.body.ok) {
          await refreshLists();
          selectList(selectedListId);
        } else toast(res.body.error || 'Delete failed');
      });
      actions.appendChild(doneBtn);
      actions.appendChild(editBtn);
      actions.appendChild(delBtn);
      row.appendChild(title);
      row.appendChild(actions);
      li.appendChild(row);
      const meta = document.createElement('div');
      meta.className = 'flex flex-wrap gap-2 items-center text-xs text-gray-500';
      if (item.due_date) {
        const due = document.createElement('span');
        due.className = dueDateClass(item.due_date, item.done);
        due.textContent = 'Due ' + item.due_date;
        meta.appendChild(due);
      }
      if (item.recurrence) {
        const rec = document.createElement('span');
        rec.className = 'text-indigo-600 dark:text-indigo-400 font-medium';
        rec.textContent = 'Recurring · every ' + item.recurrence.interval + ' ' + item.recurrence.unit;
        meta.appendChild(rec);
      }
      if (item.assignees && item.assignees.length) {
        item.assignees.forEach((a) => {
          const b = document.createElement('span');
          b.className = 'px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-900/30';
          b.textContent = '@' + a;
          meta.appendChild(b);
        });
      }
      li.appendChild(meta);
      const tagHost = document.createElement('div');
      tagHost.className = 'flex flex-wrap gap-2';
      if (T && item.tags && item.tags.length) {
        item.tags.forEach((t) => tagHost.appendChild(T.makeFilledPill(t)));
        T.recordTags(item.tags);
      }
      if (tagHost.childNodes.length) li.appendChild(tagHost);
      els.itemsList.appendChild(li);
    });
  }
  async function selectList(id) {
    selectedListId = id;
    renderListSidebar();
    const list = lists.find((l) => l.id === id);
    if (!list) return;
    els.emptyState.classList.add('hidden');
    els.listDetail.classList.remove('hidden');
    syncDetailPanelVisibility();
    renderDetailHeader(list);
    const res = await api('/api/todo-lists/' + id + '/items');
    if (!res.body.ok) {
      toast(res.body.error || 'Could not load items');
      return;
    }
    renderItems(res.body.items || []);
  }
  async function refreshLists() {
    const res = await api('/api/todo-lists');
    if (!res.body.ok) return;
    lists = res.body.lists || [];
    renderListSidebar();
    if (selectedListId && lists.some((l) => l.id === selectedListId)) {
      const list = lists.find((l) => l.id === selectedListId);
      if (list && els.listDetail && !els.listDetail.classList.contains('hidden')) renderDetailHeader(list);
      ensureSelectedListVisible();
    } else if (lists.length && !selectedListId) {
      const visible = listsForSidebar();
      if (visible.length) selectList(visible[0].id);
    }
  }
  function openListDialog(edit) {
    document.getElementById('listDialogTitle').textContent = edit ? 'Edit list' : 'New list';
    document.getElementById('editListId').value = edit ? edit.id : '';
    document.getElementById('listName').value = edit ? edit.name : '';
    document.getElementById('listDescription').value = edit ? edit.description || '' : '';
    const vis = edit ? edit.visibility : 'private';
    setListVisibility(vis, { keepCalendar: true });
    populateCalendarSelect(edit && edit.personal_calendar_id ? edit.personal_calendar_id : undefined);
    document.getElementById('listDueDate').value = edit && edit.due_date ? edit.due_date : '';
    if (listTagCtrl) listTagCtrl.setTags(edit ? edit.tags : []);
    renderAssigneePicker('listAssigneePicker', edit ? edit.assignees : []);
    fillRecurrenceFields('list', edit && edit.recurrence, els.listForm);
    if (usesFirebase) renderShareCheckboxes(edit ? edit.shared_with : []);
    els.listDialog.showModal();
  }
  function openItemDialog(item) {
    document.getElementById('editItemId').value = item.id;
    document.getElementById('editItemDescription').value = item.description || '';
    document.getElementById('editItemDueDate').value = item.due_date || '';
    if (editItemTagCtrl) editItemTagCtrl.setTags(item.tags || []);
    renderAssigneePicker('editItemAssigneePicker', item.assignees || []);
    fillRecurrenceFields('editItem', item.recurrence, els.itemEditForm);
    els.itemDialog.showModal();
  }
  document.getElementById('btnNewList').addEventListener('click', () => openListDialog(null));
  document.getElementById('btnEditList').addEventListener('click', () => {
    const list = lists.find((l) => l.id === selectedListId);
    if (list) openListDialog(list);
  });
  document.getElementById('btnDeleteList').addEventListener('click', async () => {
    if (!selectedListId || !confirm('Delete this list and all items?')) return;
    const res = await api('/api/todo-lists/' + selectedListId, { method: 'DELETE', body: '{}' });
    if (res.body.ok) {
      selectedListId = null;
      els.listDetail.classList.add('hidden');
      els.emptyState.classList.remove('hidden');
      syncDetailPanelVisibility();
      await refreshLists();
      toast('List deleted', 'success');
    } else toast(res.body.error || 'Delete failed');
  });
  document.getElementById('listDialogCancel').addEventListener('click', () => els.listDialog.close());
  document.getElementById('itemDialogCancel').addEventListener('click', () => els.itemDialog.close());
  document.querySelectorAll('.todo-segmented button[data-vis]').forEach((btn) => {
    btn.addEventListener('click', () => setListVisibility(btn.dataset.vis || 'private'));
  });
  document.getElementById('toggleItemAdvanced').addEventListener('click', () => {
    const panel = document.getElementById('itemAdvancedPanel');
    const icon = document.getElementById('itemAdvancedIcon');
    const hidden = panel.classList.toggle('hidden');
    icon.classList.toggle('fa-chevron-down', hidden);
    icon.classList.toggle('fa-chevron-up', !hidden);
  });
  if (els.listSearch) els.listSearch.addEventListener('input', renderListSidebar);
  if (els.showDoneLists) {
    els.showDoneLists.addEventListener('change', () => {
      renderListSidebar();
      ensureSelectedListVisible();
    });
  }
  if (els.clearItemTagFilters) {
    els.clearItemTagFilters.addEventListener('click', () => {
      tagFilterSelected.clear();
      renderItemTagFilters();
      renderItems(currentItems);
    });
  }
  if (els.hideCompletedItems) {
    els.hideCompletedItems.addEventListener('change', () => renderItems(currentItems));
  }
  els.listForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (listTagCtrl) listTagCtrl.harvestPending();
    const id = document.getElementById('editListId').value;
    const payload = {
      name: document.getElementById('listName').value.trim(),
      description: document.getElementById('listDescription').value.trim(),
      visibility: document.getElementById('listVisibility').value,
      due_date: document.getElementById('listDueDate').value || null,
      tags: listTagCtrl ? listTagCtrl.getTags() : [],
      assignees: getAssigneePicker('listAssigneePicker'),
    };
    const calSel = document.getElementById('listPersonalCalendar');
    if (calSel) {
      const v = calSel.value;
      payload.personal_calendar_id = v ? parseInt(v, 10) : null;
    }
    if (usesFirebase && payload.visibility === 'private') payload.shared_with = collectShares();
    const rec = recurrencePayload(els.listForm, 'list');
    if (document.getElementById('listRecurring').checked && rec) payload.recurrence = rec;
    else if (id) payload.clear_recurrence = true;
    const path = id ? '/api/todo-lists/' + id : '/api/todo-lists';
    const res = await api(path, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    if (res.body.ok) {
      els.listDialog.close();
      await refreshLists();
      if (res.body.list) selectList(res.body.list.id);
      toast(id ? 'List updated' : 'List created', 'success');
    } else toast(res.body.error || 'Save failed');
  });
  els.itemForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedListId) return;
    if (itemTagCtrl) itemTagCtrl.harvestPending();
    const payload = {
      description: document.getElementById('itemDescription').value.trim(),
      due_date: document.getElementById('itemDueDate').value || null,
      tags: itemTagCtrl ? itemTagCtrl.getTags() : [],
      assignees: getAssigneePicker('itemAssigneePicker'),
    };
    if (document.getElementById('itemRecurring').checked) {
      payload.is_recurring = true;
      const rec = recurrencePayload(els.itemForm, 'item');
      if (rec) payload.recurrence = rec;
    }
    const res = await api('/api/todo-lists/' + selectedListId + '/items', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.body.ok) {
      document.getElementById('itemDescription').value = '';
      document.getElementById('itemDueDate').value = '';
      if (itemTagCtrl) itemTagCtrl.setTags([]);
      renderAssigneePicker('itemAssigneePicker', []);
      document.getElementById('itemRecurring').checked = false;
      document.getElementById('itemRecurrencePanel').classList.add('hidden');
      await refreshLists();
      selectList(selectedListId);
      toast('Item added', 'success');
    } else toast(res.body.error || 'Could not add item');
  });
  els.itemEditForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (editItemTagCtrl) editItemTagCtrl.harvestPending();
    const id = document.getElementById('editItemId').value;
    const payload = {
      description: document.getElementById('editItemDescription').value.trim(),
      due_date: document.getElementById('editItemDueDate').value || null,
      tags: editItemTagCtrl ? editItemTagCtrl.getTags() : [],
      assignees: getAssigneePicker('editItemAssigneePicker'),
    };
    if (document.getElementById('editItemRecurring').checked) {
      payload.is_recurring = true;
      const rec = recurrencePayload(els.itemEditForm, 'editItem');
      if (rec) payload.recurrence = rec;
    }
    const res = await api('/api/todo-items/' + id, { method: 'PUT', body: JSON.stringify(payload) });
    if (res.body.ok) {
      els.itemDialog.close();
      await refreshLists();
      selectList(selectedListId);
      toast('Item updated', 'success');
    } else toast(res.body.error || 'Update failed');
  });
  bindRecurrenceToggle('listRecurring', 'listRecurrencePanel', els.listForm);
  bindRecurrenceToggle('itemRecurring', 'itemRecurrencePanel', els.itemForm);
  bindRecurrenceToggle('editItemRecurring', 'editItemRecurrencePanel', els.itemEditForm);
  if (T && typeof FormTags !== 'undefined') {
    listTagCtrl = FormTags.initTagInputForm(T, {
      formId: 'listForm',
      wrapId: 'listTagWrap',
      inputId: 'listTagInput',
      hiddenId: 'listTagsField',
      libraryId: 'listTagLibrary',
    });
    itemTagCtrl = FormTags.initTagInputForm(T, {
      formId: 'itemForm',
      wrapId: 'itemTagWrap',
      inputId: 'itemTagInput',
      hiddenId: 'itemTagsField',
      libraryId: 'itemTagLibrary',
    });
    editItemTagCtrl = FormTags.initTagInputForm(T, {
      formId: 'itemEditForm',
      wrapId: 'editItemTagWrap',
      inputId: 'editItemTagInput',
      hiddenId: 'editItemTagsField',
      libraryId: 'editItemTagLibrary',
    });
  }
  renderAssigneePicker('itemAssigneePicker', []);
  (async function init() {
    await loadPersonalCalendars();
    await loadHouseholdMembers();
    await refreshLists();
    syncDetailPanelVisibility();
  })();
})();
