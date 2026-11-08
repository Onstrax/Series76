# Series 76 — F1: Candidato de esquema físico y contrato de datos v0.1

**Naturaleza:** documento de alineación para Kiro; **NO** Spec, DDL, implementación ni autorización de construir.
**Estado:** propuesta sometida a revisión; se apoya en F1-D01–D34 aprobadas. Las F1-D35–D42 siguen abiertas.
**Fuentes:** `series_76_electric_data.pdf` (4 páginas, siete tablas), `series_76_summary.pdf` (contexto), `assessment-en.pdf`, `F0_requirements_and_quality_catalog_v0.3.md`, `F1_domain_and_etl_kickoff_v0.7.md`.

## 1. Principios no negociables ya aprobados

1. PostgreSQL relacional normalizado y métricas tipadas; no RAG ni EAV como base.
2. Verdad documental: exclusivamente el PDF oficial, por cada cifra y condición. Conservar los valores originales de ambas columnas de torque (in-lbs y Nm), sin recalcularlos como sustitución.
3. Siete tablas T01–T07, 68 filas contadas y confirmadas manualmente por el candidato; cuatro filas iniciales N/A en T03. **No equivalen a 68 PNs únicos digitalmente verificados.**
4. Ratings separados por servicio cuando las columnas lo explicitan; `unqualified_performance` cuando no lo explicitan (T03). Nunca fabricar la atribución por servicio.
5. Evidencia por campo/celda y asociación explícita entre una celda fusionada y cada fila alcanzada; notas con alcance.
6. Frecuencia `EXPLICIT`, `NOT_SPECIFIED`, `NOT_APPLICABLE` sin inventar 0, 50 ni 60 Hz donde la fuente no lo declare.
7. Una edición puede contener varios documentos; conflictos bloquean publicación; la edición aprobada se promueve atómicamente. Las conversaciones quedan fijadas a edición salvo cambio explícito y políticas de retirada.
8. Extracción dual: OCR estructural + Gemini visual; verificación exhaustiva de la primera edición; manifiestos versionados y replay sin API. Futuras auto-publicaciones únicamente tras calibración y gates, con revisión excepcional.
9. `Motor Power` se almacena como campo tipado en configuración; sus spans pertenecen a procedencia.
10. La ingesta y las vistas de consulta no deben mezclar valores candidatos con publicados.

## 2. Grano, límites y cardinalidades

**Edición:** conjunto inmutable de hechos técnicos verificados, originado en uno o más documentos. Activar/retirar edición no reescribe sus cifras.

**PN:** una identidad canónica por `(edition_id, canonical_part_number)` tras auditoría digital. Puede existir de nuevo en otra edición. El código original y marcadores editoriales se conservan en evidencia, sin decodificar características desde su estructura textual.

**Configuración:** un PN puede documentar una o varias combinaciones de enclosure/alimentación. No se crean configuraciones no documentadas.

**Prestación:** cero o varios ratings por servicio explícito, o un rating sin atribución de servicio (o ambos si documentos lo justificaran en futura edición, con reglas de reconciliación). La existencia de ciclos y arranques en T03 no autoriza atribuir torque a un servicio concreto.

**Condición:** cero o varias condiciones operativas por configuración, con frecuencia explicita o ausencia tipada. Las medidas de velocidad/FLA/LRA de T01/T02/T06/T07 son por 50/60 Hz; las de T04/T05 no tienen ese desglose.

**Celda:** una evidencia documental puede cubrir varias filas y servir a varios hechos publicados; cada vínculo a hecho y campo debe ser explícito, verificable y pertenecer a la misma edición.

## 3. Catálogo relacional físico candidato (sin SQL)

