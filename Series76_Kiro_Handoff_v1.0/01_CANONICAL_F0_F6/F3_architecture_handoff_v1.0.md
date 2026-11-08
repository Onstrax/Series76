# Series 76 — F3 Architecture & Backend Handoff v1.0

**Estado:** CERRADA COMO ALINEACIÓN DE DISEÑO. Implementación y verificación pendientes de Kiro/F5.
**Fecha de consolidación:** 2026-11-07.
**Naturaleza:** dossier de decisiones aprobado, NO Specs finales de Kiro, NO código ni OpenAPI ejecutable.
**Base:** F3 Backend v0.2; F3 Architectural Styles, Patterns & Tactics v0.1; F2 Agent Handoff v1.1; F1 Data Handoff v1.1; F0 requirements v0.3.

## Acta de ratificación F3-ARCH-01

**El usuario aprueba la opción A:** backend Python FastAPI **monolito modular, Feature-First + Ports & Adapters / hexagonal ligera**. API y worker como procesos de despliegue separados pero misma base de código y dominio. Adoptar capas API/DTO, aplicación/casos de uso, dominio puro e infraestructura, organizadas por feature; adaptar interfaces solo en fronteras que cambian o deben simularse (datos, LLM, criptografía, cola, reloj). No hexagonal ceremonial.

**Alternativas revisadas:** (B) layered tradicional con mayor acoplamiento de dominio a infraestructura; (C) Clean/Hexagonal completa con demasiada abstracción; microservicios con sobrecoste operacional. Se conserva la opción A por testabilidad de reglas eléctricas, velocidad de entrega y evolución.

**Patrones RATIFICADOS:** Repository, DTO (diferente de modelo de dominio/ORM), Unit of Work de SQLAlchemy bajo control del caso de uso, Dependency Injection ligera, Adapter, Strategy selectiva, State Machine y Command/Idempotency. **No** DAO redundante, Event Sourcing, CQRS completo, Factory generalizada ni event bus sin necesidad.

**Estilos por subsistema:** ETL Pipe-and-Filter; agente y jobs máquinas de estados; Android Feature-First + MVVM + UDF. Cifrado defensa en profundidad: AES-256-GCM aplicación obligatorio, TLS conexiones producción, cifrado de volúmenes/backups como prerrequisito de despliegue (el compose local no lo garantiza).

**Registro de trade-offs:** ver `F3_architectural_styles_patterns_tactics_v0.1.md` y `F3_backend_api_security_design_v0.2.md`. Todas las decisiones F3-D01/02 aprobadas explícitamente; defaults técnicos demás ratificados por el usuario. Los detalles de implementación se derivan de invariantes sin alterar el producto.

## Contrato F3 consolidado (conceptual, para Specs de Kiro)

| Superficie | Operaciones y semántica aprobadas | Requisitos de seguridad / rechazo |
|---|---|---|
| Registro y login | `POST /api/auth/register`, `/login`, `/refresh`, `/logout`, `GET /api/auth/me` | Registro `user` forzado server-side, jamás `developer`; Argon2id; opaque access+refresh, hash de verificadores, revocación y rotación |
| Conversaciones | `GET /api/sessions` con filtro por título, `GET /api/sessions/{id}/messages`, `PATCH /api/sessions/{id}`, `DELETE /api/sessions/{id}` | Siempre owner; títulos descifrados solo tras autorización; borrado incluye mensajes/estado/jobs/trazas/checkpoints activos |
| Evaluación obligatoria | `POST /api/conversation` | Request mínimo `session_id?`, `query`; respuesta incluye siempre `session_id`, `answer` cuando completa o pide aclaración/confirmación |
| Trabajos asíncronos | `POST /api/conversation/jobs` → aceptación `202` con `session_id`, `job_id`, `status`; `GET /api/jobs/{id}` → estado/resultado; cancelación autorizada | `client_request_id` para idempotencia; política de reintentos y guardas contra duplicados, owner de cada job |
| Plan interpretado | Confirmar revisión del plan de la conversación | `plan_revision` condicional; 409 si obsoleto; no ejecutar criterios viejos |
| Debug | `GET /api/sessions/{id}/messages/{message_id}/trace` y listados propios | Rol `developer` Y owner; sin credenciales, cabeceras secretas ni texto de otras conversaciones |
| Operación | `/api/health`, `/api/ready`, docs de desarrollo si están habilitadas | No revelar stack trace ni secretos; readiness distingue DB/dependencias críticas |

**Contratos de respuesta:** `answer` es siempre texto user-safe (ningún número técnico sin respaldo), además de `content_blocks[]` tipados, `interpretation` visible, `plan/status` si hace falta, `source_context` verificable, advertencias y request/trace IDs no sensibles. No se expone JSON de tool calls al chat usuario. Cualquier tipo de bloque desconocido se muestra con fallback de texto seguro sin parsear números del `answer`.

