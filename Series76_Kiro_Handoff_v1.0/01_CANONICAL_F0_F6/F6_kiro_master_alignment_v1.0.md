# Series 76 — F6: Dossier maestro de alineación para Kiro v1.0

**Estado:** COMPLETO COMO PAQUETE DE TRANSFERENCIA PARA REVISIÓN DEL USUARIO; **NO** autoriza ejecutar Specs ni implementar código por sí mismo. Fecha: 2026-11-07. Las fases **F0–F5 se encuentran cerradas como decisiones de diseño**, no como software construido o probado.

## 1. Respuesta operativa: ¿son siete documentos?

**Sí: siete documentos canónicos de diseño, uno por fase F0…F6.** Sin embargo, no deberían entregarse *aislados*: Kiro necesita también los **tres PDFs originales** para comprobar requisitos y datos, y opcionalmente las notas y el histórico para defender decisiones. Este paquete contiene ambos conjuntos.

| Fase | Contrato canónico y estado | Responsabilidad |
|---|---|---|
| F0 | `F0_requirements_and_quality_catalog_v1.0.md` — cerrado | 35 historias activas, 15 QA, alcance, casos y criterios |
| F1 | `F1_data_architecture_handoff_v1.1.md` — cerrado | modelo, ETL, evidencia, publicación, contratos de operaciones |
| F2 | `F2_agent_architecture_handoff_v1.1.md` — cerrado | LangChain, tools, confirmación, resultados verificables, memoria y modelo/evals |
| F3 | `F3_architecture_handoff_v1.0.md` — cerrado | API FastAPI, tokens opacos, jobs, PostgreSQL, patrones y seguridad |
| F4 | `F4_android_ux_handoff_v1.1.md` — cerrado | Kotlin Compose, cinco destinos (tres evaluados + login/registro), UI, caché, offline explícito |
| F5 | `F5_quality_testing_delivery_handoff_v1.1.md` — plan cerrado | matriz de verificación, costes, calidad, e2e y README reproducible |
| F6 | `F6_kiro_master_alignment_v1.0.md` — dossier completo | autoridad, integración, auditoría y protocolo de transferencia |

**No sustituir los originales:**
- `assessment-en.pdf`: requerimientos externos de Konecto, fuente de autoridad para la evaluación.
- `series_76_electric_data.pdf`: **única fuente permitida de números técnicos del catálogo**, páginas 1–4 en siete tablas; auditar contra la fuente.
- `series_76_summary.pdf`: contexto de negocio, no sustituye los valores eléctricos.
- `Series 76 First Toughts.md`: ideas iniciales; históricas, algunas expresamente descartadas; **no son requisitos vinculantes**.

## 2. Precedencia de lectura y resolución de conflictos

1. Assessment original, para obligaciones del evaluador.
2. PDF eléctrico original, **exclusivamente para verdad numérica y condiciones técnicas**; summary solo para contexto narrativo.
3. Decisiones **explícitamente aprobadas** del usuario y adendas canónicas más recientes: F0 v1.0; F1 v1.1; F2 v1.1; F3 v1.0; F4 v1.1; F5 v1.1; F6 v1.0.
4. Archivos de soporte (historial ADR, esquema físico candidato) para explicación y detalle, **sin sustituir decisiones canónicas**.
5. Notas iniciales como ideas no vinculantes.

Si un documento histórico contiene `OPEN`, `CANDIDATE`, `PENDIENTE` o una opción distinta de la decisión aprobada en una adenda posterior, **la última decisión aprobada y el contrato canónico prevalecen**. Si hay contradicción real con la evaluación, Kiro debe detener únicamente el punto afectado, comparar alternativas y solicitar aprobación cuando implique cambiar una garantía esencial. Nunca resolver una contradicción inventando datos o reduciendo en silencio exactitud, seguridad o alcance aprobado.

## 3. Compromisos funcionales, técnicos y de seguridad no negociables

