"""Demostraciones reproducibles de cupos, pagos y medición local.
Ejecutar desde la raíz: python -m examples.demo_fabian --output evidencia_fabian.json
No utiliza la base de datos real ni realiza cobros.
"""
import argparse
import json
import platform
import statistics
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from time import perf_counter_ns

from app import courses, groups, enrollments, payments

DIRECTOR = dict(id='direccion-demo', role='international_director', active=True)
COORD = dict(id='coordinacion-es-demo', role='country_coordinator', active=True, country='ES')
ADMIN = dict(id='sede-madrid-demo', role='site_admin', active=True, country='ES', site_id='MAD')
A = dict(id='estudiante-mx-demo', role='student', active=True, country='MX')
B = dict(id='estudiante-co-demo', role='student', active=True, country='CO')
DATA = dict(name='Curso piloto ficticio', description='Demostración local',
            objectives='Validar inscripciones', attendance_min=80, grade_min=70)


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def run(path):
    db = enrollments.connect(path)
    start = datetime.now(timezone.utc)
    clock = lambda: start
    report = dict(executed_at=start.isoformat(), platform=platform.platform(),
                  python=platform.python_version(),
                  limitations=['Base temporal, datos e identidades ficticias.',
                               'Reloj inyectado en las pruebas de vencimiento; no se espera 30 minutos reales.',
                               'Sin autenticación ni interfaz definitiva; tiempos de funciones locales, no de pantalla.',
                               'Precio de 45.50 EUR elegido como dato ficticio.',
                               'Vencimiento exacto y bloqueo de duplicados: propuestas pendientes.'],
                  scenarios=[])
    try:
        course = courses.create(db, DIRECTOR, DATA)
        courses.publish(db, DIRECTOR, course['id'])

        def new_group(name, capacity):
            g = groups.create(db, COORD, course['id'], name, 'ES', 'MAD',
                              'docente-demo', capacity, teacher_is_enabled=lambda c, t: True)
            groups.set_price(db, DIRECTOR, g['id'], '45.50')
            return groups.open_enrollment(db, COORD, g['id'])

        def snapshot(g, at):
            rows = db.execute('SELECT status, COUNT(*) AS n FROM enrollments WHERE group_id=? GROUP BY status',
                              (g['id'],)).fetchall()
            counts = {row['status']: row['n'] for row in rows}
            occupied = db.execute("""SELECT COUNT(*) FROM enrollments WHERE group_id=?
                AND (status='confirmed' OR (status='reserved' AND expires_at>?))""",
                (g['id'], enrollments.stamp(at))).fetchone()[0]
            visible = next(x for x in enrollments.offer(db, A, course['id'], clock=lambda: at)
                           if x['id'] == g['id'])
            check(visible['available'] == g['capacity'] - occupied, 'Cupo inconsistente')
            return dict(group_id=g['id'], capacity=g['capacity'], occupied=occupied,
                        available=visible['available'], statuses=counts)

        def record(case, requirement, expected, actual):
            report['scenarios'].append(dict(case=case, requirement=requirement, expected=expected,
                                            actual=actual, result='PASS'))

        last = new_group('Madrid - último cupo', 1)
        alternative = new_group('Madrid - alternativo', 3)
        gate = Barrier(2)

        def attempt(actor):
            connection = enrollments.connect(path)
            try:
                gate.wait(timeout=10)
                try:
                    item = enrollments.reserve(connection, actor, last['id'], clock=clock)
                    return dict(student=actor['id'], response='reserved', **item)
                except enrollments.FullGroup as error:
                    return dict(student=actor['id'], response='full', message=str(error),
                                alternatives=error.alternatives)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, actor) for actor in (A, B)]
            results = [f.result(timeout=20) for f in futures]
        check(sorted(x['response'] for x in results) == ['full', 'reserved'], 'Doble reserva')
        reserved = next(x for x in results if x['response'] == 'reserved')
        full = next(x for x in results if x['response'] == 'full')
        check(any(x['id'] == alternative['id'] for x in full['alternatives']), 'Faltan alternativas')
        held = snapshot(last, start)
        check(held['occupied'] == 1 and held['available'] == 0, 'Cupo reservado incorrecto')
        winner = A if reserved['student'] == A['id'] else B
        paid_at = start + timedelta(minutes=1)
        paid = payments.respond(db, winner, reserved['payment']['id'], 'approved', clock=lambda: paid_at)
        after = snapshot(last, paid_at)
        check(after['statuses'] == {'confirmed': 1} and after['available'] == 0, 'Confirmación inconsistente')
        record('Ultimo cupo concurrente', 'RF-004 / CP-004',
               'Una reserva y un rechazo; tras pagar, una confirmada y cero disponibles.',
               dict(requests=results, after_reservation=held, payment_result=paid, after_payment=after))

        student_view = payments.consult(db, winner, paid['payment']['id'], clock=lambda: paid_at)
        admin_view = payments.consult(db, ADMIN, paid['payment']['id'], clock=lambda: paid_at)
        initial = reserved['payment']
        check(student_view['payment'] == admin_view['payment'], 'Vistas inconsistentes')
        check(all(initial[k] == student_view['payment'][k] for k in ('id','amount_minor','currency')),
              'Identidad o importe del intento cambiado')
        check(initial['currency'] == 'EUR' and initial['amount_minor'] == 4550, 'Moneda o importe incorrecto')
        record('Moneda e importe en dos perfiles', 'RF-003 / DAT-006 / CP-006',
               'Estudiante extranjero paga 45.50 EUR ficticios y Administración consulta la misma operación.',
               dict(offer=dict(group_id=last['id'], amount_minor=last['price_minor'], currency=last['currency']),
                    initial_payment=initial, student=student_view, site_admin=admin_view,
                    student_country=winner['country']))

        cancel_at = start + timedelta(minutes=2)
        enrollments.cancel(db, ADMIN, paid['enrollment']['id'], clock=lambda: cancel_at)
        cancelled = payments.consult(db, winner, paid['payment']['id'], clock=lambda: cancel_at)
        freed = snapshot(last, cancel_at)
        check(cancelled['enrollment']['status'] == 'cancelled' and
              cancelled['payment'] == paid['payment'] and freed['available'] == 1, 'Cancelación incorrecta')
        record('Cancelacion de inscripcion pagada', 'RF-004 / DAT-006',
               'Libera cupo y conserva pago aprobado original.', dict(operation=cancelled, group=freed))

        rejected_group = new_group('Madrid - rechazo', 1)
        attempt1 = enrollments.reserve(db, A, rejected_group['id'], clock=clock)
        rejected = payments.respond(db, A, attempt1['payment']['id'], 'rejected', clock=lambda: paid_at)
        rejected_state = snapshot(rejected_group, paid_at)
        check(rejected['enrollment']['status'] == 'rejected' and rejected['payment']['status'] == 'rejected'
              and rejected_state['available'] == 1, 'Rechazo incorrecto')
        record('Pago rechazado', 'RF-003 / RF-004 / CP-003',
               'No confirma y libera el lugar.', dict(operation=rejected, group=rejected_state))

        expired_group = new_group('Madrid - vencimiento', 1)
        first = enrollments.reserve(db, A, expired_group['id'], clock=clock)
        expiry = start + timedelta(minutes=30)
        expired = enrollments.get(db, A, first['enrollment']['id'], clock=lambda: expiry)
        expired_state = snapshot(expired_group, expiry)
        check(expired['enrollment']['status'] == 'expired' and expired['payment']['status'] == 'expired'
              and expired_state['available'] == 1, 'Vencimiento incorrecto')
        record('Reserva vencida', 'RF-004 / CP-004',
               'La reserva deja de ocupar cupo y conserva intento.', dict(operation=expired, group=expired_state))

        late = expiry + timedelta(minutes=1)
        second = enrollments.reserve(db, B, expired_group['id'], clock=lambda: late)
        late_payment = payments.respond(db, A, first['payment']['id'], 'approved', clock=lambda: late)
        second_payment = payments.respond(db, B, second['payment']['id'], 'approved', clock=lambda: late)
        final_state = snapshot(expired_group, late)
        check(late_payment['enrollment']['status'] == 'expired' and
              late_payment['payment']['status'] == 'approved_late' and
              second_payment['enrollment']['status'] == 'confirmed' and
              final_state['occupied'] == 1 and final_state['available'] == 0, 'Aprobación tardía incorrecta')
        record('Pago aprobado despues del vencimiento', 'RF-003 / RF-004 / CP-003',
               'Se registra sin confirmar; el nuevo estudiante mantiene su lugar.',
               dict(late_payment=late_payment, second_payment=second_payment, group=final_state))

        bench = new_group('Madrid - medición local', 20)
        query_times, reserve_times = [], []
        for i in range(20):
            actor = dict(A, id=f'benchmark-{i}')
            t = perf_counter_ns()
            listed = courses.list_courses(db, actor)
            query_times.append((perf_counter_ns() - t) / 1_000_000)
            check(any(x['id'] == course['id'] for x in listed), 'Curso no visible')
            t = perf_counter_ns()
            result = enrollments.reserve(db, actor, bench['id'])
            reserve_times.append((perf_counter_ns() - t) / 1_000_000)
            check(result['enrollment']['status'] == 'reserved', 'Reserva no realizada')

        def stats(values):
            return dict(n=len(values), mean_ms=round(statistics.mean(values), 3),
                        median_ms=round(statistics.median(values), 3),
                        max_ms=round(max(values), 3), samples_ms=[round(x, 3) for x in values])

        report['production_metrics'] = dict(course_query=stats(query_times),
                                            enrollment_reservation=stats(reserve_times),
                                            environment='SQLite local; una consulta y reserva por iteración, 20 iteraciones.',
                                            target='Pendiente de cotejar meta exacta del SRS.')
        report['defects'] = dict(scenario_failures=0, note='Sin fallos en estos escenarios; no sustituye el registro de defectos abiertos por gravedad.')
        return report
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='evidencia_fabian.json')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        report = run(Path(tmp) / 'demo.sqlite3')
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in report['scenarios']:
        print(f"{item['result']} | {item['case']}")
    print(json.dumps(report['production_metrics'], ensure_ascii=False, indent=2))
    print(f"Evidencia generada: {output.resolve()}")


if __name__ == '__main__':
    main()
