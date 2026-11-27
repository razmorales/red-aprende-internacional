"""Reservas e inscripciones. Identidad y reloj controlados por el servidor."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app import groups

RESERVATION_MINUTES = 30


class EnrollmentError(ValueError):
    pass


class FullGroup(EnrollmentError):
    def __init__(self, alternatives):
        super().__init__('No hay cupo disponible en este grupo.')
        self.alternatives = alternatives


def connect(path):
    db = groups.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL REFERENCES groups(id),
            student_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN
                ('reserved','confirmed','rejected','expired','cancelled')),
            reserved_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS enrollment_group_status
            ON enrollments(group_id,status,expires_at);
        CREATE TABLE IF NOT EXISTS payment_attempts (
            id TEXT PRIMARY KEY,
            enrollment_id TEXT NOT NULL UNIQUE REFERENCES enrollments(id),
            amount_minor INTEGER NOT NULL CHECK(amount_minor >= 0),
            currency TEXT NOT NULL CHECK(currency IN ('MXN','COP','EUR')),
            status TEXT NOT NULL CHECK(status IN
                ('pending','approved','rejected','expired','approved_late','cancelled')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            responded_at TEXT,
            simulated INTEGER NOT NULL DEFAULT 1 CHECK(simulated=1)
        );
        CREATE TABLE IF NOT EXISTS enrollment_events (
            id INTEGER PRIMARY KEY,
            enrollment_id TEXT NOT NULL REFERENCES enrollments(id),
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payment_events (
            id INTEGER PRIMARY KEY,
            payment_id TEXT NOT NULL REFERENCES payment_attempts(id),
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
    """)
    return db


def instant(clock=None):
    value = clock() if clock is not None else datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError('El reloj debe incluir zona horaria.')
    return value.astimezone(timezone.utc)


def stamp(value):
    return value.isoformat(timespec='microseconds')


def _load(db, enrollment_id):
    row = db.execute('SELECT * FROM enrollments WHERE id=?', (enrollment_id,)).fetchone()
    if row is None:
        raise EnrollmentError('Inscripción inexistente.')
    return dict(row)


def _payment(db, enrollment_id):
    row = db.execute('SELECT * FROM payment_attempts WHERE enrollment_id=?',
                     (enrollment_id,)).fetchone()
    if row is None:
        raise EnrollmentError('Intento de pago inexistente.')
    return dict(row)


def _event(db, table, actor_id, action, before, after, at):
    if table not in ('enrollment', 'payment'):
        raise ValueError('Tipo de evento inválido.')
    db.execute(f"""INSERT INTO {table}_events
        ({table}_id,actor_id,action,before_json,after_json,occurred_at)
        VALUES (?,?,?,?,?,?)""",
        (after['id'], actor_id, action,
         json.dumps(before, ensure_ascii=False) if before is not None else None,
         json.dumps(after, ensure_ascii=False), at))


def _enrollment_status(db, before, status, actor_id, at):
    db.execute('UPDATE enrollments SET status=?,updated_at=? WHERE id=?',
               (status, at, before['id']))
    after = _load(db, before['id'])
    _event(db, 'enrollment', actor_id, status, before, after, at)
    return after


def _payment_status(db, before, status, actor_id, at, responded_at=None):
    db.execute("""UPDATE payment_attempts SET status=?,updated_at=?,responded_at=?
        WHERE id=?""", (status, at, responded_at or before['responded_at'], before['id']))
    after = _payment(db, before['enrollment_id'])
    _event(db, 'payment', actor_id, status, before, after, at)
    return after


def _expire(db, at, group_id=None):
    """Dentro de una transacción de escritura; caducidad al alcanzar el límite."""
    sql = "SELECT * FROM enrollments WHERE status='reserved' AND expires_at<=?"
    params = [at]
    if group_id is not None:
        sql += ' AND group_id=?'
        params.append(group_id)
    for row in db.execute(sql, params).fetchall():
        item = dict(row)
        _enrollment_status(db, item, 'expired', 'system', at)
        payment = _payment(db, item['id'])
        if payment['status'] == 'pending':
            _payment_status(db, payment, 'expired', 'system', at)


def _occupied(db, group_id, at):
    return db.execute("""SELECT COUNT(*) FROM enrollments WHERE group_id=? AND
        (status='confirmed' OR (status='reserved' AND expires_at>?))""",
        (group_id, at)).fetchone()[0]


def _offer(db, course_id, at, exclude=None):
    rows = db.execute("""SELECT g.id,g.course_id,g.name,g.country,g.site_id,
        g.timezone,g.capacity,g.price_minor,g.currency,
        g.capacity-(SELECT COUNT(*) FROM enrollments e WHERE e.group_id=g.id
          AND (e.status='confirmed' OR (e.status='reserved' AND e.expires_at>?))) AS available
        FROM groups g JOIN courses c ON c.id=g.course_id
        WHERE g.course_id=? AND g.status='open' AND c.status='published'
        ORDER BY g.name,g.id""", (at, course_id))
    return [dict(r) for r in rows if r['id'] != exclude]


