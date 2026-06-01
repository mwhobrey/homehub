/** Assignment detail: submit work, artifacts, grading */
(function () {
  const root = document.getElementById('assignmentDetailRoot');
  if (!root) return;

  const assignmentId = parseInt(root.dataset.assignmentId, 10);
  const submissionId = parseInt(root.dataset.submissionId, 10);
  const canManage = root.dataset.canManage === '1';

  function toast(msg, isError) {
    if (typeof window.showToast === 'function') window.showToast(msg, isError);
    else alert(msg);
  }

  const submitBtn = document.getElementById('submitWorkBtn');
  if (submitBtn) {
    submitBtn.addEventListener('click', async () => {
      const note = document.getElementById('studentNote')?.value || '';
      try {
        await SchoolAPI.submitWork(assignmentId, { student_note: note });
        toast('Work submitted');
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Submit failed', true);
      }
    });
  }

  const linkForm = document.getElementById('addLinkForm');
  if (linkForm) {
    linkForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(linkForm);
      try {
        await SchoolAPI.addLinkArtifact(submissionId, {
          artifact_type: 'link',
          url: fd.get('url'),
          note: fd.get('note'),
        });
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Add link failed', true);
      }
    });
  }

  const fileInput = document.getElementById('artifactFile');
  const fileBtn = document.getElementById('uploadArtifactBtn');
  if (fileBtn && fileInput) {
    fileBtn.addEventListener('click', async () => {
      const file = fileInput.files?.[0];
      if (!file) {
        toast('Choose a file first', true);
        return;
      }
      try {
        await SchoolAPI.uploadArtifact(submissionId, file, document.getElementById('fileNote')?.value);
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Upload failed', true);
      }
    });
  }

  document.querySelectorAll('[data-delete-artifact]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!confirm('Remove this artifact?')) return;
      try {
        await SchoolAPI.deleteArtifact(btn.dataset.deleteArtifact);
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Delete failed', true);
      }
    });
  });

  const gradeForm = document.getElementById('gradeForm');
  if (gradeForm && canManage) {
    gradeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(gradeForm);
      try {
        await SchoolAPI.gradeSubmission(submissionId, {
          score: fd.get('score') ? parseFloat(fd.get('score')) : null,
          feedback_html: fd.get('feedback_html'),
          revision_requested: fd.get('revision_requested') === 'on',
          completed: fd.get('completed') === 'on',
        });
        toast('Grade saved');
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Grade failed', true);
      }
    });
  }

  const studentPicker = document.getElementById('viewStudentSelect');
  if (studentPicker) {
    studentPicker.addEventListener('change', () => {
      const url = new URL(window.location.href);
      url.searchParams.set('student', studentPicker.value);
      window.location.href = url.toString();
    });
  }
})();
