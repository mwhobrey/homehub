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
  return {list, create, update, removeMany, updateRule, deleteRule, resolveConflict};
})();

window.calendarSyncApi = (function(){
  async function status(){
    const r = await fetch('/api/calendar/status');
    return r.json();
  }
  async function writableCalendars(){
    const r = await fetch('/api/calendar/writable-calendars');
    return r.json();
  }
  async function calendars(){
    const r = await fetch('/api/calendar/calendars');
    return r.json();
  }
  async function patchCalendar(id, data){
    const r = await fetch('/api/calendar/calendars/'+id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    return r.json();
  }
  async function putShares(id, shares){
    const r = await fetch('/api/calendar/calendars/'+id+'/shares', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({shares})});
    return r.json();
  }
  async function displayPrefs(prefs){
    const r = await fetch('/api/calendar/display-prefs', {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({prefs})});
    return r.json();
  }
  async function syncNow(){
    const r = await fetch('/api/calendar/sync', {method:'POST'});
    return r.json();
  }
  async function disconnect(removeGoogleReminders){
    const r = await fetch('/api/calendar/disconnect', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({remove_google_reminders: !!removeGoogleReminders})});
    return r.json();
  }
  return {status, writableCalendars, calendars, patchCalendar, putShares, displayPrefs, syncNow, disconnect};
})();
