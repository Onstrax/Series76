# Adenda vinculante F5 v1.1 — prueba del modo offline aprobado

F5 permanece **cerrada como plan de evaluación**, con ejecución pendiente. Se extienden los casos de prueba para exigir la aprobación UX de la última conversación (no reducirlo al banner de antigüedad del caché).

| ID | Escenario | Resultado de aceptación |
|---|---|---|
| `F5-OFF-01` | Quitar conectividad con una conversación en caché abierta | En Chat y Conversations se muestra un aviso muy visible de falta de conexión, se indica que no se pueden enviar mensajes y se mantiene accesible únicamente el historial autorizado. |
| `F5-OFF-02` | Red ausente y mensaje redactado | Control Enviar inhabilitado, `composer` y borrador preservados cifrados, sin `POST` ni trabajo encolado, sin estatus falsamente `sent`/`queued`. |
| `F5-OFF-03` | Recuperar conexión | Se revalida sesión/estado; el borrador continúa intacto y **no se envía hasta una nueva acción explícita** del usuario. |
| `F5-OFF-04` | Perder red tras iniciar `POST` | Conciliación por `client_request_id`, sin duplicación ni pérdida silenciosa de trabajo. |
| `F5-OFF-05` | Internet presente pero backend devuelve 503 | Mostrar «servicio no disponible» o error remoto adecuado, **no** «sin Internet». |
| `F5-OFF-06` | Logout/cambio de usuario durante modo offline | Ningún contenido de caché anterior es visible; respuestas tardías no lo reintroducen. |
| `F5-OFF-07` | TalkBack y tamaño de texto grande | Aviso y estado deshabilitado legibles y accesibles, sin depender exclusivamente de color. |

**Regla de entrega:** Kiro debe vincular estas pruebas con F4 v1.1 y registrar evidencia real del emulador. Ninguna de estas pruebas está ejecutada en esta fase.

---

# Series 76 — F5: Quality, Evaluation & Delivery Handoff v1.0

**Estado:** CERRADA COMO PLAN DE ALINEACIÓN DE QA; pruebas NO ejecutadas; no es Spec final de Kiro.
**Fecha:** 2026-11-07.
**Entradas:** F0 requisitos y QA; F1 data handoff; F2 agente; F3 backend/security; F4 Android UX handoff.

## 1. Objetivo y orden de prioridades

La evaluación debe demostrar que la solución satisface los requisitos obligatorios de Konecto, sin cifras inventadas, reproduciéndola en Docker y Android, y con decisiones defendibles en entrevista. Principio de release: **cero defectos críticos conocidos** en integridad técnica, autorización, aislamiento, cifrado de contenidos obligatorios y persistencia; los defectos no críticos se registran con alcance y justificación. Evitar métricas irreales sin baseline.

## 2. Niveles de prueba y responsables