**Estados job:** `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, `CANCELLED`, `STALE_PLAN`, `CATALOG_WITHDRAWN`; distinción entre estado de job y de conversación/plan. Fijar transición válida en Kiro. Entrada y resultado persistentes bajo un contrato versionado.

**Reglas de concurrencia:** un trabajo activo por conversación; distintas conversaciones paralelas; transacciones cortas y leases/fencing; no transacciones SQL durante llamadas a OpenRouter; idempotencia de efectos DB no implica exactly-once billing. Al eliminar sesión, ningún worker antiguo puede resucitarla. Logout revoca tokens aunque haya solicitudes en curso; owner siempre verificado al confirmar resultados.

**Cifrado:** AES-256-GCM con nonce único/AAD contextual y DEK por conversación protegida por KEK fuera de DB. Cifrar contenidos de mensajes, títulos, planes, herramientas sensibles, trazas y checkpoints, incluidos writes/blobs auxiliares. Fallar cerrado ante plaintext legado o autenticación GCM inválida. No registrar tokens/headers/contraseñas ni en trazas cifradas. El dato técnico público y los índices estructurales mínimos pueden permanecer sin cifrar. Android cifra su propio cache por separado en F4. Backups contienen retención limitada explícita y no se promete borrado físico instantáneo.

## Matriz de aceptación F3 (verificable por Kiro)

| ID | Prueba requerida | Evidencia esperada |
|---|---|---|
| F3-AT01 | Login/refresh/logout con revocación inmediata | Token anterior rechazada después del logout y tras refresh reuse |
| F3-AT02 | Registro intenta enviar `role=developer` | Servidor rechaza/ignora atributo y asigna exclusivamente `user` |
| F3-AT03 | Developer conoce sesión de otro usuario | Endpoint Debug devuelve denegación indistinguible de recurso inexistente |
| F3-AT04 | POST obligatorio con y sin session_id | Devuelve session_id y answer, persiste multi-turn/restart |
| F3-AT05 | Jobs: dos turnos concurrentes misma sesión | Orden por sesión y contexto correcto; sesiones distintas pueden solaparse |
| F3-AT06 | Misma idempotency key repetida | Un solo efecto persistido, respuesta reproducible |
| F3-AT07 | Worker se interrumpe antes de finalizar | Lease expira, recuperación/cancelación consistente, sin escribir resultado obsoleto |
| F3-AT08 | DELETE durante llamada LLM | No reaparecen mensajes, checkpoint ni traces |
| F3-AT09 | Dump de DB/redis no aplica | Sin plaintext sensible en columnas, checkpoints, writes ni traces; lectura fallida ante ciphertext manipulado |
| F3-AT10 | Android consulta session list de otro token | Ninguna referencia a conversación ajena, ni en caché de dispositivo |
| F3-AT11 | Falla catálogo/no hay datos | No se inventan cifras; error claro o respuesta de fuente ausente |
| F3-AT12 | `docker compose` limpio con env de ejemplo | Ejecuta DB, API y worker, migraciones, seeds y health checks documentados |

**Fuera de alcance de prueba ya realizada:** no hay migraciones ejecutadas, servidor levantado, tests corridos ni cifras de latencia medidas. Estos son contratos a verificar, no resultados.

## Revisión del gate de salida de F3

- [x] Obligaciones de FastAPI, REST y Docker identificadas.
- [x] Estrategias de auth, sesiones, RBAC/owner, registro y revocación definidas.
- [x] Compatibilidad del endpoint obligatorio más jobs async definida.
- [x] Modelo conceptual de persistencia, leases/fencing, borrado y errores definido.
- [x] Cifrado aplicación + infraestructura y limitaciones documentados.
- [x] Estilos, patrones y tácticas ratificados con alternativas y rationale.
- [x] Matriz de aceptación y obligaciones para Kiro definidas.
- [ ] Implementación, E2E, test en dispositivo, pruebas de cifrado y seguridad (F5/Kiro).

**Conclusión:** F3 cerrada como alineación de diseño sin afirmar implementación ni validación empírica.

---

## ANEXO — DOCUMENTOS ORIGINALES



### Anexo A: F3 Backend y Seguridad v0.2

# Series 76 — F3: Backend, contratos REST, persistencia y seguridad — v0.2

**Naturaleza:** documento de alineación para Kiro; NO es una Spec de Kiro, implementación, OpenAPI definitivo ni aprobación de código.
**Estado:** F3 en curso, 2026-11-07. F3-D01 (tokens opacos) y F3-D02 (endpoint sync + jobs async) **APROBADAS EXPLÍCITAMENTE**; restantes defaults derivados de F0–F2, y F3-ARCH-01 pendiente de ratificación.
**Fuentes de requisitos:** `assessment-en.pdf` (especialmente backend API y Part B); `F0_requirements_and_quality_catalog_v0.3.md`; `F1_data_architecture_handoff_v1.1.md`; `F2_agent_architecture_handoff_v1.0.md`.
**Regla de cambio:** ninguna elección de este documento invalida una aprobación previa; los cambios necesitan ADR con alternativa, razones, impacto y conformidad del usuario cuando sean significativos.

## 1. Restricciones vinculantes de entrada

- FastAPI + PostgreSQL local en Docker Compose, al menos una custom LangChain Tool de consulta tabular; la app es Android nativo Kotlin/Jetpack Compose.
- `POST /api/conversation`: request `session_id?` y `query`; respuesta final compatible `{session_id, answer, ...}`. Una aclaración o confirmación pendiente también se expresa mediante un `answer` conversacional válido, no implica valores inventados.
- Auth y registro desde Android. Registro **únicamente** rol `user`; rol `developer` solo aprovisionamiento administrativo/seed controlado. Developer ve SOLO las trazas de SUS conversaciones.
- Conversaciones persistentes con listado, búsqueda **por título solamente**, renombrar, continuar, eliminar; datos y trazas detalladas purgados del almacenamiento activo al borrar.
- Interpretación visible siempre, confirmación condicional y `plan_revision`; catálogo fijado por conversación, retirada del catálogo impide recomendaciones nuevas.
- Queue duradera en PostgreSQL, orden por sesión, ingreso asíncrono adicional y no bloquear Android; request síncrono exigido por assessment intacto.
- Datos numéricos de `answer`, bloques técnicos y gráficos exclusivamente verificados o calculados de forma determinista. Nunca SQL generado sin validación ni acceso a staging.
- AES-256-GCM para contenido sensible persistido; TLS para transporte; Argon2id para contraseñas; SHA-256 de artefactos de ingesta (no hashes de contraseñas); trazas saneadas.
- Presupuesto OpenRouter USD 10 total: ≤6 evaluación/desarrollo; ≥4 reservado para demo. Gemini AI Studio se usa en ETL, con clave configurable, no para sustituir runtime del agente OpenRouter.

## 2. Comparativas arquitectónicas y decisiones

| Ref | Alternativas comparadas | Recomendación / decisión | Por qué y coste asumido | Estado |
|---|---|---|---|---|
| F3-D01 Autenticación | A: access JWT firmado + refresh opaco/denylist; B: access y refresh opacos con verificadores hashed en PostgreSQL | **B** | Revocación inmediata en servidor, owner/rol centralizados; consulta DB por request aceptable; menos duplicación de revocación que JWT + denylist | **APROBADA POR EL USUARIO 2026-11-07** |
| F3-D02 API de trabajos | A: solo POST síncrono; B: POST obligatorio síncrono + endpoint adicional asíncrono/polling | **B** | Mantiene contrato Konecto y permite estados/cola durables; añade endpoints y tests | **APROBADA POR EL USUARIO 2026-11-07** |
| F3-D03 Backend modular | A: microservicios; B: monolito modular con worker separado y DB compartida | **B** | Menos despliegue, límites internos claros; extraer servicio en futuro si escala | Default técnico |
| F3-D04 DB access | A: una conexión de DB privilegiada; B: roles por servicio (`runtime_catalog_reader`, `app_writer`, `ingest_publisher`) | **B** | Least privilege y evita lecturas de staging; migraciones y grants más elaborados | Default técnico |
| F3-D05 Persistencia en API | A: `BackgroundTasks` de FastAPI / memoria; B: tabla duradera de jobs + proceso worker independiente | **B** | Sobrevive reinicios y permite ownership/leases; requiere coordinación | Derivado de F0; default |
| F3-D06 Orden de jobs | A: lock largo sobre sesión; B: orden transaccional + solo un job activo por sesión + lease/fencing | **B** | Sin transacción SQL durante llamada de LLM; evita carrera de dos workers | Default técnico |
| F3-D07 Cifrado | A: cifrado DB transparente solamente; B: AES-256-GCM en aplicación, claves fuera de DB, AAD contextual | **B** | Protege ante copia DB aislada, también checkpoints y trazas; limita búsqueda y complica claves | Aprobado previamente; diseño de detalle derivado |
| F3-D08 Manejo claves | A: única clave global cifrando filas; B: DEK por conversación envuelta por KEK externa a DB | **B** | Aislamiento y crypto-shredding activo más sencillo; overhead y rotación controlada | Default sujeto a viabilidad de implementación |
| F3-D09 Repo y migraciones | A: SQL ad hoc; B: repositorios tipados + transacciones en servicios + migraciones versionadas | **B** | Mantenibilidad y consistencia; código adicional justificado | Default técnico |
| F3-D10 API responses | A: texto libre exclusivamente; B: envelopes tipados `answer` + bloques y status/error | **B** | Android sin parsing de números ni herramientas; obligación contractual | Ya aprobado |
| F3-D11 Transporte móvil | A: permitir HTTP siempre; B: HTTPS obligatorio fuera de debug; excepción local de emulador estrecha y documentada | **B** | Tráfico seguro en producción; preparación de entorno demo extra | Default técnico |
| F3-D12 Auditoría de borrado | A: retener full trace; B: eliminar trazas detalladas, retener a lo sumo evento mínimo sin contenido | **B** | Política de privacidad previamente aprobada; menos auditoría retrospectiva | Aprobado previamente |

### 2.1. Notas decisivas sobre F3-D01

**Opción B recomendada:** access token opaco con vida corta; refresh token opaco aleatorio y rotativo; verificador irreversible en servidor (identificador público + hash SHA-256 de secreto de alta entropía, comparación en tiempo constante). **No** aplicar SHA-256 directo a contraseñas: Argon2id. No almacenar access/refresh en plaintext en la DB ni registrar tokens en logs. Auth header `Authorization: Bearer <token>`; SQL valida expiración, revocación, propietario y rol. Logout invalida en el servidor la familia de refresh y los access tokens asociados a esa sesión de login, sin cerrar sesiones de otros dispositivos salvo que usuario lo solicite explícitamente. Rotación refresh atómica, detectar reuse -> revocar familia y solicitar login. Usar entropía CSPRNG ≥128 bits (preferentemente 256). La forma binaria/hex/base64url es un detalle de la Spec.

**Opción A alternativa:** JWT access (5–15 min) + refresh hash/rotación. Para revocación inmediata necesitaría token denylist, chequeo de sesión server-side o versioning, diluyendo la ventaja stateless. No se recomienda para este monolito.

**Registro:** el cliente NO puede enviar ni elegir rol; el servidor siempre fuerza `user`, email canónico único, password Argon2id, mínimo de fortaleza y límites razonables de longitud, respuesta segura, cooldown/rate limits para login/registro y cuentas de prueba. Email es identificador **no verificado** si no se implementa envío real; no fingir verificación. Provisionar `developer` solo mediante CLI/seed en entorno explícitamente autorizado, no mediante endpoint público, fixtures sin credenciales reales en repositorio. La verificación de correo con servicio saliente no es obligatoria; documentar el límite para producción real.

### 2.2. Notas decisivas sobre F3-D02

- Mantener endpoint obligatorio `POST /api/conversation` para una respuesta final. Implementación puede admitir/enqueue y aguardar un resultado de forma asíncrona sin bloquear el event loop, con timeout y errores controlados; la respuesta final SIEMPRE contiene `session_id` + `answer`, incluidos planes de aclaración y respuesta verificada. Si timeout, comunicar estado de trabajo sin afirmar que terminó, y conservar job durable; un retry idempotente no duplica.
- Agregar `POST /api/conversation/jobs`: `202 Accepted` con `job_id`, `session_id` (creada si faltaba), `status`, referencias de polling, `request_id`. `GET /api/jobs/{job_id}` devuelve estado y, al completar, `session_id`, `answer`, `content_blocks` validados; cancelación si corresponde. El cliente móvil usa este protocolo para no bloquear el hilo y consultar progreso. No reutilizar `202` como una respuesta final ficticia del endpoint obligatorio.
- Considerar `Retry-After`, `Cache-Control: no-store`, tiempos máximos de worker, límites de jobs pendientes por usuario/sesión, expiración de jobs y limpieza. Idempotency-Key por intento lógico, no por cada retry de transporte.
- Los workers serializan por sesión pero pueden ejecutar sesiones distintas en paralelo. El orden debe ser secuencia aceptada transaccionalmente, NO una suposición de que `SKIP LOCKED` garantiza FIFO. Estado `QUEUED|RUNNING|AWAITING_CONFIRMATION|COMPLETED|FAILED|CANCELLED|EXPIRED`; `lease_expires_at`, `attempt_count`, `fencing_token`, `accepted_seq`, `next_retry_at`. Al recuperar lease vencida, comprobar resultado antes de reenviar a modelo; la facturación externa puede seguir siendo *at least once*, aunque efectos de persistencia sean idempotentes.
- `DELETE` de conversación marca cancelación/tombstone y hace guard transaccional antes de persistir cualquier respuesta tardía; purga activa de datos y claves; no reanimar conversación mediante workers. Definir UX para job ya aceptado cuando se cancela sesión (404/410 sin contenido ajeno).

## 3. Arquitectura backend candidata y fronteras

- `api`: FastAPI routers y DTOs; dependencias de identidad/owner; rate limits y idempotencia; no llama al SQL arbitrario del LLM.
- `application`: UseCases/Services que controlan transacciones, auth, conversaciones, planes, jobs y respuesta; protección/validación técnica en límites.
- `agent`: LangChain con herramientas tipadas y presupuesto; state adapter a checkpoints cifrados; eval harness separado.
- `domain`: PN, filtros AST, edition, reglas de comparabilidad, ranking y unidades, sin dependencias de FastAPI o DB.
- `infrastructure`: SQLAlchemy async / repositorios, crypto, OpenRouter client, migrations, worker, clock, tracing; `catalog_reader` de solo lectura.
- `worker`: proceso aparte desde la misma imagen, no microservicio externo; toma trabajos durables y maneja leases/fencing.
- `db`: PostgreSQL con esquemas del dominio F1 más `identity`, `conversation`, `execution` (nombres candidatos). Evitar introducir Redis/RabbitMQ sin evidencia.

No confundir `auth_session_id` con `conversation.session_id`. `thread_id` de LangGraph puede derivar del turno/conversación tras autorización y no confiere permisos.

## 4. Inventario de API conceptual (rutas candidatas, no OpenAPI final)

| Método | Ruta | Semántica de producto | Protecciones y notas |
|---|---|---|---|
| POST | `/api/auth/register` | Alta de usuario con email+password; rol siempre user | público, validación, throttle, 201; nunca accepts role developer |
| POST | `/api/auth/login` | Crear sesión de login / tokens | genérico 401, rate limit, Argon2id, no logs de password |
| POST | `/api/auth/refresh` | Renovar y rotar refresh en transacción | consumo único y reuse detection |
| POST | `/api/auth/logout` | Revocación server-side de la sesión de login actual | idempotente, purga local la coordina Android |
| GET | `/api/auth/me` | Identidad/rol actual | no exponer hashes/tokens |
| GET | `/api/sessions` | Propias conversaciones (orden fecha), búsqueda título, cursor | auth, owner, descifrado acotado, paginación |
| GET | `/api/sessions/{id}/messages` | Historia y bloques técnicos para reanudar | owner, cursor y orden; no traces |
| PATCH | `/api/sessions/{id}` | Renombrar título | owner, cifrado, límites de tamaño |
| DELETE | `/api/sessions/{id}` | Cancelar trabajos y eliminar contenido/traces activos | owner, 204; no resurrection |
| POST | `/api/conversation` | **Obligatorio**: pregunta directa y `session_id?` | final `session_id`, `answer`, campos adicionales; auth y idempotencia |
| POST | `/api/conversation/jobs` | Encolar trabajo y responder pronto | 202 + job_id + session_id + state |
| GET | `/api/jobs/{id}` | Polling, estado y resultado final | owner, scope; no trazas técnicas |
| POST | `/api/jobs/{id}/cancel` | Cancelar intento pendiente si permitido | owner, status idempotente |
| POST | `/api/sessions/{id}/plans/{rev}/confirm` | Confirmar revisión vigente de plan | owner; versión exacta, no stale execution |
| GET | `/api/sessions/{id}/messages/{mid}/trace` | Debug de una respuesta específica | role=developer **AND** owner; trazas saneadas |
| GET | `/api/health` | Proceso vivo | no información sensible |
| GET | `/api/ready` | Preparación DB/migración/worker/catálogo | acceso limitado o redacción de detalles |

**Nota:** `POST /api/sessions` explícito para crear conversación vacía es opcional si `POST /api/conversation` sin `session_id` cumple la necesidad. La app puede navegar a un chat en borrador antes de enviarlo; no necesita crear filas vacías salvo que la experiencia aprobada lo requiera. `POST /api/auth/register` y `POST /api/auth/login` no presuponen OAuth ni correo saliente.

## 5. Envelopes conceptuales

**Respuesta final del endpoint obligatorio:**
- Obligatorios: `session_id`, `answer`.
- Candidatos adicionales: `turn_id`, `message_id`, `status` (COMPLETED / NEEDS_CLARIFICATION / AWAITING_CONFIRMATION), `interpretation_summary` (visible, sin detalles internos), `plan` (ID, revisión, confirmación necesaria), `content_blocks` (tipos autorizados), `catalog_edition_id`, `warnings`, `sources`/`fact_refs`, `request_id`.
- `content_blocks` con unión discriminada: `text`, `product_card`, `comparison_table`, `matching_part_numbers` (total y lista/paginación), `bar_chart` de métrica comparable, `clarification` o `plan_review`. Máximo 3 fichas completas (o top-1), sin nombres de tools en cliente. Cada cifra/renderizado de métricas proviene de hechos verificados y condiciones; el mismo renderer determinista produce las afirmaciones numéricas en `answer`.
- No exponer `model`, nombres de tools, prompts, parámetros de llamadas, stack traces ni token-usage en respuesta end-user. Debug sólo endpoint autorizado.

**Resultado job:** `job_id`, `session_id`, `status`, `created_at`, `updated_at`, opcional `result` final con el mismo envelope del endpoint obligatorio, `error` tipado si falla. No retornar cuerpo cifrado ni DEK.

**Error envelope:** `error.code` (estables: `VALIDATION_ERROR`, `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `STALE_PLAN`, `CATALOG_WITHDRAWN`, `JOB_CANCELLED`, `RATE_LIMITED`, `UPSTREAM_UNAVAILABLE`, `BUDGET_EXCEEDED`, `INTERNAL_ERROR`), `error.user_message` localizado ES/EN, `request_id`, `retryable`, `details` sólo sanitizados y tipados. Diferenciar `NO_RESULTS` (resultado de negocio exitoso) de `UPSTREAM_UNAVAILABLE` (fallo). Nunca incluir SQL, prompt, secretos o PII sensible.

