# Adenda vinculante F4 v1.1 — UX sin conectividad (aprobación explícita)

**Prioridad:** prevalece sobre cualquier redacción más genérica de F4 v1.0 que solo mencione `offline cache`, `disconnected` o un banner con fecha de sincronización. F4 se mantiene cerrada como **alineación de diseño**; no hay implementación ni pruebas ejecutadas.

## Comportamiento obligatorio en Conversations y Chat

1. **Aviso persistente y evidente** cuando el dispositivo esté sin conexión: «**Sin conexión. Puedes consultar las conversaciones guardadas, pero no podrás enviar mensajes hasta recuperar la conexión.**» En inglés: «**You're offline. You can view saved conversations, but you can't send messages until you're back online.**» Los textos son ejemplos de copy localizable; conservar inequívocamente el significado.
2. **Deshabilitar la acción Enviar** mientras no exista conectividad utilizable; mostrar visualmente el estado inhabilitado y dar una explicación accesible (TalkBack / descripción de estado). Deshabilitar la acción, no eliminar el composer: el usuario puede escribir o editar un borrador que queda localmente protegido.
3. **No aceptar el envío ni hacer enqueue offline.** No marcar el mensaje como `sent`, `queued` ni `completed`; no generar falsas confirmaciones de servidor. Reconectar **no envía automáticamente** el borrador: el usuario vuelve a pulsar Enviar.
4. **Historial en caché:** solo contenido previamente autorizado de la propia cuenta, con etiqueta «Última sincronización»/datos quizá desactualizados; una cuenta no autenticada tras logout no ve caché; account switch limpia el anterior.
5. **Conectividad vs. disponibilidad del servicio:** sin red comprobada → aviso «sin conexión»; con red pero API inaccesible, token inválido o upstream caído → error de servidor/autenticación según diagnóstico, nunca atribuir indiscriminadamente al usuario una falta de Internet. El indicador de red es una señal, no prueba de disponibilidad HTTP.
6. **Pérdida de red durante solicitud en curso:** el resultado remoto queda `indeterminado` hasta conciliarlo con `client_request_id`/`job_id`; el reintento conserva la clave idempotente y no crea mensajes duplicados.
7. **Recuperación:** al volver a tener conectividad, revalidar sesión y estado de servidor, recuperar jobs pendientes y habilitar Enviar cuando proceda, respetando lifecycle y sin disparar mensajes pendientes sin consentimiento.
8. **QA exigida:** tests Compose / instrumentación para banner visible en Chat/Conversations, botón deshabilitado, borrador preservado, no llamadas de red offline, recuperación sin autoenvío, pérdida de conectividad durante submit, error 503 con Internet, protección de caché tras logout/cambio de cuenta y descripciones de accesibilidad.

## Opciones consideradas y razón

- **A, adoptada:** aviso explícito + bloqueo de envío + borrador local sin cola automática. Evita expectativas falsas y mensajes tardíos no deseados; preserva el valor del historial offline.
- **B, descartada:** encolar mensajes offline y enviarlos después sin intervención. Añade sincronización/conflictos y puede lanzar consultas o gastar tokens contra expectativas del usuario.
- **C, descartada:** permitir pulsar Enviar para mostrar error después. Ofrece peor retroalimentación y hace creer que la operación podría ser aceptada.

---

# Series 76 — F4: Android Native UX & Architecture Handoff v1.0

**Estado:** F4 CERRADA COMO ALINEACIÓN; implementación y pruebas pendientes. Se documentan decisiones técnicas delegadas con ganadores claros y ratificaciones UX anteriores.
**Fecha:** 2026-11-07.
**Naturaleza:** dossier de alineación para Kiro, NO Spec final, diseño en Figma, código Kotlin ni implementación.
**Fuentes:** Assessment Konecto Part B, F0 requirements v0.3, F1 data handoff v1.1, F2 agent handoff v1.1, F3 architecture handoff v1.0.

## 1. Decisiones vinculantes heredadas

