/**
 * Household reminder/event categories — styles, API, and Setup manager UI.
 */
(function () {
  const STYLE_ID = 'reminder-category-styles';
  const DEFAULT_COLOR = '#2563eb';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function safeKey(key) {
    return String(key || '').replace(/[^a-zA-Z0-9_-]/g, '');
  }

  function applyStyles(categories) {
    let css = '';
    (categories || []).forEach((c) => {
      if (!c || !c.key) return;
      const key = safeKey(c.key);
      const col = c.color || DEFAULT_COLOR;
      css += `.rem-cat-dot-${key}{background:${col} !important;}`;
    });
    css += '.rem-cat-pill{transition:background-color .15s,box-shadow .15s;}';
    css += '.rem-cat-pill:hover{box-shadow:0 0 0 1px rgba(var(--primary-rgb,37,99,235),0.35);}';
    let el = document.getElementById(STYLE_ID);
    if (!el) {
      el = document.createElement('style');
      el.id = STYLE_ID;
      document.head.appendChild(el);
    }
    el.textContent = css;
  }

  function populateSelect(selectEl, categories, selectedKey) {
    if (!selectEl) return;
    const opts = ['<option value="">—</option>'];
    (categories || []).forEach((c) => {
      const sel = selectedKey && c.key === selectedKey ? ' selected' : '';
      opts.push(
        `<option value="${escapeHtml(c.key)}" data-color="${escapeHtml(c.color || DEFAULT_COLOR)}"${sel}>${escapeHtml(c.label || c.key)}</option>`
      );
    });
    selectEl.innerHTML = opts.join('');
  }

  async function fetchList() {
    const r = await fetch('/api/reminder-categories');
    return r.json();
  }

  async function saveList(categories) {
    const r = await fetch('/api/reminder-categories', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories }),
    });
    return r.json();
  }

  function slugFromLabel(label) {
    const raw = String(label || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
    let key = raw || 'category';
    if (!/^[a-z]/.test(key)) key = `cat_${key}`;
    return key.slice(0, 64);
  }

  function mountManager(container, options) {
    if (!container) return;
    const onChange = typeof options?.onChange === 'function' ? options.onChange : null;
    let categories = Array.isArray(options?.initial) ? options.initial.slice() : [];
    let editingKey = null;

    function render() {
      container.innerHTML = '';
      if (!categories.length) {
        const empty = document.createElement('p');
        empty.className = 'text-[10px] text-gray-500';
        empty.textContent = 'No categories yet. Add one below.';
        container.appendChild(empty);
      }
      categories.forEach((cat) => {
        const row = document.createElement('div');
        row.className = 'border rounded p-2 space-y-2';
        row.dataset.key = cat.key;
        const isEditing = editingKey === cat.key;
        if (isEditing) {
          row.innerHTML = `
            <label class="block text-[10px] font-semibold">Label</label>
            <input type="text" class="cat-edit-label w-full h-8 border rounded px-2 text-xs" value="${escapeHtml(cat.label || '')}" maxlength="48">
            <p class="text-[10px] text-gray-500">Key: <code>${escapeHtml(cat.key)}</code></p>
            <div class="cat-edit-color"></div>
            <div class="flex gap-2">
              <button type="button" class="cat-save px-2 py-1 text-xs rounded bg-blue-600 text-white">Save</button>
              <button type="button" class="cat-cancel px-2 py-1 text-xs rounded border">Cancel</button>
            </div>`;
          const colorMount = row.querySelector('.cat-edit-color');
          let picker = null;
          if (window.homehubColorPicker && colorMount) {
            picker = window.homehubColorPicker.mount(colorMount, {
              value: cat.color || DEFAULT_COLOR,
              label: 'Color',
            });
          }
          row.querySelector('.cat-save')?.addEventListener('click', () => {
            const label = row.querySelector('.cat-edit-label')?.value?.trim();
            if (!label) {
              window.alert('Label is required.');
              return;
            }
            cat.label = label;
            if (picker) cat.color = picker.getValue() || cat.color;
            editingKey = null;
            persist();
          });
          row.querySelector('.cat-cancel')?.addEventListener('click', () => {
            editingKey = null;
            render();
          });
        } else {
          const bg = cat.color || DEFAULT_COLOR;
          row.innerHTML = `
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="w-3 h-3 rounded-full flex-shrink-0" style="background:${escapeHtml(bg)}"></span>
                <span class="font-medium truncate">${escapeHtml(cat.label || cat.key)}</span>
              </div>
              <div class="flex gap-1 flex-shrink-0">
                <button type="button" class="cat-edit px-2 py-0.5 text-xs rounded border">Edit</button>
                <button type="button" class="cat-delete px-2 py-0.5 text-xs rounded border border-red-300 text-red-700">Delete</button>
              </div>
            </div>`;
          row.querySelector('.cat-edit')?.addEventListener('click', () => {
            editingKey = cat.key;
            render();
          });
          row.querySelector('.cat-delete')?.addEventListener('click', () => {
            if (!window.confirm(`Delete category "${cat.label || cat.key}"? Existing events keep the key but may look uncategorized.`)) {
              return;
            }
            categories = categories.filter((c) => c.key !== cat.key);
            persist();
          });
        }
        container.appendChild(row);
      });

      const addRow = document.createElement('div');
      addRow.className = 'border border-dashed rounded p-2 space-y-2 mt-2';
      addRow.innerHTML = `
        <p class="text-[10px] font-semibold">Add category</p>
        <input type="text" class="cat-new-label w-full h-8 border rounded px-2 text-xs" placeholder="e.g. Vet visits" maxlength="48">
        <div class="cat-new-color"></div>
        <button type="button" class="cat-add px-2 py-1 text-xs rounded bg-blue-600 text-white">Add</button>`;
      let newPicker = null;
      const newColorMount = addRow.querySelector('.cat-new-color');
      if (window.homehubColorPicker && newColorMount) {
        newPicker = window.homehubColorPicker.mount(newColorMount, {
          value: DEFAULT_COLOR,
          label: 'Color',
        });
      }
      addRow.querySelector('.cat-add')?.addEventListener('click', () => {
        const label = addRow.querySelector('.cat-new-label')?.value?.trim();
        if (!label) {
          window.alert('Enter a label.');
          return;
        }
        let key = slugFromLabel(label);
        if (categories.some((c) => c.key === key)) {
          let n = 2;
          while (categories.some((c) => c.key === `${key}_${n}`)) n += 1;
          key = `${key}_${n}`.slice(0, 64);
        }
        categories.push({
          key,
          label,
          color: (newPicker && newPicker.getValue()) || DEFAULT_COLOR,
        });
        addRow.querySelector('.cat-new-label').value = '';
        if (newPicker) newPicker.setValue(DEFAULT_COLOR);
        persist();
      });
      container.appendChild(addRow);
    }

    async function persist() {
      const res = await saveList(categories);
      if (!res.ok) {
        window.alert(res.error || 'Could not save categories');
        return;
      }
      categories = res.categories || categories;
      applyStyles(categories);
      if (onChange) await onChange(categories);
      editingKey = null;
      render();
    }

    applyStyles(categories);
    render();

    return {
      refresh: async () => {
        const res = await fetchList();
        if (res.ok) {
          categories = res.categories || [];
          applyStyles(categories);
          if (onChange) await onChange(categories);
          render();
        }
      },
    };
  }

  window.homehubReminderCategories = {
    applyStyles,
    populateSelect,
    fetchList,
    saveList,
    mountManager,
  };
})();
