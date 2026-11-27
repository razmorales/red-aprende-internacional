import tempfile
import unittest
from pathlib import Path
from app import courses, groups

DIRECTOR = dict(id='direction-1', role='international_director', active=True)
COORD = dict(id='coord-mx', role='country_coordinator', active=True, country='MX')
STUDENT = dict(id='student-1', role='student', active=True, country='CO')
DATA = dict(name='Curso piloto', description='Capacitación', objectives='Practicar',
            attendance_min=80, grade_min=70)


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = groups.connect(Path(self.temp.name) / 'test.sqlite3')
        self.course = courses.create(self.db, DIRECTOR, DATA)
        courses.publish(self.db, DIRECTOR, self.course['id'])

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def create(self, country='MX', site='CDMX', **kwargs):
        options = dict(teacher_is_enabled=lambda c, t: t == 'teacher-1')
        options.update(kwargs)
        return groups.create(self.db, dict(COORD, country=country), self.course['id'],
                             'Grupo piloto', country, site, 'teacher-1', 2, **options)

    def test_three_sites_currency_and_timezone(self):
        for country, site, currency, zone in [
            ('MX', 'CDMX', 'MXN', 'America/Mexico_City'),
            ('CO', 'BOG', 'COP', 'America/Bogota'),
            ('ES', 'MAD', 'EUR', 'Europe/Madrid')]:
            with self.subTest(country=country):
                item = self.create(country, site)
                self.assertEqual((item['currency'], item['timezone']), (currency, zone))

    def test_draft_course_cannot_create_group(self):
        draft = courses.create(self.db, DIRECTOR, DATA)
        with self.assertRaises(groups.GroupError):
            groups.create(self.db, COORD, draft['id'], 'Grupo', 'MX', 'CDMX',
                          'teacher-1', 2, teacher_is_enabled=lambda c, t: True)

    def test_foreign_country_cannot_create(self):
        with self.assertRaises(PermissionError):
            groups.create(self.db, COORD, self.course['id'], 'Grupo', 'ES', 'MAD',
                          'teacher-1', 2, teacher_is_enabled=lambda c, t: True)

    def test_invalid_site_and_disabled_teacher(self):
        with self.assertRaises(groups.GroupError):
            self.create('MX', 'MAD')
        with self.assertRaises(groups.GroupError):
            self.create(teacher_is_enabled=lambda c, t: False)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM groups').fetchone()[0], 0)

    def test_price_only_director_and_valid_amount(self):
        item = self.create()
        with self.assertRaises(PermissionError):
            groups.set_price(self.db, COORD, item['id'], '100')
        for amount in ('NaN', '-1', '1.001', True):
            with self.subTest(amount=amount), self.assertRaises(groups.GroupError):
                groups.set_price(self.db, DIRECTOR, item['id'], amount)
        self.assertEqual(groups.set_price(self.db, DIRECTOR, item['id'], '150.25')['price_minor'], 15025)

    def test_open_requires_price_and_locks_course(self):
        item = self.create()
        with self.assertRaises(groups.GroupError):
            groups.open_enrollment(self.db, COORD, item['id'])
        self.assertFalse(courses.load(self.db, self.course['id'])['academic_locked'])
        groups.set_price(self.db, DIRECTOR, item['id'], '100')
        groups.open_enrollment(self.db, COORD, item['id'])
        self.assertTrue(courses.load(self.db, self.course['id'])['academic_locked'])
        self.assertEqual(groups.load(self.db, item['id'])['status'], 'open')
        with self.assertRaises(groups.GroupError):
            groups.set_price(self.db, DIRECTOR, item['id'], '120')
        with self.assertRaises(courses.CourseError):
            courses.update(self.db, DIRECTOR, self.course['id'], dict(DATA, grade_min=90))

    def test_open_rolls_back_on_audit_failure(self):
        item = self.create()
        groups.set_price(self.db, DIRECTOR, item['id'], '100')
        self.db.execute("""CREATE TRIGGER fail_open BEFORE INSERT ON group_events
                        WHEN NEW.action='opened' BEGIN SELECT RAISE(ABORT,'fallo'); END""")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            groups.open_enrollment(self.db, COORD, item['id'])
        self.assertFalse(courses.load(self.db, self.course['id'])['academic_locked'])
        self.assertEqual(groups.load(self.db, item['id'])['status'], 'draft')

    def test_scoped_visibility_and_foreign_open(self):
        mx = self.create()
        es = self.create('ES', 'MAD')
        self.assertEqual(groups.list_groups(self.db, STUDENT), [])
        groups.set_price(self.db, DIRECTOR, es['id'], '40')
        with self.assertRaises(PermissionError):
            groups.open_enrollment(self.db, COORD, es['id'])
        groups.open_enrollment(self.db, dict(COORD, country='ES'), es['id'])
        self.assertEqual([g['id'] for g in groups.list_groups(self.db, STUDENT)], [es['id']])
        self.assertEqual([g['id'] for g in groups.list_groups(self.db, COORD)], [mx['id']])
        admin = dict(id='admin', role='site_admin', active=True, country='MX', site_id='CDMX')
        self.assertEqual([g['id'] for g in groups.list_groups(self.db, admin)], [mx['id']])
        self.assertEqual(len(groups.list_groups(self.db, DIRECTOR)), 2)
        with self.assertRaises(PermissionError):
            groups.list_groups(self.db, dict(STUDENT, active=False))


if __name__ == '__main__':
    unittest.main()