| Entidad tentativa | Identidad/grano | Campos principales candidatos | Integridad esencial |
|---|---|---|---|
| `catalog_edition` | `edition_id` interno | `manifest_digest`, etiqueta, estado, fechas, versión de políticas | digest único; solo promovible con gate satisfactorio; hechos inmutables tras aprobación |
| `edition_source_document` | `(edition_id, document_id)` | rol de fuente, orden de incorporación | dos FK reales; documento autorizado; detectar conflicto entre fuentes |
| `part_number` | `part_id` por edición | `edition_id`, `canonical_pn`, `printed_pn` | `UNIQUE(edition_id, canonical_pn)` tras inventario; unique auxiliar `(edition_id,part_id)` para FK compuestas |
| `electrical_configuration` | `configuration_id` por PN y perfil | `edition_id`, `part_id`, `enclosure`, `voltage_v`, `phase_state`, `phase_count`, `configuration_availability`, `motor_power_w`, `motor_power_status` | FK compuesta PN-edición; perfil inequívoco; valores NUMERIC; `motor_power_w` condicionado por status |
| `configuration_supply_mode` | `(configuration_id, mode)` | `mode` AC / DC | no crear diferencias artificiales de medición entre AC y DC en una sección conjunta; validación de conjunto no vacío cuando la fuente documenta modos |
| `service_performance` | rating para servicio expresamente documentado | `edition_id`, `configuration_id`, `service_type`, `torque_inlbs`, `torque_nm`, `duty_s4_pct`, `cycles_per_hour`, `starts_per_hour`, disponibilidad por campo | una combinación `(configuration,service)` única si el grano se verifica; FK edición/configuración |
| `unqualified_performance` | rating sin atribución de servicio | `edition_id`, `configuration_id`, mismas familias tipadas y estados | jamás duplicar por servicio; ciclos/arranques independientes donde existen |
| `operating_condition` | configuración + frecuencia documentada | `edition_id`, `configuration_id`, `frequency_state`, `frequency_hz` | si `EXPLICIT`, Hz presente y positivo; de otro modo Hz nulo; unicidad semántica con nulos |
| `electrical_measurement` | bloque de mediciones de una condición | `edition_id`, `condition_id`, `operating_speed_sec`, `fla_a`, `lra_a`, estados por campo | una fila por condición cuando está documentada; cifras no negativas con significado específico; no usar 0 para ausencia |

**NOTA:** los nombres, el tipo de clave interna (`BIGINT`/`UUID`), el conjunto final de estados, precisión de cada `NUMERIC` y la ubicación de restricciones compuestas son **candidatos**, no aprobaciones tácitas. La elección D27 elimina la tabla `motor_power_rating` previamente contemplada.

### 3.1. Alimentación y equivalencias

- Para T04: `24 V`, modos admitidos AC y DC, On/Off, sin valores sintéticos a 50/60 Hz.
- Para T05: `24 V`, modo DC, Modulating, sin inventar compatibilidad AC.
- Para 110/220 V monofásicos: `phase_count=1` si está expresamente documentada; T03 `phase_count=3`.
- El tipo de modo `AC/DC` es un conjunto de modos permitidos cuando el encabezado así lo documenta, no un permiso para inventar corrientes o tiempos específicos de cada modo.
- `UNKNOWN`, `NOT_SPECIFIED` y `NOT_APPLICABLE` no son sinónimos; conservar semántica de fuente.

### 3.2. Prestaciones y campos sin dato

Representar disponibilidad por métrica, de forma que `AVAILABLE` exija valor tipado y evidencia, mientras una ausencia explícita no pueda contener un número publicable. Propuesta preliminar de estados: `AVAILABLE`, `NOT_APPLICABLE`, `NOT_DOCUMENTED`, `NOT_VERIFIED`; la indicación literal `N/A` conservará su evidencia y se mapeará con regla aprobada. `NOT_LISTED` es un resultado de búsqueda, no una medición en base de datos. Los requisitos `UNKNOWN` pertenecen al usuario, no al registro técnico.

Conservar escala y texto de origen en la celda; aritmética usando `Decimal` y política de redondeo documentada. El torque impreso en in-lbs y en Nm son **dos valores oficiales independientes**, incluso cuando la conversión matemática exacta no coincida por redondeo editorial.

## 4. Procedencia documental (propuesta)

| Entidad tentativa | Grano | Información importante | Validaciones |
|---|---|---|---|
| `source_document` | contenido binario único | SHA-256, nombre, tamaño, páginas, tipo, política de autoridad | huella de bytes; sin asumir autenticidad del fabricante por el hash |
| `source_section` | tabla dentro de documento/edición | `edition_id`, `document_id`, página, código T01–T07, encabezado jerárquico | `UNIQUE(edition_id, table_code)` para edición inicial; FK documento–edición |
| `source_row` | fila visual | `edition_id`, `section_id`, ordinal, PN relacionado cuando corresponda, estado documental | `UNIQUE(section_id,ordinal)`; conserva las 4 filas N/A |
| `source_cell_evidence` | celda visual original | `edition_id`, sección, fila ancla, columna/ruta de encabezados, texto, bbox, extensión, verificación | celda original una sola vez; conservar ubicación y contexto |
| `source_cell_row_coverage` | vínculo celda–fila cubierta | `edition_id`, `cell_id`, `row_id` | PK compuesta, FKs reales, misma sección/edición, cobertura no inferida por forward-fill |
| `source_note` | nota literal | sección, tipo, marcador, texto, ámbito | notas/asteriscos fieles; no inventar certificaciones |
| `source_note_row_scope` | fila afectada por nota | `note_id`, `row_id`, `edition_id` | FKs reales y ámbito documental verificado |
| `service_field_evidence`, `unqualified_field_evidence`, `measurement_field_evidence`, `configuration_field_evidence` | vínculo entre **campo tipado** y celda original | ID de entidad, `field_code` validado por familia, `cell_id`, edición, opcionalmente rol de evidencia | FKs reales a entidad/celda/edición; rechazar campos inválidos y referencias cruzadas |

