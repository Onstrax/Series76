# Series 76 — F1 Data Architecture Handoff v1.1

**Tipo:** dossier de alineación arquitectónica para Kiro. **No** es Spec, DDL, código, migración ni autorización de implementar.
**Estado:** F1 cerrada como alineación contractual de diseño (no como implementación validada). Adenda §8–§13 completa contratos operativos y aceptación; pruebas empíricas siguen pendientes.
**Fuentes:** `assessment-en.pdf`, `series_76_electric_data.pdf`, `series_76_summary.pdf`, alineación F0 v0.15, catálogo funcional F0 v0.3, F1 histórico v0.9, anexo físico v0.1.
**Jerarquía de autoridad:** assessment para requisitos; PDF eléctrico para cifras técnicas; decisiones aprobadas para comportamiento de producto; resumen solo para contexto. Los ejemplos de modelo no son transcripciones certificadas del PDF.

## 1. Alcance y parámetros de verdad

- Siete tablas T01–T07 en cuatro páginas, **68 filas visualmente contadas y ratificadas**, cuatro PN listados con bloque N/A en T03. No afirmar todavía 68 **PN únicos digitalmente auditados**.
- El PDF del assessment requiere `ingest.py` o pipeline equivalente que procese el PDF original; PostgreSQL es obligatorio; `pgvector` no necesario; LangChain debe utilizar por lo menos una herramienta personalizada para consultas tabulares.
- Los dos valores oficiales de torque (in-lbs y Nm) se conservan de forma independiente. Cálculos derivados en operaciones deterministas, sin reescritura de las cifras originales.
- Contexto de fuente: T01/T02/T06/T07 separan torque/duty por servicio y velocidad/FLA/LRA por frecuencia; T03 no atribuye torque/duty a un servicio, pero **sí diferencia ciclos y arranques por hora**; T04 On/Off 24 V AC/DC y T05 Modulating 24 V DC; las celdas fusionadas de potencia y notas deben conservar alcance. No inferir significado de subcadenas del PN.

## 2. Modelo relacional autorizado (estructura, no SQL)

**Áreas y permisos:** esquemas lógicos `catalog`, `provenance`, `ingestion`, `publication` dentro de una instancia PostgreSQL; roles separados para (a) pipeline/editor de ingesta, (b) publicador, (c) runtime de lectura del agente. El rol de runtime no tendrá permisos de UPDATE/DELETE sobre catálogo ni acceso a staging. El acceso a ediciones publicadas/retiradas debe gestionarse sin exponer borradores.

| Tabla o familia conceptual | Grano e identidad | Principales atributos y garantías |
|---|---|---|
| `catalog_edition` | una versión inmutable publicada o candidata | `edition_id`, `manifest_digest`, estado, tiempo, referencia a edición anterior; estados controlados |
| `edition_source_document` | pertenencia documento–edición | FKs reales, orden/rol de fuente |
| `part_number` | un PN canónico por edición | `part_id`, `edition_id`, PN impreso/canónico; `UNIQUE(edition_id, canonical_pn)` una vez auditado inventario |
| `supply_profile` + `supply_profile_mode` | perfil nominal y modos AC/DC admitidos | voltaje `NUMERIC`, fase documentada o estado explícito, conjunto canónico de modos; unicidad semántica |
| `electrical_configuration` | PN × configuración documentada | FK compuesta al PN/edición, perfil, enclosure, potencia en W y su estado, disponibilidad; no crear variantes sin evidencia |
| `service_performance` | una prestación atribuida a servicio | `service_type`, `torque_inlbs`, `torque_nm`, `duty_s4_pct`, `cycles_per_hour`, `starts_per_hour`, cada uno con estado |
| `unqualified_performance` | prestación cuyo alcance por servicio no está especificado | mismas familias tipadas; **no** desdoblar por On/Off/Modulating sin evidencia (caso T03) |
| `operating_condition` | una frecuencia explícita/no especificada/no aplicable por configuración | `frequency_state`, `frequency_hz`; `frequency_hz` presente solo si EXPLICIT |
| `electrical_measurement` | una fila por condición operativa | velocidad en segundos, FLA y LRA en A; estado y evidencia individuales; sin valores por frecuencia ficticios |
| `source_document`, `source_section`, `source_row` | PDF, tabla, fila real | hash SHA-256, posición y orden documental; no omitir N/A ni notas |
| `source_cell_evidence` | celda visual y texto fiel | coordenadas, encabezado jerárquico, valor impreso, unidad, grupo; edición/documento |
| `source_cell_row_coverage` | celda ↔ fila | FKs reales; documentar cobertura por combinación de celda fusionada y filas |
| `source_note`, `source_note_row_scope` | nota ↔ filas afectadas | conservar marcador, texto original y alcance; no añadir certificaciones inferidas |
| familias `*_field_evidence` | campo tipado ↔ celda real | tablas puente y FKs reales; evitar relación genérica `entity_type/id` sin integridad referencial |
| `ingestion_run`, `staging_extraction_candidate`, `staging_discrepancy`, `verification_record` | intentos, candidatos, discrepancias, correcciones | versiones de motores y prompts, reviewer, estados, timestamps, diffs, ubicación |
| `verification_manifest`, `catalog_current`, `catalog_publication_event` | verificación, activación y retiro | hash canónico, promoción atómica, historial de eventos |