**HTTP candidato:** 200 respuestas, 201 registro, 202 accepted jobs, 204 deletes, 400/422 validación, 401 token, 403 rol, 404 recurso propio/no visible (preferible para enumeración), 409 conflictos/revisión stale, 410 recurso explícitamente retirado/cancelado si no revela existencia ajena, 429 límites, 502/503 upstream y 500 genérico. Crear contrato final inequívoco en Kiro; no cambiar `POST /api/conversation`.

## 6. Semántica de aislamiento y operaciones

- Todas las queries de conversación incluyen `owner_user_id` autoritativo, no tomado del cuerpo; permisos backend antes de descifrar.
- `developer` NO es superusuario en API de chat/Debug; solo rol habilitante y propiedad propia. Inexistente y no autorizado pueden devolver el mismo 404 para reducir enumeración.
- En eliminación, write guard por `deleted_at`/tombstone o análogo, cancelación de jobs, prevención de writes retrasados y eliminación de traces/checkpoints activos. No prometer eliminación inmediata de backups fuera del almacenamiento activo; política de backups y retención explicitada en F3/F5.
- Búsqueda solo por título: obtener conjunto acotado de títulos cifrados del usuario, descifrar tras autorización, normalizar Unicode y buscar; paginar. No `ILIKE` de ciphertext ni índice indiscriminado con términos plaintext.
- Sesión fija `catalog_edition_id`, cambio explícito y versionado; edición retirada bloquea nuevas recomendaciones y mantiene histórico, sin contaminar otros usuarios.

