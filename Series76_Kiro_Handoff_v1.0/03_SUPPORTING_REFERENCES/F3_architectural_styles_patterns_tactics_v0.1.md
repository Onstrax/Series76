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
