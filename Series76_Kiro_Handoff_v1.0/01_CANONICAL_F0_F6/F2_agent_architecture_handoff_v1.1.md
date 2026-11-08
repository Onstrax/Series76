# Series 76 — F2 Agent Architecture Handoff v1.0

**Tipo:** dossier de alineación y transferencia a Kiro; **no** Spec, código ni autorización de implementación.
**Estado:** F2 cerrable como **diseño** tras aprobación de este paquete; experimentos empíricos obligatorios se ejecutan con Kiro (F5). 2026-11-07.
**Base vinculante:** assessment-en.pdf; Series 76 electrical data PDF; F0 requirements v0.3; F1 handoff v1.1; F2 decision pack v0.2; registro F0 histórico v0.17.

## 1. Decisiones vinculantes y límites

1. LangChain con agente real que invoca por lo menos una **custom LangChain Tool** de consulta de datos tabulares en PostgreSQL. Sin text-to-SQL. El agente es **híbrido con autonomía limitada**: escoge entre tools autorizadas, no decide permisos, cifras ni reglas técnicas.
2. Datos numéricos oficiales solo del PDF eléctrico verificado y cálculos **Decimal deterministas** con unidad, redondeo y contexto. Ni respuesta JSON, ni campo `answer`, ni gráficas pueden mostrar una cifra técnica libre del LLM.
3. SQL tipado sobre catálogo publicado read-only, edición fijada por conversación. Datos del PDF/respuestas de tools son datos no confiables para el LLM, no nuevas instrucciones.
4. Interpretación visible **siempre**. Aclaración/confirmación bloqueante únicamente ante ambigüedad, contradicción, delegación material o propuesta de prioridades/recomendación no aceptada. Consulta simple exacta o filtro determinado puede ejecutarse sin segundo turno.
5. Cuatro persistencias lógicas separadas: mensajes de chat; estado de dominio; checkpoints de ejecución; trazas del agente. En datos sensibles, AES-256-GCM y eliminación con conversación, sin plaintext residual en checkpoints o trazas. Un `thread_id` no equivale a autorización.
6. Recomendación final verifica entorno, alimentación, tipo de servicio y torque. Si faltan requisitos físicos, ofrecer preliminares identificados como **no verificados**; preferencias delegadas pueden ser propuestas/justificadas, no inventar condiciones físicas.
7. Ranking lexicográfico explícito, desempate Base Part Number, manejo de no-comparables. Mostrar todos los PN coincidentes por listado/paginación, máximo tres fichas completas; top-1 cuando usuario pide solo uno. No se certifica aptitud industrial integral.
8. API obligatoria `POST /api/conversation` con `session_id` opcional en request y `session_id`, `answer` en response. F3 fija envelopes/HTTP, pero la UI y el agente usarán bloques técnicos estructurados y estados explícitos.
9. ES/EN, respuesta en idioma del último turno salvo instrucción específica. Fuera del PDF o summary no introducir hechos técnicos externos; abstención clara.
10. OpenRouter mediante modelos configurables por variable de entorno; máximo USD 6 de desarrollo/evals y mínimo USD 4 intactos de la clave para la demo final; Gemini AI Studio se reserva para extracción documental de F1 y no sustituye el runtime OpenRouter.

## 2. Arquitectura de responsabilidades (sin imponer partición de código)

