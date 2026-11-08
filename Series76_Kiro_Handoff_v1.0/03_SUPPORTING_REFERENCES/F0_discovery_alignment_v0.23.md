# Series 76 Technical Assistant — Documento vivo de alineación F0

**Versión:** 0.11 (historial F0 cerrado; decisiones incrementales F1; NO es una Spec de Kiro)  
**Fecha de actualización:** 2026-11-07 (America/Bogota; F0 cerrada y seguimiento F1 en curso)  
**Estado:** **F0 formalmente cerrada por aprobación explícita del candidato**. F1 abierta para inventario, modelado de dominio y ETL. Consultar §40–43 para decisiones y correcciones vigentes. Las entradas anteriores que señalan decisiones F0 abiertas son historial y están superadas. El catálogo F0 es material de alineación aprobado, no Specs de Kiro.  
**Lectura del historial:** las secciones 13–23 incluyen decisiones y preguntas de versiones anteriores por trazabilidad; si divergen, prevalecen la tabla de decisiones vigente (§4) y las novedades ratificadas en §24–35. Los pendientes históricos ya resueltos permanecen como historial, no se reabren. **Las preguntas de versiones anteriores no son decisiones abiertas si fueron cerradas posteriormente.** Se agrega como observación F1 que el PDF tiene **7 tablas eléctricas independientes**, repartidas en 4 páginas; el inventario anterior de 6 agrupaba erróneamente las dos tablas de Explosionproof en p. 4.

**Objetivo:** documentar la visión acordada por el candidato y el arquitecto asesor, más hipótesis, riesgos, alternativas y preguntas abiertas, antes de pedirle a Kiro la generación formal de specifications, design y tasks.

## 1. Fuentes y precedencia

1. `assessment-en.pdf`: restricciones contractuales y criterios de evaluación.
2. `series_76_electric_data.pdf`: única fuente de verdad de cifras técnicas de actuadores; cuatro páginas de tablas representadas como imágenes.
3. `series_76_summary.pdf`: contexto de negocio y glosario; no puede sustituir a la fuente oficial para datos numéricos.
4. `Series 76 First Toughts.md`: ideas iniciales e hipótesis del candidato.
5. Decisiones y aclaraciones expresas del candidato durante esta alineación.

En caso de contradicción con el assessment, debe prevalecer el assessment y registrarse el conflicto. Las hipótesis técnicas de este documento no son decisiones aprobadas.

## 2. Restricciones verificadas del assessment

- Backend Python/FastAPI; LangChain como framework de agente; al menos una herramienta LangChain personalizada que consulte tablas.
- Ingesta ejecutable desde el PDF original y datos procesados o instrucciones reproducibles para generarlos.
- PostgreSQL local, containerizado; `pgvector` solo si el caso de uso requiere búsqueda vectorial.
- API fija como mínimo `POST /api/conversation`, request con `query` y `session_id` opcional, response con `session_id` y `answer`, campos adicionales libres.
- Historial multi-turno persistente por sesión; recuperación tras reinicio.
- App nativa Kotlin/Jetpack Compose (opción escogida): conversaciones, chat con comparación visual y Debug exclusivo de desarrolladores; loading/error en todas.
- Edge cases: IDs inválidos, ausencias, ambigüedad, cero coincidencias.
- Sólo las tablas eléctricas proporcionadas pueden autorizar números técnicos.
- Modelos a través de OpenRouter, configuración por variables de entorno; presupuesto total de la clave entregada USD 10.
- Un único repositorio, Dockerfile, Compose, `.env.example` sin credenciales, README reproducible e inclusión de la configuración del asistente de desarrollo.
- Login y voz son opcionales en la prueba; el candidato **eligió** incluir login y posponer voz.
- Fecha límite expresada por candidato: lunes 2026-11-09 final del día (hora exacta por confirmar); disponibilidad aproximada: ocho horas diarias.

## 3. Visión del producto aprobada por el candidato

**Personas usuarias:** ingenieros de selección, mantenimiento y técnicos de planta.  
**Idiomas:** inglés y español.  
**Horizonte:** MVP completo reproducible, con arquitectura que permita evolución a producción; prioridad equilibrada entre cumplimiento y calidad.  
**Capacidades:** consulta por Base Part Number; búsqueda y filtrado por requisitos; explicaciones exclusivamente fundamentadas en PDFs; comparación, conversiones, cálculos derivados deterministas, detección de incompatibilidades y asistencia para formular requisitos; recomendaciones ordenadas y justificadas.  
**Recomendaciones:** mostrar la lista nominal completa de coincidencias y las fichas completas de `min(N, 3)` en búsquedas y rankings múltiples; si se pide **top-1**, mostrar el ganador y el total de elegibles sin desplegar otros PN. Ordenamiento **lexicográfico aprobado**, prioridades explícitas primero y desempate estable por Base Part Number.  
**Aclaraciones:** APROBADO: mostrar siempre la interpretación; exigir confirmación sólo según intención, ambigüedad, riesgo o criterios delegados, sin bloquear consultas exactas inequívocas. Plan versionado y corregible; nunca asumir requisitos físicos desconocidos. Se permiten resultados preliminares claramente marcados cuando faltan criterios de compatibilidad; no llamarlos recomendaciones verificadas.  
**Restricciones expresas:** los criterios duros y preferencias deben tratarse de modo diferente; consultas fuera de las fuentes disponibles no se responden especulativamente.  
**Conversaciones:** crear, listar, continuar, renombrar, borrar y buscar.  
**Autenticación:** desde primera versión; login/logout y autorregistro de cuentas `user` desde Android; cuentas de prueba precargadas (`user` y `developer`); ningún registro público puede crear `developer`; acceso por propietario; Debug visible solo para rol developer, también en producción, solo trazas propias en app.  
**Trazas:** completas durante la vida de la conversación, con controles de acceso por rol+propietario, redacción de secretos; al borrar conversación, borrar también trazas detalladas del almacenamiento activo. Backups y auditoría mínima requieren política en F3.  
**UI:** tabla de hasta tres productos con highlights semánticos y comparación simultánea de hasta dos; filtros visuales; barras opcionales donde aporten y barras agrupadas sólo con unidades/condiciones compatibles; no tortas/histogramas para esta comparación. Debug como tercera pantalla navegable en la misma build, visible exclusivamente para developer y protegida en API.  
**Voz:** diferida. **Budget:** máximo de USD 6 de la clave de OpenRouter para desarrollo, comparación y evals, reservando por lo menos USD 4 para demo/uso final; Google AI Studio disponible solo para experimentación auxiliar según el assessment.  
**Proceso:** siete fases F0–F6; revisiones y rectificaciones mediante opciones más ADR, aprobación expresa del candidato; Kiro generará posteriormente specs, diseño, código, pruebas y documentación, sin tomar decisiones de producto no autorizadas.

## 4. Registro de decisiones (ADR-lite)

| ID | Tema | Estado | Decisión/hipótesis | Razonamiento y consecuencias |
|---|---|---|---|---|
| D-001 | Fases | APROBADA | F0 alcance; F1 dominio/ETL; F2 agente; F3 APIs/backend; F4 Android; F5 calidad/entrega; F6 transferencia Kiro | Evitar implementación antes del cierre de criterios | 
| D-002 | Documentación | APROBADA | ADR + requisitos INVEST + escenarios de calidad + trazabilidad requirement→component→test | Entrevista y mantenibilidad |
| D-003 | Stack | APROBADA | FastAPI, PostgreSQL, Kotlin/Compose; LangChain y OpenRouter impuestos por assessment | Cumplimiento |
| D-004 | Retrieval técnico | APROBADA | SQL estructurado mediante herramientas tipadas; no text-to-SQL libre | Mayor auditabilidad; pgvector no necesario por defecto |
| D-005 | Identidad | APROBADA | Autenticación primera versión con autorregistro exclusivo de rol `user`, logout y cuentas precargadas de prueba `user`/`developer` | Propiedad de sesiones, rol asignado exclusivamente por backend; provisionamiento de developers fuera de app |
| D-006 | Idiomas | APROBADA | Inglés y español | Casos y evaluaciones bilingües |
| D-007 | Fuentes | APROBADA | Solo PDF eléctrico autoriza valores técnicos; cálculos derivados permitidos | Requiere cálculo determinista, procedencia y unidades |
| D-008 | Recomendaciones | APROBADA | Evaluar entorno, alimentación, servicio y torque para recomendación documentada; si falta un grupo físico relevante, candidatos PRELIMINARY; todos los PN coincidentes y hasta tres fichas completas; top-1 bajo mismo ranking | No certificar aptitud integral de instalación ni inventar dato físico delegado |
| D-009 | Trazas | APROBADA | Trazas completas de herramienta/ejecución | Requiere retención, redacción de secretos y RBAC |
| D-010 | Debug | APROBADA | Pantalla navegable en build de producción; UI oculta para no-developers y endpoint protegido por RBAC+propiedad | Trazas de todas las conversaciones persistidas para auditoría interna autorizada; usuarios developer solo sus conversaciones desde app |
| D-011 | Voz | APROBADA | Posponer hasta terminar obligatorio + login | Foco en fiabilidad |
| D-012 | Extracción | ABIERTA | Comparar OCR de tablas, visión multimodal, combinación | PDF de imagen con tablas densas y celdas combinadas |
| D-013 | Orquestación | APROBADA | Híbrido con autonomía limitada: selección/composición de herramientas tipadas bajo controlador, límites y guardrails | Flexibilidad sin libertad para inventar datos ni ejecutar SQL libre |
| D-014 | Estado | APROBADA CON DISEÑO PENDIENTE | Historial, estado de dominio, checkpoints y trazas lógicamente separados; se favorece checkpoint PostgreSQL | Definir implementación y sincronía en F2/F3 |
| D-015 | Modelos | APROBADA EN MÉTODO; MODELOS ABIERTOS | Seleccionar por tarea con benchmarks de calidad, soporte tools/JSON, latencia/coste; presupuesto OpenRouter para evaluación máximo USD 6 | USD 4 reservados para demo final; AI Studio solo auxiliar según assessment |
| D-016 | Opcionales | PARCIALMENTE CERRADA | No MCP, no RAG/pgvector, no voz por ahora; considerar cola PostgreSQL, gráficas y criptografía solo si aportan | No añadir tecnologías por currículum |
| D-017 | Respuesta | APROBADA | Híbrida: LLM para interpretar/explicar, valores técnicos calculados/renderizados por backend desde fuente verificada | Control de cifras en texto libre, provenance y validación de claims pendientes de diseño |
| D-018 | Ranking | APROBADA | Ranking lexicográfico; prioridades explícitas prevalecen sobre orden textual; proponer y confirmar prioridades provisionales; desempate final estable por Base Part Number | La semántica de «mejor» depende de cada métrica y su comparabilidad; no asignar ceros a N/A |
| D-019 | Concurrencia | DIRECCIÓN APROBADA; CONTRATO PENDIENTE | Serialización duradera por sesión en PostgreSQL, admisión asíncrona de turnos adicionales | Definir API de trabajos, respuesta de POST obligatorio, FIFO por sesión, idempotencia y recuperación |
| D-020 | Offline Android | APROBADA CON DISEÑO PENDIENTE | Cache de conversaciones + metadatos/tokens seguros; NO agentes locales ni offline first; al logout no mostrar cache, al cambio de usuario purgar anterior, al borrado sincronizar ambos | Cifrado, aislamiento por owner y UX de error por definir |
| D-021 | Búsqueda semántica | APROBADA | No RAG, no pgvector, no fine-tuning de embeddings para el corpus actual | El PDF técnico es tabular; exact match y filtros SQL garantizan más control |
| D-022 | Alcance Debug | APROBADA | Trazas completas almacenadas server-side para auditoría; la app muestra solo las propias si el rol es developer | Auditoría transversal, si procede, requerirá permiso y flujo distintos del móvil |
| D-023 | UI de comparaciones | APROBADA | Hasta tres fichas/columnas y vista dual; permitir tablas informativas de condiciones diferentes con advertencia, sin proclamar ganador no comparable; highlights semánticos; barras/multibarras opcionales sólo con condiciones homogéneas | Tabla principal, gráficos nunca sustituyen cifras exactas |
| D-024 | MCP | APROBADA | No integrar MCP en MVP; reevaluar solo ante caso real de herramienta externa | Evita superficie y complejidad artificiales |
| D-025 | Presupuesto LLM | APROBADA | Máximo USD 6 para selección/benchmarks/evals/desarrollo y reserva mínima USD 4 de clave provista para funcionamiento/demo | Medición de coste por ejecución, guardrail de presupuesto y mocks |
| D-026 | Confirmación del plan | APROBADA | Política C: vista de interpretación siempre, confirmación condicional según intención, ambigüedad/riesgo/delegación. Plan versionado y corregible. Lookup devuelve todos los valores contextuales pertinentes si es legible. | Lookups inequívocos sin bloqueo; las recomendaciones con planes no triviales requieren aprobación |
| D-027 | Criptografía adicional | ALCANCE BASE APROBADO; AES-256-GCM APROBADO POR EL CANDIDATO | SHA-256 para integridad de artefactos; Argon2id para passwords; TLS y Android Keystore; cifrar contenido sensible de conversaciones/trazas antes de PostgreSQL con AES-256-GCM; almacenamiento de claves separado, detalles de rotación, indexación y granularidad de claves pendientes para F3. No ML-DSA ni ML-KEM en MVP. | Cubre amenaza de filtración sólo de BD; requiere cifrar títulos y trazas sensibles, separar y rotar claves, diseñar búsqueda y backups |
| D-028 | Catálogo de tools | MÉTODO APROBADO; DISEÑO ABIERTO | Preferencia por tools especializadas get/search/compare cuando ensayos muestren mejora; si no, tool tipada única | Pruebas iguales para ambas y límite de gasto establecido |
| D-029 | OCR y visión | CANDIDATA | Comparar 2–3 pipelines, validación humana exhaustiva de datos aceptados | No confiar en confianza OCR/LLM para aprobar cifras |
| D-030 | Gráficos Android | APROBADA | Barras opcionales y barras agrupadas si mejoran comparación y mantienen mismas unidades/condiciones; sin tortas/histogramas por defecto | Tabla sigue como presentación canónica de valores exactos; N/A no es cero |


