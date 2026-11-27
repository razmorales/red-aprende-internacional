import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from app import courses, groups, enrollments, group_catalog

D = dict(id='director', role='international_director', active=True)
A = dict(id='student-mx', role='student', active=True, country='MX')
B = dict(id='student-co', role='student', active=True, country='CO')
START = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = enrollments.connect(Path(self.tmp.name) / 'test.sqlite3')
        c = courses.create(self.db, D, dict(name='Piloto', description='Prueba',
            objectives='Practicar', attendance_min=80, grade_min=70))
        self.course = courses.publish(self.db, D, c['id'])
        self.mx = self.make('MX', 'CDMX', 'teacher-mx', True)
        self.es = self.make('ES', 'MAD', 'teacher-es', True)
        self.draft = self.make('ES', 'MAD', 'teacher-es', False)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def make(self, country, site, teacher, opened):
        actor = dict(id='coord-'+country, role='country_coordinator', active=True, country=country)
        item = groups.create(self.db, actor, self.course['id'], 'Grupo '+site, country,
                             site, teacher, 1, teacher_is_enabled=lambda c,t: True)
        groups.set_price(self.db, D, item['id'], '120')
        if opened:
            groups.open_enrollment(self.db, actor, item['id'])
        return item['id']

    def query(self, actor=A, at=START, **kwargs):
        return group_catalog.list_available(self.db, actor, clock=lambda: at, **kwargs)

    def test_scoped_catalog(self):
        self.assertEqual({x['id'] for x in self.query()}, {self.mx,self.es})
        self.assertEqual(len(self.query(D)), 3)
        admin = dict(id='admin', active=True, role='site_admin', country='MX', site_id='CDMX')
        self.assertEqual([x['id'] for x in self.query(admin)], [self.mx])
        coord = dict(id='coord-es', active=True, role='country_coordinator', country='ES')
        self.assertEqual({x['id'] for x in self.query(coord)}, {self.es,self.draft})
        teacher = dict(id='teacher-es', active=True, role='teacher', country='MX')
        self.assertEqual({x['id'] for x in self.query(teacher)}, {self.es,self.draft})
        with self.assertRaises(PermissionError):
            self.query(dict(A, active=False))

    def test_course_site_and_currency_visible(self):
        row = next(x for x in self.query() if x['id'] == self.es)
        self.assertEqual((row['course_name'],row['site_name'],row['timezone'],
                          row['price_minor'],row['currency']),
                         ('Piloto','Madrid','Europe/Madrid',12000,'EUR'))

    def test_read_only_and_updated_capacity(self):
        enrollments.reserve(self.db, A, self.mx, clock=lambda: START)
        before = list(self.db.iterdump())
        row = next(x for x in self.query() if x['id'] == self.mx)
        self.assertEqual(row['available'], 0)
        self.assertTrue(row['is_full'])
        self.assertEqual([x['id'] for x in self.query(only_available=True)], [self.es])
        later = START + timedelta(minutes=31)
        row = next(x for x in self.query(at=later) if x['id'] == self.mx)
        self.assertEqual(row['available'], 1)
        self.assertEqual(before, list(self.db.iterdump()))

    def test_empty_filter_and_no_mutation(self):
        before = list(self.db.iterdump())
        self.assertEqual(self.query(course_id='not-found'), [])
        self.assertEqual(before, list(self.db.iterdump()))


if __name__ == '__main__':
    unittest.main()