- Aplicación nativa **Kotlin + Jetpack Compose**; mínimo tres pantallas evaluables: **Conversations, Chat, Developer Debug**. Login y Registro son pantallas adicionales aprobadas.
- Backend fuente de verdad de usuarios, permisos, conversaciones, mensajes, planes, catálogo, trazas y estados de jobs; Android puede cachear lectura de sus propias conversaciones, no efectuar inferencia local.
- Listar/crear/continuar/renombrar/borrar/buscar conversaciones **solo por título**. Selección de una conversación conserva session_id y edición fijada. Cifrado de títulos y contenido en backend.
- Interfaz bilingüe **ES/EN**, respuesta en idioma del último mensaje, con preferencia explícita del usuario si la fija. Strings de UI localizables; unidades y números técnicos nunca inferidos desde prosa.
- Interpretación del agente **visible siempre**; confirmar cuando haya ambigüedad, delegación o recomendación compleja; plan_version/revision anti-replay. Estado preliminar vs recomendado según cuatro grupos de verificación (entorno, alimentación, servicio y torque).
- Listado de **todos los identificadores elegibles** y número de coincidencias, pero renderizar **máximo tres fichas completas** y comparación intensiva de **dos simultáneos**. Top-1 solicitado: ganador y total de alternativas, sin listar otras referencias si no se solicitan.
- Comparación por métricas equivalentes; highlights según menor/mayor/umbral; barras opcionales solo cuando mejoren comparación sin ocultar condiciones. Nunca tortas/histogramas arbitrarios. No ganador donde no haya comparabilidad.
- Debug disponible en build Release pero **navegable solo a developer**, comprobación server-side de role + ownership, trazas por mensaje/ejecución con tool name, parámetros saneados, resultados, fallos, latencias y costes si se obtienen. No debug en mensajes visibles de usuario.
- Auth por Bearer opaco+refresh, tokens/credenciales no expuestos; registro público solo `user`, developer provisionado externamente. Multiusuario: cachés aislados. Cambio de usuario purga caché anterior; logout lo hace inaccesible, podrá volver a acceder tras autenticar la misma cuenta, salvo políticas de borrado remoto.
- Borrado de conversación en servidor retira mensajes, planes, jobs y trazas activas; cliente invalida caché y no resucita contenido mediante sync tardío.
- `POST /api/conversation` con `session_id?` y `answer` se conserva para evaluación. Cliente puede usar `/api/conversation/jobs` para UI asíncrona con polling de resultados.
- Tiempo/disponibilidad: la entrega del assessment es de una semana y la clave OpenRouter USD 10 con reserva de uso; minimizar extras que no afecten evaluación.

## 2. Contratos de presentación: regla absoluta

**El cliente renderiza tipos, no procesa prosa**. JSON conceptual `conversation_response` incluye `session_id`, `message_id`, `answer`, `status`, `interpretation`, `plan`, `content_blocks`, `warnings`, `source_context`, `trace_id` user-safe. Campos que no apliquen son opcionales; `answer` sigue siendo texto completo user-safe por obligación de assessment. Fuentes técnicas proceden de los mismos hechos autorizados que `answer`.

`content_blocks` discriminados: `text` (prosa), `product_summary`, `product_detail`, `comparison_table`, `metric_bars`, `requirements_summary`, `source_notes`, `no_matches`, `partial_candidates` y `error_info`. Cada bloque debe identificar `schema_version`, tipo y campos pertinentes; Android no debe fabricar una cifra de un string de prosa ni deducir una métrica ausente como cero.

Modelo de datos de pantalla para un valor técnico: `metric_code`, `display_label`, `value` decimal de origen, `unit`, `availability`, `service`, `frequency_context`, `provenance_ref`, `comparison_direction`, `comparable` y `note_ref` (si aplica). Tipos/JSON concretos se especificarán en Kiro a partir de esta semántica.

Convenciones: unidades por columna, format decimal sin cambiar dato original, etiqueta 50/60 Hz visible cuando importa, N/A diferenciado de no documentado y no comparable, nota de página accesible sin tool names, no deducir certificaciones. Header/legend del gráfico nunca oculta condiciones. Texto de `answer` sigue validez numérica como un bloque.

## 3. Navegación candidata (cinco destinos)