**No automatizar decisiones no sustentadas:** un valor compartido visualmente no se propaga por heurística de `forward-fill`; una fila N/A existe en la procedencia pero no tiene métricas elegibles; `NULL` no representa todos los motivos de ausencia; una columna de 24 V DC no se transforma en AC/DC.

## 3. Integridad y reglas para Kiro

**Declarativa**: PK; FKs simples/compuestas cuando evitan cruces entre ediciones; UNIQUE del PN por edición, sección y fila; unicidad semántica del perfil; pares valor+estado coherentes mediante CHECK; `NUMERIC` sin coerción/redondeo silencioso; duty porcentual dentro de dominio documentado; frecuencia EXPLICIT ↔ Hz positivo; campos ausentes ↔ sin valor falso; índices mínimos por PK, FK, unicidad y edición vigente.

**Gate transaccional de edición**: validar todos los documentos autorizados, firmas de layout, 7 tablas/68 filas para edición inicial, cada fila/nota/celda relevante, estado de los N/A, torques en ambas unidades, condiciones 50/60 Hz, modos AC/DC, cobertura de celdas combinadas, conflictos, enlaces a evidencia, hash y manifiesto. Si cualquier inconsistencia crítica persiste, NO activar edición. Solo cambiar el puntero activo tras éxito integral; edición anterior permanece accesible para historial y sesiones fijadas, salvo retiro explícito por error grave. La retirada detiene nuevas recomendaciones de esa edición.

**Inmutabilidad y versión**: nueva edición para una corrección posterior; no UPDATE en cifras publicadas. Reingesta/replay idénticos no crean ediciones duplicadas. Correlacionar cada ejecución con manifiesto y huellas de documentos; registrar nueva ejecución aun cuando no haya nuevo catálogo.

**Seguridad**: nada de SQL generado libremente por LLM. Runtime solo SELECT de superficie publicada autorizada; la elección de versión debe validar estado y contexto de sesión. Cifrado AES-256-GCM de conversaciones/trazas es obligación de F3 y no implica cifrar cifras técnicas públicas.

## 4. Contrato conceptual de ingesta (no JSON schema final)

| Artefacto | Debe contener | Verificaciones |
|---|---|---|
| `source_inventory` | documentos, SHA-256, tamaños, páginas, tablas, layout declarado | input íntegro, siete tablas previstas en caso inicial |
| `extraction_candidates` | OCR local y Gemini, coordenadas, texto bruto, cabeceras, candidatos por campo | trazabilidad de cada extractor; nunca tratar confianza como verdad |
| `reconciliation_report` | divergencias, ausencias, span de celdas, conflicto de unidades o fila-columna | todo hallazgo queda resuelto o en cuarentena |
| `normalized_facts` | PN, configuración, ratings por servicio/no atribuidos, condiciones, medidas, estados | tipos, comparabilidad, correspondencia con encabezado/nota |
| `evidence_map` | por cada campo normalizado: celda(s) y alcance de fila | cobertura completa e integridad referencial |
| `human_corrections` | correcciones de primera edición con valor previo, valor verificado, motivo, revisor y referencia | aplicación determinista, no silenciosa; hash del input |
| `verification_report` | resultado de checks, conteos, métricas y razones de rechazo | cero anomalías críticas no resueltas |
| `verification_manifest` | hashes, versión de esquema/reglas/extractores, hechos canónicos, correcciones y digest final | re-ejecutabilidad y no duplicación |