## 5. Riesgos y oportunidades

| Riesgo | Impacto | Mitigación candidata, no aprobada |
|---|---|---|
| OCR confunde tabla/fila/columna/unidades/celdas combinadas | Crítico | Ingesta en dos etapas + manifiesto y auditoría visual fila/celda contra PDF |
| Un mismo Base Part Number con comportamientos distintos por servicio/frecuencia | Crítico | Modelar dimensiones y no aplanar la fila a un único valor |
| Modelo LLM genera cifras aunque JSON sea válido | Crítico | Datos numéricos construidos por backend desde SQL + renderizado de bloques estructurados |
| Usuario no aporta valores de compatibilidad y delega al LLM | Alto | Separar criterios de seguridad/compatibilidad de preferencias delegables |
| Herramienta ejecuta parámetros no autorizados | Alto | Schemas tipados, enums, validaciones, SQL parametrizado/readonly, límites de consultas |
| Prompt injection divulga logs/operaciones internas | Alto | Rol developer validado server-side, limitación de tool permissions, prompt treated as untrusted |
| Concurrencia genera historial contradictorio | Alto | Versionado por sesión, idempotencia por envío, único turno activo o serialización durable |
| Trazas exponen tokens, datos de otro usuario, prompts | Alto | Redacción, separación lógica y retención; acceso por rol y propiedad |
| Extra features ponen en riesgo plazo | Alto | Gate explícito: contribución a caso de uso, riesgo, coste, evidencia y dependencias |
| Modelos proveedor no admiten strict JSON + tools a la vez | Medio/alto | Verificación por endpoint y tests contractuales contra modelos candidatos |
| Usuario pregunta algo no presente en PDFs | Medio | Declarar incapacidad, no acudir a conocimiento genérico del LLM |
| API no es reproducible sin claves externas adicionales | Alto | Pipeline local/correcciones versionadas; .env.example; instrucciones de regeneración |

## 6. Reglas de dominio aún por diseñar

- Dimensiones: enclosure (Weatherproof/Explosionproof), suministro (24 V AC/DC; 110/220 V monofásico; 220 V trifásico donde aplique), modo On/Off vs Modulating, motor/torque, duty cycle, cycles/starts per hour, speed, FLA, LRA, motor power, frecuencia 50/60 Hz cuando aplica, certificaciones y notas.
- El PDF 24 V Explosionproof separa números de parte de On/Off y Modulating; otras tablas presentan atributos de ambos servicios por número de parte. No modelar de forma universal sin validación.
- En 220 V Weatherproof 3-phase la tabla contiene N/A para determinadas entradas; no extrapolar otros valores.
- Notas/asteriscos, frecuencia, motor power de celdas fusionadas y valores vacíos requieren semántica explícita.
- Un campo ausente puede representar no aplicable, no disponible, desconocido, no incluido en el subconjunto o fallo de extracción; es necesario preservar el motivo.
- Datos técnicos fuera de los documentos no son susceptibles de inferencia o extrapolación.
- Ranking a definir: filtros obligatorios, preferencias y sus pesos, unidades normalizadas, dirección de orden, desempates y rango de valores.
- Derivaciones: sólo fórmulas y conversiones aprobadas, valores originales conservados, redondeo definido, marcación como DERIVED y evidencia.

## 7. Alternativas técnicas que requieren debate

### 7.1. Respuesta y exactitud
A) LLM libre con contexto SQL: natural pero riesgo de cifras incorrectas.  
B) Plantillas enteramente deterministas: robustas pero menos conversacionales.  
C) **APROBADO**: LLM para intención y explicación + construcción/renderizado determinista de valores y cálculos confiables. Textos numéricos libres aún exigen controles.

### 7.2. Orquestación del agente
A) Agente dinámico que decide herramienta y ciclos; máximo margen, coste y superficie de falla.  
B) Flujo acotado de operaciones tipadas; predecible, menos expresivo.  
C) **APROBADO**: híbrido con autonomía limitada, guardrails, límites y catálogo de herramientas tipadas.

### 7.3. Criterios de aclaración
Estados candidatos `UNSPECIFIED`, `SPECIFIED`, `NO_PREFERENCE`, `DELEGATED`, `UNKNOWN`; separar criterios de compatibilidad de ranking y parámetros condicionales. `UNKNOWN` no equivale a `DELEGATED`. No exigir todos los criterios a preguntas de identificación exacta.

### 7.4. Memoria persistente
A) Sólo historial de mensajes y reconstruir estado en cada turno.  
B) Historial más estado estructurado versionado (criterios, referencias, resultados previos).  
C) **APROBADO CONCRETAMENTE COMO DIRECCIÓN**: B + checkpoints persistentes en PostgreSQL para ejecución/resumibilidad.  
D) Event sourcing completo; coste considerable.  
Mantener separados: mensajes visibles, estado de dominio, estado técnico del agente, trazas de auditoría.

### 7.5. Concurrencia
A) Lock asyncio local, inadecuado para múltiples workers/restarts.  
B) Serializar por sesión mediante control DB/versioning e idempotencia y rechazar/esperar colisiones.  
C) Cola durable PostgreSQL por sesión, workers y states, admite rearme tras restart; diseño más complejo.  
D) Broker Redis/RabbitMQ, innecesario sin demanda demostrada.

### 7.6. Debug exclusivo de desarrolladores
A) Ruta de navegación en build `debug` + backend RBAC `developer` (evaluada y descartada por el usuario al exigir Debug en producción).  
B) **APROBADA**: ruta de navegación dentro de la build de producción, habilitada por rol `developer` y protegida por propiedad y rol en backend.  
C) Pantalla en flavor dev/demo con acceso explícito para evaluadores, release sin funcionalidad de debug.  
Una bottom sheet/modal puede complementar detalle, pero no sustituye inequívocamente una tercera pantalla.

### 7.7. OCR/visión
A) OCR de tablas local; B) modelo visual para tablas; C) pipeline combinado; D) extracción seguida de validación manual exhaustiva versionada. Todos deben asociar cada dato a página, tabla, fila y versión de origen. Prueba en muestras representativas y verificación 100% de celdas cargadas antes de permitir consultas técnicas.

### 7.8. Adiciones tecnológicas
- MCP: descartado en MVP, salvo futura integración externa con caso real.
- pgvector y RAG: descartados en alcance actual; no hay corpus narrativo extenso. Alternativas SQL tipadas aprobadas.
- Colas: potencialmente justificadas por concurrencia por sesión y ejecución durable; evitar broker adicional si PostgreSQL basta.
- Criptografía: TLS, Argon2id, autorización, secretos y Keystore como base. SHA-256 para comprobar integridad del PDF/manifiesto contra hash confiable. ML-DSA y ML-KEM descartados explícitamente para el MVP. No afirmar origen fabricante por firmar nuestro propio manifiesto.
- Caché de historial Android: aprobada, incluyendo separación por usuario, ocultar en logout y purgar anterior en cambio de usuario; falta definir cifrado local, sincronización/borrado y protección de claves.

## 8. Catálogo inicial de casos de uso (candidatos; no INVEST final)

| UC | Objetivo | Resultado exitoso | Casos límite |
|---|---|---|---|
| UC-01 | Autenticarse | Token/sesión segura; identidad estable | Credenciales inválidas, token vencido, usuario sin permiso |
| UC-02 | Crear conversación | Sesión asociada al propietario | Doble creación por reintento |
| UC-03 | Consultar modelo exacto | Ficha con valores exactos y procedencia | PN inválido, similar, no incluido |
| UC-04 | Recomendar según restricciones | Conjunto filtrado y ranking explicado | Faltan criterios, incompatibilidad, 0 resultados |
| UC-05 | Comparar modelos | Tabla comparable y highlights con unidades | Diferentes frecuencias, valores N/A |
| UC-06 | Refinar por follow-up | Estado actualizado sin repetir todo | Pronombres, revisiones, referencias ambiguas |
| UC-07 | Explicar valores documentados | Conceptos cubiertos por PDFs y límites | Consulta sin respaldo documental |
| UC-08 | Convertir/calcular | Resultado determinista con fórmula y procedencia | Fuentes incompletas, incompatibilidad de unidades |
| UC-09 | Gestionar conversaciones | Listar, continuar, renombrar, borrar, buscar | Permisos, concurrencia, borrado y trazas |
| UC-10 | Depurar respuesta | Developer ve tool calls, argumentos, resultados y error | Acceso user ordinario, secretos en log |
| UC-11 | Continuar tras reinicio | Estado e historial consistentes | Turno interrumpido, reintentos duplicados |
| UC-12 | Bilingüismo | Consulta y respuesta natural en inglés/español | Mezcla idiomas, nombres técnicos y códigos inalterados |

## 9. Estrategia de evaluación (borrador)

- Golden set validado manualmente por tabla/fila/columna; checksums de PDF, manifiesto de ingesta y cotejo integral de cifras/unidades.
- Pruebas de IDs válidos/incorrectos, casos de 24V, trifásico, ambos servicios, 50/60 Hz, N/A y notas.
- Evals de extracción de slots, identificación de tipo de pregunta, tool selection y memoria multi-turno bilingüe.
- Correctitud de restricciones hard/soft y ranking; propiedades monotónicas y ties deterministas.
- Concurrencia por sesión, idempotencia de request, caída del backend, reanudación, borrado.
- Seguridad: ownership por ID, roles, prompt injection, exfiltración de traces, SQL injection y secrets leakage.
- UI/UX: loading/error/empty states, comparaciones, accesibilidad, offline/reconexión.
- Presupuesto: medir tokens/costo por intención, número de llamadas LLM, p50/p95 y latencia por etapa.
- Definir thresholds antes de implementar. Cero discrepancias numéricas en suite verificada como requisito de aceptación, sin prometer perfección universal de un LLM.

## 10. Preguntas prioritarias restantes de F0

1. ¿Se adopta el agente híbrido de autonomía limitada como hipótesis principal de evaluación, o comparamos formalmente A/B/C en un spike?
2. ¿Qué atributos de compatibilidad obligan a aclaración antes de recomendar? ¿Se admite 'desconozco' como dato completo sin recomendar?
3. ¿Delegar criterios al agente significa política determinista documentada y no decisión libre del LLM?
4. ¿Cómo se define un ranking? ¿Cuál es el orden de prioridades por defecto y cómo manejar multiobjetivo/empates?
5. ¿Qué operaciones de consultas compuestas debe cubrir el MVP, más allá de lookup, filtrar, comparar, convertir y recomendar?
6. ¿Persistimos state slots/conversation history/checkpoints, con qué versión/ciclo de vida, y qué es la fuente canónica?
7. Se aprobó serialización persistente por sesión en PostgreSQL y admisión asíncrona adicional. Queda por diseñar el contrato exacto de admisión/consulta de trabajos y recuperación en F3.
8. Debug en misma build y con rol developer ya aprobado. Falta definir ruta UX, almacenamiento/retención y auditoría privilegiada fuera del móvil.
9. Caché por usuario aprobada; resolver almacenamiento cifrado, invalidez de tokens, exclusión de backup y borrado consistente local/remoto.
10. ¿Qué estrategia reproducible y de bajo coste usaremos para OCR/visión y revisión exhaustiva de las tablas?
11. Confirmar hora exacta de entrega el lunes 2026-11-09, zona horaria y presupuesto real de pruebas.

## 11. Próximas actividades de F0

- Precisar los tipos de consulta y los requisitos mínimos por intención.
- Definir el catálogo de criterios y las reglas de aclaración/rechazo/delegación.
- Definir el contrato de recomendaciones (ranking, todos los nombres, top-3 fichas, evidencia y comparaciones).
- Registrar edge-case policy y criterios de aceptación sin entrar en diseño físico de tablas.
- Congelar F0 con decisión y justificación del candidato; pasar a F1.

## 12. Reglas de evolución del documento

- Nunca promover `ABIERTA` a `APROBADA` por inferencia del asistente.
- Cada cambio debe conservar el razonamiento anterior, el problema detectado, alternativas, la elección explícita y el impacto en requisitos/pruebas.
- Las decisiones de implementación serán trasladadas a Kiro como restricciones de diseño; este archivo **no reemplaza** specs formales.
- Actualizar versión y fecha en cada nueva consolidación relevante.


---

## 13. Bitácora de cambios v0.1 → v0.2

- El usuario explicó que consideraba fine-tuning del **modelo generador de embeddings**, interpretación técnicamente válida para mejorar retrieval; se separa conceptualmente del chunking. RAG/pgvector/fine-tuning se descartan por falta de corpus narrativo y por la superioridad de consultas tabulares exactas.
- Se aprueban respuesta híbrida con cifras derivadas de backend e agente híbrido con autonomía limitada, dejando por definir límites y validadores concretos.
- Se aprueba auth desde inicio, RBAC + propietario y Debug presente en producción para cuentas developer; trazas persistidas en servidor para posible auditoría interna/external mediante otra autorización.
- Se reduce la cantidad de resultados con ficha completa de 5 a 3, con tabla comparativa hasta 3 y comparación de 2 en paralelo. Todos los IDs compatibles deben seguir disponibles cuando se pide el conjunto completo.
- Se aprueba caché móvil por usuario, sin inferencia offline; se proponen semánticas de logout/cambio de usuario/borrado, pendientes de diseño seguro.
- Se aprueba un límite de gasto de USD 6 para desarrollo y USD 4 como reserva, así como evaluación de 1–2 esquemas alternativos de herramientas por ensayos.
- Ranking lexicográfico y cola PostgreSQL se registran como **preferencias, no arquitectura decidida**.
- Se añade la propuesta del usuario de confirmación previa del plan interpretado antes de ejecutar: queda **abierta** por sus consecuencias UX, de costo, latencia, idempotencia y estado.
- Se agrega debate de gráficas y caso concreto de criptografía ML-DSA/ML-KEM/SHA-256; se distingue entre controles básicos obligatorios y extras sujetos a valor.

