# Red Aprende Internacional

Sistema de gestión de capacitación para una red con sedes piloto en Ciudad de México, Bogotá y Madrid. Proyecto de Ingeniería de Software de la Universidad Tecnológica de la Mixteca, grupo 502-B, equipo III.

## Estado del proyecto

Se completó la etapa de descubrimiento y acuerdo del segundo parcial. El alcance fue aceptado por la clienta con las precisiones incorporadas en el acta 1.1. El repositorio contiene la documentación inicial y las pantallas del prototipo. La implementación y la ejecución de las pruebas quedan pendientes.

## Documentación

- [Entrega del segundo parcial](docs/502_B_3.pdf). Incluye entrevistas, SRS inicial, prototipo, metodología, métricas, plan de desarrollo y acta con evidencia de aceptación.
- [Acta de alcance 1.1](docs/alcance/Acta_de_alcance_v1.1.pdf).
- [Fuente LaTeX del acta](docs/alcance/Acta_de_alcance_v1.1.tex).

El PDF entregado el 3 de noviembre de 2026 se conserva como referencia de esa entrega. Las decisiones posteriores deberán registrarse con su fecha y evidencia.

## Alcance del piloto

- Cursos y grupos organizados por país y sede, con asignación de docentes.
- Horarios de sede y equivalencias para cada usuario.
- Inscripciones, cupos y reservas de 30 minutos durante el pago simulado.
- Registro de asistencia y calificación final.
- Constancias sujetas a aprobación académica, con folio único e historial.
- Permisos para Dirección Internacional, Coordinación de País, Administración de Sede, Docente y Estudiante.

El piloto utiliza enlaces externos de videoconferencia y pagos simulados. Quedan fuera la lista de espera, los cobros y devoluciones bancarias reales, la conversión de divisas, una plataforma propia de videollamadas y el diseño de exámenes.

## Reglas principales

- El curso piloto requiere al menos 80 % de asistencia y 70/100 de calificación final. Ambas condiciones deben cumplirse.
- Una sesión cancelada por la institución no genera ausencia. Si se reprograma, solo se cuenta la celebrada. Sin sesiones celebradas, la asistencia es no calculable y se bloquea la constancia.
- Las reservas vigentes y las inscripciones confirmadas ocupan cupo. Las solicitudes simultáneas no pueden reservar el mismo último lugar.
- Un pago rechazado o una reserva vencida libera el cupo. Una aprobación tardía se registra sin confirmar la inscripción.
- Cada grupo tiene un precio ficticio fijo en MXN, COP o EUR según la sede organizadora. Cada intento conserva el importe y la moneda originales.

Los detalles y criterios de aceptación se encuentran en el acta y el SRS.

## Método y métricas

Se eligió el modelo en espiral de Boehm. Los ciclos consideran objetivos, análisis y reducción de riesgos, desarrollo y validación, y planificación del siguiente ciclo.

Las cinco métricas seleccionadas son tiempo de respuesta, tiempo de corrección de fallos de seguridad, defectos abiertos por gravedad, porcentaje de pruebas de aceptación aprobadas y satisfacción de la clienta. Las metas del equipo y sus condiciones de medición están documentadas en la entrega.

## Equipo

- Raziel Morales Pérez — liderazgo, entrevista, evidencias y alcance.
- Fabián Santiago Jiménez — coordinación del SRS, cursos, grupos, inscripciones, cupos y datos.
- José Ángel Gaytán Pérez — prototipo, recorrido e interfaces.
- Luis Antonio Arteaga Lázaro — metodología, métricas, plan, permisos y aprobación.

## Desarrollo

Las instrucciones de instalación, tecnologías y comandos de ejecución se añadirán al iniciar la implementación. Actualmente no existe una aplicación ejecutable en este repositorio.

## Uso de IA

Se utilizó ChatGPT (OpenAI) como apoyo para preparar entrevistas, redactar y revisar documentación y organizar esta publicación. La declaración de uso de IA de la entrega académica está incluida en su PDF. El equipo es responsable de revisar las futuras contribuciones antes de integrarlas.

La copia pública del PDF omite la imagen de la firma manuscrita del líder. La entrega académica original conserva su firma.