**Dos vías de reconstrucción**: `fresh extraction` ejecuta OCR+Gemini desde el PDF y exige clave Gemini proporcionada por el evaluador; `verified replay` verifica las entradas y reconstruye desde artefactos aprobados versionados sin API externa. Documentar claramente la distinción entre *repetir extracción* y *repetir reconstrucción*. Conservar `.env.example` sin secretos reales.

**Auditoría inicial:** se verifican manualmente **todos** los hechos y notas relevantes contra el PDF, registrando correcciones. **Escalabilidad futura:** auto-publicación solo cuando la plantilla sea reconocida, existan evaluaciones independientes de calibración y todas las validaciones pasen; revisión humana excepcional ante cualquier incertidumbre. No afirmar garantía infalible sobre PDFs desconocidos.

## 5. Repertorio mínimo de operaciones de dominio (F2 implementará herramientas)

| Operación de negocio | Entrada semántica | Resultado estructurado; condición de seguridad |
|---|---|---|
| `get_part` | PN exacto, edición de sesión y, opcionalmente, servicio/frecuencia | PN identificado o ausente, configuraciones y prestaciones documentadas, `N/A`, notas, evidencias; nunca mutar catálogo |
| `search_parts` | filtros tipados, AND/OR/NOT agrupado, rangos, unidades, edición | todos los PN coincidentes con metadatos de elegibilidad/indeterminación; SQL parametrizado, no modelo generando SQL |
| `rank_candidates` (servicio, no necesariamente tool) | conjunto filtrado, prioridades explícitas/confirmadas | orden lexicográfico reproducible; PN desempate; nunca ordenar por métrica no comparable |
| `compare_parts` (servicio, no necesariamente tool) | hasta tres PN, condiciones de comparación | tabla estructurada, diferencias comparables, advertencias por condiciones incompatibles; dual de dos en app |
| `get_source_notes` | sección, PN, configuración o hecho | notas oficiales con ámbito; nunca inferir certificaciones |
| `convert_units` (servicio) | valor documentado y par de unidades compatible | valor derivado con etiqueta, precisión y regla; **no** sustituir cifras originales |

**Resultado para móvil (adelanto contractual, F3 lo fija):** separar prosa de explicación de bloques técnicos generados determinísticamente, con `source_edition_id`, `result_status` (verified/preliminary/unavailable), condiciones, listas exhaustivas de PN cuando corresponda, top hasta 3 fichas, reglas de ranking, notas y referencias de evidencia. Debe respetar `POST /api/conversation` → `session_id`, `answer` del assessment. El LLM jamás dicta valores técnicos serializados.

## 6. Tests de aceptación basados en la fuente (sin alegar ejecución)

1. T01: mismo PN retorna torques por servicio diferentes con unidades correctas.
2. T01/T02/T06/T07: 50 y 60 Hz no se intercambian en velocidad/FLA/LRA.
3. T03: cuatro filas iniciales aparecen documentadas N/A, sin métricas ficticias; torque de filas válidas no se atribuye a un servicio inexistente.
4. T04/T05: 24 V AC/DC On/Off ≠ 24 V DC Modulating.
5. Celdas fusionadas: una celda respalda exactamente las filas donde aplica, no mediante forward-fill genérico.
6. Notas de certificación: su texto y alcance permanecen fieles, incluidos asteriscos como marcas editoriales.
7. Ingesta errónea: no cambia edición activa; repetición idéntica no crea duplicados.
8. Edición retirada: respuestas históricas no se falsifican, pero no se emiten nuevas recomendaciones basadas en ella.
9. `search_parts` nunca devuelve candidato como `verified` si faltan condiciones físicas relevantes.
10. No se mezcla una medida procedente de una edición o condición distinta.

**Pendientes empíricos posalineación**: inventario digital y unicidad de 68 filas/PN; prueba real del extractor local (PaddleOCR o Docling), Gemini y conciliación; construcción de golden data; cotejo manual exhaustivo inicial; test real de recreación sobre instalación limpia. **No se presentan como ejecutados.**

## 7. Resultado de F1 y entrada a F2