| Nivel | Qué probar | Herramientas candidatas / evidencia |
|---|---|---|
| Verificación documental | 7 tablas, 68 filas, 4 N/A, celdas/números/notas/certificaciones, PN, frecuencia | Golden dataset revisado contra PDF original y manifest SHA-256; diff por celda y 100 % de campos publicados verificados |
| Unitaria dominio | Filtros AND/OR/NOT, torque unidades, elegibilidad, ranking lexicográfico, abstención, no comparabilidad, plans | pytest + property-based (Hypothesis) sobre objetos sin FastAPI/LLM |
| Integración ETL | OCR+Gemini candidates, merge, thresholds, correcciones, cuarentena, replay, publicación atómica | Fixtures deterministas, inputs golden e inyección de errores; fresh extraction separado de replay |
| Integración DB | Migraciones, FKs, estados, UNIQUE, edición activa y retirada, read-only surface, staging inaccesible | PostgreSQL real en contenedor; tests transaccionales; raw DB/permissions |
| Contrato backend | REST sync/async, DTOs Pydantic, errores, auth, ownership, plan revision, result typed | pytest + FastAPI test client/httpx async, contract snapshots con versionado |
| Agente con herramientas mock | tool selection, typed arguments, timeouts, escaping, max loops, injection, response facts, ES/EN | tool-mocks, respuestas LLM controladas y fake clock; deterministas en CI |
| Agent Evals con API real | al menos 2 modelos por función; bilingüismo, ambigüedad, coste, tool calling, false claims, multitur | Conjunto ciego controlado de ~36 escenarios, JSON output, tracing de coste; ≤ USD 6 totales de gasto evaluativo |
| Concurrencia y fallos | idempotency, serialización por sesión, lease expire, worker restart, delete during job, token refresh races | PostgreSQL+api+worker; inyección de interrupciones; asserts de estado final |
| Seguridad | IDOR, role escalation, revocación, prompt injection, ciphertext tampering, DB-only disclosure, unsafe logs | pruebas adversariales automatizadas y revisión manual focalizada |
| Android unit / UI | ViewModel, UiState, navegación login/register/chat/debug, 3-product table, 2-product dual, no leak ES/EN | JUnit + coroutine test + Compose UI tests semánticos |
| Android integrado | Emulator ↔ Compose ↔ FastAPI; 202 jobs, plan 409, caché, logout/switch, offline banners | Instrumented tests + demo manual con dispositivo/emulador |
| Reproducibilidad | Clone limpio, .env.example, compose, migraciones, seeds, ingest replay, app build/emulador | checklist de cold-start grabado/logs, README independiente y README security notes |

**No confundir cobertura de código con cobertura de escenarios:** ambas son deseables, pero las garantías de datos se miden por hechos comprobados, no líneas ejecutadas.

## 3. Golden dataset y matriz de casos de dominio

- A partir de PDF oficial, preservar valor impreso+unidad+fila+celda; comparar contra catálogo publicado con igual precisión, incluyendo datos no disponibles y notas. No basta coincidencia OCR-Gemini.
- Verificar por separado T01 (dos servicios; 50/60 Hz), T02 (notas y asteriscos), T03 (4 N/A y alcance de torque/duty), T04–T05 (24V AC/DC vs DC), T06–T07 (tablas distintas de 110/220).
- Pruebas de propiedades: más restricciones AND no deben aumentar conjunto elegible; un valor N/A nunca satisface un filtro numérico; igualdad de filtros reordenados AND; conversión inversa dentro de tolerancia **solo para cálculos derivados**, no sustituye cifras oficiales; ranking lexicográfico estable; comparar velocidades únicamente bajo condiciones compatibles.
- Retirada de edición: bloquea nuevas recomendaciones y conserva historial visible; al cambiar la edición de una conversación, no reescribir respuestas anteriores.

## 4. Evaluación del LLM / modelos OpenRouter

**Regla de gasto aprobada:** hard limit clave USD 10; de esa cifra ≤ USD 6 para desarrollo/benchmark/evals, ≥ USD 4 para demo final. El pipeline de test real debe contabilizar gasto **acumulado**, no por modelo. Google AI Studio opcional para ETL y con clave propia, sin reemplazar runtime OpenRouter.

**Funciones / al menos 2 candidatos:**
1. Interpretación bilingüe y AST: Qwen3-235B-A22B-2507 y GPT-4.1 mini.
2. Invocación de herramientas: DeepSeek V3.2 y Qwen3-235B-A22B-2507.
3. Clarificación/explicación: GPT-4.1 mini y Qwen3-235B-A22B-2507.
Verificar identificadores, disponibilidad real, compatibilidad de tool calling/JSON y precios *antes* de benchmark; cualquier cambio exige registrar rationale. No crear obligación de usar tres modelos distintos si uno es mejor para varios roles.

