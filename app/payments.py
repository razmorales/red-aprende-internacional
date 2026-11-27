"""Resultados del pago simulado; sin cobros ni devoluciones reales."""
from app import enrollments as e
from app import groups


def respond(db, actor, payment_id, outcome, *, clock=None):
    """Simular una respuesta de pago propia; usar identidad y reloj del servidor."""
    groups.identity(actor)
    if actor['role'] != 'student':
        raise PermissionError('Solo el estudiante realiza su pago simulado.')
    if outcome not in ('approved', 'rejected'):
        raise e.EnrollmentError('Resultado de pago inválido.')
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM payment_attempts WHERE id=?',
                         (payment_id,)).fetchone()
        if row is None:
            raise e.EnrollmentError('Intento de pago inexistente.')
        payment = dict(row)
        item = e._load(db, payment['enrollment_id'])
        if actor['id'] != item['student_id']:
            raise PermissionError('El intento pertenece a otro estudiante.')
        at = e.stamp(e.instant(clock))
        e._expire(db, at, item['group_id'])
        item = e._load(db, item['id'])
        payment = e._payment(db, item['id'])

        if payment['responded_at'] is not None:
            previous = 'approved' if payment['status'] in ('approved','approved_late') else 'rejected'
            if previous != outcome:
                raise e.EnrollmentError('El intento ya tiene una respuesta definitiva.')
            return {'enrollment': item, 'payment': payment}

        if item['status'] == 'reserved' and payment['status'] == 'pending':
            new_status = 'confirmed' if outcome == 'approved' else 'rejected'
            payment = e._payment_status(db, payment, outcome, actor['id'], at, at)
            item = e._enrollment_status(db, item, new_status, actor['id'], at)
        elif item['status'] == 'expired' and payment['status'] == 'expired':
            status = 'approved_late' if outcome == 'approved' else 'rejected'
            payment = e._payment_status(db, payment, status, actor['id'], at, at)
        else:
            raise e.EnrollmentError('El intento ya no admite una respuesta de pago.')
        return {'enrollment': item, 'payment': payment}


def consult(db, actor, payment_id, *, clock=None):
    """Consultar la misma operación desde perfiles autorizados."""
    groups.identity(actor)
    row = db.execute('SELECT enrollment_id FROM payment_attempts WHERE id=?',
                     (payment_id,)).fetchone()
    if row is None:
        raise e.EnrollmentError('Intento de pago inexistente.')
    return e.get(db, actor, row['enrollment_id'], clock=clock)