- Backend FastAPI Python; base de datos PostgreSQL local mediante Docker Compose; agente orquestado con **LangChain** y **al menos una herramienta custom** que consulta datos tabulares.
- Script ETL que procesa `series_76_electric_data.pdf`; además, modo `verified_replay` reproducible sin `GEMINI_API_KEY`; `fresh_extraction` usa OCR local + Gemini AI Studio con clave propia y conciliación. Primera edición con **100% de validación manual** contra PDF; no presentar coincidencia OCR/Gemini como prueba absoluta.
- `POST /api/conversation`: petición con `session_id` opcional y `query`; respuesta final conserva **`session_id` y `answer`**; persistencia multi-turn tras reinicio. API de trabajos asíncronos separada, sin romper el contrato obligatorio.
- Android nativo **Kotlin Jetpack Compose**: Conversations, Chat y Developer Debug como tres pantallas distinguibles; Login/Registro adicionales aprobadas. Developer Debug visible únicamente a cuenta developer y solo trazas **propias**, siempre comprobado por backend.
- Datos técnicos: el PDF eléctrico gobierna cualquier cifra; unidades originales, torque por servicio cuando documentado, medidas por 50/60 Hz cuando aplica, modalidad AC/DC, nota de CSA y alcance de celdas fusionadas. Cuatro N/A de T03 conservadas como N/A; datos ausentes no son cero.
- No RAG ni pgvector para esta edición: **SQL tipado determinista**; el LLM interpreta y orquesta herramientas controladas. Alternativa B: tools especializadas como candidata inicial, comparar con alternativa A genérica en evaluaciones iguales; no declarar ganadora antes del experimento. Ranking lexicográfico y cálculos hechos por servicios deterministas. `answer` y bloques estructurados basados en las **mismas cifras y comparaciones verificadas**.
- Plan interpretado visible; confirmación condicional; cuatro grupos necesarios para recomendación verificada (entorno, alimentación, servicio, torque); preliminar ≠ compatible verificado. Versión de plan anti-replay y edición de catálogo fijada por conversación; ediciones retiradas no emiten nuevas recomendaciones.
- Búsqueda de conversaciones **solo por títulos**; crear/renombrar/eliminar; eliminación con jobs pendientes sin resurrección. Cifrar títulos, mensajes, estados/checkpoints sensibles y trazas por **AES-256-GCM en aplicación**, con claves fuera de DB, DEK/KEK y pruebas de fail-closed. TLS en despliegue; cifrado de volúmenes/backups como control de infraestructura productiva, no falsa promesa del Docker Compose del evaluador.
- Autenticación aprobada: **Bearer opaco** con refresh rotativo, hashes en servidor, Argon2id en contraseñas, separación de roles y ownership. Registro público solo `user`; developer provisionado por procedimiento administrativo; semilla de demo local repetible.
- Trabajos duraderos en PostgreSQL: un turno activo por conversación, jobs idempotentes, leases y fencing; distinción entre idempotencia del sistema y llamadas externas facturables. Cifrado aplicado también a cualquier estado persistido del agente. Sin SQL generado libremente por el LLM.
- Android: Feature-First + MVVM/UDF, Room para caché de lectura, protección local mediante Keystore, navegación tipada y polling seguro; comparación detallada dual, hasta tres fichas, nombres de todos los PN elegibles salvo top-1, barras solo para métricas comparables.
- **OFFLINE (adenda 2026-11-07):** aviso evidente en Conversations y Chat: «Sin conexión. Puedes consultar conversaciones guardadas, pero no podrás enviar mensajes hasta recuperar la conexión»; **Enviar inhabilitado**, borrador conservado, sin envío ni encolado automático al reconectar; recuperar jobs pendientes mediante identificadores y no confundir ausencia de Internet con HTTP 503.
- Modelos OpenRouter configurables por variables; al menos **dos candidatos por responsabilidad** (interpretación, tool-calling, explicación). Validar disponibilidad/tool support/cost antes de pruebas. Límite **USD 10** total, no gastar más de USD 6 en desarrollo/evals, reservar al menos USD 4 para demostración. Gemini solo para extracción opcional; modelos del agente por OpenRouter.
- Un único repositorio GitHub con backend, worker, Android, ingesta, Dockerfile, Compose, `.env.example`, migraciones, seeds, datos procesados o reproducción, README completo y directorio real de configuración del asistente usado (p.ej. `.kiro/`). Voz postergada; no MCP/RAG/postcuántica/microservicios por defecto.

## 4. Organización aprobada y patrones con alternativas rechazadas