**A. Auth graph**: Login → Register → Login/Conversations. `Register` crea solo user. Expiración de token → refresh automático seguro; si falla, cerrar auth y ocultar caché.

**B. Main graph**: Conversations → Chat(sessionId) → DebugTrace(messageId), SOLO developer; alternativamente Developer Debug list como destino propio dentro de main, con deep link contextual a trace. Se mantienen las tres pantallas obligatorias como **destinos navegables distintos**, no modal.

Navegación **type-safe Navigation Compose** en un módulo de app; pasar IDs y parámetros ligeros, no serializar mensajes completos por ruta. Back restaura estado al proceso, ViewModel maneja SavedStateHandle. Un solo módulo Gradle inicial con paquetes Feature-First, sin multimódulo prematuro.

Diagrama textual:

```
App launch -> token válido? -> Conversations : Login <-> Register
Conversations -> New chat | Existing chat -> Chat
Developer only: Conversations/Chat -> Developer Debug -> Trace detail
Logout -> Auth; account switch -> purga cache anterior -> Auth
```

## 4. Pantalla Conversations: contratos y estados

**Funciones:** título, fecha de última actividad, indicador de trabajos pendientes, buscar por título, abrir, nueva, renombrar, eliminar con confirmación, logout, identidad de cuenta. Solo conversaciones del token.

**Estados:** first load, refreshing, lista vacía, lista cargada, offline cache (banner 'Última sincronización'), error remoto recuperable, borrado en progreso, borrado confirmado, sesión expirada. Al cambiar de cuenta no se presenta ni un frame de caché anterior.

**Paginación:** usar cursor u orden estable para API; filtro se ejecuta exclusivamente en los títulos de usuario autorizados y descifrados (servidor), con fallback a filtro local de caché etiquetado como parcial cuando no hay red. Un resultado offline no debe presentarse como total exhaustivo del backend.

**Borrado:** acción confirmada por backend antes de declarar éxito definitivo; bloqueo de jobs activos, cache invalidation en respuesta. Si la conexión falla antes de confirmar, estado indeterminado y reconciliación segura al volver a conectar; jamás reconstruir en servidor desde caché.

## 5. Pantalla Chat: UI y experiencia

**Disposición:** lista de mensajes, composer fijo, indicadores de pending/processing, interpretación visible (collapse/expand), bloques estructurados, cita/evidencia accesible, panel plan de confirmación, advertencias claras. No mostrar tools, tokens, razones internas, prompts, SQL ni trazas.

**Flujo de nueva conversación:** app envía primera consulta sin session_id; backend crea sesión y devuelve `session_id` incluso con job asíncrono, app sustituye borrador local provisional y asocia job; back navigation no pierde ejecución.