## 7. Cifrado, claves y ciclo de vida (diseño candidato)

- Cifrado de contenido **antes** de persistir en PostgreSQL, no solo cifrado de disco/TDE. AES-256-GCM con nonce único aleatorio de 96 bits por operación (o estrategia aprobada de unicidad robusta), AAD con propósito, owner, conversation, record id y versión de formato. Fallo de tag -> error cerrado y auditoría segura. Nunca reutilizar par clave/nonce.
- DEK por conversación; KEK fuera de la base de datos; DB conserva ciphertext de DEK envuelta y metadatos `key_id`, `cipher_version`. Demo local: secretos por entorno/fichero fuera de repo; evolución prod: secret manager/KMS. No almacenar KEK en PG ni en repo. Una clave para cada conversación reduce alcance y facilita borrado de DEK; **no elimina copias en backups**.
- Cifrar títulos, mensajes, contenido de estado, checkpoints del agente, tool outputs y trazas sensibles, y excluir tokens/contraseñas/headers sensibles de las trazas desde el origen; saneamiento previo a cifrado. Metadatos no cifrados que permitan funcionamiento (FKs, tiempos, estados, owner, secuencia) se minimizan, no prometer que DB copia o logs no revelen metadatos.
- Compatibilidad de checkpoint LangGraph: revisar versión instalada; helper por defecto AES-EAX y aceptación de plaintext legado no satisfacen política. Preferir serializer/adapter compatible con AES-256-GCM y `fail closed`, compatible con pending writes, blobs y recover; verificar bytes físicos antes de declarar éxito. Si no es viable, diseñar persistencia de checkpoints de contenido mínimo no sensible **sin perder recuperación**, o proponer ADR autorizado, no escribir plaintext.
- Cifrado local en Android se decide F4 con Keystore; no inferir que AES del backend cifra el caché cliente. TLS obligatorio para producción, desarrollo emulador excepcionalmente HTTP loopback / `10.0.2.2` con policy debug-specific, sin cleartext habilitado globalmente en release.

## 8. Concurrencia, persistencia e idempotencia

**Entidades conceptuales adicionales a F1:** `users`, `auth_sessions`, `token_verifiers`, `conversations`, `messages`, `domain_states`, `plans`, `turn_jobs`, `job_attempts`, `encrypted_checkpoints`, `tool_traces`, `key_metadata`, `audit_events_minimal`. FK owner y edition siempre; no depender de `session_id` simple como prueba de propiedad.