- **Backend:** monolito modular FastAPI, Feature-First + hexagonal ligera (puertos/adaptadores en fronteras con valor: almacenamiento, LLM, criptografía, cola y reloj). **Comparado con:** capas tradicionales más acopladas, Clean/Hexagonal completa más ceremonial y microservicios más costosos. API y worker son procesos distintos del mismo sistema y código.
- **Persistencia:** Repository + Unit of Work/transactions controladas por caso de uso + DTOs Pydantic; no DAO adicional redundante; ORM/SQLAlchemy solo en infraestructura, casos de uso sin commits dispersos.
- **ETL:** Pipe-and-Filter, staging separado de catálogo publicado, evidencia por celda, publicación atómica, revisión humana inicial exhaustiva; autopublicación futura únicamente tras calibración independiente y ausencia de anomalías.
- **Agente/jobs:** máquina de estados explícita, comandos idempotentes, adapters y Strategy solo en puntos variables. No Event Sourcing, CQRS completo, buses de eventos, Factory universal o interfaces por clase.
- **Android:** Feature-First MVVM + UDF / StateFlow, Retrofit + OkHttp, Room y caché protegido; un módulo Gradle inicial, no multimódulo prematuro. Offline explícito y seguro.

## 5. Matriz transversal de aceptación y fuente

| Prioridad | Obligación | Fuente | Evidencia que Kiro debe generar |
|---|---|---|---|
| P0 | Endpoint obligatorio + contexto persistente | Assessment/F0/F3 | Tests sync `session_id` opcional, `answer`, restart y seguimiento |
| P0 | No inventar números ni asociaciones | PDF/F1/F2 | Golden fuente, 7 tablas, 68 filas, 4 N/A iniciales, notas y 100% auditoría manual |
| P0 | LangChain + herramienta custom | Assessment/F2 | Tool invocada, trazas sanitizadas Debug y resultados tabulares |
| P0 | Tres pantallas Android + Debug protegido | Assessment/F4 | Demostración/emulador y tests role+owner; sin internals en chat |
| P0 | PostgreSQL + Docker + ingesta desde PDF | Assessment/F1/F3 | Cold start, migraciones, verified replay y fresh extraction documentada |
| P0 | Reproducibilidad repo y README | Assessment/F5 | Instalación limpia paso a paso + directorio real de configuración de Kiro |
| P0 elegido | Registro/login/roles/aislamiento | F0/F3 | Registro user only, login/logout/revoke y cross-user deny |
| P0 elegido | AES-256-GCM app + control de claves | F2/F3 | DB dump sin plaintext, tampering fail-closed, checkpointer cifrado |
| P0 elegido | Jobs/idempotencia/confirmaciones | F2/F3/F4 | restart/lease, stale plan, delete race, no duplicate output |
| P0 elegido | Offline UX claro | F4 v1.1/F5 v1.1 | Banner en ambas pantallas, envío bloqueado, borrador sin autoenvío, tests 503 vs no red |
| P0 elegido | Evaluación de modelos y presupuesto | F2/F5 | ≥2 candidatos por función, resultados y gasto medido ≤USD 6 de desarrollo |

**Referencia histórica, no resultado comprobado:** inventario manual de 7 tablas, 68 filas y 4 filas N/A. Kiro debe extraer y auditar los valores desde el PDF oficial y rechazar cualquier discrepancia crítica.

## 6. Riesgos de alta prioridad y mitigación

1. PDF rasterizado, celdas fusionadas, notas y métricas ambiguas: OCR+visión reconciliados, evidencia por campo y revisión manual inicial total; nunca forward-fill indiscriminado.
2. `answer` del LLM mezcla cifras/claims falsos: composición híbrida y comprobación determinista de comparaciones, ranking, unidades, claims y contenido de tablas/gráficos.
3. Cifrado persistente insuficiente: una implementación de LangGraph puede usar otro modo por defecto; **mantener AES-256-GCM** y probar también pending writes / checkpoints; no confiar en que cifrado de volumen implique cifrado por campo.
4. Job cancelado o conversación borrada durante upstream call: tombstones/fencing, transacciones cortas, no resurrection, sin duplicados lógicos.
5. Seguridad: IDOR, refresh replay, developer indebido, secretos en prompts y logs, recuperación indebida de caché; pruebas adversariales específicas.
6. Latencia y coste: canary reducido de modelos por función, sin gastar la reserva final; timeouts y error explícito cuando proveedor no disponible.
7. Reproducibilidad: no exigir Gemini para `verified_replay`, fijar versiones/entorno y probar arranque desde clon limpio.
8. Sobrediseño frente a tiempo: implementar mandatory funcional + compromisos aprobados, y recortar solo extras no comprometidos; no cambiar garantías esenciales sin consulta.