| Capa | Hace | No hace |
|---|---|---|
| Autenticación/admisión (FastAPI) | JWT/session, owner, rol, edition, replay protection, rate/cost guard, encolado secuencial por sesión | Delegar autorización al modelo |
| DomainConversationState | Referentes, restricciones, prioridades, `plan_revision`, latest comparison set, idioma, edición; transiciones versionadas | Tratar el historial de prosa como autoridad única |
| Semantic interpreter (LLM) | Intención bilingüe, cláusulas AND/OR/NOT, PN mencionados, referencias, relevancia, borrador de preguntas | Crear reglas físicas no aprobadas o cifras de ficha |
| Policy engine determinista | Valida AST, cobertura de requisitos, necesidad de aclaración, permisos de consulta, versiones de plan | Adivinar torque, alimentación, certificados |
| LangChain agent | Escoger tool(s) en allowlist, recibir resultados con presupuesto acotado | SQL arbitrario, mutación de DB, lectura de staging o sesiones ajenas |
| Domain services | get/search, unidad, ranking, comparabilidad, notas, total vs paginación | Reinterpretar instrucciones del usuario sin confirmación |
| Response composer | `answer` con claims verificables y references; cards/tables/charts construidos de hechos | Renderizar prosa numérica no sustentada |
| Persistence/observability | Historial, estado, checkpoints, trazas cifradas; correlación; eliminación | Loggear secretos, cabeceras sensibles o PII sin protección |

## 3. Máquina de estados y contratos conceptuales

**Turno externo:** `ACCEPTED -> INTERPRETING -> INTERPRETED -> (NEEDS_CLARIFICATION | AWAITING_CONFIRMATION | EXECUTING) -> VERIFYING -> COMPLETED`, con `FAILED`, `CANCELLED`, `STALE_PLAN`, `SOURCE_WITHDRAWN` como finales/especiales. Una solicitud en `NEEDS_CLARIFICATION` no se reanuda hasta que llegue una respuesta del usuario; un plan en `AWAITING_CONFIRMATION` no ejecuta tools potencialmente costosas sin ratificación de la revisión correcta. Las transiciones ocurren sin mantener transacciones SQL abiertas mientras el LLM responde.

**Identificadores distintos:** `user_id`, `session_id`, `message_id`, `turn_id`/`run_id`, `plan_id`, `plan_revision`, `catalog_edition_id`, `thread_id`, `tool_call_id`, `trace_id`, `request_id/idempotency_key`. Ninguno debe reutilizarse silenciosamente como sustituto de autorización.

**Plan interpretado, datos mínimos conceptuales:**

| Campo | Semántica e invariantes |
|---|---|
| `intent` | EXACT_LOOKUP / FILTER_SEARCH / COMPARISON / RECOMMENDATION / DERIVED_CALCULATION / EXPLANATION / FOLLOWUP / OUT_OF_SCOPE |
| `filter_ast` | Nodos `AND`, `OR`, `NOT` (NOT con dominio acotado); predicados de campo allowlist, operadores, unidades y valores tipados; prohibido SQL raw |
| `referents` | PN exacto + lista ordenada de productos del contexto; resolución de pronombres con procedencia y ambigüedad |
| `criteria` | Grupo de requerimiento, `SPECIFIED`/`NO_PREFERENCE`/`UNKNOWN`/`DELEGATED`/`UNSPECIFIED`/`CONFLICTING`, tipo hard/preference, origen, prioridad |
| `data_status` | AVAILABLE / NOT_APPLICABLE / NOT_DOCUMENTED / NOT_LISTED / UNVERIFIED; distinto de estados del usuario |
| `catalog_edition_id` | Autoritativo desde sesión validada, nunca tomado de argumento del LLM |
| `plan_revision` | Monótono por sesión; aprobación aplica solo a esa revisión exacta; cambios invalidan aprobación |
| `presentation_intent` | Respuesta simple/lista/top-1/tabla 2–3/comparación dual/gráfico de barras comparable |
| `response_language` | Último turno salvo elección explícita, independiente del idioma del PN y unidades |

**Política de interpretación transparente:** devolver `interpretation_summary` visible con criterios aplicados, propuestos/delegados/ignorados y formato previsto; no revelar nombres de herramientas ni prompts internos. Al preguntar por un PN específico, si varias mediciones posibles son legibles, mostrar todas etiquetadas y evitar confirmación innecesaria. Si la consulta es búsqueda por un solo filtro, no exigir cobertura de recomendación.