**Transacciones cortas separadas:**
1. Aceptar turno y reservar secuencia mediante bloqueo breve de conversación; idempotency key `UNIQUE(owner_id, client_request_id)`. Crear nueva conversación y primer trabajo atómicamente si session_id omitida.
2. Worker adquiere un trabajo reclamable con `SKIP LOCKED` y verifica que no existe otro `RUNNING` de esa sesión; crea lease y fencing token bajo transacción; commit.
3. Descifra contexto solo tras owner/edition checks y ejecuta el agente fuera de transacción.
4. Persiste resultado final en transacción breve sólo si fence/lease/owner/plan revision/conversación viva coinciden; commits de mensajes, estado, bloque de respuesta y trazas correlacionados; bloquea resurrección.
5. Si falla worker, lease expira; restituye trabajo a cola o marca fallido según intentos. Reintentos de LLM pueden consumir tokens adicionalmente y deben respetar presupuesto.
6. Confirmación de plan `plan_revision` impide replays de planes anteriores; mensajes mientras espera aclaración no ejecutan un ranking obsoleto.
7. DELETE bloquea nuevos trabajos, revoca/cancela pendientes, purga contenido y DEK/encapsulados activos bajo semántica atómica apropiada. No conservar traces en cola/retry tables después de delete.

**Testing indispensable:** 2 posts simultáneos en misma sesión; cross-session paralelo; misma key dos veces; worker kill a mitad de LLM; lease stale intentando escribir; delete durante job; confirmación de revisión vieja; logout y requests concurrentes. Unicidad de efectos en DB no asegura exactamente una llamada al proveedor externo; el reporte debe ser honesto.

## 9. Operación y reproducibilidad

- Docker Compose: `db` PostgreSQL con volumen, `api` FastAPI, `worker` mismo código/imagen y entrypoint de job processor; migraciones con paso explícito; backend arranca incluso si modelo no responde, pero `/ready` refleja dependencias críticas y errores claros al consultar.
- Variables en `.env.example` placeholder (sin secretos): `DATABASE_URL`, `OPENROUTER_API_KEY`, `AGENT_MODEL`, `INTERPRETER_MODEL`, `ANSWER_MODEL`, `ENCRYPTION_KEK`/path, `AUTH_TOKEN_POLICY`, `GEMINI_API_KEY` (solo ingest fresh), `LOG_LEVEL`, `API_BASE_URL`, límites de tiempo/cola/coste. Si app no puede conectar, README distingue Android emulator vs device.
- Alembic o mecanismo de migración versionado, seeds de usuarios `user`/`developer` controlados vía CLI/env y documentación sin credenciales reales en repositorio. Docker image no incluye .env ni claves.
- Política de backups: aclarar que borrado inmediato significa DB activa/cache/traces activos; backups con retención finita, cifrado y restauración que respete tombstones para evitar resurrecciones. No crear backup local innecesario con plaintext.
- Metrics p50/p95, cola, tool calls, tokens, coste, errors, latencias y request_id. OpenTelemetry opcional: usar logging/tracing estructurado con IDs si OTel añade demasiado alcance; no registrar payloads sensibles en observabilidad general.

## 10. QA y matriz de aceptación vinculada

| Requisito / escenario | Contrato de F3 | Evidencia de implementación requerida |
|---|---|---|
| Assessment `POST /api/conversation` | sync contract con `session_id`/`answer` | request sin/con sesión, respuesta y estado correcto |
| US-001, US-033 y US-036 | register/login/refresh/logout/me | no `developer` en registro; Argon2id, revocación y token theft simulations |
| US-002 y US-003 | scope owner+RBAC en rutas | IDOR del usuario y developer vs otras conversaciones: denegación |
| US-004–009 | endpoints sesiones y title search | reinicio, búsqueda título cifrado, rename, delete, no restauración de contenido |
| US-010–024, US-034 | typed `content_blocks`, `answer`, planes | cifras del PDF y comparabilidad coherentes en texto y JSON |
| US-013 | plan revision confirm | stale plan 409, no ejecución de revisión antigua |
| US-025 | envelope de errores estable | errores ES/EN legibles, sin stack/secretos |
| US-028 | tokens y respuestas para caché F4 | last validated history; logout bloquea datos antiguos |
| US-029 / borrado | jobs, lease, fencing, idempotency | concurrent submits, restart worker, stale completion, delete race |
| US-030 | trace endpoint y storage | llamada+params+results saneados en propias conversaciones; no leaks |
| QA-08 cifrado | AES-GCM DB y checkpoints | extracción directa de DB no muestra plaintext; tamper detection; fail closed |
| QA presupuesto | auditoría usage/cost por intento | no superar límite USD 6 de evals; reserva USD 4 no gastada |
| QA reproducibilidad | Compose, migraciones, seeds, env | ejecución limpia backend+DB+worker+Android sin instrucciones adicionales |

## 11. Preguntas realmente pendientes de criterio del usuario

1. **F3-D01 CERRADA:** B tokens opacos en DB con refresh rotativo, aprobada por el usuario. Alternativa JWT evaluada y descartada.
2. **F3-D02 CERRADA:** B endpoint obligatorio síncrono + API async jobs, aprobada por el usuario. Solo síncrono evaluado y descartado.
3. **Confirmación opcional de seguridad/comportamiento, si el usuario desea:** tratamiento de correo sin verificación, sesión multi-dispositivo y alcance logout; defaults del documento son no verification (documentada), varias sesiones por usuario, logout del dispositivo actual.

## 12. Gate de salida F3 (no afirmar aún cerrado)

- [x] Inventario de contratos, fronteras, envelopes y estados, candidatos a revisión.
- [x] Comparativas y justificaciones de defaults técnicos.
- [x] Protocolo de cola durable y de eliminación coherente con sesiones.
- [x] Superficie de seguridad: auth, scopes, AES-GCM, secretos, roles, controles.
- [x] Aprobación F3-D01 y D02 (2026-11-07).
- [ ] Revisión final del documento de transferencia + consistencia con F0/F1/F2 y pruebas sin código.
- [ ] Tests ejecutados/SDK Android/API/OpenRouter: corresponden a Kiro/F5, no inventar evidencia.

### Referencias revisadas (consultas públicas)

- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- PostgreSQL 18, explicit locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL 18, SELECT SKIP LOCKED: https://www.postgresql.org/docs/current/sql-select.html
- Android security / Keystore: https://developer.android.com/privacy-and-security/keystore


---

## 13. ADENDA v0.2 — estilos, patrones y defensa en profundidad

**Aprobaciones expresas desde v0.1:** F3-D01 B tokens opacos Bearer con sesiones/refresh rotativos almacenados por verificador SQL; F3-D02 B POST contractual síncrono + API adicional de jobs asíncronos; y ratificación de defaults técnicos de §2 por el usuario. No se cambia la política de que `session_id` conversacional NO equivale a sesión de autenticación.

