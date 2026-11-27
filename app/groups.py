"""Grupos del piloto. Recibe identidad validada por el servidor, no por la UI."""
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from app import courses

SEDES = {
    'MX': ('CDMX', 'America/Mexico_City', 'MXN'),
    'CO': ('BOG', 'America/Bogota', 'COP'),
    'ES': ('MAD', 'Europe/Madrid', 'EUR'),
}


class GroupError(ValueError):
    pass


def connect(path):
    db = courses.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id),
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            site_id TEXT NOT NULL,
            timezone TEXT NOT NULL,
            teacher_id TEXT NOT NULL,
            capacity INTEGER NOT NULL CHECK(capacity > 0),
            price_minor INTEGER CHECK(price_minor >= 0),
            currency TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','open')),
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS group_events (
            id INTEGER PRIMARY KEY,
            group_id TEXT NOT NULL REFERENCES groups(id),
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
    """)
    return db


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(actor):
    if not isinstance(actor, dict) or not actor.get('id') or actor.get('active') is not True:
        raise PermissionError('Se requiere identidad activa validada.')
    if actor.get('role') not in ('international_director', 'country_coordinator',
                                  'site_admin', 'teacher', 'student'):
        raise PermissionError('Perfil no autorizado.')


def coordinator(actor, country):
    identity(actor)
    if actor['role'] != 'country_coordinator' or actor.get('country') != country:
        raise PermissionError('Solo Coordinación del país organizador puede realizar esta operación.')


def load(db, group_id):
    # Auxiliar interno: no exponer directamente como operación de usuario.
    row = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if row is None:
        raise GroupError('Grupo inexistente.')
    return dict(row)


def record(db, actor, action, before, after):
    db.execute("""INSERT INTO group_events
        (group_id, actor_id, action, before_json, after_json, occurred_at)
        VALUES (?,?,?,?,?,?)""", (
            after['id'], actor['id'], action,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False), after['updated_at']))


def create(db, actor, course_id, name, country, site_id, teacher_id, capacity,
           *, teacher_is_enabled):
    """teacher_is_enabled(course_id, teacher_id): consulta confiable de servidor."""
    coordinator(actor, country)
    if country not in SEDES or SEDES[country][0] != site_id:
        raise GroupError('Sede no válida para el país.')
    if not isinstance(name, str) or not name.strip():
        raise GroupError('Nombre obligatorio.')
    if not isinstance(teacher_id, str) or not teacher_id.strip():
        raise GroupError('Docente obligatorio.')
    if type(capacity) is not int or capacity <= 0:
        raise GroupError('La capacidad debe ser un entero positivo.')
    _, zone, currency = SEDES[country]
    group_id = str(uuid4())
    with db:
        db.execute('BEGIN IMMEDIATE')
        if courses.load(db, course_id)['status'] != 'published':
            raise GroupError('Se requiere un curso publicado.')
        if not teacher_is_enabled(course_id, teacher_id):
            raise GroupError('Docente no habilitado para el curso.')
        db.execute("""INSERT INTO groups
            (id,course_id,name,country,site_id,timezone,teacher_id,capacity,currency,created_by,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (group_id, course_id, name.strip(), country, site_id, zone, teacher_id,
             capacity, currency, actor['id'], now()))
        after = load(db, group_id)
        record(db, actor, 'created', None, after)
    return after


def set_price(db, actor, group_id, amount):
    identity(actor)
    if actor['role'] != 'international_director':
        raise PermissionError('Solo Dirección Internacional fija el precio.')
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value < 0 or value > Decimal('999999999.99'):
            raise ValueError
        minor = value * 100
        if minor != minor.to_integral_value():
            raise ValueError
        minor = int(minor)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise GroupError('Importe ficticio inválido; máximo dos decimales.') from None
    with db:
        db.execute('BEGIN IMMEDIATE')
        before = load(db, group_id)
        if before['status'] != 'draft':
            raise GroupError('El precio queda fijo desde la apertura.')
        db.execute('UPDATE groups SET price_minor=?, updated_at=? WHERE id=?',
                   (minor, now(), group_id))
        after = load(db, group_id)
        record(db, actor, 'price_set', before, after)
    return after


def open_enrollment(db, actor, group_id):
    identity(actor)
    with db:
        db.execute('BEGIN IMMEDIATE')
        before = load(db, group_id)
        coordinator(actor, before['country'])
        if before['status'] == 'open':
            return before
        if before['price_minor'] is None:
            raise GroupError('Dirección Internacional debe fijar el precio antes de abrir.')
        courses.lock_academic_criteria(db, actor, before['course_id'])
        db.execute("UPDATE groups SET status='open', updated_at=? WHERE id=?", (now(), group_id))
        after = load(db, group_id)
        record(db, actor, 'opened', before, after)
    return after


def list_groups(db, actor, course_id=None):
    identity(actor)
    role = actor['role']
    filters, params = [], []
    if role == 'country_coordinator':
        filters.append('g.country=?')
        params.append(actor.get('country'))
    elif role == 'site_admin':
        filters.append('g.country=? AND g.site_id=?')
        params.extend([actor.get('country'), actor.get('site_id')])
    elif role == 'teacher':
        filters.append('g.teacher_id=?')
        params.append(actor['id'])
    elif role == 'student':
        filters.append("g.status='open' AND c.status='published'")
    if course_id is not None:
        filters.append('g.course_id=?')
        params.append(course_id)
    query = 'SELECT g.* FROM groups g JOIN courses c ON c.id=g.course_id'
    if filters:
        query += ' WHERE ' + ' AND '.join(filters)
    result = [dict(row) for row in db.execute(query + ' ORDER BY g.name,g.id', params)]
    if role == 'student':
        fields = ('id','course_id','name','country','site_id','timezone','capacity',
                  'price_minor','currency','status')
        result = [{k: row[k] for k in fields} for row in result]
    return result
