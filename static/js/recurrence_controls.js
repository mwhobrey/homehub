/**
 * Shared recurrence UI: "Repeat forever" toggles optional end date.
 */
window.homehubRecurrence = (function () {
  function foreverInput(form) {
    return form && form.querySelector('[name=rec_repeat_forever]');
  }

  function endInput(form) {
    return form && form.querySelector('[name=rec_end_date]');
  }

  function syncEndDateDisabled(form) {
    const forever = foreverInput(form);
    const end = endInput(form);
    if (!forever || !end) return;
    const on = !!forever.checked;
    end.disabled = on;
    if (on) end.value = '';
    const wrap = end.closest('[data-rec-end-wrap]');
    if (wrap) wrap.classList.toggle('opacity-50', on);
  }

  function bind(form) {
    if (!form || form.dataset.recurrenceBound === '1') return;
    const forever = foreverInput(form);
    const end = endInput(form);
    if (!forever || !end) return;
    form.dataset.recurrenceBound = '1';
    forever.addEventListener('change', () => syncEndDateDisabled(form));
    end.addEventListener('change', () => {
      if (end.value) forever.checked = false;
      syncEndDateDisabled(form);
    });
    syncEndDateDisabled(form);
  }

  function applyRuleEndDate(form, endDate) {
    const forever = foreverInput(form);
    const end = endInput(form);
    if (!forever) return;
    if (!endDate) {
      forever.checked = true;
      if (end) end.value = '';
    } else {
      forever.checked = false;
      if (end) end.value = endDate;
    }
    syncEndDateDisabled(form);
  }

  /** Value for API: null = no end (forever), string = until date. */
  function endDateForPayload(form) {
    const forever = foreverInput(form);
    if (forever && forever.checked) return null;
    const end = endInput(form);
    const v = end && end.value;
    return v ? v : null;
  }

  return { bind, applyRuleEndDate, endDateForPayload, syncEndDateDisabled };
})();