**No bloquean la siguiente fase de diseño:** elección del OCR local definitivo (benchmark de implementación), tamaño exacto de PK interna (`BIGINT`/UUID según patrones de API y migraciones), microestructura de índices y nombres de cada tabla puente. Son detalles técnicos de bajo impacto que Kiro puede proponer manteniendo las garantías previas. Si Kiro encuentra una contradicción semántica o un trade-off nuevo de producto/seguridad, debe registrarlo y solicitar aprobación.

**Debe abordar F2:** arquitectura híbrida agentic con límites, inventario de tools y evaluación A/B de herramienta única vs especializadas, origen de cifras de respuesta, memoria persistente y checkpoints, validación de planes confirmados, multi-idioma, mitigación de inyección, trazas y presupuesto máximo de USD 6 desarrollo/evals.

**Decisión de proceso:** las próximas respuestas priorizarán grupos de decisiones verdaderamente influyentes. Las opciones de ganador técnico claro se resolverán con justificación y se añadirán al dossier, sin generar código ni Specs finales por fuera de Kiro.


---

## 8. Adenda de cierre de F1: aclaración sobre el gate de salida

**Motivo:** el candidato detectó correctamente que cerrar el diseño físico no equivale a haber transferido contratos de ETL, operaciones de dominio y criterios integrales de aceptación. Las §§4–6 de la v1.0 eran conceptuales; esta adenda fija sus obligaciones observables, **sin generar Specs técnicas para Kiro**. La v1.0 no debe interpretarse como evidencia de ETL ejecutado o producto validado.

**Estados distinguibles:** (i) decisión de diseño aprobada, (ii) contrato de comportamiento completado, (iii) prueba planeada, (iv) prueba ejecutada satisfactoriamente. Sólo (i) y (ii) aplican al cierre F1. Nunca marcar (iv) sin ejecución real y su evidencia.

## 9. Contrato operativo de ingesta — comportamiento, no JSON Schema

### 9.1 Entradas obligatorias y precondiciones

- Uno o más PDFs fuente identificados con SHA-256 real, tamaño, número de páginas, origen autorizado y rol documental. Para el assessment, **sólo** `series_76_electric_data.pdf` autoriza cifras técnicas; `series_76_summary.pdf` puede enriquecer contexto de negocio, no valores técnicos.
- Identificación de formato/plantilla, versión de reglas de normalización y de validación, configuración del extractor OCR y versión/identificador del modelo Gemini cuando se emplee.
- Modo `fresh_extraction` (requiere credenciales Gemini aportadas en entorno, OCR local y conciliación) o `verified_replay` (requiere manifiesto y artefactos previamente aprobados; ninguna llamada a IA).
- Parámetros de reproducción declarados; todos los secretos deben venir de entorno/gestor de secretos y quedar fuera de artefactos.

### 9.2 Productos contractuales y dependencias

| Producto | Contenido mínimo verificable | Reglas de fallo / dependencia |
|---|---|---|
| Inventario de fuente | hash, identificador de documento, páginas, secciones, plantilla declarada, autorizaciones | si cambia el hash o formato sin correspondencia registrada: detener / cuarentena |
| Extracciones originales | texto/candidato por OCR y Gemini, coordenadas, encabezado contextual, región y extractor | no permite consultas del agente; ausencia de candidato != cero |
| Mapa de reconciliación | coincidencias y diferencias por celda, agrupaciones, fila, unidad, nota, resolución | discrepancia no resuelta impide publicación |
| Datos normalizados | PN, supply profile, configuraciones, prestaciones por servicio o no atribuidas, mediciones/frecuencias, ausencias explícitas | tipos semánticos y relaciones deben ser válidos |
| Evidencias | para cada campo publicado, enlace a celda/celdas y filas cubiertas, incluyendo notas | dato técnico sin evidencia -> rechazo |
| Correcciones | anterior/nuevo, justificación, hash fuente, celda, revisor, motivo, revisión | nunca cambiar automáticamente una corrección para otro hash de documento |
| Reporte de verificación | conteos, pruebas declarativas, cobertura, diferencias, cambios de plantilla y estado | `PASS` únicamente si no existen anomalías críticas abiertas |
| Manifiesto canónico | huellas de fuente, versiones, artefactos, hechos, correcciones, reporte, digest estable | debe poder verificarse por reproducción desde artefactos aprobados |
| Evento de publicación | edición anterior/nueva, hash de manifiesto, estado, fecha, motivo | activación atómica; fallo deja la edición anterior intacta |

### 9.3 Semántica de ejecución