**Modelo del turno:** `draft` (local, no enviado), `submitting`, `queued`, `running`, `needs_clarification`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`, `disconnected`/reconciling. El cliente no infiere estado del job por el tiempo transcurrido; consulta a servidor y conserva `client_request_id` hasta conocer aceptación.

**Confirmación:** UI muestra criterios `specified`, `delegated`, `unknown`, `no_preference`, `conflicting`, condiciones y ranking propuesto; botones `Confirmar` y `Editar/corregir`. Confirmar incluye `plan_revision`; si 409 stale, recargar plan y solicitar aprobación nueva; no reejecutar automáticamente.

**Comparación:** tabla horizontal hasta 3 productos, encabezado de métrica accesible/fijo, unidades y contextos visibles; selector dual para comparar dos de las tres fichas, highlights por regla verificada. Mostrar COUNT + PN de todas las coincidencias; hasta 3 detalles completos; tabla dual no significa eliminar el tercer candidato. `metric_bars` solo si valores equivalentes, con orientación menor/mejor explicitada y valores textuales alternativos (accesibilidad). No mostrar pie/histogramas. Ordenación nunca se recalcula en UI en contradicción con backend.

**Estados de fallo:** backend ausente, timeout, token expirado, catalog withdrawn, no matches, producto N/A, insufficient requirements, server error, rate limit. Mensajes ES/EN claros, opciones de reintentar/corregir solo cuando procede. Consulta sin conexión no se acepta como enviada; texto redactado se mantiene localmente pero NO se encola automáticamente para envío futuro en MVP.

**Errores de duplicado:** si se pierde respuesta a `POST /jobs`, app reintenta con mismo `client_request_id`, y reconcilia server status. Nunca genere nueva idempotency key hasta determinar si usuario inicia una nueva intención.

## 6. Pantalla Developer Debug

Destino navegable real disponible en Release. Se muestra en la UI exclusivamente cuando `auth/me` confirma `role=developer`, pero esto es conveniencia; cada endpoint vuelve a verificar rol y owner. Una cuenta developer no es superadmin en la app.

**Entrada recomendada**: pantalla propia accesible desde Conversations/menú sólo para desarrolladores; desde mensaje, navegación a detalle de trace de **su** ejecución. En la pantalla, lista de turns y estados → detalle por tool call (tool, args saneados, resultado saneado, error, duración, coste/tokens si existe, trace id, timestamp). Distinguir tool attempts de ejecución del turno; identificar casos sin tools.

**Protección y borrado:** sin tokens, passwords, cabeceras secretas, KEK/DEK, cadena de prompt interna sensible; errores 401/403/404 claros sin divulgar pertenencia; borrado de sesión elimina trazas; debug no recibe tool traces embebidos en respuesta normal. Extra auditoría interna/externa fuera de alcance de app y no justifica retener trazas después del borrado.

## 7. Arquitectura cliente: alternativas y selección

| Decisión | Alternativas comparadas | Selección y justificación | Estado |
|---|---|---|---|
| Organización | Layer-First vs Feature-First | **Feature-First** aprobado; cohesión y mantenibilidad | Aprobada |
| Presentación | Estado local disperso vs MVVM+UDF | **MVVM+UDF**, ViewModel/stateflow, eventos unidireccionales | Aprobada |
| Gradle | Un módulo con paquetes vs muchos módulos | **Un módulo** para MVP; modularizar solo con evidencia de tiempo de compilación o ownership | Default técnico |
| Navegación | String rutas vs Navigation Compose type-safe | **Type-safe IDs**, evita payloads voluminosos en navigation | Default técnico |
| Cache DB | Room vs JSON archivos | **Room** para lista y mensajes estructurados; manejo de migraciones y consultas | Default técnico |
| Preferencias | DataStore vs SharedPreferences | **DataStore** para settings no sensibles; tokens nunca en plaintext | Default técnico |
| Cliente HTTP | Retrofit+OkHttp vs Ktor client | **Retrofit+OkHttp** por ergonomía de REST y auth interceptors; Ktor válido pero no aporta ventaja inmediata | Default técnico sujeto a compatibilidad |
| DI | manual vs Hilt | **Manual/ligera** inicialmente; Hilt si Kiro detecta complejidad de lifecycle por features, justificar | Default técnico |
| UI updates | polling visible vs WebSocket/FCM | **Polling con backoff y recuperación**; sin conexión push extra | Default técnico |
| Sync | lectura cache + revalidación vs offline-first completo con conflict sync | **Caché de lectura**, servidor fuente de verdad; no cola offline de mensajes | Aprobada en F0 |
| Local encryption | Keystore-wrapped data keys vs cache en claro | **Cifrado de payloads locales** y secretos con claves respaldadas por Android Keystore, nunca log plaintext | Default técnico sujeto a viabilidad específica |

**Nota sobre Room cifrado:** Room no cifra automáticamente todo el archivo de base de datos. Evaluar cifrado de base completa soportado (p.ej., driver compatible auditado) frente a cifrado a nivel campo/payload con AES-GCM y claves protegidas por Keystore. No declarar privacidad ante dump de caché sin probarla. Evitar bibliotecas abandonadas; si cifrar payload hace imposible búsqueda en títulos local, descifrar solo después de auth en app, nunca persistir un índice plaintext que invalide el objetivo.

**Source of truth:** servidor autoridad de modificaciones y resultados de agente; Room réplica local para lectura de historial, sincronizada y marcada con `last_sync_at` y `revision`. UI puede observar Room para rapidez, pero las acciones de mutación/confirmación se validan en servidor. Offline no se considera ranking actualizado.

## 8. Políticas de caché y sesión (aprobadas con detalle derivado)

- Clave/caché separado por usuario; acceso a contenido requiere autenticación local vigente/confirmada tras login, sin mostrar cache al logout. Al cambiar a otra cuenta, purge de la anterior y de cualquier key wrapped residual.
- Al volver a la misma cuenta después de logout, se permite recuperar cache previamente guardado si el diseño seguro lo soporta; si no, resincronizar sin prometer conservación local. No dejar plaintext accesible entre sesiones.
- Título y mensajes cifrados localmente; no depender solo de bloqueo visual, especialmente en backups Android. Configurar exclusiones de backup de cache y tokens según necesidad.
- Caché borra conversación local después de confirmación remota; si servidor retorna no existente por borrado en otro dispositivo, purgar. Nunca subir datos cacheados para restaurar conversación borrada.
- Refresh token rotation: sincronizar solicitudes concurrentes para evitar refresh replay falso; si falla refresh, ocultar data sin permitir una ventana de exposición por recomposición.
- Logout y cambio de cuenta deben cancelar polling y solicitudes en curso; respuestas tardías no pueden escribir cache del usuario equivocado (generation/account epoch guard).

## 9. Accesibilidad, internacionalización y formatos

- Idiomas ES/EN (strings, formatos numéricos/fechas, error UX y textos), no traducir PN ni identificadores técnicos.
- Pantallas compactas a anchas; soportar portrait y landscape razonables, scroll horizontal accesible con encabezados, fuentes escalables, TalkBack labels y alternate table/text para gráficos; contrastes adecuados y dark/light mode.
- Unidades siempre visibles, valores tabulares y separadores decimales sin alterar sentido. `N/A` no se convierte en 0 y `UNKNOWN` se diferencia de `NOT_APPLICABLE`.
- Ocultar detalles internos a usuarios finales, pero mensajes de falla deben ser accionables. No exponer stack trace.

## 10. UI tests y acceptance matrix

| ID | Given/When/Then | Verificación |
|---|---|---|
| F4-AT01 | Login correcto y retorno a Conversations | token gestionado seguro, pantallas protegidas |
| F4-AT02 | Registro desde UI intenta elevación de rol | `developer` no elegible ni enviado; backend fuerza user |
| F4-AT03 | Cerrar sesión con caché existente | historial no visible sin auth |
| F4-AT04 | Cambio cuenta A→B | cero datos visibles/caché cruzados, incluso respuesta tardía del servidor A |
| F4-AT05 | Lista offline con cache | solo contenido anteriormente autorizado, banner de antigüedad |
| F4-AT06 | Sesión nueva y job 202 | session_id persistido, job progress y polling, UI no bloquea main thread |
| F4-AT07 | Reintentar aceptación HTTP perdida | misma idempotency key, no duplicación |
| F4-AT08 | Plan tiene revision vencida | 409 provoca recarga y confirmación nuevamente, sin ejecución vieja |
| F4-AT09 | API retorna dos torques por servicio | la vista etiqueta ambos con servicio, jamás los fusiona |
| F4-AT10 | Comparación 3 y selector 2 | tabla accesible con 3; dual 2; highlights sólo donde comparable |
| F4-AT11 | Métrica N/A, frecuencia ausente | no gráfico engañoso ni valor cero |
| F4-AT12 | Usuario normal visita route Debug indirectamente | navegación no expuesta + 403/404 servidor para traces |
| F4-AT13 | Developer consulta trace de otro usuario | denegación backend y cero data de respuesta |
| F4-AT14 | Error 503/timeout al enviar | borrador intacto, retry seguro, estados claros ES/EN |
| F4-AT15 | DELETE de chat durante job | cache invalidado; resultado tardío no resucita chat |
| F4-AT16 | Dump de storage local | contenido sensible no legible sin claves bajo threat model definido |
| F4-AT17 | Cambio idioma ES↔EN | PN, unidades y datos técnicos no cambian numéricamente |
| F4-AT18 | Texto grande/TalkBack | navegación, comparación y gráficos accesibles |
| F4-AT19 | Permiso release e HTTP inseguro | release no permite cleartext general; configuración debug local limitada |

**No ejecutadas:** estas son condiciones de aceptación para Kiro, no resultados.

## 11. Resolución final de decisiones de interfaz (opciones evaluadas)

**F4-D01 — UX de la interpretación visible — SELECCIONADA A:**
- **A (adoptada):** chip o tarjeta compacta de criterios interpretados debajo de cada respuesta, expandible a detalle de criterios y supuestos; panel prominente y accionable cuando se requiere confirmación. Menos ruido en turnos simples, pero la interpretación continúa siempre visible.
- **B:** panel completo fijo para todas las consultas, incluso consultas exactas. Máxima visibilidad pero mucha fricción de pantalla.

**F4-D02 — Gráficos — A YA APROBADA EN F0:**
- **A (adoptada):** tabla principal + comparación dual + barras opcionales por métrica comparable, incluyendo agrupadas/multibarra solo cuando los grupos comparten unidades y condiciones; leyendas y lectura accesible. No torta/histogramas.
- **B:** tablas exclusivamente, sin gráficos. Más simple, menor valor comparativo visual.

**F4-D03 — Sincronización del historial — SELECCIONADA A:**
- **A (adoptada):** Room como caché local para lectura inmediata; revalidación al abrir y al recuperar conectividad, polling solo de jobs en curso; no WorkManager/push para sincronización continua en background. Explicar estado offline.
- **B:** sincronización periódica WorkManager y actualización de historial en background. Más fresca, mayor complejidad y no indispensable.

## 12. Criterio para cerrar F4

- [x] Inventario de pantallas/destinos obligatorios, más auth.
- [x] Flujos de registro, login, historial, chat, confirmación y Debug propuestos.
- [x] Contrato de renderización de tipos técnicos y protección ante valores no documentados.
- [x] Propuesta MVVM+UDF, cache y protección local con alternativas y tests.
- [x] F4-D01 A por UX compacta con interpretación siempre visible y confirmación condicional ya aprobada; F4-D02 A ratificada previamente; F4-D03 A por alineación con caché de lectura y ausencia de exigencia de sync background.
- [x] Handoff con trazabilidad de F0-F3 y gates sin código; pendientes empíricos declarados.
- [ ] Screenshots, Compose tests, pruebas dispositivo y seguridad cache: pendientes Kiro/F5.

## 13. Fuentes externas para justificar decisiones tecnológicas (no fuentes de datos técnicos)

- https://developer.android.com/topic/architecture/ui-layer
- https://developer.android.com/topic/architecture/data-layer
- https://developer.android.com/guide/navigation/design/type-safety
- https://developer.android.com/topic/architecture/data-layer/offline-first
- https://developer.android.com/privacy-and-security/security-config


## 14. Acta de cierre de F4 / trade-offs explícitos

**Justificación D01:** vista compacta, visible y expandible es preferible a panel grande en todos los turnos porque móvil tiene espacio limitado, mientras la confirmación obligatoria sigue prominente para recomendaciones ambiguas o delegaciones. No elimina la transparencia aprobada.

**Justificación D02:** se aprovecha la aprobación previa del usuario sobre barras individuales/agrupadas cuando realmente aporten comparación. No se reabre la decisión. La tabla sigue fuente primaria de valores y contexto, las barras son representaciones derivadas de métrica `comparable=true`, 2–3 productos y una unidad/contexto homogéneos.

**Justificación D03:** mantener lectura local actualizada en apertura y tras reconectar con Room, sin sincronizador periódico obligatorio, cumple el alcance y evita riesgo de fuga por background/account switch; WorkManager se justificaría solo con necesidad de sincronización fiable independiente de UI.

**Dependencias F3 ↔ F4:** `client_request_id` de idempotencia; `session_id` persistente; `job_id` de polling; `plan_revision`; `content_blocks` tipados; `source_context` y `trace_id` seguro; owner+developer del backend. Mantener los formatos finales en Specs generadas por Kiro sin modificar semántica.

**No implementado:** rutas, pantallas, cifrado Room, tests, autenticación, renderizado, ni verificación en emulador. La aprobación de F4 es solo de diseño.