## 7. Estado de fases y límites del cierre

| Fase | Diseño | Implementación/verificación |
|---|---|---|
| F0 | Cerrado | Historias/QA pendientes de ejecución |
| F1 | Cerrado | ETL, auditoría numérica, DDL/migraciones, benchmark pendientes |
| F2 | Cerrado | Evals tools/modelos, checkpointer/claims verificados pendientes |
| F3 | Cerrado | Backend/auth/jobs/cifrado y tests pendientes |
| F4 | Cerrado, adenda offline incluida | Android, UX y pruebas instrumentadas pendientes |
| F5 | Plan cerrado, adenda offline incluida | Todas las pruebas/evidencias pendientes |
| F6 | Dossier consolidado | Requiere autorización explícita para generar Specs e implementar |

## 8. Protocolo de transferencia a Kiro (después de la luz verde)

1. Cargar todos los documentos canónicos F0–F6 y los PDFs originales. Leer `00_START_HERE/README_HANDOFF.md` y usar `KIRO_START_PROMPT.md` como contexto de arranque, **solo cuando el usuario autorice la fase de Kiro**.
2. Generar las propias **Specs de Kiro** (requirements, design, tasks) y mapa por historias/QA, separadas de estos documentos de alineación, conservando diferencias entre obligaciones externas, decisiones del usuario y candidatos técnicos.
3. Implementar en slices verticales a partir de dependencias y gates: entorno/migraciones/ingesta, dominio+tools, API/contexto y auth, respuesta verificable, cola/debug/crypto, Android UI/cache, e2e y README. Probar progresivamente, no posponer pruebas críticas.
4. Registrar evidencia verificable de tests con comandos, fecha/commit, entorno, resultados, logs saneados y coste real. No tratar 68 filas manuales como golden dataset ejecutado ni afirmar cobertura universal por ejecutar 36 prompts.
5. Cuando haya incompatibilidad técnica real, informar alternativas comparadas, impacto y justificación. Pedir aprobación si requiere modificar seguridad, fuente de verdad, requisitos, UX aprobada o contratos del assessment. No simplificar silenciosamente para compilar.
6. Preparar repo único, `.kiro/` real, README reproducible, seeds locales e instrucciones Android/emulador y Dev Debug. Evitar subir secretos reales.

## 9. Resultado de auditoría F6 — 2026-11-07

**Comprobado documentalmente:** todos los 7 dossiers base existen; fuentes originales presentes; F0 histórico contiene cierre definitivo, pero también estados preliminares antiguos, por lo que se añadió **cubierta canónica F0 v1.0**; F4 no expresaba como requisito suficientemente explícito el aviso + envío inhabilitado, por lo que se incorporó **F4 v1.1**; F5 recibió **F5 v1.1** con pruebas nuevas. La integridad de archivos se comprobará mediante SHA-256 en el paquete.

**Sin validar empíricamente:** exactitud de los 68 PN/medidas, capacidad real de OCR y Gemini, soporte tool/JSON de modelos, rendimiento, seguridad de implementaciones, cifrado Android/Room, backend ni build. No afirmar que hubo validación de sistema o benchmarks.

**Puntos que Kiro puede concretar sin cambiar decisiones:** SQL DDL y Alembic, DTO/JSON exactos, APIs de polling detalladas, codecs AES-GCM, tests CI, navegación concreta Compose, tipos Kotlin, elección final de provider/model según evidencia y disponibilidad. **No reabrir** decisiones aprobadas por comodidad técnica.

## 10. Gate de transferencia

- [x] Siete dossiers canónicos F0–F6, con versiones vigentes identificadas.
- [x] Tres PDFs originales y notas iniciales disponibles para cotejo.
- [x] Precedencia, decisiones técnicas, trade-offs y requisitos integrados en el dossier.
- [x] Adenda offline aprobada F4 y casos adicionales F5.
- [x] Matriz de transferencia y responsabilidades Kiro establecidas sin generar Specs.
- [ ] **Aprobación explícita del usuario para comenzar generación de Specs/implementación.** No se infiere de un «continuemos» durante la fase de planificación.

**Estado:** LISTO PARA REVISIÓN Y ENTREGA; requiere autorización de ejecución de Kiro.
