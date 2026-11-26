import tempfile
import unittest
from pathlib import Path
from app import courses

DIRECTOR = {'id': 'direction-1', 'active': True, 'role': 'international_director'}
STUDENT = {'id': 'student-1', 'active': True, 'role': 'student'}
DATA = dict(name='Curso piloto', description='Capacitación internacional',
            objectives='Aplicar los conceptos del curso', attendance_min=80, grade_min=70)


class CourseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.db = courses.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_create_persists_after_reopening(self):
        item = courses.create(self.db, DIRECTOR, DATA)
        self.db.close()
        self.db = courses.connect(self.path)
        self.assertEqual(courses.load(self.db, item['id'])['attendance_min'], '80')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM course_events').fetchone()[0], 1)

    def test_unauthorized_create_does_not_write(self):
        with self.assertRaises(PermissionError):
            courses.create(self.db, STUDENT, DATA)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM courses').fetchone()[0], 0)

    def test_invalid_values_do_not_write(self):
        for value in (-1, 101, True, 'NaN', 'Infinity', ''):
            with self.subTest(value=value), self.assertRaises(courses.CourseError):
                courses.create(self.db, DIRECTOR, dict(DATA, grade_min=value))
        with self.assertRaises(courses.CourseError):
            courses.create(self.db, DIRECTOR, dict(DATA, name=' '))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM courses').fetchone()[0], 0)

    def test_draft_update_records_before_and_after(self):
        item = courses.create(self.db, DIRECTOR, DATA)
        updated = courses.update(self.db, DIRECTOR, item['id'], dict(DATA, name='Nuevo nombre'))
        self.assertEqual(updated['name'], 'Nuevo nombre')
        event = self.db.execute("SELECT * FROM course_events WHERE action='updated'").fetchone()
        self.assertIn('Curso piloto', event['before_json'])
        self.assertIn('Nuevo nombre', event['after_json'])

    def test_publish_is_idempotent_and_visible(self):
        item = courses.create(self.db, DIRECTOR, DATA)
        self.assertEqual(courses.list_courses(self.db, STUDENT), [])
        courses.publish(self.db, DIRECTOR, item['id'])
        courses.publish(self.db, DIRECTOR, item['id'])
        self.assertEqual(len(courses.list_courses(self.db, STUDENT)), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM course_events WHERE action='published'").fetchone()[0], 1)

    def test_locked_update_rejected_without_mutation(self):
        item = courses.create(self.db, DIRECTOR, DATA)
        courses.publish(self.db, DIRECTOR, item['id'])
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            courses.lock_academic_criteria(self.db, DIRECTOR, item['id'])
        with self.assertRaises(courses.CourseError):
            courses.update(self.db, DIRECTOR, item['id'], dict(DATA, attendance_min=1))
        self.assertEqual(courses.load(self.db, item['id'])['attendance_min'], '80')

    def test_published_criteria_editable_before_enrollment(self):
        item = courses.create(self.db, DIRECTOR, DATA)
        courses.publish(self.db, DIRECTOR, item['id'])
        updated = courses.update(self.db, DIRECTOR, item['id'], dict(DATA, grade_min=75))
        self.assertEqual(updated['grade_min'], '75')

    def test_enrollment_failure_rolls_back_criteria_lock(self):
        item = courses.create(self.db, DIRECTOR, DATA)
        courses.publish(self.db, DIRECTOR, item['id'])
        with self.assertRaises(RuntimeError):
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                courses.lock_academic_criteria(self.db, DIRECTOR, item['id'])
                raise RuntimeError('La apertura del grupo falló')
        self.assertFalse(courses.load(self.db, item['id'])['academic_locked'])

    def test_unknown_course_does_not_add_events(self):
        with self.assertRaises(courses.CourseError):
            courses.publish(self.db, DIRECTOR, 'missing')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM course_events').fetchone()[0], 0)

    def test_inactive_user_is_denied(self):
        with self.assertRaises(PermissionError):
            courses.list_courses(self.db, dict(DIRECTOR, active=False))


if __name__ == '__main__':
    unittest.main()