- Un `fresh_extraction` puede devolver `REJECTED`, `QUARANTINED` o `VERIFIED_READY`; jamás publicar directamente candidatos OCR/LLM.
- El `verified_replay` **reconstruye desde artefactos aprobados** y verifica hashes y transformaciones; **no demuestra** que una nueva inferencia visual reproduciría las mismas observaciones.
- Reejecutar una entrada y manifiesto idénticos puede crear un nuevo registro de ejecución auditable, pero no otra edición con los mismos hechos.
- El pipeline no hace `forward-fill` indiscriminado; una celda compartida tiene enlaces explícitos a las filas que cubre.
- Sólo el publicador privilegiado activa una nueva edición; runtime del agente nunca puede ver staging ni publicar.
- La edición inicial exige auditoría manual del 100% de hechos, notas y N/A relevantes contra imagen oficial; mantener 7 tablas y 68 filas como **oráculo de la edición inicial**, no criterio global para otros PDFs.
- Autopublicación futura sólo después de calibración independiente, plantilla conocida y checks completos. Si dos extractores coinciden en un error no detectable por reglas, persiste riesgo residual: no prometer garantía absoluta.

### 9.4 Taxonomía de errores ETL para diseño posterior

`INPUT_UNREADABLE`, `HASH_MISMATCH`, `TEMPLATE_UNKNOWN`, `SECTION_MISSING`, `ROW_COUNT_MISMATCH`, `CELL_COORDINATE_AMBIGUOUS`, `EXTRACTOR_DISAGREEMENT`, `UNSUPPORTED_UNIT`, `DUPLICATE_IDENTITY`, `SOURCE_CONFLICT`, `EVIDENCE_MISSING`, `CORRECTION_STALE`, `PUBLICATION_FAILED`.

Los identificadores son vocabulario de alineación, **no** claves públicas definitivas; Kiro los traducirá en Specs y formatos apropiados, manteniendo significado y severidad. Registrar detalles de diagnóstico sin secretos.

## 10. Contrato conceptual de operaciones del dominio

**Regla compartida:** cada operación recibe un contexto autenticado y una edición explícita validada para la sesión; los identificadores provenientes del LLM no otorgan permisos. Toda herramienta invoca repositorios SQL tipados y read-only con parámetros validados; sin SQL libre.

| Operación | Entrada válida de dominio | Salida e invariantes | Distinciones de fallo |
|---|---|---|---|
| `get_part` | PN exacto, edición; servicio/frecuencia opcionales | presente o no listado; configuraciones, prestaciones, condiciones, notas y evidencia, sin adjudicar service faltante | PN malformado, PN no listado, PN listado N/A, dato no documentado |
| `search_parts` | AST de filtros explícitos `AND/OR/NOT` con agrupación, rangos, unidades, contexto | coincidencias verificadas y preliminares/indeterminadas separadas, orden estable; no mezclar ediciones | filtro inválido, valor no comparable, sin resultados, criterio no documentado |
| `rank_candidates` | elegibles + prioridades lexicográficas confirmadas + equivalencia de condiciones | orden reproducible, desempate por PN; no inventar scores ni ganador entre métricas incomparables | indeterminación o métricas faltantes: advertencia/no ranking de ese criterio |
| `compare_parts` | hasta 3 PN de la misma edición y condiciones a comparar | datos lado a lado, notas, condiciones y advertencias; dual en Android es presentación, no semántica distinta | condiciones distintas: comparación informativa sin ganador inválido |
| `get_source_notes` | identidad de PN/configuración/hecho/tabla y edición | texto y alcance exacto, no certificación inferida | nota inexistente vs no verificada |
| `convert_units` | magnitud autorizada y unidad destino compatible | valor derivado, precisión/política de redondeo, fuente, etiqueta de derivado | unidad no compatible o magnitud insuficiente: error explícito |

**Colección completa vs payload móvil:** si N coincidencias exceden 3, el sistema comunica el **total y todos los PN** (con transporte paginado si es necesario), pero la respuesta de chat expone **máximo 3 fichas completas**. En modo top-1, sólo una ficha completa y total de alternativas; nunca hacer pasar un subconjunto por el conjunto completo. La paginación (si se implementa) debe fijar edición, orden y filtros, evitando resultados inconsistentes.