**Dossier de decisiones arquitectónicas:** `F3_architectural_styles_patterns_tactics_v0.1.md` (referencia vinculante para la discusión, NO Spec de Kiro). Documenta alternativas comparadas en topología, estilos y patrones; candidato preferido: monolito modular Feature-First + puertos/adaptadores ligeros, ETL Pipe-and-Filter, Android Feature-First + MVVM/UDF; Repository + DTO Pydantic + Unit of Work de alcance por caso de uso, sin capa DAO redundante.

**Cifrado por capas:** comparar app-level AES-256-GCM solo vs cifrado volumen solo vs ambos + TLS. Se adopta como **default técnico recomendado** defensa en profundidad: mantener AES-GCM en aplicación, requerir cifrado de volumen y backups en despliegues productivos y TLS en enlaces de producción; Docker Compose local no puede certificar ni forzar cifrado de disco del anfitrión. Documentar amenaza/limitación, clave fuera PostgreSQL y metadata residual. No sustituir AES-GCM por cifrado de disco.

**Límites de abstracción:** abstraer infraestructura en puertos solo cuando aporte separación verificable (PostgreSQL, proveedor LLM, crypto, queue, reloj, etc.), no interfaces por clase. No microservicios ni bus externo, no DAO+repo duplicados, no CQRS/event sourcing plenos. Tests unitarios para núcleo de dominio sin red; contratos API estables.

**Única ratificación pendiente de arquitectura organizativa:** F3-ARCH-01 (A: Feature-First + hexagonal ligera recomendada; B: Layer-first; C: Hexagonal completa). Esto no bloquea la discusión de F4, pero sí el gate final de F3.


### Anexo B: Estilos, Patrones y Tácticas v0.1

# Series 76 — F3: Estilos, patrones y tácticas de arquitectura — v0.1

**Tipo:** Documento de alineación para Kiro; no Spec, no código y no aprobación de implementación.
**Fecha:** 2026-11-07. **Estado:** elección técnica propuesta con justificación; la decisión arquitectónica global de organización queda para ratificación del usuario.
**Vínculos:** `F3_backend_api_security_design_v0.2.md`, `F2_agent_architecture_handoff_v1.1.md`, `F1_data_architecture_handoff_v1.1.md`, `F0_requirements_and_quality_catalog_v0.3.md`.
**Disciplina:** aplicar patrones según riesgos reales, no para exhibir vocabulario. Una decisión técnica de ganador claro puede establecerse por delegación; los trade-offs de arquitectura global se validan con el candidato.

## 1. Jerarquía de decisiones: no son nombres intercambiables

| Nivel | Qué decide | Elección objetivo | Estado |
|---|---|---|---|
| Topología | Componentes desplegables | Monolito modular FastAPI + worker separado sobre misma imagen/código + PostgreSQL | Aprobado F3-D03 |
| Organización del código | Co-localización de cambios | Feature-First / vertical slices, con `shared` pequeño y explícito | Propuesto para ratificación |
| Regla de dependencias | Aislamiento de dominio | Hexagonal/Ports & Adapters *ligera*, sin abstracciones innecesarias | Propuesto para ratificación |
| Ejecución ETL | Secuencia de transformaciones | Pipe-and-Filter verificable, staging, gate, publicación atómica | Derivado de F1 |
| Ejecución agentic | Estados y transiciones | Máquina de estados explícita + LangChain controlado, sin tool/sql arbitrary | Aprobado F2 |
| Procesamiento de turnos | Concurrencia | Comandos/jobs duraderos en PostgreSQL, worker por sesión serializada | Aprobado F0/F3 |
| Android UI | Estado / eventos | Feature-First + MVVM + UDF; Compose, ViewModel, StateFlow | Propuesto F4, no F4 cerrado |
| Seguridad en reposo | Defensa en profundidad | AES-256-GCM en app + volumen/backup cifrado en despliegue prod | Default F3 con dependencia de infraestructura |

### 1.1. Alternativas arquitectónicas (y rechazo razonado)

1. **Layer-First clásico.** Pros: familiar, rápido al principio. Contras: cambios por feature se dispersan por `/routers`, `/services`, `/models`, `/repositories`; facilita referencias cruzadas indiscriminadas. **No priorizar.**
2. **Hexagonal completa + DDD/CQRS/event sourcing + microservicios.** Pros: límites muy explícitos, escalabilidad por equipos. Contras: duplicación de contratos, mappers, eventos, acoplamiento operativo y demasiada superficie para un catálogo de 68 filas y plazo corto. **Rechazar de entrada.**
3. **Feature-First + hexagonal ligera dentro de monolito modular.** Pros: coherencia por caso de uso, dominio verificable sin redes/DB/LLM, adaptadores intercambiables donde se justifiquen; Kiro puede trabajar feature por feature. Contras: coordinación de entidades compartidas y disciplina para evitar imports circulares. **Preferida.**
4. **Data-Flow como arquitectura GLOBAL.** Es valiosa para ETL, pero no reemplaza state machines, identidad, REST ni estado de conversaciones. **Aplicar solo a procesos de datos**.
5. **Event-driven como estilo global.** No aporta para registro/login o consultas exactas; introducir broker, consistencia eventual y recuperación. **No introducir bus de eventos**. La cola PostgreSQL admite *commands* durables y estados sin comprometerse con event sourcing.

## 2. Paquetes conceptuales (no árbol de código definitivo)

```
repo/
  backend/
    app/
      bootstrap/                  # composición/configuración de dependencias y routers
      features/
        auth/                     # API / application / domain / infrastructure cuando aporte
        conversations/            # messages, plans, state, delete, search titles
        catalog/                  # consulta de edición publicada y evidencia
        recommendations/          # eligibility, comparability, rankings
        agent/                    # llm, tools, orchestrator, answer verifier
        jobs/                     # commands, durable queue, leasing, fencing
        debug/                    # traces autorizadas / redactadas
      shared/
        security/                 # crypto ports, authorization helpers, policy
        persistence/              # Session factory, transaction boundaries
        contracts/                # tipos realmente compartidos entre features
        observability/            # redacción, ids, métricas
    ingestion/                    # pipeline separado con staging, reconcile, validate
    migrations/
    tests/                        # unit/domain/integration/contract/evals/security
  android/
    app/                          # shell de navegación, wiring (un módulo Gradle inicial)
      core/                       # network, security, database, design system
      feature/
        auth/                     # registro/login
        conversations/            # listado, búsqueda, rename, delete
        chat/                     # plan, streaming/polling, comparison
        debug/                    # trazas solo role developer + own conversation
  docs/                           # ADRs, traceability, setup
```

Reglas: los routers no hablan directamente con SQLAlchemy; los ViewModels no invocan Retrofit/Room directamente; el dominio no importa FastAPI/LangChain/SQLAlchemy; repositorios no deciden permisos por cuenta propia; una feature no importa internals de otra sino contratos públicos, coordinador o puertos explícitos. `shared` no es un cajón de sastre. No más capas ni módulos de los que faciliten tests y evolución. Evitar carpetas vacías o scaffolding arquitectónico ceremonial.

## 3. Patrones concretos, evaluación y alcance

