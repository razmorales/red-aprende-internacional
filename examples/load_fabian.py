"""Carga local reproducible según la meta interna del SRS 1.1.
Datos sintéticos sembrados directamente, no operaciones de producción.
Ejecutar: python -m examples.load_fabian --output evidencia_carga_fabian.json
"""
import argparse
import json
import math
import platform
import statistics
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from time import perf_counter_ns
from app import courses, groups, enrollments

USERS = 20
ROUNDS = 5
TARGET_MS = 1000


def seed(db):
    now = datetime.now(timezone.utc)
    at = enrollments.stamp(now - timedelta(days=1))
    expires = enrollments.stamp(now - timedelta(days=1) + timedelta(minutes=30))
    catalog, group_rows, registrations, payments = [], [], [], []
    for i in range(100):
        cid = f'load-course-{i:03}'
        catalog.append((cid, f'Curso de carga {i:03}', 'Datos ficticios', 'Medir carga',
                        '80', '70', 'published', 'load-director', at, 1))
        for country, (site, zone, currency) in groups.SEDES.items():
            gid = f'{cid}-{site}'
            price = {'MXN': 50000, 'COP': 15000000, 'EUR': 12000}[currency]
            group_rows.append((gid, cid, f'Grupo {site}', country, site, zone, 'load-teacher',
                               30, price, currency, 'open', 'load-coord', at))
            for j in range(10):
                eid = f'{gid}-enrollment-{j}'
                registrations.append((eid, gid, f'{gid}-student-{j}', 'confirmed', at, expires, at))
                payments.append((f'{eid}-payment', eid, price, currency, 'approved', at, at, at))
    with db:
        db.executemany("""INSERT INTO courses
            (id,name,description,objectives,attendance_min,grade_min,status,created_by,updated_at,academic_locked)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", catalog)
        db.executemany("""INSERT INTO groups
            (id,course_id,name,country,site_id,timezone,teacher_id,capacity,price_minor,currency,status,created_by,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", group_rows)
        db.executemany("""INSERT INTO enrollments
            (id,group_id,student_id,status,reserved_at,expires_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""", registrations)
        db.executemany("""INSERT INTO payment_attempts
            (id,enrollment_id,amount_minor,currency,status,created_at,updated_at,responded_at)
            VALUES (?,?,?,?,?,?,?,?)""", payments)


def counts(db):
    return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('courses', 'groups', 'enrollments', 'payment_attempts')}


def stats(samples):
    valid = [x['ms'] for x in samples if x['ok']]
    failures = [x for x in samples if not x['ok']]
    ordered = sorted(valid)
    p95 = ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None
    return dict(attempts=len(samples), successful=len(valid), failed=len(failures),
                p95_ms=round(p95, 3) if p95 is not None else None,
                mean_ms=round(statistics.mean(valid), 3) if valid else None,
                max_ms=round(max(valid), 3) if valid else None,
                target_ms=TARGET_MS,
                target_met_local=not failures and p95 is not None and p95 <= TARGET_MS,
                samples=samples)


def run(path):
    db = enrollments.connect(path)
    try:
        seed(db)
        initial = counts(db)
        assert initial == dict(courses=100, groups=300, enrollments=3000, payment_attempts=3000)
        gate = Barrier(USERS)

        def worker(index):
            conn = None
            result = []
            try:
                conn = enrollments.connect(path)
                for round_id in range(ROUNDS):
                    actor = dict(id=f'load-user-{index}-{round_id}', role='student',
                                 active=True, country='MX')
                    for operation in ('course_query', 'enrollment_reservation'):
                        gate.wait(timeout=60)
                        t = perf_counter_ns()
                        error = None
                        try:
                            if operation == 'course_query':
                                if len(courses.list_courses(conn, actor)) != 100:
                                    raise AssertionError('Catálogo incompleto')
                            else:
                                gid = f'load-course-{index:03}-MAD'
                                item = enrollments.reserve(conn, actor, gid)
                                if item['enrollment']['status'] != 'reserved':
                                    raise AssertionError('Reserva no creada')
                        except Exception as exc:
                            error = f'{type(exc).__name__}: {exc}'
                        elapsed = (perf_counter_ns() - t) / 1_000_000
                        result.append(dict(operation=operation, user=index, round=round_id+1,
                                           ms=round(elapsed, 6), ok=error is None, error=error))
                return result
            except BaseException:
                gate.abort()
                raise
            finally:
                if conn is not None:
                    conn.close()

        with ThreadPoolExecutor(max_workers=USERS) as executor:
            futures = [executor.submit(worker, i) for i in range(USERS)]
            results = [sample for future in futures for sample in future.result()]
        metrics = {op: stats([x for x in results if x['operation'] == op])
                   for op in ('course_query','enrollment_reservation')}
        final = counts(db)
        at = enrollments.stamp(enrollments.instant())
        overbooked = db.execute("""SELECT COUNT(*) FROM groups g WHERE g.capacity <
            (SELECT COUNT(*) FROM enrollments e WHERE e.group_id=g.id AND
            (e.status='confirmed' OR (e.status='reserved' AND e.expires_at>?)))""", (at,)).fetchone()[0]
        consistent = final['enrollments'] == initial['enrollments'] + metrics['enrollment_reservation']['successful']
        consistent = consistent and final['payment_attempts'] == final['enrollments'] and overbooked == 0
        return dict(executed_at=datetime.now(timezone.utc).isoformat(),
                    environment=dict(platform=platform.platform(),python=platform.python_version(),
                                     sqlite=db.execute('SELECT sqlite_version()').fetchone()[0]),
                    setup=dict(initial=initial, workers=USERS, rounds=ROUNDS,
                               samples_per_operation=USERS*ROUNDS,
                               percentile_method='Rango más próximo: ceil(0.95*n)',
                               fixture='Inserciones SQL sintéticas, fuera de la medición.',
                               measurement='Funciones Python/SQLite; conexiones abiertas antes de medir. Barrera por operación y ronda. Sin HTTP/UI.'),
                    metrics=metrics, final=final,
                    integrity=dict(overbooked_groups=overbooked, consistent=consistent),
                    limitations=['20 hilos locales, no sesiones web autenticadas.',
                                 'La carga crece con las reservas exitosas.',
                                 'Los usuarios de prueba son identidades ficticias; no valida existencia en módulo real.',
                                 'Cumplimiento local de la meta no equivale a aceptación de rendimiento extremo a extremo.'])
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='evidencia_carga_fabian.json')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        report = run(Path(tmp) / 'load.sqlite3')
    path = Path(args.output)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Initial:', report['setup']['initial'])
    for name, metric in report['metrics'].items():
        print(name, {k:v for k,v in metric.items() if k != 'samples'})
    print('Integrity:', report['integrity'])
    print('Evidence:', path.resolve())
    if not report['integrity']['consistent'] or any(m['failed'] for m in report['metrics'].values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
