# Avance de Fabián — grupos, inscripciones, cupos y pagos simulados

Estado al 27 de noviembre de 2026. Rama: `feature/grupos-fabian`, basada en `feature/cursos-raziel`. Responsable: Fabián Santiago Jiménez.

## Alcance y ejecución

Módulos locales de Python 3.12 y SQLite, compatibles con `app/courses.py`. Las pantallas definitivas y la identidad autenticada siguen pendientes de integración con José Ángel y Luis. No se realizan cargos reales.

Desde la raíz, en Windows:

```powershell
python -m unittest discover -s tests -v
python -m examples.demo_fabian --output evidencia_fabian.json
```

En Linux se puede usar `python3`. El demostrador usa una base temporal independiente y genera datos ficticios; no modifica la base de trabajo. El reloj inyectado permite probar el vencimiento sin esperar 30 minutos.

## Resultados observados

Ejecuciones en Windows con Python 3.12.10, verificadas en las capturas de PowerShell compartidas por Fabián el 27 de noviembre. No son resultados inventados ni equivalen a aceptación del sistema completo.

| Versión probada | Pruebas | Tiempo total | Resultado |
|---|---:|---:|---|
| Base de Raziel | 10 | 0.325 s | OK |
| Grupos (4a0a66a) | 18 | 0.743 s | OK |
| Reservas (2b84d14) | 26 | 1.838 s | OK |
| Pagos (1533f32) | 35 | 2.918 s | OK |
| Demostración (8c6d6cd) | 6 escenarios locales | No medido como total | PASS en los seis |

Las 35 pruebas incluyen 10 de cursos y 25 de nuestra aportación. La revisión de otro integrante y las pruebas desde la aplicación integrada siguen pendientes. La evidencia detallada fue generada en la computadora de Fabián el 27 de noviembre a las 20:38:58 UTC. Se conserva en [evidencia_fabian.json](evidencias/evidencia_fabian.json), con copia íntegra verificada (SHA-256: 0759e9aa134afe1aa6b74b06dc0b9312dba7446de39e7e597ba0dbc59337eca9).

## Trazabilidad de pruebas y demostraciones

| Requisito / criterio | Prueba | Resultado esperado | Resultado observado |
|---|---|---|---|
| RF-002 / DAT-003 | test_groups.py | Grupo de curso publicado, sede válida, docente habilitado, precio fijado por Dirección y bloqueo académico | 8 pruebas OK, con verificación de permisos y reversión ante fallo |
| RF-003 / DAT-005 | test_reservation_and_payment_snapshot | Reserva e intento de pago vinculados, plazo de 30 min | OK |
| RF-004 / CP-004 | test_concurrent_last_seat y escenario Ultimo cupo concurrente | Una reserva y un rechazo, sin sobrecupo; tras aprobación, una confirmada | OK / PASS |
| RF-004 | test_full_group_alternatives_only_same_course | No crear reserva; mostrar otros grupos disponibles del mismo curso | OK |
| RF-004 | test_expiration_at_boundary_and_reallocation | Una reserva vencida libera lugar | OK / PASS; frontera exacta provisional |
| RF-003 / RF-004 | test_rejection_releases_seat_and_allows_new_attempt | Pago rechazado no confirma y libera lugar | OK / PASS |
| RF-003 / RF-004 | test_late_approval_after_reallocation | Pago tardío registrado, sin confirmar ni quitar el cupo reasignado | OK / PASS |
| DAT-006 / CP-006 | test_payment_snapshot_and_two_profiles y demostración Moneda e importe en dos perfiles | Mismo identificador, importe y moneda antes y después del pago | OK / PASS; consultas de funciones, no pantallas |
| RF-004 / DAT-006 | test_cancel_confirmed_preserves_original_payment | Cancelación libera lugar sin alterar pago original | OK / PASS |
| RF-003 / DAT-007 | test_atomic_rollback_on_payment_creation_failure, test_payment_and_confirmation_rollback_together | Fallo intermedio revierte inscripción y pago | OK |

Los IDs se cotejarán con la última versión del SRS compartido antes de integrar; esta tabla no sustituye la actualización del documento ni certifica la ejecución de todos sus casos de aceptación.

## Métricas asignadas

### Production Metrics

Responsable: Fabián. Medición local del 27 de noviembre, SQLite en archivo temporal, Windows, Python 3.12.10, catálogo ficticio con un curso publicado, 20 consultas y 20 reservas secuenciales, sin carga web ni de red. Se midió el tiempo de llamada con perf_counter_ns, en milisegundos.

| Operación | Muestras | Media (ms) | Mediana (ms) | Máximo (ms) |
|---|---:|---:|---:|---:|
| Consultar cursos | 20 | 0.145 | 0.136 | 0.197 |
| Registrar reserva | 20 | 7.335 | 7.049 | 8.617 |

Fuente: salida de examples.demo_fabian y [JSON original](evidencias/evidencia_fabian.json). Son mediciones preliminares; falta cotejar la meta y condiciones exactas del documento vigente y repetir desde la aplicación integrada según la frecuencia acordada. No se afirma cumplimiento de una meta no verificada. El tiempo de la suite de pruebas no es tiempo de respuesta de una operación.

### Defect Metrics

Responsable: Fabián. En la última ejecución se observaron 0 fallos de 35 pruebas y 0 fallos de 6 escenarios. No se ha validado un inventario global de defectos abiertos, por lo que no se puede afirmar que el sistema tenga cero defectos. Clasificar cada defecto reproducible por gravedad, responsable, estado, evidencia y corrección verificada.

