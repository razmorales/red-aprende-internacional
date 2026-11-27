"""RF-005: catálogo autorizado y disponibilidad en una consulta de solo lectura."""
from app import groups, enrollments

SITE_NAMES = {'CDMX': 'Ciudad de México', 'BOG': 'Bogotá', 'MAD': 'Madrid'}


def list_available(db, actor, course_id=None, *, only_available=False, clock=None):
    """Identidad del servidor; horarios de sesiones se integrarán con su módulo."""
    groups.identity(actor)
    role = actor['role']
    filters, params = [], [enrollments.stamp(enrollments.instant(clock))]
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
    query = """SELECT g.id,g.course_id,c.name AS course_name,g.name,g.country,
        g.site_id,g.timezone,g.capacity,g.price_minor,g.currency,g.status,
        g.capacity-(SELECT COUNT(*) FROM enrollments e WHERE e.group_id=g.id
          AND (e.status='confirmed' OR (e.status='reserved' AND e.expires_at>?))) AS available
        FROM groups g JOIN courses c ON c.id=g.course_id"""
    if filters:
        query += ' WHERE ' + ' AND '.join(filters)
    rows = []
    for row in db.execute(query + ' ORDER BY c.name,g.name,g.id', params):
        item = dict(row)
        item['site_name'] = SITE_NAMES.get(item['site_id'], item['site_id'])
        item['is_full'] = item['available'] == 0
        if only_available and (item['status'] != 'open' or item['available'] <= 0):
            continue
        rows.append(item)
    return rows