**Confirmación y reanudación:** una confirmación autenticada, idempotente, compara `(session_id, plan_id, plan_revision, user_id)` contra el estado activo. Una corrección crea nueva revisión e invalida la anterior. La confirmación no debe llegar como una instrucción irrestricta al LLM; el backend valida y materializa el plan aprobado. Si una edición ha sido retirada, no ejecutar nuevas recomendaciones sobre ella.

## 4. AST y capacidades de consulta

**Campos filtrables:** PN exacto, enclosure, voltaje nominal, modo de corriente, fase documentada, servicio, torque según servicio, duty S4, ciclos/hora, arranques/hora, velocidad/FLA/LRA según frecuencia, potencia, notas/certificación explícita. Un mismo atributo puede ser filtro duro, preferencia o campo de respuesta. Rangos inclusivos/exclusivos y OR/AND agrupados. No convertir `NULL`/N/A en cero.

**Reglas:** comparar métricas solo bajo servicio, frecuencia, alimentación y unidad compatibles; la aplicabilidad de cada contexto es un predicado de dominio. Dato sin desglose por servicio (T03) no implica servicio On/Off ni Modulating. FLA bajo distintas tensiones no prueba mayor eficiencia. Si una métrica necesaria para ranking falta o no es comparable, no declarar ganador: separar opciones indeterminadas, solicitar aclaración o aplicar prioridades alternativas **solo tras aceptación**.

## 5. Contrato conceptual de tools (no Pydantic Spec)

**A — baseline:** única `query_parts` con operación GET/SEARCH y payload discriminado.

**B — candidata preferida:**

| Custom tool | Input model-visible | Input inyectado por servidor | Output tipado | Fallos semánticos |
|---|---|---|---|---|
| `get_part_details` | `part_number`, `service?`, `frequency?`, `requested_fields?` | edición autorizada, permisos, política de límites, `trace_id` | estado PART_FOUND / PART_NOT_LISTED; configuraciones, hechos etiquetados, notas, evidencia | INVALID_PN, PART_NOT_LISTED, N_A, SOURCE_WITHDRAWN |
| `search_parts` | `filter_ast`, `requested_fields?`, `sort_hint?` (no autoritativo), `page/cursor?` | edición, máximo por página, función de consulta parametrizada | `total_matches`, `matched_pns_page`, `next_cursor`, candidatos verificados/indeterminados, hechos y evidencia | INVALID_FILTER, NO_RESULTS, NOT_COMPARABLE, SOURCE_WITHDRAWN |
| `get_source_notes` **condicional** | PN o sección + tipo de nota | edición, autorización, bounds | notas literales con alcance/evidencia | NOT_DOCUMENTED |

`rank_candidates`, `compare_parts` y `convert_units` quedan en **servicios deterministas**, no necesariamente tools del LLM. La UX entrega todos los números de parte coincidentes mediante páginas sin afirmar que una página truncada sea la lista entera. El backend determina el ranking, no acepta `sort_hint` del LLM como prioridad no confirmada.

**Outputs internos de tools:** `source_edition`, `configuration_id`, `service_scope`, `frequency_state`, typed facts `fact_id`, valor original y unidad, `data_status`, `evidence_ref`, notas y cualquier derived fact con fórmula/operandos. No concatenar un dump SQL con instrucciones en la respuesta. Los resultados de tools se someten a la misma sanitización de contenido no confiable que cualquier documento externo.

**Decisión A/B:** B se adopta *si* obtiene una mejora material sobre A en exactitud de selección de herramienta/argumentos con coste proporcional; si paridad o degradación, A. La cantidad de tools por sí sola no demuestra capacidad superior. La elección concreta queda condicionada al benchmark de F5.

## 6. Verificación de toda salida visible

**Regla dominante:** los números que describen productos en `answer`, tarjetas, tablas y gráficas se construyen desde facts recuperados o derivados deterministas; la UI nunca extrae valores técnicos de cadenas generadas por el modelo.

