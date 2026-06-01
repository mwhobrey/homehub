/**
 * Full-spectrum color picker: native color input + hex text field.
 */
(function () {
  const HEX_RE = /^#?[0-9a-fA-F]{6}$/;
  const SHORT_RE = /^#?[0-9a-fA-F]{3}$/;

  function normalizeHex(value) {
    if (value == null) return null;
    let raw = String(value).trim();
    if (!raw) return null;
    if (!raw.startsWith('#')) raw = `#${raw}`;
    if (SHORT_RE.test(raw)) {
      const h = raw.replace('#', '');
      raw = `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`;
    }
    if (!HEX_RE.test(raw)) return null;
    return raw.toLowerCase();
  }

  function textColorForBg(hex) {
    const n = normalizeHex(hex);
    if (!n) return '#ffffff';
    const r = parseInt(n.slice(1, 3), 16);
    const g = parseInt(n.slice(3, 5), 16);
    const b = parseInt(n.slice(5, 7), 16);
    const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return lum > 0.55 ? '#111827' : '#ffffff';
  }

  /**
   * @param {HTMLElement} container
   * @param {{ value?: string, label?: string, onChange?: (hex: string|null) => void, allowClear?: boolean }} opts
   */
  function mount(container, opts) {
    if (!container) return null;
    opts = opts || {};
    container.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'flex flex-wrap items-center gap-2';

    if (opts.label) {
      const lbl = document.createElement('span');
      lbl.className = 'text-xs font-semibold text-gray-600';
      lbl.textContent = opts.label;
      wrap.appendChild(lbl);
    }

    const native = document.createElement('input');
    native.type = 'color';
    native.className = 'w-10 h-9 p-0 border rounded cursor-pointer bg-white';
    native.title = 'Pick any color';

    const text = document.createElement('input');
    text.type = 'text';
    text.className = 'w-24 h-9 border rounded px-2 text-xs font-mono';
    text.placeholder = '#2563eb';
    text.maxLength = 7;
    text.autocomplete = 'off';
    text.spellcheck = false;

    const swatch = document.createElement('span');
    swatch.className = 'inline-block w-6 h-6 rounded border flex-shrink-0';
    swatch.setAttribute('aria-hidden', 'true');

    let current = normalizeHex(opts.value) || '#2563eb';

    function apply(hex, silent) {
      const n = normalizeHex(hex);
      if (!n) return false;
      current = n;
      native.value = n;
      text.value = n;
      swatch.style.background = n;
      swatch.style.borderColor = n;
      if (!silent && typeof opts.onChange === 'function') opts.onChange(n);
      return true;
    }

    apply(current, true);

    native.addEventListener('input', () => apply(native.value));
    text.addEventListener('change', () => {
      const n = normalizeHex(text.value);
      if (n) apply(n);
      else text.value = current;
    });
    text.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        text.blur();
      }
    });

    wrap.appendChild(native);
    wrap.appendChild(text);
    wrap.appendChild(swatch);

    if (opts.allowClear) {
      const clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'text-xs text-gray-500 hover:text-gray-800 underline';
      clearBtn.textContent = 'Clear';
      clearBtn.addEventListener('click', () => {
        current = null;
        text.value = '';
        swatch.style.background = 'transparent';
        if (typeof opts.onChange === 'function') opts.onChange(null);
      });
      wrap.appendChild(clearBtn);
    }

    container.appendChild(wrap);

    return {
      getValue() {
        return normalizeHex(text.value) || current;
      },
      setValue(hex) {
        if (hex) apply(hex, true);
        else {
          current = null;
          text.value = '';
          swatch.style.background = 'transparent';
        }
      },
      normalizeHex,
      textColorForBg,
    };
  }

  window.homehubColorPicker = { mount, normalizeHex, textColorForBg };
})();
