/**
 * HomeHub personal calendars — local buckets for events and Google import targets.
 */
(function () {
  const DEFAULT_COLOR = '#2563eb';
  const uiAlert = (msg, title) => {
    if (window.globalToast) window.globalToast(msg, 'error');
    else if (window.homehubDialog?.alert) window.homehubDialog.alert(msg, { title: title || 'Error' });
    else window.alert(msg);
  };
  const uiConfirm = async (msg, title, okText, cancelText) => {
    if (window.homehubDialog?.confirm) {
      return window.homehubDialog.confirm(msg, {
        title: title || 'Confirm',
        okText: okText || 'OK',
        cancelText: cancelText || 'Cancel',
      });
    }
    return window.confirm(msg);
  };

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function fetchList() {
    const r = await fetch('/api/calendar/personal-calendars');
    return r.json();
  }

  async function createCalendar(data) {
    const r = await fetch('/api/calendar/personal-calendars', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  }

  async function updateCalendar(id, data) {
    const r = await fetch(`/api/calendar/personal-calendars/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  }

  async function deleteCalendar(id) {
    const r = await fetch(`/api/calendar/personal-calendars/${id}`, { method: 'DELETE' });
    return r.json();
  }

  async function fetchHouseholdMembers() {
    const r = await fetch('/api/calendar/household-members');
    return r.json();
  }

  async function updateShares(calendarId, shares) {
    const r = await fetch(`/api/calendar/personal-calendars/${calendarId}/shares`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shares }),
    });
    return r.json();
  }

  function calendarSubtitle(cal) {
    if (cal.is_household) return 'Shared with everyone';
    if (cal.is_owner) {
      const n = (cal.shared_with || []).length;
      if (n) return `Shared with ${n} member${n === 1 ? '' : 's'}`;
      return 'Private — only you';
    }
    return 'Shared with you';
  }

  function populateSelect(selectEl, calendars, selectedId) {
    if (!selectEl) return;
    const opts = [];
    (calendars || []).forEach((c) => {
      const sel = selectedId && String(c.id) === String(selectedId) ? ' selected' : '';
      opts.push(
        `<option value="${c.id}" data-color="${escapeHtml(c.color || DEFAULT_COLOR)}"${sel}>${escapeHtml(c.name || `Calendar ${c.id}`)}</option>`
      );
    });
    selectEl.innerHTML = opts.join('') || '<option value="">—</option>';
  }

  function mountManager(container, options) {
    if (!container) return null;
    const onChange = typeof options?.onChange === 'function' ? options.onChange : null;
    let calendars = Array.isArray(options?.initial) ? options.initial.slice() : [];
    let editingId = null;
    let sharingId = null;
    let householdMembers = null;

    async function loadMembers() {
      if (householdMembers) return householdMembers;
      const res = await fetchHouseholdMembers();
      if (!res.ok) {
        uiAlert(res.error || 'Could not load household members');
        return [];
      }
      householdMembers = res.members || [];
      return householdMembers;
    }

    async function renderSharePanel(cal, row) {
      row.innerHTML = `
        <p class="text-[10px] font-semibold">Share "${escapeHtml(cal.name || '')}"</p>
        <p class="text-[10px] text-[var(--muted-text)]">Loading household members…</p>`;
      let members = [];
      try {
        members = await loadMembers();
      } catch (err) {
        console.warn('household members', err);
        if (sharingId !== cal.id) return;
        row.innerHTML = `
          <p class="text-[10px] font-semibold">Share "${escapeHtml(cal.name || '')}"</p>
          <p class="text-[10px] text-red-600">Could not load household members.</p>
          <button type="button" class="pc-share-cancel px-2 py-1 text-xs rounded border border-[var(--input-border)]">Cancel</button>`;
        row.querySelector('.pc-share-cancel')?.addEventListener('click', () => {
          sharingId = null;
          render();
        });
        return;
      }
      if (sharingId !== cal.id) return;
      const shared = new Map((cal.shared_with || []).map((s) => [s.grantee_uid, s]));
      const memberRows = members
        .map((m, idx) => {
          const cur = shared.get(m.uid);
          const checked = cur ? ' checked' : '';
          const writeChecked = cur && cur.can_write ? ' checked' : '';
          const label = escapeHtml(m.email || m.uid);
          const memberId = `pc-share-${cal.id}-${idx}`;
          const writeId = `pc-share-write-${cal.id}-${idx}`;
          return `
            <div class="flex items-center gap-2 text-xs py-1">
              <input type="checkbox" class="pc-share-member" id="${memberId}" data-uid="${escapeHtml(m.uid)}"${checked}>
              <label class="flex-1 truncate" for="${memberId}">${label}</label>
              <div class="flex items-center gap-1 text-[10px] text-[var(--muted-text)]">
                <input type="checkbox" class="pc-share-write" id="${writeId}" data-uid="${escapeHtml(m.uid)}"${writeChecked}${checked ? '' : ' disabled'}>
                <label for="${writeId}">Can edit</label>
              </div>
            </div>`;
        })
        .join('');
      row.innerHTML = `
        <p class="text-[10px] font-semibold">Share "${escapeHtml(cal.name || '')}"</p>
        <p class="text-[10px] text-[var(--muted-text)]">Selected members see events on their Home calendar.</p>
        <div class="max-h-40 overflow-y-auto border border-[var(--input-border)] rounded p-2 space-y-1">${memberRows || '<p class="text-[10px] text-[var(--muted-text)]">No other household members yet. Members appear here after they sign in with Firebase.</p>'}</div>
        <div class="flex gap-2">
          <button type="button" class="pc-share-save px-2 py-1 text-xs rounded bg-[var(--primary-color)] text-white">Save sharing</button>
          <button type="button" class="pc-share-cancel px-2 py-1 text-xs rounded border border-[var(--input-border)]">Cancel</button>
        </div>`;
      row.querySelectorAll('.pc-share-member').forEach((chk) => {
        chk.addEventListener('change', () => {
          const write = row.querySelector(`.pc-share-write[data-uid="${chk.dataset.uid}"]`);
          if (write) {
            write.disabled = !chk.checked;
            if (!chk.checked) write.checked = false;
          }
        });
      });
      row.querySelector('.pc-share-save')?.addEventListener('click', async () => {
        const shares = [];
        row.querySelectorAll('.pc-share-member:checked').forEach((chk) => {
          const uid = chk.dataset.uid;
          const write = row.querySelector(`.pc-share-write[data-uid="${uid}"]`);
          shares.push({ grantee_uid: uid, can_write: !!(write && write.checked) });
        });
        const res = await updateShares(cal.id, shares);
        if (!res.ok) {
          uiAlert(res.error || 'Could not update sharing');
          return;
        }
        sharingId = null;
        await reload();
      });
      row.querySelector('.pc-share-cancel')?.addEventListener('click', () => {
        sharingId = null;
        render();
      });
    }

    function render() {
      container.innerHTML = '';
      if (!calendars.length) {
        const empty = document.createElement('p');
        empty.className = 'text-[10px] text-[var(--muted-text)]';
        empty.textContent = 'No calendars yet. Add one below.';
        container.appendChild(empty);
      }
      calendars.forEach((cal) => {
        const row = document.createElement('div');
        row.className = 'border border-[var(--input-border)] rounded-lg p-2 space-y-2 bg-[var(--secondary-bg)]';
        row.dataset.id = cal.id;
        const isEditing = editingId === cal.id;
        const isSharing = sharingId === cal.id;
        if (isSharing) {
          row.innerHTML = `<p class="text-[10px] text-[var(--muted-text)]">Opening share settings…</p>`;
          container.appendChild(row);
          renderSharePanel(cal, row);
          return;
        } else if (isEditing) {
          row.innerHTML = `
            <label class="block text-[10px] font-semibold">Name</label>
            <input type="text" class="pc-edit-name w-full h-8 border rounded px-2 text-xs cal-field-input" value="${escapeHtml(cal.name || '')}" maxlength="64">
            <div class="pc-edit-color"></div>
            <div class="flex gap-2">
              <button type="button" class="pc-save px-2 py-1 text-xs rounded bg-[var(--primary-color)] text-white">Save</button>
              <button type="button" class="pc-cancel px-2 py-1 text-xs rounded border border-[var(--input-border)]">Cancel</button>
            </div>`;
          let picker = null;
          const colorMount = row.querySelector('.pc-edit-color');
          if (window.homehubColorPicker && colorMount) {
            picker = window.homehubColorPicker.mount(colorMount, {
              value: cal.color || DEFAULT_COLOR,
              label: 'Color',
            });
          }
          row.querySelector('.pc-save')?.addEventListener('click', async () => {
            const name = row.querySelector('.pc-edit-name')?.value?.trim();
            if (!name) {
              uiAlert('Name is required.');
              return;
            }
            const res = await updateCalendar(cal.id, {
              name,
              color: picker ? picker.getValue() : cal.color,
            });
            if (!res.ok) {
              uiAlert(res.error || 'Could not save calendar');
              return;
            }
            editingId = null;
            await reload();
          });
          row.querySelector('.pc-cancel')?.addEventListener('click', () => {
            editingId = null;
            render();
          });
        } else {
          const bg = cal.color || DEFAULT_COLOR;
          const subtitle = calendarSubtitle(cal);
          const badge = cal.is_household
            ? '<span class="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--primary-color)]/15 text-[var(--primary-color)]">Household</span>'
            : '';
          const actions = [];
          if (cal.can_edit) {
            actions.push('<button type="button" class="pc-edit px-2 py-0.5 text-xs rounded border border-[var(--input-border)]">Edit</button>');
          }
          if (cal.can_share) {
            actions.push('<button type="button" class="pc-share px-2 py-0.5 text-xs rounded border border-[var(--input-border)]">Share</button>');
          }
          if (cal.is_owner && !cal.is_household) {
            actions.push('<button type="button" class="pc-delete px-2 py-0.5 text-xs rounded border border-red-300 text-red-700">Delete</button>');
          }
          row.innerHTML = `
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="w-3 h-3 rounded-full flex-shrink-0" style="background:${escapeHtml(bg)}"></span>
                <div class="min-w-0">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-medium truncate text-sm">${escapeHtml(cal.name || `Calendar ${cal.id}`)}</span>
                    ${badge}
                  </div>
                  <p class="text-[10px] text-[var(--muted-text)] truncate">${escapeHtml(subtitle)}</p>
                </div>
              </div>
              <div class="flex gap-1 flex-shrink-0 flex-wrap justify-end">${actions.join('')}</div>
            </div>`;
          row.querySelector('.pc-edit')?.addEventListener('click', () => {
            editingId = cal.id;
            sharingId = null;
            render();
          });
          row.querySelector('.pc-share')?.addEventListener('click', () => {
            sharingId = cal.id;
            editingId = null;
            render();
          });
          row.querySelector('.pc-delete')?.addEventListener('click', async () => {
            if (
              !(await uiConfirm(
                `Delete calendar "${cal.name}"? Events keep their data but lose this calendar assignment.`,
                'Delete Calendar',
                'Delete',
                'Cancel'
              ))
            ) {
              return;
            }
            const res = await deleteCalendar(cal.id);
            if (!res.ok) {
              uiAlert(res.error || 'Could not delete calendar');
              return;
            }
            await reload();
          });
        }
        container.appendChild(row);
      });

      const addRow = document.createElement('div');
      addRow.className = 'border border-dashed border-[var(--input-border)] rounded-lg p-2 space-y-2 mt-2';
      addRow.innerHTML = `
        <p class="text-[10px] font-semibold">Add calendar</p>
        <input type="text" class="pc-new-name w-full h-8 border rounded px-2 text-xs cal-field-input" placeholder="e.g. Family, Work…" maxlength="64">
        <div class="pc-new-color"></div>
        <div class="pc-add-shares space-y-1"></div>
        <button type="button" class="pc-add px-2 py-1 text-xs rounded bg-[var(--primary-color)] text-white">Add</button>`;
      let newPicker = null;
      const newColorMount = addRow.querySelector('.pc-new-color');
      if (window.homehubColorPicker && newColorMount) {
        newPicker = window.homehubColorPicker.mount(newColorMount, {
          value: DEFAULT_COLOR,
          label: 'Color',
        });
      }
      const addShareMount = addRow.querySelector('.pc-add-shares');
      loadMembers().then((members) => {
        if (!addShareMount) return;
        if (!members.length) {
          addShareMount.innerHTML = '<p class="text-[10px] text-[var(--muted-text)]">Share with household members (optional — appears after others sign in).</p>';
          return;
        }
        addShareMount.innerHTML = `
          <p class="text-[10px] font-semibold">Share with (optional)</p>
          ${members.map((m, idx) => {
            const memberId = `pc-add-share-${idx}`;
            const writeId = `pc-add-share-write-${idx}`;
            const label = escapeHtml(m.email || m.uid);
            return `
              <div class="flex items-center gap-2 text-xs py-0.5">
                <input type="checkbox" class="pc-add-share-member" id="${memberId}" data-uid="${escapeHtml(m.uid)}">
                <label class="flex-1 truncate" for="${memberId}">${label}</label>
                <div class="flex items-center gap-1 text-[10px] text-[var(--muted-text)]">
                  <input type="checkbox" class="pc-add-share-write" id="${writeId}" data-uid="${escapeHtml(m.uid)}" disabled>
                  <label for="${writeId}">Can edit</label>
                </div>
              </div>`;
          }).join('')}`;
        addShareMount.querySelectorAll('.pc-add-share-member').forEach((chk) => {
          chk.addEventListener('change', () => {
            const write = addShareMount.querySelector(`.pc-add-share-write[data-uid="${chk.dataset.uid}"]`);
            if (write) {
              write.disabled = !chk.checked;
              if (!chk.checked) write.checked = false;
            }
          });
        });
      });
      addRow.querySelector('.pc-add')?.addEventListener('click', async () => {
        const name = addRow.querySelector('.pc-new-name')?.value?.trim();
        if (!name) {
          uiAlert('Enter a name.');
          return;
        }
        const shares = [];
        addRow.querySelectorAll('.pc-add-share-member:checked').forEach((chk) => {
          const uid = chk.dataset.uid;
          const write = addRow.querySelector(`.pc-add-share-write[data-uid="${uid}"]`);
          shares.push({ grantee_uid: uid, can_write: !!(write && write.checked) });
        });
        const res = await createCalendar({
          name,
          color: (newPicker && newPicker.getValue()) || DEFAULT_COLOR,
          shares,
        });
        if (!res.ok) {
          uiAlert(res.error || 'Could not create calendar');
          return;
        }
        addRow.querySelector('.pc-new-name').value = '';
        if (newPicker) newPicker.setValue(DEFAULT_COLOR);
        await reload();
      });
      container.appendChild(addRow);
    }

    async function reload() {
      const res = await fetchList();
      if (!res.ok) {
        uiAlert(res.error || 'Could not load calendars');
        return;
      }
      calendars = res.calendars || [];
      if (onChange) await onChange(calendars);
      editingId = null;
      sharingId = null;
      render();
    }

    const ready = reload();

    return {
      refresh: reload,
      ready,
      getCalendars: () => calendars.slice(),
    };
  }

  window.homehubPersonalCalendars = {
    fetchList,
    populateSelect,
    mountManager,
  };
})();