**Advertencia:** una FK tipada prueba que la entidad y celda existen; no demuestra por sí sola que el campo publicado iguale el número impreso. El gate de verificación cotejará texto, número, unidad, sección, fila y alcance. Las evidencias de celdas fusionadas pueden apoyar múltiples configuraciones sin copiar la celda original.

## 5. Ingesta, manifiestos, edición activa y permisos

| Entidad tentativa | Grano | Responsabilidad |
|---|---|---|
| `ingestion_run` | intento de ejecución | método fresh/replay, hashes de entrada, motores/versiones, fecha, duración, estado y fallos |
| `staging_extraction_candidate` | hipótesis de un extractor sobre una celda/campo | OCR/Gemini, valor bruto, estructura, bbox, confianza cuando exista, versión de modelo |
| `staging_discrepancy` | desacuerdo o fallo | origen, localización, tipo, valor OCR, valor Gemini, regla fallida y resolución pendiente |
| `verification_record` | revisión/rectificación por evidencia | original propuesto, corrección, justificación, revisor, estado, id de manifiesto |
| `verification_manifest` | paquete determinista de datos autorizados | documentos y SHA, versión de normalización, reglas, correcciones, contenido canónico y su digest |
| `catalog_current` | puntero único a edición activa | edición vigente y cambio transaccional |
| `catalog_publication_event` | evento de publicación/retiro | edición, actor, fecha, motivo, resultado y digest de manifiesto |

**Fresh extraction:** comienza desde PDF y ejecuta OCR + Gemini (clave propia por variable de entorno); produce candidatos, conciliación y errores. **Verified replay:** lee PDF y artefactos verificados/versionados, valida sus hashes y reconstruye la misma proyección sin llamar a Gemini; no significa «rehacer la inferencia». Un manifiesto nuevo corrige por versión; no reescribe silenciosamente una edición publicada.

**Separación de confianza:** el rol de consulta del agente no puede leer staging ni leer borradores, aunque un bug omita un filtro en lógica Python. Vista o repositorio publicado por edición; requiere **validar** qué mecanismo escoger en D40.

**Publicación atómica:** las validaciones de cada celda, tabla, sección, nota, PN, estado, clave y consistencia de documento se ejecutan antes de cambiar el puntero vigente. Una nueva edición no elimina la anterior. Retirar una edición impide nuevas recomendaciones sobre ella; historial previo permanece como registro histórico, salvo eliminación por usuario de la conversación. Una edición retirada no se vuelve a publicar silenciosamente.

## 6. Índices mínimos y reglas relacionales

**Índices inicialmente justificados:** PK/UNIQUE de edición/PN/section/row, soporte de FKs frecuentes según la consulta y borrados, acceso a edición vigente. Los filtros de torque/voltaje/velocidad se optimizarán después de analizar consultas reales, no antes, por tamaño actual (68 filas).

**FK compuestas:** aplicar `(edition_id, parent_id)` en relaciones cuyo padre podría existir en otra edición; otras relaciones pueden heredar edición indirectamente si existe una garantía formal equivalente.

**CHECK candidatos:** números disponibles con valor presente; estados ausentes sin números; frecuencia explícita con Hz no nulo y positivo; rango de duty S4%; `phase_count` coherente con `phase_state`; `motor_power` positivo cuando documentado. No convertir automáticamente «no disponible» en cero.

**Unicidad con nulos:** normalizar los atributos de perfil de alimentación y el conjunto de modos; decidir D38 si usar `supply_profile` o firma verificable de una configuración; no confiar en un `UNIQUE` convencional con nulos de significado ambiguo.

**Precisión:** `NUMERIC` sin redondeos silenciosos y la representación impresa en evidencia; escala fija por métrica vs variable continúa abierta D35.

## 7. Diez comprobaciones de modelo (propuestas, no ejecutadas)

| ID | Pregunta/escenario | Resultado estructural exigido |
|---|---|---|
| M-01 | PN exacto T01 | On/Off y Modulating con torques diferentes, ambos oficiales |
| M-02 | Velocidad T01 a 50 Hz vs 60 Hz | Cada medición usa su condición publicada, no la de otro servicio/frecuencia |
| M-03 | T03 primeras cuatro filas N/A | PN listados, sin torques falsos y con estado documental |
| M-04 | T03 fila válida | torque/duty sin atribución ficticia de servicio; ciclos y arranques independientes |
| M-05 | T04 24 V AC/DC vs T05 24 V DC | exclusión correcta de Modulating 24 V AC que no aparece documentado |
| M-06 | `motor_power_w` celda fusionada | una celda respaldando varias filas autorizadas, sin forward-fill heurístico |
| M-07 | Nota CSA de T02 | nota y alcance conservados, sin inferencia desde los caracteres del PN |
| M-08 | Perfil de configuración repetido con fase ausente | rechazo de duplicado lógico, aunque la DB permita NULL |
| M-09 | Edición con celda no verificada o conflicto de PDFs | rechazo integral; no cambia edición activa |
| M-10 | Retirar edición fijada en sesión antigua | historial consultable, bloqueadas nuevas recomendaciones sobre edición retirada |