| ID | Hallazgo o limitación | Clasificación | Estado |
|---|---|---|---|
| LIM-F01 | Identidades ficticias; falta conectar autenticación, ámbito real y habilitación de docentes | Dependencia de integración, impacto alto | Pendiente |
| LIM-F02 | Consultas de pagos desde dos perfiles funcionan por código; falta evidencia visual | Dependencia de interfaz | Pendiente |
| LIM-F03 | Caducidad efectiva al consultar o realizar operaciones, sin proceso en segundo plano; falta comprobar refresco visual | Limitación de implementación | Pendiente |
| LIM-F04 | Estados del grupo draft/open; falta acordar cierre y conexión con el módulo académico | Dependencia de integración | Pendiente |
| LIM-F05 | Prueba independiente por otro integrante y revisión de la clienta | Validación pendiente | Pendiente |

Estas limitaciones se mantienen separadas de los defectos reproducidos. Si se reproduce un fallo, registrar su gravedad y estado; no convertir dependencias en defectos confirmados sin una prueba.

## Acuerdos confirmados y propuestas

Confirmados por el acta 1.1 (FUE-007): grupos por sede, sin lista de espera; reserva de 30 min; pago aprobado dentro del plazo confirma el lugar; rechazo, vencimiento o cancelación liberan el cupo; pago tardío no confirma; conservación de identificador, importe, moneda, estado y fechas; precio ficticio fijo por grupo, moneda según sede, sin conversión.

Propuestas técnicas del equipo: IDs UUID, fechas UTC con zona, importe en unidades monetarias menores (entero), sedes CDMX/BOG/MAD, países MX/CO/ES, estados internos en inglés, transacciones SQLite BEGIN IMMEDIATE, auditoría en la misma transacción. Precio de 45.50 EUR solo como dato ficticio de esta demostración. La cifra no es una tarifa real ni una exigencia de la clienta.

Pendientes de confirmación en el hilo del 26 de noviembre: vencimiento exactamente al cumplir 30 min (implementado provisionalmente como vencido); bloqueo de segunda solicitud con reserva vigente o inscripción confirmada; precisión sobre conteo de reservas vigentes junto a confirmadas (ya implementada conforme al SRS trabajado, pendiente de respuesta explícita al nuevo hilo). No atribuir esas respuestas a la clienta.

## Contrato provisional para integración

- Abrir una conexión por operación o hilo con enrollments.connect(path); usar la misma base SQLite que courses. No compartir una conexión entre hilos.
- Identidad validada en servidor: id, active, role, country y site_id cuando corresponda. Roles: international_director, country_coordinator, site_admin, teacher, student. No aceptar identidad arbitraria desde la interfaz real.
- groups.create recibe curso publicado, sede, docente y capacidad; requiere callback confiable teacher_is_enabled(course_id, teacher_id).
- groups.set_price y groups.open_enrollment fijan el precio y bloquean criterios académicos antes de inscripciones.
- enrollments.offer muestra precio, moneda y disponibilidad; reserve devuelve enrollment y payment, o FullGroup con alternatives; get consulta estados; cancel libera el lugar; set_capacity impide bajar de los cupos ocupados.
- payments.respond simula aprobación o rechazo por identificador; payments.consult consulta la operación con permiso. Mostrar approved_late como aprobación tardía sin confirmación y pedir nueva solicitud.
- No pasar clock desde la interfaz de producción: solo se inyecta para pruebas.
- Luis debe acordar identidad, ciclo de cierre, docentes habilitados y consumo de inscripciones confirmadas. José Ángel debe conectar pantallas y preparar capturas. Raziel debe integrar el módulo de cursos y coordinar la revisión.

## Plan de trabajo y riesgos

Estimaciones propuestas para coordinar, no horas reales registradas retrospectivamente.

| Tarea | Responsable | Esfuerzo estimado | Fecha objetivo | Estado | Dependencia |
|---|---|---:|---|---|---|
| Grupos y apertura | Fabián | 2 h | 27 nov | Probado localmente | Cursos |
| Reservas y concurrencia | Fabián | 3 h | 27 nov | Probado localmente | Grupos |
| Pagos simulados | Fabián | 2 h | 27 nov | Probado localmente | Reservas |
| Evidencias, métricas y documentación | Fabián | 2 h | 27 nov | Parcial | Ejecuciones locales |
| Conectar permisos y pantallas | Fabián, Luis, José Ángel | 3 h | 28 nov | Pendiente | Identidad y UI |
| Revisión independiente e integración | Fabián y equipo | 2 h | 28 nov | Pendiente | Módulos conectados |
| Actualizar SRS y responder observaciones | Fabián, Raziel | 2 h | 29 nov | Pendiente | Revisión de clienta |

Riesgos: demora de respuestas sobre reglas límite, contratos incompatibles, retrasos de integración y falta de tiempo para revisión independiente. Mitigación: mantener decisiones provisionales explícitas, compartir contrato, probar temprano y conservar evidencias reales.

## Registro de cambios y uso de IA

27 nov: grupos y precios (ec27868), pruebas de grupos (4a0a66a), reservas (cfe5c4b), pruebas de reservas (2b84d14), pagos (b046a3e), pruebas de pagos (1533f32), demostrador y medición (8c6d6cd). Afectan RF-002, RF-003, RF-004, DAT-003, DAT-005, DAT-006 y DAT-007; cotejar IDs con la versión vigente. Motivo: materializar las reglas del alcance y verificar excepciones. No se modifica el PDF histórico.

Se utilizó ChatGPT (OpenAI) para proponer la estructura, generar código, pruebas y documentación y registrar resultados. Fabián descargó los cambios y ejecutó las pruebas y demostraciones en su entorno Windows. La revisión humana detallada del código, la prueba por otro integrante, la integración y la aceptación por la clienta siguen pendientes. Los resultados se transcribieron de capturas reales; no se simularon tiempos ni se afirmó una revisión no realizada.
