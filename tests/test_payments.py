import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app import courses, groups, enrollments, payments

DIRECTOR = dict(id='director', active=True, role='international_director')
COORD = dict(id='coord-es', active=True, role='country_coordinator', country='ES')
ADMIN = dict(id='admin-es', active=True, role='site_admin', country='ES', site_id='MAD')
A = dict(id='student-mx', active=True, role='student', country='MX')
B = dict(id='student-co', active=True, role='student', country='CO')
DATA = dict(name='Curso piloto', description='Capacitación', objectives='Practicar',
            attendance_min=80, grade_min=70)
START = datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc)


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = enrollments.connect(Path(self.temp.name) / 'test.sqlite3')
        self.course = courses.create(self.db, DIRECTOR, DATA)
        courses.publish(self.db, DIRECTOR, self.course['id'])
        item = groups.create(self.db, COORD, self.course['id'], 'Madrid',
                             'ES', 'MAD', 'teacher-1', 1,
                             teacher_is_enabled=lambda c, t: True)
        groups.set_price(self.db, DIRECTOR, item['id'], '45.50')
        self.group = groups.open_enrollment(self.db, COORD, item['id'])
        self.first = self.reserve(A)
        self.eid = self.first['enrollment']['id']
        self.pid = self.first['payment']['id']

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def reserve(self, actor, at=START):
        return enrollments.reserve(self.db, actor, self.group['id'], clock=lambda: at)

    def respond(self, outcome='approved', at=START + timedelta(minutes=1), actor=A):
        return payments.respond(self.db, actor, self.pid, outcome, clock=lambda: at)

    def available(self, at=START):
        return enrollments.offer(self.db, A, self.course['id'],
                                 clock=lambda: at)[0]['available']

    def test_approval_confirms_same_seat(self):
        at = START + timedelta(minutes=29, seconds=59)
        result = self.respond(at=at)
        self.assertEqual(result['enrollment']['status'], 'confirmed')
        self.assertEqual(result['payment']['status'], 'approved')
        self.assertEqual(result['enrollment']['id'], self.eid)
        self.assertEqual(result['payment']['id'], self.pid)
        self.assertEqual(self.available(at), 0)
        with self.assertRaises(enrollments.FullGroup):
            self.reserve(B, at)
        self.assertEqual(self.available(START + timedelta(hours=1)), 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM enrollments').fetchone()[0], 1)

    def test_rejection_releases_seat_and_allows_new_attempt(self):
        at = START + timedelta(minutes=1)
        result = self.respond('rejected', at)
        self.assertEqual(result['enrollment']['status'], 'rejected')
        self.assertEqual(result['payment']['status'], 'rejected')
        self.assertEqual(self.available(at), 1)
        retry = self.reserve(A, at)
        self.assertNotEqual(retry['payment']['id'], self.pid)
        self.assertEqual(self.available(at), 0)

    def test_late_approval_after_reallocation(self):
        at = START + timedelta(minutes=31)
        second = self.reserve(B, at)
        result = self.respond(at=at)
        self.assertEqual(result['enrollment']['status'], 'expired')
        self.assertEqual(result['payment']['status'], 'approved_late')
        self.assertEqual(self.available(at), 0)
        other = enrollments.get(self.db, B, second['enrollment']['id'], clock=lambda: at)
        self.assertEqual(other['enrollment']['status'], 'reserved')
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM enrollments WHERE status='confirmed'").fetchone()[0], 0)

    def test_exact_boundary_provisional(self):
        at = START + timedelta(minutes=30)
        result = self.respond(at=at)
        self.assertEqual(result['payment']['status'], 'approved_late')
        self.assertEqual(result['enrollment']['status'], 'expired')
        self.assertEqual(self.available(at), 1)

    def test_payment_snapshot_and_two_profiles(self):
        at = START + timedelta(minutes=1)
        self.respond(at=at)
        student = payments.consult(self.db, A, self.pid, clock=lambda: at)
        admin = payments.consult(self.db, ADMIN, self.pid, clock=lambda: at)
        self.assertEqual(student['payment'], admin['payment'])
        self.assertEqual((admin['payment']['id'], admin['payment']['amount_minor'],
                          admin['payment']['currency']), (self.pid, 4550, 'EUR'))
        with self.assertRaises(groups.GroupError):
            groups.set_price(self.db, DIRECTOR, self.group['id'], '60')

    def test_cancel_confirmed_preserves_original_payment(self):
        at = START + timedelta(minutes=1)
        original = self.respond(at=at)['payment']
        at += timedelta(minutes=1)
        enrollments.cancel(self.db, ADMIN, self.eid, clock=lambda: at)
        result = payments.consult(self.db, A, self.pid, clock=lambda: at)
        self.assertEqual(result['enrollment']['status'], 'cancelled')
        self.assertEqual(result['payment'], original)
        self.assertEqual(self.available(at), 1)

    def test_idempotent_response_and_conflicting_response(self):
        result = self.respond()
        repeat = self.respond(at=START + timedelta(minutes=40))
        self.assertEqual(result, repeat)
        with self.assertRaises(enrollments.EnrollmentError):
            self.respond('rejected')
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM payment_events WHERE action='approved'").fetchone()[0], 1)

    def test_unauthorized_payment_access(self):
        for actor in (B, ADMIN, dict(A, active=False)):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.respond(actor=actor)
        foreign = dict(ADMIN, country='MX', site_id='CDMX')
        for actor in (B, foreign):
            with self.assertRaises(PermissionError):
                payments.consult(self.db, actor, self.pid, clock=lambda: START)
        self.assertEqual(payments.consult(self.db, A, self.pid, clock=lambda: START)
                         ['payment']['status'], 'pending')

    def test_payment_and_confirmation_rollback_together(self):
        self.db.execute("""CREATE TRIGGER fail_confirmation BEFORE UPDATE ON enrollments
                        WHEN NEW.status='confirmed'
                        BEGIN SELECT RAISE(ABORT,'fallo'); END""")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.respond()
        result = payments.consult(self.db, A, self.pid, clock=lambda: START)
        self.assertEqual(result['payment']['status'], 'pending')
        self.assertEqual(result['enrollment']['status'], 'reserved')


if __name__ == '__main__':
    unittest.main()