def offer(db, actor, course_id, *, clock=None):
    groups.identity(actor)
    if actor['role'] != 'student':
        raise PermissionError('Esta consulta corresponde a la oferta estudiantil.')
    return _offer(db, course_id, stamp(instant(clock)))


def reserve(db, actor, group_id, *, clock=None):
    """Comprobar y ocupar el cupo en una única transacción SQLite."""
    groups.identity(actor)
    if actor['role'] != 'student':
        raise PermissionError('Solo el estudiante solicita su inscripción.')
    full = None
    with db:
        db.execute('BEGIN IMMEDIATE')
        moment = instant(clock)
        at = stamp(moment)
        group = groups.load(db, group_id)
        if group['status'] != 'open' or group['price_minor'] is None:
            raise EnrollmentError('El grupo no tiene inscripciones abiertas.')
        _expire(db, at, group_id)
        duplicate = db.execute("""SELECT id FROM enrollments WHERE group_id=? AND
            student_id=? AND (status='confirmed' OR (status='reserved' AND expires_at>?))""",
            (group_id, actor['id'], at)).fetchone()
        if duplicate:
            # Propuesta pendiente de confirmación de la clienta.
            raise EnrollmentError('Ya existe una reserva vigente o inscripción confirmada.')
        if _occupied(db, group_id, at) >= group['capacity']:
            full = FullGroup([g for g in _offer(db, group['course_id'], at, group_id)
                              if g['available'] > 0])
        else:
            enrollment_id, payment_id = str(uuid4()), str(uuid4())
            expires = stamp(moment + timedelta(minutes=RESERVATION_MINUTES))
            db.execute("""INSERT INTO enrollments
                (id,group_id,student_id,status,reserved_at,expires_at,updated_at)
                VALUES (?,?,?,'reserved',?,?,?)""",
                (enrollment_id, group_id, actor['id'], at, expires, at))
            db.execute("""INSERT INTO payment_attempts
                (id,enrollment_id,amount_minor,currency,status,created_at,updated_at)
                VALUES (?,?,?,?,'pending',?,?)""",
                (payment_id, enrollment_id, group['price_minor'], group['currency'], at, at))
            item, payment = _load(db, enrollment_id), _payment(db, enrollment_id)
            _event(db, 'enrollment', actor['id'], 'reserved', None, item, at)
            _event(db, 'payment', actor['id'], 'created', None, payment, at)
            result = {'enrollment': item, 'payment': payment}
    if full is not None:
        raise full
    return result


def _can_manage(actor, group):
    groups.identity(actor)
    return (actor['role'] == 'site_admin' and actor.get('country') == group['country']
            and actor.get('site_id') == group['site_id'])


def _can_read(actor, item, group):
    groups.identity(actor)
    role = actor['role']
    return (role == 'international_director'
            or (role == 'country_coordinator' and actor.get('country') == group['country'])
            or _can_manage(actor, group)
            or (role == 'student' and actor['id'] == item['student_id']))


def get(db, actor, enrollment_id, *, clock=None):
    """Consulta autorizada; refleja el vencimiento aun sin una tarea en segundo plano."""
    groups.identity(actor)
    with db:
        db.execute('BEGIN IMMEDIATE')
        item = _load(db, enrollment_id)
        group = groups.load(db, item['group_id'])
        if not _can_read(actor, item, group):
            raise PermissionError('No tiene acceso a esta inscripción.')
        _expire(db, stamp(instant(clock)), group['id'])
        return {'enrollment': _load(db, enrollment_id), 'payment': _payment(db, enrollment_id)}


def cancel(db, actor, enrollment_id, *, clock=None):
    groups.identity(actor)
    with db:
        db.execute('BEGIN IMMEDIATE')
        item = _load(db, enrollment_id)
        group = groups.load(db, item['group_id'])
        if not _can_manage(actor, group):
            raise PermissionError('Solo Administración de la sede organizadora cancela inscripciones.')
        at = stamp(instant(clock))
        _expire(db, at, group['id'])
        item = _load(db, enrollment_id)
        if item['status'] not in ('reserved','confirmed'):
            return item
        after = _enrollment_status(db, item, 'cancelled', actor['id'], at)
        payment = _payment(db, enrollment_id)
        if payment['status'] == 'pending':
            _payment_status(db, payment, 'cancelled', actor['id'], at)
        return after


def set_capacity(db, actor, group_id, capacity, *, clock=None):
    groups.identity(actor)
    if type(capacity) is not int or capacity <= 0:
        raise EnrollmentError('La capacidad debe ser un entero positivo.')
    with db:
        db.execute('BEGIN IMMEDIATE')
        before = groups.load(db, group_id)
        if not _can_manage(actor, before):
            raise PermissionError('Solo Administración de la sede modifica sus cupos.')
        at = stamp(instant(clock))
        _expire(db, at, group_id)
        if capacity < _occupied(db, group_id, at):
            raise EnrollmentError('La capacidad no puede ser menor a los lugares ocupados.')
        db.execute('UPDATE groups SET capacity=?,updated_at=? WHERE id=?',
                   (capacity, at, group_id))
        after = groups.load(db, group_id)
        groups.record(db, actor, 'capacity_updated', before, after)
        return after
