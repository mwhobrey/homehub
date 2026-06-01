/** School module API client */
(function (global) {
  const JSON_HEADERS = { 'Content-Type': 'application/json', Accept: 'application/json' };

  async function parseResponse(res) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      const err = new Error(data.error || res.statusText || 'request_failed');
      err.code = data.error;
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function get(path) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    return parseResponse(res);
  }

  async function send(method, path, body) {
    const res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: JSON_HEADERS,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return parseResponse(res);
  }

  const SchoolAPI = {
    dashboard: () => get('/api/school/dashboard'),
    listClasses: () => get('/api/school/classes'),
    createClass: (payload) => send('POST', '/api/school/classes', payload),
    updateClass: (id, payload) => send('PATCH', `/api/school/classes/${id}`, payload),
    deleteClass: (id) => send('DELETE', `/api/school/classes/${id}`),
    listEnrollments: (classId) => get(`/api/school/classes/${classId}/enrollments`),
    enroll: (classId, payload) => send('POST', `/api/school/classes/${classId}/enrollments`, payload),
    unenroll: (enrollmentId) => send('DELETE', `/api/school/enrollments/${enrollmentId}`),
    listCategories: (classId) => get(`/api/school/classes/${classId}/categories`),
    createCategory: (classId, payload) => send('POST', `/api/school/classes/${classId}/categories`, payload),
    listAssignments: (classId) => get(`/api/school/classes/${classId}/assignments`),
    createAssignment: (classId, payload) => send('POST', `/api/school/classes/${classId}/assignments`, payload),
    updateAssignment: (id, payload) => send('PATCH', `/api/school/assignments/${id}`, payload),
    deleteAssignment: (id) => send('DELETE', `/api/school/assignments/${id}`),
    submitWork: (assignmentId, payload) => send('POST', `/api/school/assignments/${assignmentId}/submit`, payload),
    addLinkArtifact: (submissionId, payload) => send('POST', `/api/school/submissions/${submissionId}/artifacts`, payload),
    uploadArtifact: async (submissionId, file, note) => {
      const fd = new FormData();
      fd.append('file', file);
      if (note) fd.append('note', note);
      const res = await fetch(`/api/school/submissions/${submissionId}/artifacts`, {
        method: 'POST',
        credentials: 'same-origin',
        body: fd,
      });
      return parseResponse(res);
    },
    deleteArtifact: (id) => send('DELETE', `/api/school/artifacts/${id}`),
    gradeSubmission: (submissionId, payload) => send('POST', `/api/school/submissions/${submissionId}/grade`, payload),
    attendance: (classId, payload) => send('POST', `/api/school/classes/${classId}/attendance`, payload),
    getAttendance: (classId, date) => get(`/api/school/classes/${classId}/attendance?date=${encodeURIComponent(date)}`),
    gradebook: (classId) => get(`/api/school/classes/${classId}/gradebook`),
    analytics: (classId) => get(`/api/school/classes/${classId}/analytics`),
  };

  global.SchoolAPI = SchoolAPI;
})(typeof window !== 'undefined' ? window : globalThis);