| Patrón | Alternativas | Elección | Beneficio concreto | Coste/riesgo |
|---|---|---|---|---|
| Feature-First | Layer-first vs feature-first | Feature-first en ambos | Cohesión, ownership, cambios concentrados | Evitar duplicar infraestructura o DTOs comunes |
| Ports & Adapters | Acoplar dominio al framework vs puertos | Puertos en DB, LLM, crypto, reloj y cola, no por cada clase | Test sin OpenRouter/PG; sustituir proveedores | Interfaces innecesarias si se aplican universalmente |
| Repository | SQL directo en router vs repositorios por agregado/consulta | Repo para persistencia de conversaciones, sesiones, consultas catálogo | Aislar SQL, permisos y selección edición | Evitar crear repos genéricos CRUD por cada tabla |
| DAO | DAO separado de Repository vs SQLAlchemy mappings en adapter | **No añadir DAO adicional** salvo consulta SQL compleja aislada | Menos duplicación; SQLAlchemy es la capa de acceso concreta | Puede introducirse query adapter específico si surge necesidad |
| DTO | ORM como JSON vs Pydantic request/response y modelos de dominio | DTOs Pydantic en límites, mapeados a objetos de dominio | Validación, no filtrar campos secretos, contratos estables | Mantener mapeos manuales/revisables |
| Unit of Work | commits por repositorio vs transacción en caso de uso | UoW controlada en servicios/casos de uso | Atomicidad entre mensajes, estado, jobs, trazas | SQLAlchemy ya hace tracking UoW: no duplicar mecánicamente |
| Service / Use Case | Lógica en router/repos vs servicios de aplicación | Casos de uso explícitos para operaciones relevantes | Testabilidad, transacciones y autorización | Evitar un `Service` trivial por entidad |
| Adapter | SDK OpenRouter/Gemini directamente en dominio vs adapter | Adaptadores por frontera externa | Trazabilidad, mocks, compatibilidad | Cuidado con no ocultar diferencias importantes de APIs |
| Strategy | ifs repetidos vs estrategia por ranking/proveedor | Ranking lexicográfico fijo; interface de proveedor solo cuando se comparen modelos | Cambio probado sin alterar el núcleo | No introducir estrategias ficticias de ranking |
| State Machine | flags sueltos vs transiciones explícitas | Estados para jobs y planes | Evita confirmaciones obsoletas y writes tras delete | Estados/transiciones han de verificarse con tests |
| Command + idempotency | disparo en background vs jobs persistentes | `turn_job` con `client_request_id`, lease/fencing | Reintentos, durabilidad, orden en conversación | Operaciones externas no son exactamente-once |
| Factory/DI | Instanciación directa en handlers vs composition root | FastAPI Depends/factories limitadas para servicios y adapters | Tests y configuración | No contenedor DI adicional sin necesidad |
| Facade | Clientes reciben detalles de subsistemas vs interfaz orquestada | API y ApplicationService como fachada de casos de uso | No exponer tool/SQL ni detalles del agente | No duplicar una `Facade` si el use case ya lo hace |
| Observer/reactivity | Polling ad hoc de UI vs StateFlow/UDF en Android | ViewModel+StateFlow y coroutines | UI consistente no bloqueante | No mezclar múltiples fuentes de verdad |
| Circuit breaker | Ninguno vs CB general | **No obligatorio al inicio**; timeouts/retries/cost caps primero | Tolerancia provider outages si medimos necesidad | CB no sustituye backoff/timeouts |
| Outbox / events | Events indiscriminados vs comandos PostgreSQL | No usar outbox sin side effect multi-sistema probado | Reduce infraestructura | Revisar si futuro necesita eventos externos |
| CQRS | Modelo write y read separados vs consultas especializadas | **Ligero solo si la respuesta compuesta lo requiere**, no CQRS pleno | Read models optimizados si escala | No duplicar catálogo / lógica de consistencia |
| Event Sourcing | Reconstruir verdad desde eventos vs estado+audit minimal | Rechazar | Cumple borrado de conversaciones más claramente | Eventos con contenido chocan con borrado inmediato |

### 3.1. Repository, DAO, DTO, ORM, UoW: distinción obligatoria

- **DTO:** forma de datos que entra/sale por API o tool. Pydantic/Python, serializable, versión de contrato, sin exponer ORM ni secretos.
- **Domain model:** conceptos e invariantes técnicos; no necesariamente uno-a-uno con tabla ni JSON.
- **ORM model:** materialización concreta de PostgreSQL en el adapter de persistencia.
- **DAO:** función/clase de acceso de bajo nivel orientada a operaciones SQL/filas. No es necesaria como capa adicional junto con Repository sobre la misma tabla; funciones SQL específicas pueden existir en infraestructura.
- **Repository:** abstracción semántica para obtener/guardar agregados o consultas de dominio; las lecturas del catálogo pueden usar query service tipado para evitar repositorio CRUD genérico.
- **Unit of Work:** delimita una transacción con múltiples repositorios; SQLAlchemy Session YA implementa UoW internamente, así que la capa de aplicación solo coordina begin/commit/rollback y la vida de la sesión. Ningún repository ejecuta commits arbitrarios.
- **Mapeos:** DTO <> domain <> ORM, no mapeos circulares; validaciones de frontera frente a invariantes del dominio.
- **Concurrencia:** AsyncSession por request/tarea, no compartir la misma sesión SQLAlchemy entre tareas; transacciones cortas, nunca a través de network await LLM.

## 4. Arquitecturas por subsistema

### 4.1. Backend: request y side effects

- Controller/Router valida transporte y compone dependencias, mapea errores HTTP. **NO** filtra derecho de lectura con un check de UI únicamente.
- Application Use Case autoriza owner y rol, controla estado y unidad transaccional; invoca domain services de elegibilidad/ranking y ports para datos.
- Agent adapter usa LangChain con herramientas con parámetros tipados; no ejecuta SQL libre ni extrae `edition_id` de texto de LLM.
- Repository/query adapter usa la superficie publicada de catálogo read-only. Separa acceso de catálogo y escritura de conversaciones.
- Encryption port recibe material y contexto AAD; implementación AES-256-GCM, DEK por conversación, KEK fuera PG, rotación versionada; cifra checkpoints, traces, títulos, mensajes y artefactos sensibles.
- Job worker separado consume comandos durables de PostgreSQL; auto restart; promueve estados con fencing y versionamiento.

### 4.2. ETL: pipe-and-filter con evidencia

`Original PDF (SHA-256) -> raster/extracción -> OCR y Gemini -> candidatos estructurados -> reconciliación -> normalización tipada -> validaciones + evidencia por celda -> verificación humana inicial/QA -> manifiesto -> publicación atómica`.

Cada etapa recibe/emite contrato versionado, guarda origen y discrepancias. Nuevas ediciones autopublican solo después de calibración independiente y gates aprobados; `verified replay` evita dependencia de proveedor.

### 4.3. Android: Feature-First + MVVM + UDF

UI Compose observa `StateFlow<UiState>` del ViewModel mediante API lifecycle-aware; acciones del usuario llegan a ViewModel/casos de uso, que invocan Repository. Repository coordina API remota y caché local autorizado (fuente de verdad remota para contenido y estado de servidor; caché como réplica de lectura, no autoridad para mensajes pendientes). Gráficos/tablas muestran bloques estructurados, nunca parsean prosa numérica. Auth afecta habilitación de Debug y alcance de caché. Sin segundo motor de inferencia offline.