**Conjunto de ~36 escenarios inicialmente:** 6 exact PN, 6 filtros complejos, 6 recomendaciones incompletas/confirmaciones, 6 comparaciones+unidades, 6 multitur/contexto y 6 adversariales/fuera de alcance, equilibrando ES/EN. Semillas y resultados esperados documentados, casos no vistos por el agente durante el diseño, nunca inventar datos del PDF. Extender si fallan áreas críticas.

**Métricas:** exactitud de intención, cumplimiento de AST, tool accuracy, factor de costo/turno, latencia p50/p95, tasa JSON válida, mantenimiento de contexto, abstención apropiada, cumplimiento de constraints; **cero afirmaciones técnicas falsas y cero leakage** en casos críticos del conjunto evaluado. Anotar resultados con IC/denominadores; no afirmar precisión universal ni inferir p95 del mundo real a partir de 36 pruebas.

**Método de selección:** ejecutar primero canary barato por función, luego pares A/B con mismas preguntas y prompts. Rechazar modelo que falle bloqueo crítico (fabricar números, ignorar permisos, herramientas maliciosas), priorizar calidad en casos difíciles, luego coste/latencia. Regla de escape: si tool-calling se degrada, elegir alternativa A tool genérica si gana bajo mismas métricas; no gastar presupuesto intentando salvar por prompts repetidos sin justificación.

## 5. Pruebas críticas de seguridad y persistencia

| Prueba | Condición aprobatoria |
|---|---|
| user A lee conversation de B | HTTP 404/403 sin contenido ni metadatos sensibles |
| developer A lee trace de developer B | Denegado, aunque tenga rol developer |
| registro con role developer | Servidor crea user o rechaza; nunca developer |
| refresh replay / logout | Se revocan tokens actuales y familias según política; no entra con credencial vieja |
| DB dump sin KEK | Mensajes, títulos, traces y checkpoint sensible cifrados; no plaintext reutilizable |
| manipulación de ciphertext | AES-GCM falla cerrado, no sustituye payload con valor corrupto |
| token/secretos en logs | Cero secretos en logs/traces de debug ni `answer` |
| prompt injection en consulta | Tools limitadas, no cambia tenant, edition, scope ni ejecuta SQL arbitrario |
| borrado a mitad de job | no resurrection de messages, traces o DEK, aunque worker termine luego |
| jobs duplicados, worker kill | idempotencia persistida, reintentos acotados, sin dos respuestas contradictorias |
| cache Android después de logout | inaccessible; account switch purge sin exposición en recomposition |
| sync offline y borrado remoto | cache del cliente no restaura datos eliminados del servidor |

## 6. QA Android y accesibilidad

- Compose semantics, TalkBack labels, texto grande, modo claro/oscuro, scroll horizontal accesible. Tests de 3 candidatos y comparación dual de 2, gráficos con alternativa textual y unidad/contexto.
- Estados: loading, empty, queued, running, error, offline cache, no matches, N/A, plan awaiting confirmation, stale plan, session expired, catalog withdrawn, deletion pending.
- Verificar rutas: Conversations, Chat, Developer Debug; Login y Registro funcionales. Una navegación directa a Debug sin rol jamás obtiene trazas, aunque el destino UI esté presente en el APK.
- No ANR: network/DB/cifrado fuera del main thread, y polling se cancela según lifecycle.

## 7. Conjunto mínimo de end-to-end para la demo

1. Registrarse con usuario nuevo y confirmar rol user; salir e iniciar sesión.
2. Consultar PN exacto (On/Off/Modulating), confirmar cifras verificadas y nota de evidencia.
3. Buscar candidatos por alimentación y filtro de torque; mostrar count/nombres y hasta tres fichas.
4. Recomendar con criterios incompletos; revisar interpretación, corregir, confirmar revisión y obtener ranking.
5. Comparar dos modelos, alternar tercero y mostrar barra solo si métricas comparables.
6. Cambiar a 50 Hz en un seguimiento sin repetir PN; reiniciar backend; reabrir historial.
7. Abrir Developer Debug para una sesión propia y comprobar tool args/resultados; verificar denegación en rol user.
8. Simular backend caído, recuperar conversación desde caché, conservar borrador y reconectar.
9. Enviar dos turnos seguidos a misma conversación; cerrar/reabrir app; conservar orden y estados finales.
10. Eliminar conversación con job en proceso y comprobar que no reaparezca.
11. Ejecutar verified replay y publicación verificada sin llamada Gemini; fresh extraction con GEMINI_API_KEY propia documentada.
12. Reproducir desde repo limpio en Docker Compose y emulador con datos seed y credenciales demostrativas que no son secretos reales.

