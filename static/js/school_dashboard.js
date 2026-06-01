/** School index + class detail helpers */
(function () {
  function toast(msg, isError) {
    if (typeof window.showToast === 'function') window.showToast(msg, isError);
    else alert(msg);
  }

  const createClassForm = document.getElementById('createClassForm');
  if (createClassForm) {
    createClassForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(createClassForm);
      const teacherSelect = createClassForm.querySelector('[name="teacher_ids"]');
      const teacher_ids = teacherSelect
        ? Array.from(teacherSelect.selectedOptions).map((o) => o.value)
        : [];
      if (!teacher_ids.length) {
        toast('Select at least one teacher', true);
        return;
      }
      const studentSelect = createClassForm.querySelector('[name="student_ids"]');
      const student_ids = studentSelect
        ? Array.from(studentSelect.selectedOptions).map((o) => o.value)
        : [];
      try {
        await SchoolAPI.createClass({
          name: fd.get('name'),
          subject: fd.get('subject'),
          term: fd.get('term'),
          teacher_ids,
          student_ids,
        });
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Failed to create class', true);
      }
    });
  }

  const enrollForm = document.getElementById('enrollStudentForm');
  if (enrollForm) {
    enrollForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const classId = enrollForm.dataset.classId;
      const studentSelect = enrollForm.querySelector('[name="student_ids"]');
      const student_ids = studentSelect
        ? Array.from(studentSelect.selectedOptions).map((o) => o.value)
        : [];
      if (!student_ids.length) {
        toast('Select at least one student', true);
        return;
      }
      try {
        await SchoolAPI.enroll(classId, { student_ids, role: 'student' });
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Enroll failed', true);
      }
    });
  }

  document.querySelectorAll('[data-unenroll]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!confirm('Remove this enrollment?')) return;
      try {
        await SchoolAPI.unenroll(btn.dataset.unenroll);
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Remove failed', true);
      }
    });
  });

  const assignmentForm = document.getElementById('createAssignmentForm');
  if (assignmentForm) {
    assignmentForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const classId = assignmentForm.dataset.classId;
      const fd = new FormData(assignmentForm);
      try {
        await SchoolAPI.createAssignment(classId, {
          title: fd.get('title'),
          instructions_html: fd.get('instructions_html'),
          due_at: fd.get('due_at'),
          points_possible: parseFloat(fd.get('points_possible') || '100'),
          status: fd.get('status') || 'assigned',
          category_id: fd.get('category_id') ? parseInt(fd.get('category_id'), 10) : null,
          allow_late: fd.get('allow_late') === 'on',
        });
        window.location.reload();
      } catch (err) {
        toast(err.message || 'Create assignment failed', true);
      }
    });
  }

  const attendanceForm = document.getElementById('attendanceForm');
  if (attendanceForm) {
    attendanceForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const classId = attendanceForm.dataset.classId;
      const date = attendanceForm.querySelector('[name="date"]').value;
      const records = [];
      attendanceForm.querySelectorAll('[data-student-id]').forEach((row) => {
        const sid = row.dataset.studentId;
        const status = row.querySelector('select')?.value || 'present';
        records.push({ student_id: sid, date, status });
      });
      try {
        await SchoolAPI.attendance(classId, { records });
        toast('Attendance saved');
      } catch (err) {
        toast(err.message || 'Attendance failed', true);
      }
    });
  }
})();