1. Tool devuelve hechos con procedencia verificable, estado, unidad y contexto.
2. El agente puede devolver un **plan de contenido**/esquema de explicación e intenciones de afirmación, pero no valores de producto autoritativos.
3. Backend valida afirmaciones: `has_more_torque`, `is_faster`, `same_frequency`, `no_result`, etc. solo si hay una comprobación determinista y condiciones comparables. Una frase no numérica también puede ser falsa: la verificación no se limita a detectar dígitos.
4. El compositor inserta valores y PN únicamente desde facts/requests autorizadas mediante placeholders tipados, con unidades, valores originales e identificación de edición. Las cifras provenientes del usuario se etiquetan como **requisito declarado**, nunca como especificación del catálogo.
5. Si no existe evidencia, eliminar la afirmación o emitir `INSUFFICIENT_INFORMATION`/solicitar aclaración. Ninguna cadena LLM no revisada puede contener afirmaciones técnicas no sustentadas.
6. `answer` se renderiza a partir de fragmentos aprobados igual que `content_blocks`; las gráficas reciben series del backend, no de LLM.
7. En la app se muestran highlights solo cuando es válido definir mejor/peor; en corriente hay contexto obligatorio y los datos ausentes nunca se grafican como 0.

**Candidato de bloques (F3 definirá schema):** `text`, `interpretation`, `clarification`, `product_card`, `comparison_table`, `bar_comparison`, `warnings`, `source_reference`, `error`. Cada bloque técnico incluye `fact_refs` y condiciones; debug via otro endpoint con autorización `developer` del propietario, nunca dentro del chat final.

## 7. Persistencia, protección y coherencia

- **Cuatro ámbitos**: messages (contenido visible), domain state (criterios, referencias, revisión), graph checkpoint (estado interno, mensajes/herramientas potencialmente duplicados) y execution traces (tool calls). Separados lógicamente, correlacionados por `session_id`/`run_id`, cifrado de payload sensible antes de persistir y verificación del borrado.
- **Cola por sesión respaldada por PostgreSQL** según F0/F3: orden, idempotencia, resultados duraderos; dos sesiones independientes procesables concurrentemente. El graph loop no posee la cola ni decide orden de turnos.
- **Versiones:** una conversación fija `catalog_edition_id`; retirada grave prohíbe nuevas recomendaciones, conserva historial anterior como histórico hasta eliminación autorizada.
- **Checkpoint y claves:** `thread_id` opaco, no PII. Implementación LangGraph estándar `EncryptedSerializer.from_pycryptodome_aes()` usa AES-EAX por defecto, **no AES-GCM** (ver código fuente). Se exige integración parametrizada o `CipherProtocol` controlado con AES-256-GCM, autenticación de ciphertext y comportamiento fail-closed. Debe comprobarse que bytes cifrados, writes pendientes, metadata sensible y traces no queden en plaintext. Un modo de lectura legacy sin cifrar debe rechazarse para nuevos entornos.
- **Borrado:** cancela trabajos, invalida confirmaciones, impide escrituras tardías y purga mensajes, estado, checkpoints y traces activos. Separa datos retenidos en backups con política explícita y nunca promete borrado físico instantáneo.
- **Restricciones de datos:** usuario `developer` solo accede a debug de **sus propias** conversaciones. No exponer system prompts, tokens, credenciales, keys, Authorization ni headers en las trazas; conservar timings y argumentos/resultados seguros.

Fuentes de framework revisadas: https://reference.langchain.com/python/langchain/agents/factory/create_agent ; https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/langgraph/checkpoint/serde/encrypted.py ; https://github.com/langchain-ai/langgraph/blob/main/.github/THREAT_MODEL.md ; https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/README.md .

## 8. Orquestación y límites (default condicionado)

