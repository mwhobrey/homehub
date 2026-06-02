// Phase 2 client: basic fetch helpers (non-invasive). Future enhancements will integrate UI.
window.remindersApi = (function(){
  async function list(scope, dateStr){
    const params = new URLSearchParams({scope: scope||'day', date: dateStr});
    const r = await fetch('/api/reminders?'+params.toString());
    return r.json();
  }
  async function create(data){
    const r = await fetch('/api/reminders', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return r.json();
  }
  async function update(id, data){
    const r = await fetch('/api/reminders/'+id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return r.json();
  }
  async function removeMany(ids, creator){
    const r = await fetch('/api/reminders', {method:'DELETE', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ids, creator})});
    return r.json();
  }
  async function updateRule(id, data){
    const r = await fetch('/api/recurring_rules/'+id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return r.json();
  }
  async function deleteRule(id, creator){
    const r = await fetch('/api/recurring_rules/'+id, {method:'DELETE', headers:{'Content-Type':'application/json'}, body: JSON.stringify({creator})});
    return r.json();
  }
  async function resolveConflict(id, resolution){
    const r = await fetch('/api/reminders/'+id+'/resolve-conflict', {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({resolution})});
    return r.json();
  }
  async function patchOccurrence(ruleId, data){
    const r = await fetch('/api/recurring_rules/'+ruleId+'/occurrence', {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return r.json();
  }
  return {list, create, update, removeMany, updateRule, deleteRule, resolveConflict, patchOccurrence};
})();

window.calendarSyncApi = (function(){
  async function parseJsonSafe(response){
    const ct = response.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      return { ok: false, error: `non_json_response_${response.status}` };
    }
    try {
      return await response.json();
    } catch (_) {
      return { ok: false, error: `invalid_json_response_${response.status}` };
    }
  }
  async function status(){
    const r = await fetch('/api/calendar/status');
    return parseJsonSafe(r);
  }
  async function writableCalendars(){
    const r = await fetch('/api/calendar/writable-calendars');
    return parseJsonSafe(r);
  }
  async function calendars(){
    const r = await fetch('/api/calendar/calendars');
    return parseJsonSafe(r);
  }
  async function patchCalendar(id, data){
    const r = await fetch('/api/calendar/calendars/'+id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return parseJsonSafe(r);
  }
  async function putShares(id, shares){
    const r = await fetch('/api/calendar/calendars/'+id+'/shares', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({shares})});
    return parseJsonSafe(r);
  }
  async function displayPrefs(prefs){
    const r = await fetch('/api/calendar/display-prefs', {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({prefs})});
    return parseJsonSafe(r);
  }
  async function syncNow(){
    const r = await fetch('/api/calendar/sync', {method:'POST'});
    return parseJsonSafe(r);
  }
  async function disconnect(removeGoogleReminders){
    const r = await fetch('/api/calendar/disconnect', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({remove_google_reminders: !!removeGoogleReminders})});
    return parseJsonSafe(r);
  }
  async function syncMode(mode){
    const r = await fetch('/api/calendar/sync-mode', {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mode})});
    return parseJsonSafe(r);
  }
  async function importOptions(){
    const r = await fetch('/api/calendar/import/options');
    return parseJsonSafe(r);
  }
  async function importPreview(selections){
    const r = await fetch('/api/calendar/import/preview', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({selections})});
    return parseJsonSafe(r);
  }
  async function importCommit(selections){
    const r = await fetch('/api/calendar/import/commit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({selections})});
    return parseJsonSafe(r);
  }
  async function patchImportMapping(id, data){
    const r = await fetch('/api/calendar/import/mappings/'+id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return parseJsonSafe(r);
  }
  return {status, writableCalendars, calendars, patchCalendar, putShares, displayPrefs, syncNow, disconnect, syncMode, importOptions, importPreview, importCommit, patchImportMapping};
})();