## 14. F0.1 — Taxonomía de intenciones y niveles de aclaración (propuesta sin aprobar)

| Clase | Ejemplo | Información mínima | Confirmación candidata | Resultado |
|---|---|---|---|---|
| `EXACT_LOOKUP` | Datos del PN X | PN resoluble; atributo si pregunta parcial; dimensión si referencia ambigua | Ninguna si inequívoca | Respuesta/ficha estructurada con procedencia |
| `FILTER_SEARCH` | Todos los 220V con torque ≥ T | Al menos un filtro verificable; semántica AND/OR | Si hay condiciones ambiguas/delegadas | Todos los PN coincidentes, hasta 3 fichas si pertinente |
| `PRODUCT_RECOMMENDATION` | Recomienda modelo para necesidades | Compatibilidad suficiente, preferencias relevantes explícitas o delegadas con política aprobada | Sí, especialmente al emplear criterios delegados | Ranking estable + justificación + cautelas |
| `COMPARE` | Compara X e Y | Referencias claras, servicio/frecuencia comparable cuando corresponda | Solo si faltan parámetros o se aplican supuestos | Tabla hasta 3 y vista de 2 |
| `DERIVED_CALCULATION` | Convierte Nm a in-lbs, diferencia relativa | Fuentes, unidades y fórmula aprobada | Según ambigüedad/riesgo | Valor derivado etiquetado + origen y regla |
| `DOCUMENTED_EXPLANATION` | Qué es FLA | Evidencia en los PDFs | No para preguntas simples | Explicación acotada, sin datos externos |
| `FOLLOW_UP` | ¿y el segundo? | Referente recuperable del estado/historial | Solo ante referencia equívoca | Continuación con contexto correcto |
| `OUT_OF_SCOPE` | Precio, instalación, normas no documentadas | Ninguna | No | Abstención precisa indicando limitación de fuente |

### 14.1. Política de confirmación — tres opciones abiertas

A. **Siempre confirma**: fidelidad a idea original del usuario; mayor fricción, llamadas extra, costo y dificultad de cola.
B. **Confirma cuando hay decisión o interpretación no trivial**: recomendaciones y supuestos delegados sí; lookups inequívocos no. Control del usuario para escenarios importantes.
C. **Siempre muestra interpretación, confirmación solo condicional**: vista informativa no bloqueante para consultas simples, aprobación requerida para riesgo/ambigüedad.

En cualquier caso, el *plan aprobado* debe ser una entidad versionada y vinculada al propietario, sesión y consulta; `confirm` debe comparar versión exacta y ser idempotente. Una corrección invalida versiones anteriores. El flujo no debe pedir confirmar parámetros sobre los que no exista evidencia de que importen a la consulta.

### 14.2. Estados de criterios y procedencia — propuesta

No mezclar el estado de valor de un criterio con la aprobación de la interpretación general. Criterio:

- `UNSPECIFIED`: no mencionado.
- `SPECIFIED`: valor/intervalo/conjunto explícito.
- `NO_PREFERENCE`: instrucción explícita de no filtrar/ordenar por este criterio.
- `DELEGATED`: autoriza aplicar una política documentada de preferencias, NO inventar compatibilidad física.
- `UNKNOWN`: se declara desconocimiento; no equivale a delegación.
- `NOT_APPLICABLE`: no relevante para la intención o no aplica según fuente verificada.
- `CONFLICTING`: hay restricciones incompatibles o referencias contradictorias; bloquea ejecución o requiere corrección.

Metadatos candidatos: clase `HARD/SOFT/CONTEXT`, operador, valor, unidad, origen `USER/CONTEXT/DOCUMENTED_DEFAULT/POLICY`, mensaje fuente, prioridad explícita/derivada, versión, alcance (solo turno/sesión), estado de aprobación e indicación al usuario. Defaults de seguridad/electrificación jamás proceden de invento del LLM.

### 14.3. Catálogo de filtros y precauciones — propuesta

Compatibilidad potencial: enclosure, tipo y tensión de alimentación, número de fases, modo On/Off vs Modulating, torque mínimo exigido, frecuencia cuando corresponde, límites de duty cycle, ciclos/arranques por hora, corriente FLA/LRA si limitaciones eléctricas, velocidad, potencia. Notas y certificaciones deben ser restricciones documentadas y no inferirse desde el nombre del modelo. No todos aplican a todas las intenciones. La importancia y obligatoriedad de cada criterio está **pendiente** de matriz por intención y caso de uso.

## 15. F0.1 — Ranking, UI y flujo asíncrono (propuestas)

- Ranking lexicográfico: primero cumplimiento estricto de hard constraints; después preferencias en **prioridad explícita del usuario**; cuando no haya prioridad explícita, pedirla o presentar orden provisional para aprobación; nunca asumir que primer atributo mencionado es el más importante si lenguaje indica otra cosa. Dirección `higher/lower/target/range` por semántica del criterio, no por signo aritmético sin contexto. Empate estable por identificador o regla aprobada; registrar razones por resultado.
- Gráficas: máximo una barra/dot plot por métrica y unidades comparables para 2–3 candidatos; no pie ni histograma para ese uso; tabla obligatoria como fuente principal.
- Cola PostgreSQL: usar admisión transaccional e idempotency key, encolar turnos por sesión con secuencia total, `pending/running/completed/failed`, leases con caducidad, reintentos con deduplicación y revisión del estado de negocio; no mantener transacción abierta durante LLM. El backend debe conservar la compatibilidad del POST requerido para respuestas finales normales; `202 pending` y endpoint de estado opcional requieren validación específica respecto del assessment. `async/await` y coroutines evitan ANR en Android; una cola no es condición para ello.
- Dev trace: ruta solo visible a developers en misma build de producción, backend autoriza rol y pertenencia del mensaje; backend puede mantener registros para auditorías globales pero ésta es otra función/permisión, no acceso transversal del developer móvil.
- Caché: al cerrar sesión no mostrar datos locales anteriores, sin afirmar que eso equivale a cifrado o revocación criptográfica; separar por owner, impedir acceso sin autenticar y evaluar cifrado usando Android Keystore. En cambio de usuario, purgar cache anterior; al borrar, coherencia servidor-dispositivo y tratamiento de falta de conectividad.

## 16. Evaluación específica de criptografía adicional

**Histórico (decisión ya cerrada en v0.3):** ¿se incorpora una firma digital verificable del manifiesto de ingesta aprobado (ML-DSA), o solo hash SHA-256? **Resuelto después:** solo SHA-256; ML-DSA descartado. Firmar un manifiesto propio demuestra autoría del proyecto y detección de alteraciones, NO autoría del fabricante. Requiere estrategia de clave privada, distribución de clave pública y verificación reproducible.

ML-KEM es un KEM para establecer claves compartidas que luego alimentan cifrado simétrico; no reemplaza TLS ni cifra datos por sí mismo. Se descarta del MVP. ML-DSA tampoco se empleará para firma del manifiesto ni login, dada su complejidad adicional sin beneficio proporcional.

Seguridad base no negociable: TLS en contextos de red, Argon2id para hash de contraseñas, sesiones/tokens autorizados, redacción de secretos, control de acceso a sesión/trace, protección local de cache y manejo cuidadoso de secretos y datos; pruebas de abuso.

## 17. Pruebas iniciales de F0.1 (ejemplos de escenarios)

- Lookup exacto sin confirmación innecesaria si ese flujo se aprueba; recuperación tras reinicio.
- Recomendación con criterio `UNKNOWN` de alimentación: nunca suponer tensión; aclarar límite.
- «220 V y (Weatherproof o Explosionproof)»: filtros correctamente agrupados.
- «Lo más importante es la corriente», aunque se mencione al final: orden de prioridad explícito prevalece.
- «No importa la velocidad»: excluir velocidad como filtro y como preferencia salvo aprobación ulterior.
- «Encárgate tú» para la velocidad: aplicar solo política documentada, no un umbral eléctrico inventado.
- Revisión del plan después de confirmación: `plan_version` obsoleta no ejecuta.
- Envío repetido por reintento: una sola admisión, un resultado consultable.
- Usuario A sin rol developer intenta consultar trace de B: denegado.
- Developer A intenta consultar trace de conversación B en app: denegado.
- Logout y cambio de usuario: sin fugas por base local, memoria UI ni backups.
- Gráfica y tabla: mismas métricas y unidades; `N/A` nunca interpretado como cero.
- Límite USD 6 de experimentación: se detienen benchmarks de OpenRouter al alcanzar tope reservado.

## 18. Preguntas de cierre F0.1 a responder con el candidato

1. Confirmación: ¿siempre o por riesgo? ¿Preview opcional no bloqueante para lookups?
2. Recomendaciones: ¿enclosure, potencia, fase, servicio y torque se preguntan siempre aunque el usuario desconozca alguno? ¿Qué constituye recomendación preliminar no segura?
3. Ranking sin prioridad explícita: ¿pedir orden o presentar propuesta que usuario confirma? ¿Regla para empate?
4. Si usuario pide mostrar **todos** los compatibles, ¿permitimos scroll/identificadores ilimitados en la lista, con top-3 solo detalles y gráficos?
5. Cola: ¿202 accepted y polling cuando turno adicional se encola, manteniendo 200 con `answer` final para turno normal? ¿Aceptamos semántica mixta y qué hace Android?
6. Gráficas: ¿activar barras por comparación cuando mejoran legibilidad, además de tabla canónica?
7. [HISTÓRICO, CERRADO] ML-DSA: se evaluó firma de manifiesto; se descartó junto con ML-KEM en la decisión D-027. No reabrir sin nuevo caso de uso.
8. Tool catalog: ¿evaluar `get/search/compare` frente a tool única en golden tests antes de fijar?
9. Entrega: confirmar hora exacta (no inferir 23:59) y zona horaria del lunes 9/11.

## 19. Evidencia técnica a consultar en F1–F5

- Assessment páginas 1–6 (usuario) para contratos y requisitos.
- PDF eléctrico páginas 1–4 (usuario) para esquema, unidades, ausencias y validación.
- NIST FIPS 203/204 para usos reales de ML-KEM y ML-DSA.
- PostgreSQL `SKIP LOCKED` permite diseño de consumidores de cola, pero no elimina automáticamente necesidad de FIFO por sesión, leases o idempotencia.
- OWASP Mobile recomienda cifrado de datos sensibles y claves gestionadas por Android Keystore. Evitar asumir que `EncryptedSharedPreferences` es elección actual sin verificar su deprecación.
- LangGraph checkpoint en PostgreSQL permite persistencia de ejecución; el historial producto/estado de dominio sigue separado.


---

## 20. Bitácora de cambios v0.2 → v0.3 (aprobaciones expresas y consecuencias)

- **Confirmación:** D-026 pasa a APROBADA: interpretación siempre visible; confirmación únicamente cuando importan ambigüedad, riesgo, decisiones o criterios delegados; revisar/corregir sin reiniciar conversación. Un lookup inequívoco no queda bloqueado por un clic extra.
- **Preliminares:** permitido devolver candidatos basados en filtros conocidos sin presentarlos como compatibles/verificados para la aplicación real; mostrar qué restricciones faltan y permitir iterar.
- **Prioridades:** si no se expresan, el sistema propone ranking provisional lexicográfico para confirmación; instrucciones como «lo más importante» tienen precedencia sobre el orden de mención; prohibido inventar condiciones físicas. D-018 queda como preferencia pendiente de resolver casos de empate y reglas.
- **Visualizaciones:** tablas comparativas y comparación dual siguen siendo las vistas principales; barras opcionales, incluso agrupadas cuando respeten dimensiones y unidades; no gráficos sin aporte.
- **Concurrencia:** dirección durable por sesión con PostgreSQL aprobada; admisión asíncrona adicional, sin bloquear hilo principal Android; compatibilidad con contrato obligatorio y secuencia estricta por sesión pendientes.
- **Criptografía:** cierre de debate ML-DSA y ML-KEM: descartados MVP por no resolver eficientemente amenazas concretas. **Aprobado** cifrado autenticado de mensajes y trazas sensibles usando AES-256-GCM antes de persistir en PostgreSQL, con separación de claves/datos; evaluar envelope encryption en F3; definir estrategia de claves/rotación/búsqueda en F3. SHA-256 para artefactos, Argon2id para passwords, TLS en transporte y Keystore en móvil.
- **Modelos y tools:** método aprobado: comparar herramienta única vs especializadas con el mismo set, eligiendo la más precisa/sencilla con máximo USD 6 de gasto de desarrollo.

## 21. F0.1 — Matriz conceptual inicial de criterios (PARA VALIDACIÓN; NO regla ya aprobada)