- Punto de partida: `create_agent` + middleware de llamadas y herramientas + structured output. **No** se da al LLM control sobre validación/confirmación/autorización; esas etapas son servicios/coordinadores externos. Si la reanudación y la gestión de interrupciones no resultan legibles/correctas con esta composición, usar `StateGraph` explícito, conservando un nodo LangChain que selecciona y ejecuta tools.
- No asumir soporte simultáneo de tool calling y structured output nativo en el proveedor real; comprobar endpoint exacto y, si es necesario, separar fase de interpretación estructurada y fase de invocación. `ToolStrategy` puede consumir un paso/model call adicional. Los resultados JSON válidos no son necesariamente técnicamente correctos.
- Límites configurables `max_model_calls_per_turn`, `max_tool_calls_per_turn`, `max_token_budget`, `max_walltime`, `max_cost_usd`, `max_result_rows`; topes iniciales conservadores y ajuste por evals, sin loops infinitos. Ningún retry sobre errores semánticos `NO_RESULTS`/`N_A`; reintentos limitados para red/modelo/DB cuando idempotentes, con backoff y presupuesto. Fail-closed para exceder límites.
- OpenRouter: registrar provider/model exactos y usos, routing `require_parameters=true` cuando se necesiten features, readiness check de saldo y comparación de capacidad. Provider fallback automático no debe cambiar inadvertidamente capacidades/requisitos de privacidad.

## 9. Selección empírica de modelos y tools sin gastar el presupuesto

**No se declara ganador de modelo ni tool antes de probarlo.** Candidatos iniciales en OpenRouter, sujetos a disponibilidad y precio del día:

| Candidato | Hipótesis, no resultado de eval | Fuente/cautela |
|---|---|---|
| `qwen/qwen3-235b-a22b-2507` | Multilingüe; coste relativamente bajo; tool/JSON reportados | Ver endpoint real y precios actuales en OpenRouter |
| `deepseek/deepseek-v3.2` | Alternativa agentic de bajo coste | La compatibilidad de tools depende del proveedor concreto |
| `openai/gpt-4.1-mini` | Referencia comparativa con herramientas y JSON | Coste potencialmente superior; tomar pricing actual del endpoint |

No incluir modelos retirados; la página de `google/gemini-2.5-flash-lite` indica discontinuación en octubre de 2026, así que no usarlo como dependencia del sistema entregado aunque aparezcan precios históricos en la web. Mantener `AGENT_MODEL`, `INTERPRETER_MODEL?`, `FALLBACK_MODEL?`, settings de endpoint/proveedor como env vars; **varios configurados no implican varias llamadas por turno**.

**Golden eval set:** mínimo 36 escenarios bilingües equilibrados, 8 familias: PN exactos, torques duales/condiciones 50–60, T03 N/A/no atribuido, 24V AC/DC, filtros booleanos y rangos, followups/correcciones, ranking/abstención, prompt injection/IDOR. Incluir escenarios long-tail adversariales y fallos de servidor/LLM separados. Expected outputs provienen del golden dataset validado en F1, no de otro LLM como juez de cifras.

**Proceso:**
1. Validación de schemas y SQL con fixtures/fakes, sin OpenRouter; tests de property-based del AST y comparabilidad.
2. Smoke tests live: 1–2 turnos por modelo y feature; verificar combinación exacta tool/JSON; descartar endpoints incompatibles.
3. Benchmark fijo con mismos prompts, datasets, parámetros y provider/model pinned; tool A vs B sobre submuestra representativa y rest ids comparables. Capturar toda falla por categoría.
4. Analizar **errores críticos** primero (números no verificados, autorización, filtro equivocado y selección incorrecta de servicio), después precisión/recall semánticos, tool selection, requests de aclaración, tokens, p50/p95 y coste. Preferir opción más simple si empatan.
5. Prueba de reserva: gasto real del key no superar USD 6 de desarrollo+evals; suspender benchmarks antes de consumir los USD 4 reservados. Verificar saldo vía API de OpenRouter o dashboard sin exponer key.

