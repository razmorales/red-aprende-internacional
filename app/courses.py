"""Cursos y publicación. Adaptador local de prueba; requiere identidad del servidor."""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4


class CourseError(ValueError):
    pass


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            objectives TEXT NOT NULL,
            attendance_min TEXT NOT NULL,
            grade_min TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft', 'published')),
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS course_events (
            id INTEGER PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id),
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
    ''')
    columns = {row[1] for row in db.execute("PRAGMA table_info(courses)")}
    if "academic_locked" not in columns:
        db.execute("ALTER TABLE courses ADD COLUMN academic_locked INTEGER NOT NULL DEFAULT 0")
        db.commit()
    return db


def authorize(actor):
    if not isinstance(actor, dict) or not actor.get('id') or not actor.get('active'):
        raise PermissionError('Se requiere un usuario activo autenticado.')
    if actor.get('role') != 'international_director':
        raise PermissionError('Solo Dirección Internacional puede administrar cursos.')


def validate(payload):
    expected = {'name', 'description', 'objectives', 'attendance_min', 'grade_min'}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise CourseError('Proporcione nombre, descripción, objetivos y ambos umbrales.')
    result = {}
    for field in ('name', 'description', 'objectives'):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise CourseError(f'El campo {field} requiere texto.')
        result[field] = value.strip()
    for field in ('attendance_min', 'grade_min'):
        try:
            if isinstance(payload[field], bool):
                raise InvalidOperation
            value = Decimal(str(payload[field]))
        except (InvalidOperation, ValueError):
            raise CourseError(f'El umbral {field} debe ser numérico.') from None
        if not value.is_finite() or not Decimal(0) <= value <= Decimal(100):
            raise CourseError(f'El umbral {field} debe estar entre 0 y 100.')
        result[field] = str(value)
    return result


def load(db, course_id):
    row = db.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
    if row is None:
        raise CourseError('Curso inexistente.')
    return dict(row)


def record(db, actor, action, before, after):
    db.execute('''INSERT INTO course_events
        (course_id, actor_id, action, before_json, after_json, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?)''', (
            after['id'], actor['id'], action,
            json.dumps(before, ensure_ascii=False) if before else None,
            json.dumps(after, ensure_ascii=False), after['updated_at']))


def create(db, actor, payload):
    authorize(actor)
    data = validate(payload)
    course_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute('''INSERT INTO courses (id, name, description, objectives, attendance_min,
            grade_min, status, created_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            course_id, data['name'], data['description'], data['objectives'],
            data['attendance_min'], data['grade_min'], 'draft', actor['id'], now))
        after = load(db, course_id)
        record(db, actor, 'created', None, after)
    return after


def update(db, actor, course_id, payload):
    authorize(actor)
    data = validate(payload)
    with db:
        db.execute('BEGIN IMMEDIATE')
        before = load(db, course_id)
        changed_thresholds = any(
            Decimal(before[field]) != Decimal(data[field])
            for field in ('attendance_min', 'grade_min'))
        if before['academic_locked'] and changed_thresholds:
            raise CourseError('Los criterios académicos están bloqueados desde la apertura de inscripciones.')
        db.execute('''UPDATE courses SET name=?, description=?, objectives=?,
            attendance_min=?, grade_min=?, updated_at=? WHERE id=?''', (
                data['name'], data['description'], data['objectives'],
                data['attendance_min'], data['grade_min'],
                datetime.now(timezone.utc).isoformat(), course_id))
        after = load(db, course_id)
        record(db, actor, 'updated', before, after)
    return after


def publish(db, actor, course_id):
    authorize(actor)
    with db:
        db.execute('BEGIN IMMEDIATE')
        before = load(db, course_id)
        if before['status'] == 'published':
            return before
        db.execute("UPDATE courses SET status='published', updated_at=? WHERE id=?", (
            datetime.now(timezone.utc).isoformat(), course_id))
        after = load(db, course_id)
        record(db, actor, 'published', before, after)
    return after


def lock_academic_criteria(db, actor, course_id):
    """Llamar dentro de la transacción que abre inscripciones de un grupo.

    La identidad debe provenir de la sesión validada. Este método participa
    en la transacción del llamador, que debe confirmar o revertir ambos cambios.
    """
    if not isinstance(actor, dict) or not actor.get('id') or not actor.get('active'):
        raise PermissionError('Se requiere un usuario activo autenticado.')
    if actor.get('role') not in ('international_director', 'country_coordinator', 'site_admin'):
        raise PermissionError('Se requiere autorización para abrir inscripciones.')
    if not db.in_transaction:
        raise CourseError('Abra primero la transacción de inscripción del grupo.')
    before = load(db, course_id)
    if before['status'] != 'published':
        raise CourseError('Las inscripciones requieren un curso publicado.')
    if before['academic_locked']:
        return before
    db.execute('UPDATE courses SET academic_locked=1, updated_at=? WHERE id=?', (
        datetime.now(timezone.utc).isoformat(), course_id))
    after = load(db, course_id)
    record(db, actor, 'academic_locked', before, after)
    return after


def list_courses(db, actor):
    if not isinstance(actor, dict) or not actor.get('id') or not actor.get('active'):
        raise PermissionError('Se requiere un usuario activo autenticado.')
    if actor.get('role') == 'international_director':
        return [dict(row) for row in db.execute('SELECT * FROM courses ORDER BY name, id')]
    return [dict(row) for row in db.execute(
        "SELECT * FROM courses WHERE status='published' ORDER BY name, id")]


def main():
    parser = argparse.ArgumentParser(description='Demostración local del módulo de cursos')
    parser.add_argument('action', choices=['create', 'update', 'publish', 'list'])
    parser.add_argument('--database', default='courses.sqlite3')
    parser.add_argument('--id')
    parser.add_argument('--data', help='Archivo JSON con datos del curso')
    args = parser.parse_args()
    # Identidad fija de prueba. La aplicación debe obtenerla de la sesión autenticada.
    actor = {'id': 'demo-direction', 'role': 'international_director', 'active': True}
    db = connect(args.database)
    try:
        if args.action == 'create':
            result = create(db, actor, json.loads(Path(args.data).read_text()))
        elif args.action == 'update':
            result = update(db, actor, args.id, json.loads(Path(args.data).read_text()))
        elif args.action == 'publish':
            result = publish(db, actor, args.id)
        else:
            result = list_courses(db, actor)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (CourseError, PermissionError, TypeError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f'{error}\n')
    finally:
        db.close()


if __name__ == '__main__':
    main()