## 8. Ocho decisiones abiertas para aprobar (F1-D35–D42)

| ID | Pregunta | Alternativas | Recomendación y razón |
|---|---|---|---|
| **D35** | Precisión física `NUMERIC` | A) `NUMERIC` libre con exactitud original y control semántico; B) `NUMERIC(p,s)` por atributo | **A** inicialmente: conserva escala editorial sin truncado silencioso; límites semánticos por campo y pruebas; definir p/s cuando evidencia lo amerite. |
| **D36** | Estado de disponibilidad por valor | A) par tipado `valor + availability_state`, validado por `CHECK`; B) tabla universal de estado por campo | **A**: minimiza EAV y permite restricciones locales. |
| **D37** | Grano de mediciones eléctricas | A) una fila `electrical_measurement` por `operating_condition` con velocidad/FLA/LRA; B) tres filas separadas por medición | **A** para PDF actual: evita fragmentación y mantiene las tres cifras de una condición sin mezclarlas. |
| **D38** | Identidad de perfiles eléctricos, incluyendo AC/DC y fase nula | A) entidad/catálogo reutilizable `supply_profile` y conjunto canónico de modos; B) firma textual por configuración calculada por la aplicación | **A**: unicidad e integridad se pueden comprobar en DB; hay coste de una entidad adicional. |
| **D39** | Localización física de staging y evidencias | A) esquemas lógicos separados en una misma DB (`ingestion`, `catalog`, `provenance`) con privilegios distintos; B) una sola colección de tablas prefijadas | **A**, con privilegios restrictivos, sin añadir servidores. |
| **D40** | Superficie de consulta del agente | A) vistas/funciones read-only filtradas a edición publicada, además de repositorios SQL tipados; B) solo repositorios Python con filtros | **A**, defensa en profundidad, evitando acceso del rol de consulta a staging; los contratos de tools se deciden en F2/F3. |
| **D41** | Corrección posterior de edición publicada | A) edición inmutable y nueva versión/manifiesto para rectificaciones; B) UPDATE in-place con historial | **A**, previene reescritura de cifras históricas usadas en conversaciones fijadas. |
| **D42** | Autopublicación futura | A) gate estricto de plantilla reconocida, cobertura completa, cero discrepancias no resueltas, calibración independiente y cuarentena ante incertidumbre; B) aceptar concordancia OCR/Gemini sin más condiciones | **A**. No garantiza matemáticamente exactitud en PDFs desconocidos; medir precisión y riesgo residual. |

**Nota de control:** D35–D42 NO están aprobadas, aunque se indiquen candidatas. Las cifras del PDF todavía no se han digitalizado y auditado. No crear ni ejecutar SQL ni ETL en esta fase de alineación.

## 9. Contrato de salida conceptual de la ingesta (pendiente de contrato final)

Cada ejecución debe poder entregar (i) un inventario de documentos y secciones con hash; (ii) filas identificadas y asociaciones PN; (iii) celdas con posición, texto y columna jerárquica; (iv) candidatos OCR/Gemini, discrepancias y correcciones; (v) hechos tipados con evidencia; (vi) informe del gate con criterios y resultados; (vii) manifiesto reproducible cuyo digest identifica la edición. No se publica si faltan notas, filas, evidencia o hay contradicciones abiertas.

No se ha escogido el OCR local definitivo ni se ha realizado extracción piloto. El benchmark y la validación manual exhaustiva son hitos de ejecución posteriores a aprobación del diseño, no resultados obtenidos.

## 10. Pendientes para cerrar F1 (tras D35–D42)

1. Validar nombres/campos definitivos, PK/FK compuestas, unicidades y restricciones locales en un diccionario final de tablas.
2. Definir el contrato formal del manifiesto y de los reportes de verificación, incluyendo rechazo/cuarentena/replay/publicación.
3. Determinar las consultas SQL de dominio necesarias para herramientas LangChain sin autorizar SQL libre; modelos y herramientas se cierran en F2.
4. Revisar seguridad/retención de artefactos de ingesta, versionado y tratamiento de clave Gemini; mecanismos detallados se cierran en F3.
5. Comprobar que cada historia y escenario de calidad de F0 está cubierto por el modelo y gate; decidir salida de F1.