**Criterios de promoción:** CERO discrepancias numéricas en casos verificados; CERO accesos de autorización indebidos; 100 % de validación de parámetros en herramientas; sin cobertura de un escenario obligatorio, no promover. Para selección de modelo, máxima tasa de éxito **de casos críticos** domina una pequeña reducción de coste; entre candidatos comparables elegir menor coste total de conversación y menor latencia. Estos son criterios de evaluación, no resultados conseguidos.

Documentación consultada: https://openrouter.ai/qwen/qwen3-235b-a22b-2507 ; https://openrouter.ai/deepseek/deepseek-v3.2 ; https://openrouter.ai/openai/gpt-4.1-mini ; https://github.com/OpenRouterTeam/docs/blob/main/guides/features/structured-outputs.mdx ; https://github.com/OpenRouterTeam/docs/blob/main/api_reference/limits.mdx .

## 10. Fallos, seguridad y política de abstención

| Condición | Respuesta de negocio | Ejecución |
|---|---|---|
| PN inválido | Solicitar corrección, sin sugerir silenciosamente otro | No tool si formato inválido evidente |
| PN no listado | Indicar que no figura en PDF | Tool exacta con estado NOT_LISTED |
| PN listado con N/A | Indicar existencia documental y falta de prestaciones | No cero, no ranking verificable |
| Cero coincidencias | Informar restricciones sin coincidencia; permitir reajustar | No retry LLM como si fuera error técnico |
| Recomendación incompleta | Preliminares etiquetados + preguntas | No asegurar compatibilidad final |
| Filtro AND/OR ambiguo | Aclaración; no cambiar precedencia en silencio | Plan AWAITING_CONFIRMATION |
| Frecuencia/servicio sin evidencia | Mostrar alcance real o pedir aclaración | No extrapolar |
| Consulta ajena/out-of-scope | Abstenerse claramente, sin buscar fuera del PDF | No tool externa ni conocimiento libre |
| Fuente retirada | Alerta sobre edición retirada; historial intacto | Bloquear nueva recomendación |
| Tool DB unavailable | Error recuperable con correlation ID | Retry limitado si seguro |
| OpenRouter 402/cuota | Error claro sin inventar respuesta | No conmutar a proveedor no autorizado automáticamente |
| Prompt injection/role escalation | Ignorar instrucción maliciosa, aplicar RBAC real | No exponer sistema o debug de tercero |
| Confirmación stale | Informar que el plan cambió; mostrar versión actual | No ejecutar plan viejo |
| Borrado vs job tardío | Conversación no reaparece | Cancelado y write guard durable |

## 11. Matriz de trazabilidad por capacidad (resumen)

| Requisitos F0/F1 | F2 diseño | Verificación F5 |
|---|---|---|
| US-010 a US-013: lookup, filtros, confirmación | interpreter + AST + plan versionado + tools | query oracle, boolean AST, stale confirmation |
| US-014 a US-018: preliminares y ranking | policy gate + domain services | missing torque, priority override, no comparable |
| US-019 a US-021, US-034: comparación/visualización | answer/content blocks backed by facts | no numeric inventions in answer/chart/cards |
| US-022 a US-026: multi-turn, idiomas | four-state separation, edition pinned | restart, pronouns, ES/EN, source withdrawn |
| US-002/US-030: auth/debug | pre-admission, role/owner, safe trace | IDOR user-vs-developer, redaction |
| US-027–029: resiliencia | ordering per session, durable state, jobs | concurrency, replays, abort/delete |
| F1 ingest integrity + provenance | published-only tools and cell refs | original PDF 7/68 and evidence exact |
| US-032 + delivery | README/env/model rationale | clean build with Docker+emulator |

## 12. Gates de cierre y tareas que siguen pendientes de pruebas (no decisiones abiertas)