| Criterio | Fuente/dimensión | Consulta exacta | Búsqueda filtrada | Recomendación y compatibilidad | Comparación y ranking | Aclaración/seguridad |
|---|---|---|---|---|---|---|
| Base Part Number | Identificador literal de cada producto/documento | Obligatorio para lookup exacto | Opcional | No es requisito físico de recomendación | Identificador estable de resultado/tie-break | Si ausente/malformado, pedirlo; si no existe, no inferir otro producto |
| Enclosure | Weatherproof / Explosionproof por sección de tabla | Contexto de registro | Filtro duro cuando lo pide | Potencial condición de seguridad: si desconocido, no afirmar aptitud para ambiente peligroso | No existe orden universal 'mejor' | No delegar una declaración de seguridad industrial al LLM |
| Fuente, tensión y fase | 24 V AC/DC; 110/220 V single phase; 220 V three phase donde figura | Contexto del registro | Filtros con AND/OR claros | Compatibilidad eléctrica crucial para recomendación definitiva | Comparar sólo configuraciones realmente identificadas | '220 V' puede necesitar aclarar monofásico/trifásico; no deducir disponibilidad de planta |
| Servicio | On/Off / Modulating; su representación cambia entre secciones | Si existen métricas de ambos, distinguirlas | Filtro | Compatibilidad funcional | Comparar dentro del mismo servicio o mostrar explícita diferencia | No inferir modo de servicio por torque o por lenguaje vago |
| Torque | On/Off y/o Modulating, valores oficiales en in-lbs y Nm | Mostrar el valor de servicio concreto | Filtro mínimo/máximo/rango | Torque mínimo necesario para concluir aptitud mecánica | Un valor mayor no es automáticamente mejor; minimizar exceso sólo si se aprueba | Si torque de aplicación desconocido, resultados preliminares, no recomendación definitiva |
| Velocidad | Segundos de giro; 50/60 Hz donde aplica | Mostrar valor y condiciones | Filtros con condiciones | Restricción dura si existe límite máximo; preferencia opcional | Menor tiempo es más rápido sólo a condiciones comparables | Si no se indica frecuencia y afecta valores, preguntar o presentar ambos etiquetados |
| Duty cycle S4% | Servicio/fila correspondiente | Valor oficial | Filtro | Restricción si aplicación demanda un duty cycle | Mayor capacidad sólo es ventaja si relevante, no criterio por defecto | No inferir ciclo de trabajo real de la planta |
| Cycles/hour y starts/hour | Dimensión según servicio/sección | Valor oficial | Filtro | Restricción según actividad requerida | Comparar métricas homogéneas | Starts y cycles no son intercambiables |
| FLA | Amperios, 50/60 Hz donde aplica | Valor oficial | Filtro si usuario establece límite | Restricción de corriente cuando se conoce; preferencia si explícita | Menor FLA puede ser preferencia, pero depende de voltaje/fase/frecuencia | 'Consumo' ambiguo entre FLA, potencia y energía; pedir precisión |
| LRA | Amperios, 50/60 Hz donde aplica | Valor oficial | Filtro si usuario establece límite | Condición relevante para arranque/dimensionamiento, dentro de lo que fuente permita | No equiparar con FLA | No estimar protecciones eléctricas o recomendaciones fuera del PDF |
| Potencia del motor | Watts, celdas eventualmente fusionadas | Valor oficial | Filtro | Característica o preferencia declarada | No convertir a consumo energético sin horas/carga | No inferir energía total o eficiencia de motor |
| Certificaciones/notas | Cabeceras/asteriscos/notas por sección/modelo | Mostrar cuando aplican | Filtro literal documentado | Restricción documental; nunca certificar instalación de forma implícita | Comparación cualitativa, no ranking universal | Nota no equivale a una certificación no indicada |
| Frecuencia | 50/60 Hz donde aplica; no todas las tablas igual | Condición que etiqueta cifra | Filtro/selector de métrica | Puede invalidar una comparación si faltan condiciones | Comparar con misma frecuencia si se usa métrica dependiente de ella | No completar por país o por voltaje de forma automática |

### 21.1. Reglas de interacción ya APROBADAS

1. Identificar intención, restricciones duras, preferencias, condiciones ignoradas/no aplicables y formato de respuesta; mostrar interpretación al usuario.
2. Solo solicitar aclaración que afecte el objetivo de la consulta. Confirmar obligatoriamente planes no triviales de selección o interpretación delegada; no bloquear lookups inequívocos.
3. Producir **preliminares** si faltan datos físicos esenciales, con etiqueta visible de no verificación, no afirmar aptitud; permitir refinamiento.
4. Lista nominal completa de coincidencias de la búsqueda/recomendación según criterios actuales; detalles para los primeros `min(N,3)`; si pide uno, top-1 con mismo algoritmo.
5. Números técnicos en salida estructurada proceden exclusivamente de tablas verificadas o cálculo determinista etiquetado; no texto de LLM tomado como fuente.
6. Consultas y respuestas bilingües; conservar identificadores literales y unidades exactas.
7. Tablas de comparación como referencia; barras sólo para métricas comparables, con unidad/condición y N/A explícitos.

### 21.2. Abiertas para cierre F0.1

- ¿Qué datos físicos mínimos permiten llamar «recomendación técnicamente compatible» y no solamente candidato filtrado? Definir por intención/aplicación, sin inventar seguridad.
- ¿Cómo expresar una **restricción delegada** cuando se desconoce una característica física indispensable? Se recomienda tratarla como UNKNOWN, no como criterio resuelto.
- ¿Qué reglas lexicográficas y direcciones aplicar cuando el usuario dice «optimiza» o «lo mejor» sin prioridad explícita? Se propone plan para aprobación, no valor por defecto no anunciado.
- ¿Qué operaciones AND/OR/NOT y agrupaciones admitiremos, y cómo validar interpretaciones compuestas?
- ¿Cómo proceder si solicitó 1 resultado pero todos son preliminares; abstención y alternativas vs top-1 preliminar etiquetado?
- ¿Qué filtros de UI permiten comparar hasta 3 pero conservar lista nominal completa?
- ¿Cuáles son los campos técnicos que permanecerán cifrados y cómo se resuelve búsqueda de conversaciones sin búsquedas full-text transparentes?
- ¿Qué política de retención/borrado aplica a trazas cuando el usuario elimina conversación? No asumir que auditoría puede retener indefinidamente.

## 22. Riesgo criptográfico y delimitación de garantías

- **Amenaza mitigada:** copia/filtración de base PostgreSQL sin obtención de claves de descifrado. Cifrado autenticado de aplicación antes de insertar, con AES-256-GCM como decisión funcional aprobada; diseño de claves pendiente de F3, claves administradas fuera de la BD.
- **Fuera de la garantía:** compromiso simultáneo del backend y claves, atacante con acceso a resultados ya descifrados, fugas por logs, backups sin protección o queries que requieran plaintext indexado.
- **Autenticación:** correo/contraseña con Argon2id (SHA-256 NO sirve como hash de contraseñas), TLS en red, roles y ownership server-side. ML-DSA como challenge-response implicaría un subsistema distinto con ciclo de vida de claves por usuario.
- **ML-KEM:** mecanismo de establecimiento de secreto que puede formar parte de un esquema híbrido, pero no cifra directamente una tabla; para almacenamiento sin intercambio queda decidido usar cifrado simétrico autenticado AES-256-GCM y correcta custodia de clave.
- **ML-DSA:** firma digital válida para autenticidad del firmante, pero no necesaria para login con contraseña ni aporta autoría del fabricante sobre manifiesto propio.
- **SHA-256:** digest de PDF/artefactos cotejado con origen confiable, no autenticación del fabricante ni protección de contraseñas.
- **Ciclo de vida por decidir:** quién genera clave, dónde reside en Docker local vs producción, rotación, backup, recuperación de pérdida, claves por conversación (opcional), versionado de cifrado, asociación de ciphertext a user/session con AAD, y protección de trazas.
- **Búsqueda:** `ILIKE` no funciona sobre ciphertext; considerar índice de metadatos no sensibles + búsqueda autorizada tras descifrar conjunto acotado, o índices especiales evaluados con su riesgo de filtración. No autorizar plaintext por comodidad.
- **Seguridad Android:** almacenamiento de tokens/cache con claves derivadas/almacenadas via Android Keystore; purga en cambio de usuario y no exposición en logout; considerar backups y memoria UI.

## 23. Matriz de siguiente sesión (F0.1)

1. Aprobar o corregir la matriz de criterios ampliada en la sección 24; en particular, los requisitos mínimos para emitir una recomendación con alcance documentado.
2. Aprobar política de preliminares vs selección validada; condiciones de aclaración y confirmación.
3. Validar ranking lexicográfico con prioridades explícitas y propuestas provisionales, más desempates, comparabilidad y semántica AND/OR.
4. Completar historias INVEST y escenarios de atributos de calidad (todavía no specs).
5. Declarar gate de F0 y continuar F1 (dominio/ETL).

### Referencias externas consultadas (F0.1)

- NIST FIPS 203 (ML-KEM): https://csrc.nist.gov/pubs/fips/203/final
- NIST FIPS 204 (ML-DSA): https://csrc.nist.gov/pubs/fips/204/final
- OWASP Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP Mobile Application Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mobile_Application_Security_Cheat_Sheet.html


---

## 24. Bitácora v0.3 → v0.4: decisiones explícitas del candidato

**Ratificaciones aprobadas:**

- **D-027 Seguridad:** descartar ML-DSA y ML-KEM para este alcance. Argon2id para contraseñas; TLS para tránsito; sesión/token bien administrados; SHA-256 de artefactos contra hash de referencia fiable; **AES-256-GCM de aplicación para datos sensibles antes de persistir en PostgreSQL**, claves separadas de BD; detalles operativos aplazados a F3. TLS y AES-GCM en reposo son controles diferentes; no construir un protocolo propio entre Android y servidor. El backend autorizado necesita plaintext para procesar contexto; Android recibe respuestas autorizadas mediante TLS.
- **D-026 Confirmación:** interpretación visible en todas las consultas; confirmación solo cuando la intención, ambigüedad, riesgo o delegación de criterios lo exijan. Nunca hacer dos turnos por un lookup exacto inequívoco.
- **D-008/023 Recomendaciones/UI:** candidatos preliminares con etiqueta explícita y posibilidad de refinar; ranking lexicográfico candidato con prioridades explícitas prevaleciendo; orden provisional del agente requiere confirmación; conjunto total de identificadores y máximo tres fichas detalladas/comparación de dos. Barras y multibarras opcionales solamente con mismas unidades y condiciones equivalentes, no reemplazan tabla.
- **D-013 Agente:** modelo híbrido con autonomía acotada aprobado. SQL tipado y resultado híbrido estructurado; cifras solamente de fuente verificada o cálculo determinista.
- **D-019 Estado:** serialización persistente por `session_id` en PostgreSQL aceptada como dirección, solicitudes adicionales admitidas asíncronamente; mecanismo y compatibilidad del endpoint obligatorio deben diseñarse en F3.
- **D-028 Herramientas:** preferencia por herramientas tipadas de dominio especializadas, sujetas a comparación justa con una herramienta tipada única dentro del presupuesto.
- **Fases, tiempo, documentación:** se mantiene F0–F6; Kiro recibe documentación de diseño validada y produce Specs posteriormente; no implementar antes de aprobación.

**No aprobados todavía:** criterio universal para distinguir recomendación documentada vs preliminar; ranking por defecto/empates; semántica exacta para conflictos; permisos de borrado/retención de auditoría; esquema físico y controles criptográficos operativos.

## 25. Inventario de secciones técnicas observado (PDF eléctrico, páginas 1–4)

| Página PDF | Contexto de tabla | Particularidad comprobable | Implicación funcional |
|---|---|---|---|
| 1 | WEATHERPROOF — 110V Single Phase | Columnas separadas On/Off y Modulating para torque/duty; velocidad, FLA y LRA por 60/50 Hz; motor power con celdas visualmente agrupadas | No unificar atributos de servicio; respetar frecuencia; verificar la propagación de celdas agrupadas |
| 1 | WEATHERPROOF — 220V Single Phase | Estructura similar; últimos modelos con `*` y nota `Sizes 6 and 7 are not CSA Certified` | Nota/certificación vinculada a los registros pertinentes; jamás declarar certificación universal |
| 2 | WEATHERPROOF — 220V 3 Phase | Cabecera de torque y duty sin subdivisión explícita On/Off vs Modulating; incluye `cycles/hour`, `starts/hour`; cuatro primeras filas bajo N/A compartido | No inventar métricas duplicadas por servicio sin validar su aplicabilidad; estados N/A diferenciados de filas ausentes |
| 3 | EXPLOSIONPROOF — 24V AC/DC On/Off | FLA/LRA, velocidad y torque sin columnas por frecuencia; `cycles/hour` | Mantener `AC/DC` como etiqueta de alimentación de la sección; no inventar frecuencia para esta fila |
| 3 | EXPLOSIONPROOF — 24V DC Modulating | Alimentación marcada `24V DC`, no `AC/DC`; `starts/hour` | No afirmar que el servicio modulating 24V admite AC si la tabla solo dice DC |
| 4 | EXPLOSIONPROOF — 110V / 220V Single Phase | Torque/duty separados por servicio; velocidad/corrientes por 50/60Hz; notas de clasificación de localizaciones peligrosas | Condiciones de frecuencia y alcance de notas deben acompañar resultado; no inferir certificación para una instalación concreta |

**Nota de fidelidad:** inventario elaborado desde las imágenes originales; no es aún una transcripción celda a celda ni valida el ETL. Las notas de tensión (`+/-10%`), frecuencia (`+/-5%`) y S4/IEC son observaciones del PDF, no licencias para inventar filas nominales de 209V/231V o convertir automáticamente variantes entre 50 y 60 Hz. La política de tolerancias necesita ser aclarada en F1 si se desea incluir como filtro.

**Diferencia respecto al resumen de negocio:** el resumen describe 24 V AC/DC, 110 V monofásica y 220 V monofásica en su introducción, pero **la tabla eléctrica también incluye 220 V trifásica**; para identificar variantes concretas prevalece el catálogo eléctrico.

