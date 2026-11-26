# Avance de Raziel — cursos y coordinación

## Estado al 26 de noviembre de 2026

Módulo local ejecutable en Python 3.12 con SQLite, preparado como propuesta técnica mientras el equipo confirma la tecnología común. Tiene registro, edición de borradores, publicación, consulta y auditoría de cambios. Diez pruebas automatizadas pasaron en la ejecución registrada en `pruebas_cursos.txt`.

La integración completa, las interfaces web y la autenticación real siguen pendientes. Ninguno de los seis escenarios solicitados por Verónica se ha ejecutado completo todavía. El adaptador de consola utiliza un usuario ficticio de Dirección Internacional.

## Ejecución

Desde la raíz del repositorio:

```bash
python3 -m app.courses create --data examples/course.json
python3 -m app.courses list
python3 -m app.courses update --id ID_DEVUELTO --data examples/course.json
python3 -m app.courses publish --id ID_DEVUELTO
python3 -m unittest discover -s tests -v
```

Los datos se guardan en `courses.sqlite3`. El identificador se obtiene del resultado de creación. La opción `--database` permite elegir otra base local.

## Fuente y propuestas

Las funciones se basan en RF-001 del SRS y en los acuerdos de Verónica sobre Dirección Internacional, cursos publicados y umbrales definidos antes de abrir inscripciones.

Propuestas técnicas pendientes de revisión del equipo:

- Python y SQLite para la primera implementación local.
- Campos obligatorios de nombre, descripción, objetivos y ambos umbrales.
- Identificadores UUID y fechas UTC en auditoría.
- Estados internos `draft` y `published`.
- Los criterios se pueden editar antes de abrir inscripciones. La operación `lock_academic_criteria` fija los umbrales dentro de la transacción que abre las inscripciones, conservando los valores para todos los grupos del curso.

Los valores del piloto son 80 y 70. Cada curso puede configurarse con sus propios umbrales.

## Pruebas y resultados

| Caso | Resultado esperado | Resultado observado |
|---|---|---|
| Crear y reabrir la base | Curso conservado y evento de creación | Aprobado |
| Crear como estudiante | Rechazo y cero registros | Aprobado |
| Texto vacío o umbrales inválidos | Rechazo y cero registros | Aprobado |
| Editar borrador | Datos actualizados y auditoría anterior/nueva | Aprobado |
| Publicar dos veces | Una sola transición y curso visible | Aprobado |
| Editar umbrales antes de abrir inscripciones | Cambio permitido | Aprobado |
| Editar umbrales después de abrir inscripciones | Rechazo sin modificar valores | Aprobado |
| Falla al abrir inscripciones | Revertir apertura y bloqueo en la misma transacción | Aprobado |
| Publicar ID inexistente | Rechazo sin evento | Aprobado |
| Consultar con cuenta inactiva | Acceso rechazado | Aprobado |

Estas pruebas verifican el módulo y sus propuestas, no la aceptación de la aplicación completa por la clienta.

## Contrato para integración

Luis suministrará la identidad validada en servidor como `{id, role, active}`. El navegador no puede elegir esos valores. El rol de Dirección Internacional se representa provisionalmente como `international_director`.

Fabián usará el ID del curso publicado como referencia del grupo y consultará los umbrales del curso. Debe acordarse con él la transacción que abre inscripciones y fija las condiciones académicas.

José Ángel conectará las pantallas de cursos con las operaciones `create`, `update`, `publish` y `list_courses`. La consola actual es solo un medio de ejecución local.

Todas las operaciones de escritura guardan su evento de auditoría en la misma transacción. Se registran actor, acción, valores anteriores y posteriores y fecha.

## Tareas de Raziel e integración

Estimaciones propuestas, por confirmar con la disponibilidad real del equipo.

| Tarea | Responsable | Esfuerzo restante | Fecha objetivo | Dependencia |
|---|---|---:|---|---|
| Confirmar tecnología y contrato común | Raziel y equipo | 1 h | 26 de noviembre | Respuesta del equipo |
| Integrar identidad y pantallas de cursos | Raziel, Luis y José Ángel | 3 h | 27 de noviembre | Autenticación e interfaces |
| Integrar grupos, inscripción y pago | Raziel y Fabián | 3 h | 28 de noviembre | Módulo de grupos y pagos |
| Ejecutar curso completo y solicitar revisión | Raziel y equipo | 3 h | 28 de noviembre | Asistencia y constancias |
| Incorporar revisión, actualizar SRS y evidencias | Raziel y equipo | 3 h | 29 de noviembre | Respuesta de Verónica |
| Verificar instalación y paquete de entrega | Raziel y otro integrante | 1 h | 30 de noviembre, antes de 8:30 | Integración final |

Riesgos del proyecto: tecnologías incompatibles, trabajo sin integración, falta de disponibilidad y demora en la respuesta de la clienta. Acciones: confirmar contrato antes de integrar, revisar avances diariamente y preparar la demostración antes del cierre. Si falta respuesta, conservar la solicitud y registrar el estado pendiente.

## Revisión con la clienta

El mensaje que publique Raziel debe indicar que actualmente se dispone del módulo local de cursos y que los seis escenarios completos siguen pendientes. Cada actualización debe enlazar el requisito, la prueba ejecutada, el resultado y la evidencia. La revisión del cliente y sus cambios se documentarán después de ocurrir.

## Registro de cambios y uso de IA

Se utilizó ChatGPT de OpenAI para generar el módulo local de cursos, las pruebas y este registro de integración. La ejecución automática obtuvo diez pruebas aprobadas. La revisión humana del código, la aprobación de la tecnología y la demostración del equipo siguen pendientes. El SRS entregado se conserva como referencia histórica y este archivo registra propuestas nuevas sin atribuirles aceptación de Verónica.

## Integración del bloqueo académico

Fabián debe iniciar `BEGIN IMMEDIATE`, verificar el permiso sobre el país y la sede del grupo y llamar a `lock_academic_criteria` dentro de la misma transacción que abre inscripciones. Confirmará ambos cambios juntos o revertirá ambos ante errores. El módulo de cursos comprueba el rol general. La validación del ámbito específico del grupo corresponde al módulo de grupos.

Las interfaces y Figma corresponden a José Ángel. Este avance entrega operaciones Python para conectar esas pantallas. La identidad autenticada corresponde a Luis. Las pruebas usan identidades ficticias.
