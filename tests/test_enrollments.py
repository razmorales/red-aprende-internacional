import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from app import courses, groups, enrollments

DIRECTOR = dict(id='director', active=True, role='international_director')
COORD = dict(id='coord-es', active=True, role='country_coordinator', country='ES')
ADMIN = dict(id='admin-es', active=True, role='site_admin', country='ES', site_id='MAD')
A = dict(id='student-mx', active=True, role='student', country='MX')
B = dict(id='student-co', active=True, role='student', country='CO')
DATA = dict(name='Curso piloto', description='Capacitación', objectives='Practicar',
            attendance_min=80, grade_min=70)
START = datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc)


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.db = enrollments.connect(self.path)
        self.course = courses.create(self.db, DIRECTOR, DATA)
        courses.publish(self.db, DIRECTOR, self.course['id'])
        self.group = self.make_group('Madrid', 1)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def make_group(self, name, capacity, course_id=None):
        group = groups.create(self.db, COORD, course_id or self.course['id'], name,
                              'ES', 'MAD', 'teacher-1', capacity,
                              teacher_is_enabled=lambda c, t: True)
        groups.set_price(self.db, DIRECTOR, group['id'], '45.50')
        return groups.open_enrollment(self.db, COORD, group['id'])

    def reserve(self, actor=A, moment=START):
        return enrollments.reserve(self.db, actor, self.group['id'], clock=lambda: moment)

    def test_reservation_and_payment_snapshot(self):
        result = self.reserve()
        e, p = result['enrollment'], result['payment']
        self.assertEqual(e['status'], 'reserved')
        self.assertEqual(datetime.fromisoformat(e['expires_at']) -
                         datetime.fromisoformat(e['reserved_at']), timedelta(minutes=30))
        self.assertEqual((p['status'], p['amount_minor'], p['currency'], p['simulated']),
                         ('pending', 4550, 'EUR', 1))
        self.assertEqual(p['enrollment_id'], e['id'])
        self.assertEqual(enrollments.offer(self.db, A, self.course['id'],
                                         clock=lambda: START)[0]['available'], 0)

    def test_full_group_alternatives_only_same_course(self):
        alt = self.make_group('Alternativo', 2)
        other = courses.create(self.db, DIRECTOR, dict(DATA, name='Otro curso'))
        courses.publish(self.db, DIRECTOR, other['id'])
        self.make_group('Otro grupo', 2, other['id'])
        self.reserve()
        with self.assertRaises(enrollments.FullGroup) as ctx:
            self.reserve(B)
        self.assertEqual([g['id'] for g in ctx.exception.alternatives], [alt['id']])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM payment_attempts').fetchone()[0], 1)

    def test_concurrent_last_seat(self):
        gate = Barrier(2)

        def attempt(actor):
            db = enrollments.connect(self.path)
            try:
                gate.wait(timeout=10)
                try:
                    result = enrollments.reserve(db, actor, self.group['id'],
                                                 clock=lambda: START)
                    return ('reserved', result['enrollment']['student_id'])
                except enrollments.FullGroup:
                    return ('full', actor['id'])
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, actor) for actor in (A, B)]
            outcomes = [future.result(timeout=20) for future in futures]
        self.assertCountEqual([o[0] for o in outcomes], ['reserved', 'full'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM payment_attempts').fetchone()[0], 1)
        self.assertEqual(enrollments.offer(self.db, A, self.course['id'],
                                         clock=lambda: START)[0]['available'], 0)

    def test_expiration_at_boundary_and_reallocation(self):
        first = self.reserve()
        before = START + timedelta(minutes=30, microseconds=-1)
        with self.assertRaises(enrollments.FullGroup):
            self.reserve(B, before)
        at = START + timedelta(minutes=30)
        self.assertEqual(enrollments.offer(self.db, B, self.course['id'],
                                         clock=lambda: at)[0]['available'], 1)
        second = self.reserve(B, at)
        old = enrollments.get(self.db, A, first['enrollment']['id'], clock=lambda: at)
        self.assertEqual(old['enrollment']['status'], 'expired')
        self.assertEqual(old['payment']['status'], 'expired')
        self.assertNotEqual(old['payment']['id'], second['payment']['id'])

    def test_duplicate_active_reservation_provisional(self):
        enrollments.set_capacity(self.db, ADMIN, self.group['id'], 2, clock=lambda: START)
        self.reserve()
        with self.assertRaises(enrollments.EnrollmentError):
            self.reserve()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0], 1)

    def test_scoped_read_and_cancel(self):
        item = self.reserve()
        eid = item['enrollment']['id']
        foreign = dict(ADMIN, country='MX', site_id='CDMX')
        for actor in (B, foreign, dict(A, active=False)):
            with self.assertRaises(PermissionError):
                enrollments.get(self.db, actor, eid, clock=lambda: START)
        with self.assertRaises(PermissionError):
            enrollments.cancel(self.db, foreign, eid, clock=lambda: START)
        self.assertEqual(enrollments.cancel(self.db, ADMIN, eid,
                                           clock=lambda: START)['status'], 'cancelled')
        after = enrollments.get(self.db, A, eid, clock=lambda: START)
        self.assertEqual(after['payment']['status'], 'cancelled')
        self.assertEqual(after['payment']['amount_minor'], 4550)
        self.assertEqual(self.reserve(B)['enrollment']['status'], 'reserved')

    def test_capacity_cannot_drop_below_occupied(self):
        enrollments.set_capacity(self.db, ADMIN, self.group['id'], 2, clock=lambda: START)
        self.reserve()
        self.reserve(B)
        with self.assertRaises(enrollments.EnrollmentError):
            enrollments.set_capacity(self.db, ADMIN, self.group['id'], 1, clock=lambda: START)
        self.assertEqual(groups.load(self.db, self.group['id'])['capacity'], 2)

    def test_atomic_rollback_on_payment_creation_failure(self):
        self.db.execute("""CREATE TRIGGER fail_payment BEFORE INSERT ON payment_attempts
                        BEGIN SELECT RAISE(ABORT,'fallo'); END""")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.reserve()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM enrollment_events').fetchone()[0], 0)
        self.assertEqual(enrollments.offer(self.db, A, self.course['id'],
                                         clock=lambda: START)[0]['available'], 1)


if __name__ == '__main__':
    unittest.main()