## 26. Matriz de semántica de criterios — revisión F0.1 candidata (no schema DB)

| Criterio | Operaciones propuestas | Condición/precaución | Rol de preferencia posible | Origen |
|---|---|---|---|---|
| `part_number` | igualdad exacta, IN lista | Normalización conservadora; no cambiar caracteres arbitrariamente ni usar parecido como equivalencia | no aplica | ID de fila |
| `enclosure` | =, IN, NOT IN | Distintos entornos; falta de enclosure no autoriza afirmar aptitud ambiental | sólo si usuario la expresa | sección |
| `voltage` | =, IN | Voltaje nominal; combinar con fase y tipo AC/DC, no filtros aislados para compatibilidad | usualmente restricción dura | sección |
| `current_type` | AC/DC/DC según evidencia | `24V AC/DC On/Off` ≠ `24V DC Modulating`; ambigüedad requiere aclaración | no inferir | página 3 |
| `phase` | monofásica/trifásica/NA para DC | No atribuir fase a DC; 220 V 1 fase y 3 fases no son equivalentes | usualmente dura | páginas 1,2,4 |
| `service` | On/Off, Modulating | Datos pueden tener columnas separadas o una única columna unificada por sección; validar interpretación en F1 | restricción dura cuando la necesidad implica servicio | secciones/columnas |
| `torque` | =, >=, <=, intervalo | Por servicio y unidad. Conservar tanto Nm como in-lbs tal como figuran; si convertir, etiquetar derivado | no asumir que más torque es siempre mejor | filas/columnas |
| `duty_cycle_s4` | =, >=, <=, intervalo | No confundir con cycles/hour o duración en segundos | más alto solo si usuario lo prioriza | filas/columnas |
| `cycles_per_hour` | =, >=, <=, intervalo | No intercambiar con starts/hour; tabla observa valores bajo torque nominal | si explícito | filas |
| `starts_per_hour` | =, >=, <=, intervalo | Distinto de cycles/hour, potencialmente relevancia por servicio | si explícito | filas |
| `operating_speed_sec` | =, >=, <=, intervalo | Menos segundos significa más rápido; para AC donde hay 50/60Hz, escoger frecuencia documentada | minimizar si rapidez es prioridad | filas/condiciones |
| `fla_a` | =, >=, <=, intervalo | Comparar dentro de condiciones eléctricas equivalentes; FLA no equivale a energía consumida | minimizar si usuario prioriza menor corriente | filas/condiciones |
| `lra_a` | =, >=, <=, intervalo | No equiparar a FLA, corriente de rotor bloqueado | minimizar si usuario prioriza LRA | filas/condiciones |
| `motor_power_w` | =, >=, <=, intervalo | Watts ≠ Wh; celda fuente puede agrupar múltiples modelos | preferencia solo si expresa potencia del motor | filas/agrupaciones |
| `certification / notes` | inclusión literal/verificación documental | No extrapolar a todas las variantes; `*` en 220V WP limita CSA. No emitir dictamen de seguridad de la instalación | no ranking automático | cabeceras/pie |
| `frequency_hz` | = 50 o 60 donde aplica | No crear variante para 24V sin desglose; no inferir frecuencia por país/voltaje | contexto de comparación; a veces requisito | columnas |

**Cuestión de diseño:** no trasladar esta tabla de criterios directamente a columnas SQL; una misma fila del PDF puede mapear a varias observaciones por servicio/frecuencia. La cardinalidad y procedencia se decidirán en F1.

## 27. Tres ejes separados: estado del criterio, dato fuente y plan

**Hipótesis recomendada para evitar ENUM confuso:**

1. **Estado del requisito del usuario:** `UNSPECIFIED`, `SPECIFIED`, `NO_PREFERENCE`, `UNKNOWN`, `DELEGATED`, `CONFLICTING`.
2. **Estado del dato recuperado:** `AVAILABLE`, `NOT_APPLICABLE`, `NOT_DOCUMENTED`, `NOT_PRESENT_IN_DATASET`, `UNVERIFIED/INGEST_ERROR` — no confundir ausencia en PDF con desconocimiento del usuario.
3. **Estado del plan:** `DRAFT`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `APPROVED`, `EXECUTING`, `COMPLETED`, `FAILED`, con versión y rechazo/invalidez cuando cambia el plan. Esto NO define todavía tablas, API ni state-machine formal.

Además de estado, cada criterio capturado tendría dimensiones conceptuales: campo, operador, valor, unidad, fuente (usuario/contexto/propuesta), naturaleza (hard/soft/contextual), prioridad explícita, ámbito y nivel de validación. Los datos propuestos por el LLM no se elevan automáticamente a requisitos físicos declarados.

## 28. Invariantes de dominio candidatos a aceptación

- **I-01 Fuente:** ninguna métrica técnica mostrada puede proceder únicamente de una salida numérica del LLM.
- **I-02 Contexto:** el PN no sustituye automáticamente una condición de servicio/frecuencia cuando la pregunta permite múltiples respuestas diferentes; devolver todos los valores etiquetados o solicitar precisión.
- **I-03 Compatibilidad:** igual voltaje no garantiza compatibilidad: fase/tipo de corriente/servicio/enclosure/torque pueden cambiar el resultado.
- **I-04 Dato ausente:** `N/A`, `no documentado`, `no listado`, `no verificado`, y `UNKNOWN` del usuario no son sinónimos.
- **I-05 Comparabilidad:** no afirmar una ventaja al comparar valores bajo condiciones incompatibles; barras sólo muestran magnitudes homogéneas con unidades y contexto visibles.
- **I-06 No inventar equivalencias:** valores oficiales de Nm e in-lbs se conservan como datos propios; conversiones se muestran como derivadas, no reemplazo silencioso de fuente.
- **I-07 Restricciones:** aplicar conjunción de restricciones duras explícitas; conservar y expresar `OR/NOT` y agrupación cuando el usuario los usa; no confundir hard filters con ranking soft.
- **I-08 Preliminares:** cuando faltan requisitos físicos relevantes, se pueden mostrar candidatos con etiqueta `PRELIMINARY` y restricciones pendientes; no declarar validación integral de instalación.
- **I-09 Ranking:** criterios de prioridad explícitos sobrepujan orden textual; propuesta de prioridad del sistema necesita confirmación; tie-break debe ser estable y explicable.
- **I-10 Plan:** aprobación de versión N no autoriza ejecución de versión N+1 con criterios modificados.
- **I-11 Seguridad:** auth/ownership backend preceden todas las operaciones, incluidas herramientas y Debug; cifrado en DB no sustituye autorización.
- **I-12 Persistencia:** el usuario no pierde turnos confirmados tras reinicio; si una ejecución quedó inconclusa, se identifica y recupera sin duplicar efectos.

**Estado:** son invariantes propuestos para revisión final; las decisiones de fondo ya aprobadas se respetan, pero nombres/casos exactos necesitan confirmación.

## 29. Escenarios de interacción para validar en F0.1 (sin inventar datos de producto)

| Escenario | Interpretación/acción candidata | Pregunta abierta |
|---|---|---|
| «Potencia del PN X» | Buscar exactamente X; no pedir enclosure/torque si no afecta respuesta | ¿Si la cifra depende de contexto, mostrar todas las variantes etiquetadas o aclarar? |
| «Todos los modelos de 220V» | Filtro por voltaje 220, incluir diferentes fases, distinguirlas en respuesta; no llamar compatibles con una instalación | ¿Mostrar resultados generales o aclarar fase antes de buscar? |
| «Recomiéndame uno para 220V, no sé torque» | Mostrar candidatos preliminares; solicitar datos físicos faltantes para recomendación fundada | ¿Puede aparecer top-1 preliminar si lo pide explícitamente? |
| «Más rápido; menos FLA, pero velocidad es lo principal» | Proponer plan lexicográfico por velocidad, luego FLA, exigir que las condiciones sean comparables | ¿Cómo presentar orden cuando modelos están en categorías eléctricas distintas? |
| «24V AC Modulating» | No devolver un 24V Modulating basado sólo en la sección 24V DC | ¿Rechazar como no documentado o ofrecer alternativa DC claramente separada? |
| «220V 3-phase PN in N/A rows» | Separar N/A de inexistente y no inventar métricas | ¿Mostramos la fila N/A como disponibilidad negada o registro informativo? |
| «On/Off o Modulating» | Reconocer OR en service, no elegir arbitrariamente | ¿Cómo se agrupan fichas si PN reúne dos servicios? |
| «¿Cuánto consume?» | Aclarar corriente/potencia/energía antes de responder, salvo si contexto lo desambigua | ¿Explicar ambas métricas documentadas para ahorrar turnos? |
| «¿Se puede usar en Zona X?» | Solo citar certificación/rótulos expresos de PDF, no certificar instalación | ¿Mostrar límites con recomendación de verificación por profesional? |
| «El segundo, pero a 50Hz» | Resolver segunda referencia del conjunto vigente y recalcular valores de esa frecuencia si corresponde | ¿Al cambiar criterio de frecuencia se invalida recomendación previa? |

## 30. Bocetos de historias INVEST (aún no specs)

- **H-01** Como técnico, quiero consultar un PN exacto y obtener solo sus métricas documentadas pertinentes, para verificar rápidamente sus características. *Prueba:* PN válido, inválido, ambiguo y con modalidades/frecuencias.
- **H-02** Como ingeniero, quiero buscar modelos por filtros numéricos y lógicos explícitos, para identificar el conjunto completo de coincidencias. *Prueba:* AND, OR, NOT, intervalos, cero resultados, N/A.
- **H-03** Como ingeniero, quiero revisar/corregir el plan de recomendación antes de que se ejecute cuando haya supuestos o preferencias delegadas, para controlar la selección. *Prueba:* confirmar vN, modificar a vN+1, impedir ejecutar vN con confirmación previa.
- **H-04** Como ingeniero, quiero conocer qué requisitos faltan y ver candidatos etiquetados como preliminares, para refinar mi consulta sin conclusiones falsas. *Prueba:* faltan torque/enclosure/fase; se conserva el contexto y no se declara compatibilidad total.
- **H-05** Como usuario, quiero comparar hasta tres modelos y resaltar hasta dos en paralelo, con unidades y condiciones visibles, para distinguir diferencias reales. *Prueba:* misma condición vs distinta frecuencia, celdas N/A, valores de servicio.
- **H-06** Como usuario autenticado, quiero continuar mis conversaciones tras reiniciar backend, sin acceder a las de otros, para mantener mi trabajo. *Prueba:* persistencia, ownership, cambio de usuario, concurrencia, cifrado.

**INVEST:** cada boceto debe dividirse aún en historias estimables y testeables; F0 registra intención y cobertura, no especificaciones finales de Kiro.

## 31. Decisiones prioritarias todavía abiertas, sólo F0.1

1. **Estatus de recomendación:** ¿para declarar "recomendación según criterios proporcionados" exigiremos como mínimo **tipo de servicio, tensión+tipo/fase, enclosure, torque mínimo**, o basta una combinación menor siempre que expliquemos qué NO ha sido verificado? Distinguirlo de aptitud industrial integral.
2. **PN con múltiples servicios/condiciones:** si pregunta una métrica sin servicio/frecuencia, ¿mostrar **todos los valores documentados etiquetados** cuando sea pequeño, o pedir aclaración por defecto?
3. **Comparaciones intercontextuales:** cuando dos candidatos tienen diferente tensión/fase, ¿permitir tabla lado a lado pero **deshabilitar ganador** para FLA, manteniendo una advertencia? Evaluar la interpretación de potencia del motor aparte.
4. **Búsqueda de conversaciones cifradas:** ¿la búsqueda del MVP será por títulos y metadatos (indexados) o por el texto de los mensajes? La segunda requiere búsqueda autorizada tras descifrar o índice seguro especializado.
5. **Borrado y auditoría:** al eliminar una conversación, ¿eliminar también las trazas vinculadas, o retener mínima auditoría desidentificada con plazo y justificación explícita? No dejar conservación indefinida sin política.
6. **Desempate lexicográfico:** si todos los criterios comparados empatan, ¿orden final estable por PN o conservar orden del catálogo? Prioridades por defecto requieren consentimiento para recomendaciones.

## 32. Condiciones de salida de F0.1 (gate propuesto)

- Confirmadas las políticas anteriores y sus casos límite.
- Catálogo de intenciones y criterios aprobado, sin introducir propiedades ausentes del PDF.
- Criterios de preliminar vs recomendación documentada, notación de procedencia y explicación acordados.
- Historias candidatas transformables a INVEST y matriz de trazabilidad lista para F0.3.
- Cualquier incertidumbre de interpretación de celdas del PDF registrada como asunto explícito de F1, no resuelta inventando valores.

---

## 33. Bitácora v0.4 → v0.5: aprobaciones del candidato y cierre funcional F0.1

**Aprobaciones explícitas:**