Preferir **un único módulo Gradle** con paquetes Feature-First y `core` antes que 10 módulos Gradle. DI manual/ligera o Hilt si reduce complejidad verificable; no adoptar 3 frameworks de inyección simultáneamente. Navegación por rutas explícitas, sin ViewModels monolíticos compartidos.

## 5. Cifrado por capas: alternativas y decisión

| Amenaza | Solo AES-GCM en aplicación | Solo cifrado de volumen | Ambos + TLS | Resultado |
|---|---|---|---|---|
| Copia lógica de PG sin KEK | Protege campos cifrados | No basta si dump lógico en claro | Protege campos cifrados | AES-GCM necesario |
| Robo del disco apagado | Protege campos cifrados, no otros archivos | Protege volúmenes | Mayor cobertura | Volumen cifrado aporta |
| WAL y backups/archivos | Solo donde el dato fue cifrado previamente | Depende de cubrir medios y copias | Complementario | Backup cifrado y scope configurado |
| Admin de BD que lee tablas | Campo cifrado protegido si KEK fuera | Volumen montado no protege | Campo cifrado aún protegido | Separación de claves vital |
| API comprometida con KEK | No garantiza protección | No protege | No garantiza protección | Min. privilegio, monitoreo, claves, seguridad runtime |
| Interceptación de tráfico | No basta | No basta | TLS (en cada enlace) | TLS obligatorio en prod |

**Decisión técnica preferida:** defense in depth: AES-256-GCM en aplicación + infraestructura con volúmenes/backup cifrados + TLS. El Docker Compose del evaluador NO puede garantizar que el host use full disk encryption: declarar prerrequisito de despliegue y validarlo cuando se controle infraestructura; no modificar discos ajenos. El catálogo técnico PDF público puede permanecer consultable, los datos de usuario sí protegidos. SHA-256 manifiesto no sustituye autenticación de fuente.

## 6. Tácticas y escenarios de calidad

| Atributo | Táctica | Evidencia exigida |
|---|---|---|
| Seguridad | Defense in depth, RBAC+owner, DB least privilege, encryption at rest/transit, saneamiento logs | ataques IDOR, DB dump sin plaintext, verify key separation; role escalation negada |
| Correctitud | Modelos tipados, determinismo, fail-closed, evidencia por celda, ranking lexicográfico | pruebas golden dataset y no numeric hallucination |
| Modificabilidad | Feature-First, puertos explícitos, DTO versionados, DI, ADR | cambio de proveedor simulado con impacto acotado |
| Resiliencia | Retry bounded + exponential backoff+jitter solo idempotente, leases/fencing, recovery jobs | worker kill/restart; token reuse; duplicate request |
| Escalabilidad | Worker separado, concurrencia por sesión, pool SQL, paginación | 2 sesiones en paralelo y orden en una sesión |
| Rendimiento | No LLM para cálculos, consultas parametrizadas, cache móvil, indexar después de EXPLAIN | latencias p50/p95 y costo por turno |
| Observabilidad | request/trace IDs, spans por tools y jobs, redacción, métricas uso | correlación user-safe para debug |
| Usabilidad | UDF, estados explícitos, confirmación condicional, JSON tipado, error recuperable | pruebas de navegación/loading/error/UI; no ANR |
| Portabilidad | Docker Compose, .env.example, migraciones, verified replay | desde clone limpio con README |
| Confidencialidad de cache | User scoping, Keystore y app-level encryption, lock on logout, wipe on account switch | pruebas con cuenta A y B sin fuga de caché |

**No imponer** circuit breaker global, event bus, pattern matching de herramientas arbitrarias, CQRS completo, DDD Tactical completo, service mesh, microservicios, factory por cada entidad, ni abstracciones sin consumidor/test. Cada adición futura exige ADR y escenario de calidad que demuestre mejora.

## 7. Políticas de dependencia y responsabilidades verificables para Kiro

1. Dominio `recommendations` no importa FastAPI, SQLAlchemy, LangChain ni SDKs de proveedor; tests unitarios sin red.
2. `features/auth`: password Argon2id, access+refresh opaque, hashes de verificador, roles server-side y revocación; ningún endpoint asigna `developer` mediante registro público.
3. La lectura de datos técnicos pasa por un puerto tipado y el único adapter SQL publicado y read-only; sólo el ETL tiene permisos staging/promoción.
4. `turn_job` es comando persistente, no evento inmutable con datos sensibles; borrado de conversación elimina jobs/plan/checkpoints/traces activos y previene resurrección.
5. Comparabilidad y hechos autorizados se procesan antes de construir `answer`; UI renderiza el mismo snapshot tipado, no parsea LLM.
6. Backend transacciona unidades cortas; la llamada OpenRouter está fuera de una transacción SQL.
7. Auth scopes se ejecutan antes de descifrar títulos, mensajes o trazas; developer siempre requiere owner igual.
8. Cifrar volumen de producción depende del entorno; README/operación documentan requerimiento y alcance, sin afirmar que Docker lo implementa universalmente.
9. Android: StateFlow UI/Repository; Room o almacenamiento local equivalente bajo política de seguridad; no cachear respuestas de otros usuarios, invalidación al cambiar cuenta.
10. Construir solo clases/puertos justificados y demostrar mediante tests; detectar ciclos de importación y dependencias cruzadas.

## 8. Decisión verdaderamente pendiente

**F3-ARCH-01 — Nivel de hexagonal/organización interna:**
- **A (preferida):** modular Feature-First + Ports & Adapters ligera; puertos solo DB/LLM/crypto/queue/reloj y algunas fronteras relevantes. Composición en bootstrap; domain services puros.
- **B:** Layer-First clásico con servicio/repo sin inversión de dependencias sistemática. Menos conceptos, peor desacoplamiento del núcleo probado.
- **C:** Clean/Hexagonal completa, interfaces y mappers para casi todo. Mayor formalismo, más coste, rara vez justificado aquí.

**Recomendación A**, sujeta a ratificación del usuario por definir la estructura global. No convertir A en aprobación histórica antes de recibirla.

**F3-SEC-02 — Cifrado de volumen:** la combinación app+storage es una preferencia técnica de ganador claro, con caveat operativo: requerimiento de despliegue prod y verificación infra; no garantía de Docker local. No requiere consentimiento especial para describir la política, pero Kiro no debe declarar el volumen cifrado sin comprobarlo.

## 9. Referencias externas contrastadas (no fuentes del assessment)

- OWASP Cryptographic Storage: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- PostgreSQL 18 Encryption Options: https://www.postgresql.org/docs/18/encryption-options.html
- AWS Prescriptive Guidance, Hexagonal Architecture: https://docs.aws.amazon.com/prescriptive-guidance/latest/hexagonal-architectures/overview.html
- SQLAlchemy 2.x Session Basics: https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- FastAPI Bigger Applications: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- Android Architecture: https://developer.android.com/topic/architecture/recommendations
- Android Guide to Architecture: https://developer.android.com/topic/architecture