**Disponibilidad:** estados del requisito del usuario, del hecho técnico y del proceso conversacional son ejes diferentes. `UNKNOWN` de usuario no equivale a `NOT_DOCUMENTED` de fuente; `NOT_LISTED` no es medida cero. Servicio de T03 no se inventa. Ranking de corrientes entre distintas alimentaciones no prueba eficiencia energética.

**Cálculos:** utilizar siempre los valores oficiales correspondientes a unidad y condición cuando existan; calcular conversiones sobre `Decimal` y declararlas derivadas; prohibido recalcular y sobrescribir un valor documental con la conversión de su columna homóloga.

## 11. Matriz explícita requisito → operación → evidencia → aceptación

| Capacidad aprobada | Operación/artefacto | Evidencia requerida | Criterio de aceptación (pendiente de ejecutar) |
|---|---|---|---|
| US-010 consulta PN | `get_part` | PN, sección/edición/celdas | diferencia On/Off–Modulating y 50/60 Hz conservada |
| US-011 filtros | `search_parts` | AST, configuración y predicados registrados | AND/OR/NOT y unidad correctos, sin asumir alimentación |
| US-014/015 preliminares | `search_parts` | estado de 4 grupos de compatibilidad | faltantes no se transforman en elegibilidad verificada |
| US-016/017 ranking/top-1 | `rank_candidates` | prioridades confirmadas y valores fuente | resultado reproducible y desempate PN |
| US-018 lista exhaustiva | `search_parts`/presentación | total, lista PN, hasta 3 fichas | ningún PN omitido silenciosamente ni cifras fabricadas |
| US-019/020 comparación | `compare_parts` | igualdad de contexto y métricas | datos mixtos se muestran con aviso; no hay ganador inválido |
| US-023/024 explicación/cálculo | notas, conversiones | fuente y parámetros del cálculo | ningún número técnico generado por LLM como autoridad |
| US-031 ingesta | pipeline y manifiesto | reporte, verificaciones, correcciones, hash | 7 tablas, 68 filas y 4 N/A iniciales; 100% auditado |
| QA integridad | gate de publicación | mapa celda-campo, reconciliación | 0 discrepancias críticas en edición inicial |
| QA reproducibilidad | `verified_replay` | artefactos y digest | mismo manifiesto/hechos, sin invocaciones Gemini |
| QA inmutabilidad | publicación/retiro | eventos y ediciones | fallo o corrección nunca muta edición anterior |
| QA seguridad | repositorios de lectura | rol read-only, pruebas IDOR y staging | agente no puede leer borradores ni cruzar ediciones |

## 12. Límites deliberados de F1 y asuntos asignados

- **F2** decide interfaz/herramientas LangChain, interpretación semántica de AST, plan confirmado, contexto y presentación numérica.
- **F3** define contratos HTTP, transporte de operaciones, autenticación, roles, cifrado de conversaciones, colas y error envelope.
- **F4** define tablas/gráficos y caché Android, sin parsear respuesta técnica desde prosa.
- **F5** materializa oráculos y automatización de pruebas/evals, umbrales empíricos y métricas.
- **Kiro en ejecución** propone SQL/migraciones, algoritmos de OCR y detalles de librerías; cualquier desviación de invariantes aprobadas requiere un ADR y aprobación.

## 13. Gate de salida F1, corregido

- [x] Decisiones de dominio aprobadas; modelo normalizado, B2, perfiles AC/DC, N/A, procedencia por celda, edición fijada, staging y publicación atómica.
- [x] Contrato de ingesta explicitado en entradas, productos, estados, validaciones, reproducción y excepciones.
- [x] Contrato de operaciones de negocio especificado como comportamiento, no como protocolo final ni esquema LangChain.
- [x] Matriz requisitos–operaciones–pruebas documentada.
- [x] Límites de responsabilidad F2–F5 y Kiro explícitos.
- [ ] ETL ejecutado y comparado contra PDF: **no realizado**; corresponde a implementación y F5.
- [ ] 68 identificadores extraídos y unicidad auditada digitalmente: **no realizado**.
- [ ] Benchmarks OCR/Gemini, esquema SQL probado y validación de reconstrucción sobre instalación limpia: **no realizados**.

**Declaración de cierre correcta:** F1 cerrada **como diseño de alineación y transferencia contractual**, no como implementación validada. Una discrepancia posterior deberá reabrir el ADR afectado, no declarar que F1 jamás fue discutida.