1. **D-008 Elegibilidad/recomendación:** exigir evaluación de los cuatro grupos — **entorno**, **alimentación (voltaje + naturaleza de corriente/fase cuando aplique)**, **servicio** y **torque requerido** — para la etiqueta de recomendación según criterios documentados. Si falta información física pertinente, ofrecer **candidatos preliminares** y permitir refinarlos. Cumplir los cuatro grupos no equivale a certificar integralmente la instalación.
2. **Lookup contextual:** devolver los valores documentados para servicios/frecuencias relevantes **cuando sea legible**, siempre etiquetados; sólo aclarar si la multiplicidad impide una respuesta segura o comprensible.
3. **Comparación heterogénea:** permitir tabla informativa con unidades/condiciones; no declarar superioridad ni mostrar highlight de «ganador» cuando las magnitudes carezcan de comparabilidad.
4. **Ranking:** lexicográfico con filtros duros previos, prioridad explícita por encima del orden textual, propuesta provisional confirmable y desempate estable por Base Part Number. No inferir automáticamente que «más torque» significa mejor.
5. **Delegación:** usuario puede indicar «no me importa, decide tú» y agente propone/aplica preferencias con explicación y confirmación cuando proceda. **La delegación NO crea hechos físicos**: criterio conversacionalmente cubierto ≠ dato técnicamente verificado. Sin información de torque de la válvula, la elegibilidad mecánica sigue sin comprobar.
6. **Estados de criterio:** aprobados tres ejes separados: estado de requisito de usuario, estado de disponibilidad del dato fuente y estado/versionado del plan. Proveniencia de valor, operador, unidad, restricción/preferencia y verificación física deben permanecer identificables; no implica enums SQL aún.
7. **Invariantes I-01 a I-12 y matriz funcional F0.1:** aprobadas en concepto; ejemplos y excepciones quedan sujetas a prueba con datos efectivamente cotejados.
8. **Criptografía:** ratificado Argon2id+TLS+sesiones/tokens, AES-256-GCM en datos sensibles en reposo con claves separadas, SHA-256 de artefactos, exclusión ML-DSA/ML-KEM. Transport TLS y cifrado de contenido almacenado son controles distintos.

**No reabrir en fase F0:** elección de RAG/MCP (descartados), voz (diferida), límite tres fichas/dual dos, debug en producción por rol y propiedad, OCR vs visión (comparación prevista en F1).

## 34. F0.2/F0.3: catálogo de requisitos y calidad vinculado

**Archivo especializado:** `F0_requirements_and_quality_catalog_v0.2.md` (revisión vigente; v0.1 conservada como historial). Contiene **32 historias candidatas US-001…US-032**, **15 escenarios de atributos de calidad QA-01…QA-15**, **12 pruebas narrativas AT-01…AT-12**, trazabilidad de las obligaciones del assessment, 16 escenarios complejos, y pendientes que bloquean diseño detallado.

**Importante:** Estos documentos no son Specifications de Kiro; su objetivo es proporcionar al generador de Specs una base aprobada, con decisiones y datos fuente, sin decidir por el candidato el diseño técnico.

**Esquema transversal de aceptación:**
- 0 discrepancias de valores técnicos en golden dataset verificado contra PDF; la cifra jamás sale del LLM como autoridad.
- Restricciones duras, negación y agrupación preservadas; separación entre búsqueda, candidato preliminar y recomendación.
- Confirmación de plan asociada a versión; estado multi-turno duradero y serialización por sesión.
- Usuarios aislados en backend, Debug sólo developer/owner, trazas sin secretos y caché local protegida.
- En Android, tabla canónica hasta tres fichas/dual dos, barras sólo cuando sean interpretables y comparables.

## 35. Pendientes de F0 y puntos de diseño que deben resolverse sin fingir aprobación

| Prioridad | Tema | Pregunta concreta | Riesgo/impacto | Destino de cierre |
|---|---|---|---|---|
| P0 | Búsqueda de conversaciones cifradas | ¿Buscar sólo títulos/metadatos o también cuerpo del chat? ¿Cómo asegurar la búsqueda sin indexar plaintext sensible? | Seguridad y funcionalidad US-009 | F0/F3 |
| P0 | Borrado y retención de trazas | ¿Borrar logs/traces completos con conversación o retener auditoría mínima bajo política finita y separada? | Privacidad vs auditoría | F0/F3 |
| P0 | Semántica «no me importa» para entorno/alimentación | Si falta dato físico y usuario delega, ¿se muestra exclusivamente PRELIMINARY hasta saber compatibilidad? **Propuesta: sí** para respetar decisión de cuatro grupos. | Seguridad y consistencia | F0 (ratificación si se requiere) |
| P1 | On/Off vs Modulating en tabla Weatherproof trifásica | No extrapolar métricas por servicio sin sustento PDF | Correctitud de ETL | F1 |
| P1 | Concurrencia/API jobs | Mantener contrato obligatorio síncrono y especificar admisión asíncrona adicional, versionado, FIFO e idempotencia | Reproducibilidad y estados | F3 |
| P1 | Métricas cuantitativas | Además de 0 discrepancias, definir umbrales de latencia, precisión de intent y tiempos de timeout | Evaluabilidad | F5 |
| P1 | Bilingüismo persistido y alcance de autentificación | Preferencia por mensaje o usuario; usuarios preconfigurados vs registro | Alcance UX/API | F0/F3/F4 |
| P1 | Interpretación de nota y celdas fusionadas | Verificación visual del PDF, no confundir OCR con verdad | Data integrity | F1 |
| P2 | Política de borrado del caché y claves | Validar cifrado local, borrado, backup y control de claves Keystore | Riesgo de filtración local | F4 |

**Gate F0.2 propuesto:** validar el catálogo US/QA y cerrar los pendientes P0 que condicionan la semántica del producto; pasar a F1 con la fuente de verdad y semántica de selección congeladas, aun si los detalles de esquema y ejecución siguen abiertos por fase.


---

## 36. Bitácora v0.5 → v0.6 (ratificación explícita F0.3)

**Fecha:** 2026-11-06 (America/Bogota). **Autoridad:** aprobación explícita del candidato en conversación. **Estado:** F0.3 en revisión, no se autoriza todavía la implementación.

1. **D-031 — Búsqueda de conversaciones — APROBADA:** buscar únicamente por **título**; el backend primero comprueba propiedad de conversación, después descifra los títulos necesarios y aplica búsqueda controlada; NO full-text de cuerpos de mensajes ni índice de plaintext compartido. Se definirá en F3 límite de procesamiento/paginación/case-folding; nunca inferir que PostgreSQL puede buscar sobre AES-GCM sin descifrar.
2. **D-032 — Eliminación y trazas — APROBADA:** una eliminación confirmada retira de almacenamiento activo la conversación, mensajes, estado estructurado, checkpoints, trabajos/ejecuciones asociados y **trazas detalladas**, y limpia caché local. **No conservar las trazas completas para auditoría tras borrado.** Puede existir evento mínimo de auditoría sin contenido, sujeto a política posterior; no inventar retención. Se debe impedir reaparición por workers en curso y por sincronización de caché. Backups, copias de proveedores y borrado físico requieren política aparte: NO prometer purga física instantánea.
3. **D-033 — Catálogo F0 — APROBADO EN CONCEPTO:** ocho áreas funcionales y 32 historias US-001…US-032; quince escenarios QA-01…QA-15; pruebas unitarias, integración, adversariales, multi-turno, UI, concurrencia y e2e. Los ID se conservan; la revisión INVEST re-clasifica algunos como transversal/habilitador sin quitar requisitos.
4. **D-034 — Criterio de cobertura física — RATIFICADO:** requisito conversacional «delegado / no me importa» NO constituye evidencia de compatibilidad industrial. Faltando entorno, alimentación, servicio o torque verificable relevante, únicamente candidatos preliminares, aunque el agente elija prioridades.
5. **D-035 — Flujo de respuesta — RATIFICADO:** interpretación visible; aclaración/confirmación condicional; respuestas híbridas cuyos números técnicos se obtienen del PDF eléctrico verificado o cálculos deterministas, nunca como autoridad del modelo.

**Precedencia y corrección del historial:** en v0.1–v0.5 hay entradas históricas que dicen «búsqueda por decidir» o «retención de trazas por decidir»; **quedan sustituidas por D-031 y D-032**. D-009 y D-010 significan trazabilidad completa **mientras existe** la conversación; no constituyen excepción a la eliminación aprobada. Una retención externa de backups o de proveedor debe abordarse como límite técnico en F3, nunca como contradicción silenciosa.

## 37. Depuración F0.3: regla de trabajo

- La versión refinada `F0_requirements_and_quality_catalog_v0.2.md` es **documentación de alineación**, no Specs, diseño detallado ni tareas de Kiro.
- Conservar los identificadores US originales y clasificarlos como experiencia de usuario, política transversal o habilitador técnico. Si una historia abarca múltiples comportamientos, registrar subcasos de aceptación, sin cambiar el alcance aprobado.
- Historias nuevas necesarias para cubrir huecos se anotan **PROPUESTAS** y requieren aprobación; no se consideran implícitamente aceptadas al descargar el documento.
- Toda obligación del assessment debe tener evidencia prevista y toda política de privacidad debe ser comprobable, incluidas las excepciones de jobs pendientes, cachés y backups.

## 38. Riesgos y preguntas residuales tras F0.3

| Tema | Situación / recomendación de discusión | Estado y fase |
|---|---|---|
| Solicitud de un solo producto y lista nominal exhaustiva | Se aprobó top-1 si se pide uno y enumerar todos los PN en búsquedas. Definir si top-1 expone sólo el PN elegido y total o también todos los IDs elegibles; no imponer comportamiento unilateralmente. | **ABIERTO F0** |
| Logout / revocación | Auth está aprobado, pero faltaba historia de cerrar sesión, expirar/revocar token y limpieza de credenciales/caché. Se propone US-033. | **PROPUESTA F0** |
| Respuestas estructuradas | UI comparativa requiere objetos tipados fuera de `answer` de contrato fijo; proponer US-034 (sin diseñar aún campos). | **PROPUESTA F0** |
| Eliminación mientras hay ejecución pendiente | Debe impedir resultados fantasma/reaparición de sesión tras borrar; proponer US-035 y gate de implementación. | **PROPUESTA F0** |
| Búsqueda título cifrado | Limitar universo al owner antes de descifrar, evitar logs de texto; política de título, case-folding y paginación en F3/F4. | APROBADO en alcance; detalles pendientes F3–F4 |
| Contrato de jobs con `POST /api/conversation` | Mantener contrato fijo con respuesta `session_id`, `answer`, y diseñar admisión asíncrona adicional compatible. | ABIERTO F3 |
| Registro vs cuentas preconfiguradas | Assessment permite login simple con usuarios precargados; registro/recuperación no exigidos. Elegir conscientemente para evitar scope creep. | ABIERTO F0/F3 |
| Selección de idioma en turnos mixtos | Bilingüismo aprobado; falta política de idioma de respuesta, cambiarlo sin mutar datos. | ABIERTO F0/F4 |
| Diseño de tokens, claves y backups | Confidencialidad y borrado lógico aprobados; gestión/rotación y límites de purga física pendientes. | ABIERTO F3/F4 |

## 39. Criterio de gate F0.3

**Cumplido por la revisión:** 32 US existentes conservadas; 8 grupos; 15 QA; matriz de cobertura del assessment; riesgos y habilitadores separados; D-031 y D-032 ratificados. **Aún por aprobación:** US-033…US-035 y las decisiones de producto residuales. Puede prepararse F1 con asuntos asignados a fase, pero no afirmar que F0 está cerrado sin confirmar estas propuestas o descartarlas motivadamente.


---

## 40. Bitácora v0.6 → v0.7: cierre formal F0 y ratificación de alcance

**Autoridad:** mensaje del candidato en la conversación: «Ok hagamos esos ajustes... las 3 recomendaciones aprobadas... sí creemos unos precargados (de cada rol) y también debemos permitir la creación de nuevos usuarios mediante la app (solo rol user; crear developers no se hace desde la app nunca)... podemos cerrar F0 y avanzar a F1». **Estado:** decisiones cerradas; no autoriza implementar código todavía.

| ID | Estado | Decisión aprobada | Consecuencias de aceptación |
|---|---|---|---|
| D-036 | APROBADA | **Registro de nuevos usuarios desde Android**, exclusivamente rol `user`; roles asignados por el backend, ignorando/rechazando cualquier rol suministrado por cliente. Crear/preparar cuentas de prueba `user` y `developer`; provisionamiento de developers exclusivamente fuera de la app mediante procedimiento administrativo. | Un registro público nunca otorga `developer`; datos privados solo del owner; credenciales con Argon2id; cuentas de demo reproducibles sin claves reales de producción. Los detalles de correo/verificación, expiración y rate limiting se deciden F3. |
| D-037 | APROBADA | Formalizar **US-033 logout/revocación**, **US-034 entrega de respuesta estructurada**; mantener borrado concurrente **US-035 como subcasos transversales obligatorios** de US-008 y US-029. | Tests de revocación, UI/cache, preservación de `session_id` y `answer`, no resurrección de sesiones borradas. |
| D-038 | APROBADA | Cuando el usuario solicita **un solo modelo**, mostrar el primer elegible del ranking y el **total** de elegibles, sin enumerar otros PN. En búsquedas/múltiples se conserva lista completa nominal y hasta 3 fichas. | La respuesta top-1 debe coincidir con el primer modelo del mismo ranking bajo los mismos criterios. |
| D-039 | APROBADA | El idioma de respuesta sigue el **último mensaje del usuario**, con prioridad a una instrucción explícita de idioma; admitir ES/EN. | Pruebas de turnos mixtos y cambios explícitos; traducción nunca altera cifras/documentación de producto. |
| D-040 | APROBADA | **Gate F0 cerrado**; se inicia **F1 (dominio, datos y ETL)**. El material F0 se transforma en insumo de Kiro tras F6; no son specs listas para implementación ni se modifica código aún. | Todo asunto técnico residual queda asignado a su fase, con nueva aprobación donde corresponda. |

**Corrección frente al assessment:** El login con cuentas precargadas es opcional en el enunciado; el candidato decidió **agregar también registro de usuarios**. Debe declararse en README como alcance añadido. NO hay registro/autocreación de `developer` ni elevación de privilegios desde UI/API pública.

**Corrección de cobertura:** La línea «voz y registro/autoservicio de cuentas no pasan a P0» de la v0.2 del catálogo es **histórica y queda anulada** para autorregistro: el registro desde Android es P0 por decisión explícita. Voz permanece diferida.