**Diseño F2 suficientemente cerrado** cuando:
- [x] Responsabilidades agentic/deterministas, lenguaje y autoridad de números.
- [x] Máquina de estados, confirmaciones, criterios y referencias multi-turno.
- [x] Tools candidatas y servicios de dominio, seguridad y errores.
- [x] Contrato conceptual de respuesta con `answer` + bloques y validación de claims.
- [x] Protección de historia, estado, checkpoints, trazas, claves y borrado.
- [x] Candidatos de modelos, plan de selección y presupuesto con gates claros.
- [x] Matriz requisito → componente → evaluación.

**Pendiente de implementación/evidencia (no inventar resultados):** exacta API de herramientas Pydantic, cumplimiento de LangChain con configuración elegida, A vs B sobre dataset, selección de modelo OpenRouter y precios del endpoint, integración AES-GCM de checkpoint, reanudación del grafo tras caída, cifrado y eliminación, performance y coste real.

**Handoff a F3:** diseñar API del plan/interrupción, jobs y polling, auth/registro, cifrado AES-GCM de mensajes/estado/checkpoints/trazas, permisos y borrado, estado HTTP, DTO de response y error, versionado y correlación. No pasar decisiones de seguridad al LLM.


---

## Addendum de evaluación por responsabilidad — v1.1, 2026-11-07

**Origen:** aprobación del usuario: probar **más de un modelo por función**, manteniendo máximo USD 6 de desarrollo/evals y al menos USD 4 para demo. No se proclama ganador sin pruebas, ni se obliga a llamar a modelos distintos en cada turno.

| Función LLM | Candidatos mínimos para probar en OpenRouter | Oráculo y failure modes | Decisión posterior |
|---|---|---|---|
| Interpretación ES/EN, criterios y AST | `qwen/qwen3-235b-a22b-2507`; `openai/gpt-4.1-mini`; comparador opcional `deepseek/deepseek-v3.2` | Exactitud de PN, AND/OR/NOT, campos, unidades, referencias, JSON válido; falsos supuestos físicos | Máxima tasa correcta en casos críticos → coste/latencia |
| Selección de herramientas y argumentos | `deepseek/deepseek-v3.2`; `qwen/qwen3-235b-a22b-2507`; comparador opcional `openai/gpt-4.1-mini` | Tool correcta, parámetros tipados, ningún acceso a staging/SQL, cero inventos, límites | Herramientas especializadas B vs general A, mismo dataset y provider/model |
| Explicación ES/EN y aclaraciones | `openai/gpt-4.1-mini`; `qwen/qwen3-235b-a22b-2507`; opcional DeepSeek | Corrección semántica de claims, abstención, idioma, legibilidad, no números libres | Si una plantilla determinista basta, 0 llamadas LLM adicionales |
| Títulos y datos numéricos/ranking | **Sin LLM por defecto** | Titulado heurístico seguro, Decimal y fuente | No gastar tokens para funciones deterministas |

**Evaluación controlada:** primero fixtures/prompt + test de schemas (sin coste), smoke de 2–3 casos por función/modelo en provider concreto, después evaluación pareada de un subconjunto pequeño de los 36 escenarios; ampliar solo candidatos competitivos y gastar como máximo los USD 6 totales, nunca una cuota de USD 6 por función. Registrar modelo, provider, precios observados, herramientas y structured output aceptados; no confundir soporte del modelo con soporte de todos los endpoints. El costo de una conversación completa decide si especializar modelos ahorra realmente dinero.

**Costes externos de referencia, variables y no presupuesto fijado:** páginas de OpenRouter verificadas para Qwen, DeepSeek y GPT-4.1 mini el 2026-11-07. Revalidar precios antes de ejecutar la batería. En ningún caso el modelo cambia el oráculo numérico del PDF.

**Anexo F3:** `F3_backend_api_security_design_v0.1.md` define protocolos/transportes y tres documentos cifrados; no cambia la decisión B de tools preferidas hasta evidencia.