## 8. Entrega / repo / README

- Un solo repositorio para API, worker, Android, ingest y docs de arquitectura y AI-assisted dev config.
- Dockerfile backend, docker-compose.yml DB/API/worker, `.env.example` sin claves, migraciones, comandos ETL, manifests verified replay, semillas controladas y documentación de red emulador ↔ host.
- README de configuración, arranque, endpoint sync y async, registro/login, test user vs developer, permisos de debug, decisiones/tradeoffs, modelos variables, presupuesto, limitaciones de seguridad, modo fresh vs replay, fallos conocidos.
- No exigir Google AI Studio como clave adicional para reproducir `verified replay`; fresh extraction opcional con GEMINI_API_KEY del evaluador.
- Entregar antes de deadline; pruebas de cold start en entorno limpio, no solo 'funciona en mi máquina'.

## 9. Gate de cierre F5 / decisiones y pruebas pendientes

- [x] Categorías y metodología, escenarios críticos y plan de evidencia definidos.
- [x] Alineación con 12 grupos previos de QA y presupuesto de OpenRouter.
- [x] **Decisión de ganador claro adoptada:** no liberar con fallos críticos conocidos de exactitud, autorización, cifrado, persistencia o compatibilidad del contrato del assessment. Funciones obligatorias antes de extras estéticos.
- [x] **Decisión de ganador claro adoptada:** si OpenRouter falla o se agota el presupuesto, retornar estado de servicio temporalmente no disponible/error explícito y preservar borrador/historial; no generar datos inventados ni asumir que el agente puede responder sin modelo. No gastar reserva de USD 4 en evaluaciones.
- [x] Consolidado como guía de evaluación, aceptación y entrega; todo resultado aparece expresamente pendiente de ejecución de Kiro.
- [ ] Ejecutar pruebas y documentar resultados: responsabilidad de Kiro/implementación, no realizada.

## Fuentes externas / guías

- https://developer.android.com/develop/ui/compose/testing
- https://developer.android.com/topic/architecture/recommendations
- https://developer.android.com/develop/background-work/background-tasks/persistent


## 10. Priorización de ejecución para Kiro

La siguiente secuencia es propuesta de orden de implementación, **no Specs generadas**: (a) entorno/migraciones/verified replay, (b) dominio + tool con golden tests, (c) auth/conversations/restore, (d) agente/confirmaciones+answer tipado, (e) jobs/Debug/crypto, (f) Android flujos obligatorios, (g) tests adversariales e2e y README cold-start. En cualquier etapa la exactitud numérica y seguridad son gates; cuando el tiempo se acorta se eliminan características optativas, no controles.

**Evidencia mínima para declarar 'pasó'**: comando de test, fecha/commit, entorno, resultado, archivo log sanitizado, conteo y denominador de casos, ausencia de errores críticos, límites conocidos y coste acumulado real. No afirmar 100 % de cobertura semántica global solo porque todas las 68 filas estén auditadas.

**Control de cambios**: si Kiro encuentra incompatibilidad de una biblioteca, debe reportar alternativa + trade-off + impacto en requisitos y pedir aprobación del usuario cuando afecte un ADR; no sustituir AES-GCM por EAX, ni eliminar agentes LangChain, ni exponer traces para simplificar.

**Gate de F5 como plan de alineación:** completado. Ejecutar pruebas sigue pendiente y es obligación posterior a green light.