## 41. Resultado del gate de F0 — evidencia de cierre

- [x] Visión de producto, usuarios ES/EN, alcance y exclusiones ratificados.
- [x] Ocho dominios/capacidades; 32 historias de partida y ampliaciones US-033/US-034/US-036. US-035 queda como pruebas transversales, no historia independiente.
- [x] Quince escenarios QA, matriz assessment→requisito→prueba, historias INVEST depuradas y habilitadores separados.
- [x] Comportamiento de recomendaciones preliminares/validadas, comparativas, ranking y aclaraciones aprobado.
- [x] Política de auth/registro/roles, búsqueda de títulos, borrado y trazas confirmada.
- [x] Decisiones de arquitectura que afectan a las funciones de F0 documentadas con límites explícitos.
- [x] Autorización explícita del candidato para cerrar F0 e iniciar F1.

**No se consideran bloqueadores de F0:** esquema SQL, granularidad de métricas, pipeline OCR/visión, contratos ampliados de API, semántica de los trabajos y latencia objetivo, que se decidirán respectivamente en F1/F2/F3/F4/F5. Evitar confundir decisión de **alcance** con aprobación de **diseño**.

## 42. Apertura F1: inventario documental y corrección del recuento

**Observación visual corregida (no producto de OCR):** En `series_76_electric_data.pdf` hay **7 tablas/secciones de datos** sobre **4 páginas**, no 6. El inventario previo agrupó como una sola sección las dos tablas de Explosionproof 110 V y 220 V monofásicas de p. 4. Se deben tratar separadamente.

| ID temporal | Página | Enclosure | Alimentación | Servicios presentes en estructura |
|---|---:|---|---|---|
| T-01 | 1 | Weatherproof | 110 V, 1-phase | On/Off y Modulating, columnas separadas en misma fila |
| T-02 | 1 | Weatherproof | 220 V, 1-phase | On/Off y Modulating, columnas separadas en misma fila; hay asteriscos/notas |
| T-03 | 2 | Weatherproof | 220 V, 3-phase | On/Off y Modulating; existen filas marcadas N/A |
| T-04 | 3 | Explosionproof | 24 V AC/DC | On/Off |
| T-05 | 3 | Explosionproof | 24 V DC | Modulating |
| T-06 | 4 | Explosionproof | 110 V, 1-phase | On/Off y Modulating, columnas separadas en misma fila |
| T-07 | 4 | Explosionproof | 220 V, 1-phase | On/Off y Modulating, columnas separadas en misma fila |

**Advertencia:** Este inventario es estructural. La cantidad de filas, los PN únicos y cada cifra deben verificarse por tabla antes de fijar cardinalidades y claves. Las celdas de *Motor Power* visualmente fusionadas, 50/60 Hz, notas y estados N/A requieren procedencia propia.

**Primera cuestión de F1 sin aprobar:** ¿Cuál será el grano/identidad del registro técnico consultable? Alternativas: (A) una fila ancha por PN+configuración, con campos por servicio y frecuencia; (B) PN + configuración eléctrica + calificación por servicio + mediciones condicionadas por frecuencia; (C) valores atomizados de tipo atributo (EAV) con unidad/contexto. La B parece una hipótesis fuerte, pero no está aprobada. Véase `F1_domain_and_etl_kickoff_v0.1.md`.

## 43. Reglas de versionado después del cierre F0

- La v0.7 conserva el historial, pero sus secciones 40–42 **prevalecen** ante notas anteriores que trataban registro o cierre F0 como abiertos.
- En F1, cada decisión nueva recibe ID estable, alternativas, motivación, evidencia del PDF, impacto y aprobación expresa.
- No escribir esquemas SQL definitivos ni implementar `ingest.py` hasta aprobar el grano del dominio y la estrategia de extracción/verificación.
- Requerimientos aprobados F0 pueden modificarse únicamente mediante decisión de cambio documentada, sin reescribir el historial.


---

## 17. Registro incremental F1: primera decisión ratificada (alineación v0.8)

**F1-D01 — APROBADA por el usuario:** adoptar un **modelo relacional normalizado** para los datos técnicos de Series 76 en PostgreSQL. Se descartaron como arquitectura base la reproducción en una sola tabla ancha del PDF y el patrón EAV genérico.

**Rationale:** preservar el grano de los números de parte, configuración eléctrica, servicio, frecuencia, mediciones y procedencia; aplicar restricciones de integridad y consultas SQL tipadas. **Trade-off aceptado:** mayor cantidad de entidades y JOINs a cambio de semántica, auditabilidad y evolución.

**Límites de la decisión:** no aprobar todavía nombres de tablas, columnas ni claves únicas sin inventario verificado. No inferir servicio en la tabla Weatherproof trifásica de página 2, no duplicar valores por frecuencia, no convertir N/A en cero y no propagar automáticamente celdas de potencia agrupadas. La selección de OCR/visión sigue abierta.

**Nuevo documento de referencia:** `F1_domain_and_etl_kickoff_v0.2.md`, que mantiene los tres ejemplos fundamentales (un PN con dos servicios, N/A, 24 V AC/DC frente a DC), añade el caso de asteriscos/CSA y propone alternativas internas B1/B2 aún por decidir.

**Estado general:** F0 sigue aprobada y congelada funcionalmente; F1-D01 aprobada; F1-D02…F1-D07 abiertas. No son Specs de Kiro.


---

## 44. Registro incremental F1: aprobaciones de granularidad, procedencia y publicación (v0.9)

**Aprobado por el candidato:** F1-D02 = B2 (ratings de servicio explícito separados de ratings sin servicio explicitado, particularmente T03); F1-D03 = evidencia por celda/campo, con manejo explícito de celdas fusionadas; F1-D06 = publicación **atómica** de ediciones totalmente verificadas, sin publicar ninguna sección incompleta ni retirar la edición vigente hasta promover otra íntegramente verificada.

**Decisiones previas preservadas:** F1-D01 modelo relacional normalizado; F0 y sus historias/QA/seguridad siguen cerrados. Las tablas T01–T07 tienen 68 filas visibles según conteo visual confirmado manualmente por el candidato; este conteo NO sustituye la auditoría de valores de cada celda.

**Pendientes aún abiertos:** F1-D04 selección de extractor (OCR estructural, visión, conciliación híbrida), F1-D05 mecanismo de verificación exhaustiva/correcciones, F1-D07 identidad/unicidad PN, F1-D08 reproducibilidad de extracción sin claves externas adicionales; detalles del tratamiento de mediciones sin frecuencia, del rango de los spans y del modelo relacional físico quedan sin aprobación implícita.

**Nueva referencia:** `F1_domain_and_etl_kickoff_v0.3.md`, §§12–14. El documento contiene benchmark propuesto y criterios para elegir método; **no se ha ejecutado ninguna evaluación OCR/vision ni construido un dataset normalizado**. F1 sigue abierta y no hay autorización de implementación.


---

## 45. Registro incremental F1 — decisiones sobre el pipeline (v0.10)

**Autoridad:** confirmaciones explícitas del candidato posteriores a la revisión v0.9. F0 permanece formalmente cerrado; este bloque sólo conserva trazabilidad histórica de decisiones F1. El detalle técnico vive en `F1_domain_and_etl_kickoff_v0.4.md`.

- **F1-D04 APROBADA:** extracción híbrida, con OCR estructural local, Gemini visual, conciliación y validación; el extractor OCR específico permanece para benchmark. No usar el LLM como fuente numérica ni considerar coincidencia de dos sistemas equivalente a exactitud demostrada.
- **F1-D05 APROBADA:** revisar manualmente el 100 % de las cifras/celdas/condiciones/notas de la edición inicial frente al PDF original, conservar las correcciones en un manifiesto versionado. El usuario busca eliminar la revisión exhaustiva en futuras ediciones del mismo formato. Se mantiene publicación atómica y gate automatizado; **no** se ha aprobado convertir PDFs futuros automáticamente en fuentes verificadas sin pruebas independientes ni umbrales de aceptación.
- **F1-D08 APROBADA (modo fresh):** la ingesta podrá tomar una clave propia de Google AI Studio mediante variable de entorno; el README debe instruir cómo obtenerla/configurarla sin almacenar valores reales. Se propone además modo `verified replay` desde artefactos validados para reproducir los resultados sin depender del proveedor; aún sujeto a aprobación.
- **Inspección visual de PN:** familias y sufijos diferenciados entre T01–T07; no se aprecia repetición del PN completo entre tablas, pero no hay todavía una lista digital auditada que certifique 68 referencias únicas. La clave lógica y alcance de edición siguen abiertas (F1-D07). No interpretar la semántica de un PN mediante subcadenas no documentadas.
- **Pendientes asignados a F1:** frecuencia no especificada, cardinalidades máximas, spans, replay reproducible, publicación automática de futuras ediciones. F0 no se reabre por ello.

La selección de proveedor de extracción es independiente de los modelos del agente operativo: el assessment requiere modelos configurables de OpenRouter para el agente. Google AI Studio se contempla como mecanismo de ingestión adicional sugerido por el enunciado. **No existe autorización para implementar código en este punto.**


---

## 46. Seguimiento F1 tras aprobaciones de identidad, frecuencia y modos de ingesta (v0.11)

El usuario ratificó expresamente: **F1-D07** (identidad interna, PN único por edición sujeto a auditoría digital), **F1-D09** (frecuencia explícita/no especificada/no aplicable) y **F1-D11** (fresh extraction con Gemini + verified replay sin Gemini). También ratificó la separación de responsabilidades, cardinalidades conceptuales y modelo normalizado de F1, sin aprobar aún el esquema físico.

**Corrección de lectura del PDF:** En la tabla trifásica de la página 2 hay columnas distintas de `Cycles per Hour` y `Starts per Hour`; torque/duty cycle siguen sin desdoblamiento explícito por servicio. Ver el análisis en `F1_domain_and_etl_kickoff_v0.5.md`, §20.1.

**8 decisiones nuevas todavía abiertas:** F1-D10 (spans), F1-D12 (autopublicación futura), F1-D13 (huella de plantilla), F1-D14 (alimentación), F1-D15 (métricas tipadas), F1-D16 (N/A), F1-D17 (notas) y F1-D18 (fijación de edición por sesión). Las alternativas y recomendaciones constan en el documento F1 v0.5, §23. **Ninguna de las ocho queda aprobada por el mero hecho de documentarse.**

**Disciplina de fases:** F0 permanece cerrado; F1 sigue en alineación. No se ha implementado código, ejecutado ingesta ni generado Specs de Kiro.


---

## 47. Registro incremental F1 — ocho aprobaciones y apertura de modelo lógico (v0.12)

**Aprobaciones expresas del usuario:** F1-D10 A (celdas combinadas ↔ filas por enlaces auditables), F1-D12 A condicionada (autopublicación futura sólo tras calibración independiente y gates), F1-D13 C (plantilla declarada + huella de layout), F1-D14 B (alimentación normalizada), F1-D15 A (métricas tipadas), F1-D16 A (disponibilidad explícita), F1-D17 A (notas con alcance verificable), F1-D18 A (edición fijada por conversación). Se registran alternativas y justificaciones en `F1_domain_and_etl_kickoff_v0.6.md`, §25.

**Disciplina:** la aprobación del modelo normalizado y de sus principios no equivale a aprobar un esquema físico. En F1 v0.6 §§26–30 se propone el mapa de identidades, PK/FK/UNIQUE, enlace a evidencia por campo, restricciones, índices mínimos y ocho decisiones F1-D19 a F1-D26 **todavía abiertas**. No hay ingesta implementada, auditoría completa de PN, migraciones ni Specs de Kiro.

**Dato de fuente con interés de calidad:** T03 (página 2 del PDF oficial) diferencia `Cycles per Hour` y `Starts per Hour`, aunque no desglosa torque y duty por servicio; conservar esta sutileza sin atribución inventada.

**Nota de seguridad de versiones:** las sesiones fijan edición del catálogo, pero no queda decidida la política de uso cuando se retira una edición por error grave. Se propone bloqueo de nuevas recomendaciones desde fuentes retiradas con conservación auditiva de respuestas antiguas; requiere aprobación.


---

## 48. Registro incremental F1 — aprobación F1-D19 a F1-D26 (alineación histórica v0.13)

El usuario confirmó explícitamente en una sola respuesta las ocho recomendaciones formuladas en `F1_domain_and_etl_kickoff_v0.6.md` §29, junto al modelo lógico candidato, las pruebas representativas y la política de no sobreindexar. Se actualizan así los estados anteriores de **ABIERTA** a **APROBADA**; las secciones históricas previas no se modifican.

- **F1-D19 B:** redundancia controlada de edición con FKs compuestas en relaciones críticas; no generalizar el campo a todo registro.
- **F1-D20 B:** un PN puede documentar varias configuraciones; ninguna se crea sin evidencia.
- **F1-D21 A:** enlaces a evidencia por campo mediante relaciones tipadas por familia y FKs comprobables; se descarta FK polimórfica textual.
- **F1-D22 A:** disponibilidad explícita con coherencia del valor y el estado; NULL ≠ N/A ≠ no listado.
- **F1-D23 A:** cifras originales y precisión editorial con NUMERIC, conservando los torques de ambas unidades oficiales.
- **F1-D24 A:** índices mínimos justificados por claves y patrones de acceso, expansión sólo mediante medición.
- **F1-D25 A:** edición retirada por error grave deja respuestas antiguas auditables pero bloquea recomendaciones nuevas; se informa de retiro.
- **F1-D26 A:** integridad local y referencial complementada con verificación completa y promoción transaccional; la DB no es por sí sola auditoría del PDF.

**Trade-off aprobado:** más FKs, asociaciones y validaciones para impedir mezclas semánticas y numéricas. **Estado F1:** pendiente todavía de definición física y aceptación de extracción. Nada de esto autoriza código, migraciones o Specs.

**Nueva referencia de detalle:** `F1_domain_and_etl_kickoff_v0.7.md` §§31–36. Contiene diccionario lógico por grano, casos de consulta de dominio CQ-01 a CQ-10, invariantes IL-13 a IL-22 y **ocho nuevas decisiones F1-D27 a F1-D34 todavía ABIERTAS**. Estas no deben atribuirse al usuario hasta que las apruebe.

**Límites empíricos:** siete tablas y 68 filas confirmadas manualmente; cuatro PN N/A en T03; unicidad digital, lectura/cotejo de cada celda y benchmark de extractores siguen sin ejecutarse. La especificación documental distingue supuestos de evidencias; no se han fabricado resultados SQL.


---

## Registro incremental F1 — ocho decisiones de persistencia e ingesta ratificadas (v0.14)

**Estado:** F0 sigue formalmente cerrado; F1 continúa abierta. El candidato aprobó expresamente F1-D27 a F1-D34 en el orden y con la justificación de `F1_domain_and_etl_kickoff_v0.7.md`:

- **D27 B:** potencia del motor como campo de configuración con evidencia propia.
- **D28 B:** unicidad semántica de configuraciones, sin duplicados por `NULL`.
- **D29 B:** staging físicamente separado de estructuras consultables.
- **D30 B:** una edición puede tener múltiples documentos, sin ampliar las fuentes del assessment actual.
- **D31 B:** conflictos entre documentos bloquean publicación.
- **D32 B:** preservación de cifras impresas, conversiones derivadas deterministas.
- **D33 B:** ausencia de métrica excluida de elegibilidad verificada; candidatos indeterminados por separado.
- **D34 B:** reingesta y replay idempotentes mediante hashes/documento/manifiesto.

**Documentos nuevos:** `F1_domain_and_etl_kickoff_v0.8.md` contiene el acta y abre F1-D35 a D42. `F1_physical_schema_candidate_v0.1.md` es un anexo de diseño físico CANDIDATO, con entidades y campos detallados que aún requieren aprobación. No hay DDL, implementación, dataset extraído ni Specs. F0 no se reabre por estas decisiones.


---

## Registro incremental F1 — cierre de decisiones D35–D42 (v0.15)

El usuario aprobó F1-D35 a F1-D42 conforme al anexo `F1_physical_schema_candidate_v0.1.md`: NUMERIC sin escala fija inicial; disponibilidad por campo tipada; mediciones por condición; perfil de alimentación normalizado; esquemas PostgreSQL con privilegios; superficie de datos publicada read-only; ediciones inmutables; y publicación automatizada futura solo condicionada a calibración y gates de calidad. Las alternativas y razones constan en `F1_domain_and_etl_kickoff_v0.9.md` y `F1_data_architecture_handoff_v1.0.md`.

El usuario además delegó decisiones técnicas de ganador claro al arquitecto, conservando aprobación explícita de alternativas de alto impacto o de información insuficiente. No se autoriza por ello implementación inmediata ni generación de las Specs finales, que corresponden a Kiro. Inicia F2 con selección de arquitectura agentic e interfaces de herramientas.


---

## Registro incremental — revisión del gate F1 y avance F2 (2026-11-07)

El candidato detectó que el cierre comunicado de F1 podía ocultar tres obligaciones de transferencia pendientes de concreción: contrato ETL, operaciones de dominio y matriz de aceptación. Revisión de `F1_data_architecture_handoff_v1.0.md` confirma que existían §§4–6 a nivel conceptual. Se publica la adenda `F1_data_architecture_handoff_v1.1.md` (§§8–13) y se distingue **alineación contractual cerrada** de **ETL/pruebas ejecutadas** (no realizadas). La siguiente fase F2 continúa sin sacrificar exactitud ni afirmar implementación.

Se incorporan `F2_agent_architecture_kickoff_v0.3.md` y `F2_agent_design_decision_pack_v0.1.md`, con controles y defaults técnicos justificados; selección de modelos y comparativa tools siguen sujetas a evidencia. Esta revisión es una corrección del proceso de documentación, no un cambio unilateral de reglas del producto.


---

## Registro incremental F2 — cierre del diseño de agente (v0.17, 2026-11-07)

El candidato ratificó el flujo de siete etapas de F2 y las decisiones técnicas de ganador claro definidas en F2 v0.3. Se adopta ritmo de decisión delegado para aspectos técnicos inequívocos, pero no se autorizan código ni Specs finales.

Se publica `F2_agent_architecture_handoff_v1.0.md`: estados/interrupciones, contrato conceptual de tools y AST, garantía de claims numéricos y cualitativos, respuesta híbrida, modelo de persistencia, controles, plan de modelos OpenRouter y matriz de aceptación. Se actualiza `F2_agent_design_decision_pack_v0.2.md`.

**Hallazgo nuevo verificado en código fuente actual:** `EncryptedSerializer.from_pycryptodome_aes` de LangGraph usa AES-EAX por defecto, y su deserializador admite payload sin marca de cifrado; no satisface sin controles adicionales la decisión de AES-256-GCM. Este riesgo queda como requisito de integración y prueba para F3/F5, no se sustituye la decisión aprobada por el candidato.

**Selección empírica pendiente:** herramientas especializadas frente a una tool general, compatibilidad real de provider+tool+structured output, modelo final, coste y latencia. Se especifica cómo probarlos y qué decisión tomar con los resultados; no se inventan benchmarks. **Estado:** F2 cerrado como transferencia de diseño, no como validación técnica.


---

## Registro incremental F3 — primera ronda (2026-11-07, v0.18)

**Usuario ratifica:** AES-256-GCM obligatorio cuando sea viable (sin sustitución silenciosa), flujo agentic F2 aprobado y preferencia por herramientas especializadas B hasta comparación A/B; evaluar al menos dos modelos **por función** (interpretación, herramientas y explicación) sin superar la cuota USD 6 de evals. Autoriza que el arquitecto resuelva las decisiones técnicas con ganadores claros, pero exige indicar opciones, selección y justificación; trade-offs de autenticación y API async se presentan para aprobación explícita.

**Paquete:** `F2_agent_architecture_handoff_v1.1.md` (matriz por responsabilidad) y `F3_backend_api_security_design_v0.1.md` (F3 en progreso, sin Specs ni código). Recomendaciones pendientes: F3-D01 tokens opacos+refresh rotativo vs JWT y F3-D02 endpoint sync obligatorio+jobs async vs solo sync. Defaults técnicos documentados con opciones comparadas: monolito modular+worker, PostgreSQL job lease/fencing, key hierarchy AES-GCM, RBAC+owner, DTOs y errores tipados, roles DB separados, TLS production, staging publicado only, logging saneado y delete race. No afirmar pruebas ejecutadas ni F3 cerrado.


---

## Registro incremental F3 — autenticación, jobs y arquitectura modular (v0.19, 2026-11-07)

El usuario **aprueba expresamente** F3-D01 B (tokens Bearer opacos con verificadores en PostgreSQL, refresh rotativo y revocación) y F3-D02 B (POST /api/conversation síncrono obligatorio, además de jobs asíncronos). Ratifica además las decisiones técnicas comparadas de F3 v0.1. Pide discutir con profundidad estilos arquitectónicos, patrones de diseño y tácticas, con especial interés en Flow, Feature-First en backend/Android, Repository, DTO/DAO y defense in depth con cifrado de disco + aplicación.

**Alternativas comparadas** (en `F3_architectural_styles_patterns_tactics_v0.1.md`): monolito en capas vs modular feature-first + hexagonal ligera vs hexagonal completa/microservicios; Data-Flow aplicado al ETL y UDF aplicado a Android en vez de backend global; Repository versus DAO adicional; DTO Pydantic versus ORM expuesto; Unit of Work transaccional; adapter, DI, facade, state machine, command/idempotency, Strategy selectivo; CQRS/Event sourcing, broker, factories genéricas y service mesh descartados de inicio por coste sin valor comprobable.

**Seguridad:** para producción, preferir cifrado de aplicación AES-256-GCM + volúmenes/backups cifrados en la infraestructura + TLS; diferencias de amenaza y limitaciones documentadas. Docker Compose no puede por sí solo garantizar cifrado del host. El usuario había aprobado AES-256-GCM y pregunta por complementariedad; no hay sustitución unilateral.

**Estado:** F3 continúa en curso; la preferencia arquitectónica global `F3-ARCH-01` A (Feature-First + Ports & Adapters ligera) requiere confirmación del usuario por ser una decisión de estructura relevante. No se autoriza implementación ni Specs todavía.

**Archivos:** `F3_backend_api_security_design_v0.2.md`; `F3_architectural_styles_patterns_tactics_v0.1.md`.


---

## Registro incremental F3 → F4 — Arquitectura ratificada (2026-11-07, v0.20)

El usuario **aprueba** F3-ARCH-01 opción A: backend FastAPI Feature-First + hexagonal ligera / Ports & Adapters selectivos; se mantienen topología monolito modular + worker y patrones Repository, DTOs separados de ORM, UoW, DI, Adapter, Strategy selectiva, State Machine y Command/Idempotency. Sin DAO redundante, event sourcing, CQRS pleno, bus de eventos ni microservicios.

Aprueba arquitectura móvil Feature-First + MVVM + UDF y ETL Pipe-and-Filter. Aprueba defensa en profundidad: TLS y AES-256-GCM aplicación obligatorios, cifrado disco/backup como responsabilidad de despliegue productivo (no garantizado por Docker Compose), Android local protegido por Keystore y cifrado propio. Mantener evidencia de threat models y límites, sin afirmar pruebas.

Se emite `F3_architecture_handoff_v1.0.md` como dossier de cierre de diseño con matriz de aceptación; abre F4 con `F4_android_ux_architecture_v0.1.md`. F4 pendientes UX de alto impacto: interpretación compacta o extensa (D01), barras condicionales o solo tablas (D02), cache on-open vs sync background (D03); el resto son defaults técnicos justificados y documentados, sujetos a pruebas. No crear Specs de Kiro ni implementar antes de autorización.


---

## Registro incremental — F4 y transición F5 (2026-11-07, v0.21)

Se consolida `F4_android_ux_handoff_v1.0.md`, cerrando F4 como diseño con ratificaciones previas: Feature-First + MVVM + UDF, cinco destinos (Login/Register/Conversations/Chat/Developer Debug), tres pantallas obligatorias claramente distintas, caché autorizado offline (no inferencia), comparación de 3 y dual de 2, barras opcionales equivalentes, planes visibles y confirmación condicional, developer solo sus trazas. Defaults técnicos comparados: Navigation Compose type-safe, Room, DataStore no sensible, Retrofit+OkHttp, polling on-visible/refresh, Keystore+AES-GCM para caché.

Decisiones UX F4-D01 A: interpretación compacta visible y expansible, confirmación prominente; F4-D02 A: barras opcionales ya aprobadas en F0; F4-D03 A: Room lectura inmediata/revalidación en apertura sin WorkManager periódico obligatorio. Se mantiene decisión de separar rutas Debug accesibles por rol y permisos backend; no se implementan ni verifican pantallas aún.

Se crea `F5_quality_testing_delivery_kickoff_v0.1.md` con pruebas, evals, presupuestos, escenarios de aceptación, amenazas y reproducibilidad. F5 abierta; no se inventan resultados, benchs ni costes reales.


---

## Registro incremental — F5 y preparación F6 (2026-11-07, v0.22)

Se adopta release gate obligatorio de **cero defectos críticos conocidos** de exactitud/autoridad numérica, autorización, AES-GCM y aislamiento multiusuario, persistencia, y contrato POST exigido por Konecto. En caso de agotamiento de OpenRouter o caídas externas, respuesta de indisponibilidad clara sin inventar números, mientras historial/caché autorizado sigue consultable. Son decisiones técnicas de alternativa claramente superior según delegación del usuario.

Se consolida `F5_quality_testing_delivery_handoff_v1.0.md` con matriz de pruebas, evals por función (al menos dos candidatos, USD 6 cap global y USD 4 reserva), QA Android, seguridad y criterios de repro cold-start. Pruebas NO ejecutadas. Se crea `F6_kiro_master_alignment_candidate_v0.1.md` con precedencia documental, invariantes, dependencias y protocolo de transferencia; F6 pendiente del green light explícito del usuario.


## Registro incremental v0.23 — F6: cierre F4/F5 y corrección UX offline (2026-11-07)

**Aprobación expresa del usuario:** se aprueba sin cambios F3-ARCH-01 (Feature-First + hexagonal ligera), estilos por subsistema (Android MVVM/UDF; ETL Pipe-and-Filter; agente/jobs máquinas de estado), patrones seleccionados y descartados, tácticas de calidad y cifrado en profundidad. F3 v1.0 es contrato de diseño vigente.

**Nueva aprobación explícita F4:** cuando no haya conexión, mostrar un aviso evidente de que no podrá enviar mensajes; bloquear la acción Enviar, conservar el borrador y el historial autorizado, sin encolar automáticamente ni ejecutar trabajo en reconexión. F4 v1.1 documenta casos de conectividad, accesibilidad y distinción de caída del servidor. F5 v1.1 añade pruebas exigibles.

**Estado de fases:** F0–F5 cerradas como **alineación de diseño**. F5 pruebas reales aún no ejecutadas. F6 prepara transferencia final y auditoría de precedencia; no existe autorización para generar Specs o iniciar implementación por este solo intercambio.

**Paquete:** siete dosieres canónicos F0–F6 más tres PDFs originales del assessment, notas originales y referencias de soporte; versiones históricas solo para trazabilidad, no prevalecen sobre los contratos canónicos.
