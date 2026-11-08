# F0 — Requisitos y calidad, edición canónica de transferencia v1.0

**Estado vinculante: APROBADO COMO DISEÑO.** No se han ejecutado pruebas ni creado código. Esta cubierta hace autoritativo el cierre del documento original F0 v0.3 sin ocultar deliberaciones históricas anteriores.

## Cómo leer este documento sin contradicciones

- El catálogo completo de historias y QA se conserva más abajo sin alteraciones. Su sección **13 (Cierre de F0)**, sección **14 (US-033, US-034, US-036)** y sección **16 (Gate de F0)** prevalecen sobre los marcadores `PENDIENTE`, `CANDIDATO` o `ABIERTO` que aparecen en **secciones históricas** 1–12.
- **35 historias activas:** US-001…US-034 y US-036. US-035 no es historia adicional sino caso transversal obligatorio de borrado concurrente.
- **15 escenarios QA** y habilitadores documentados. Pruebas e implementación se mantienen pendientes para Kiro.
- Los requisitos obligatorios del assessment prevalecen sobre nuestras decisiones; los compromisos adicionales expresamente aprobados (auth, registro público `user`, cifrado de aplicación, etc.) también son vinculantes, aunque Konecto los califique como opcionales.
- Las decisiones técnicas adoptadas después de F0 prevalecen sobre los puntos aún abiertos en los borradores históricos: **F1 v1.1**, **F2 v1.1**, **F3 v1.0**, **F4 v1.1** y **F5 v1.1**, junto con **F6 v1.0** como mapa de autoridad. Consultar el historial ADR solo para el *porqué*.
- **Aprobación nueva de UX, 7 de noviembre:** cuando no haya conexión, la UI debe indicarlo visiblemente, bloquear el envío y conservar borradores sin enviar automáticamente; definición y pruebas en F4/F5.

**El contenido siguiente es el catálogo original F0 v0.3, preservado como evidencia de decisiones y criterios de aceptación.**


---

# Series 76 — Catálogo F0.3 refinado: requisitos, INVEST, aceptación y trazabilidad

**Versión:** 0.3 · **Fecha:** 2026-11-06 · **Estado:** F0 APROBADA, con US-033/US-034/US-036 añadidas; US-035 obligatorio transversal. F1 inicia estudio de dominio y ETL. Nota: las entradas de propuestas/abiertas anteriores conservan valor histórico y quedan resueltas por §13–16.

**Estado histórico:** línea base funcional US-001…US-032 y QA-01…QA-15 aprobada en concepto; refinamientos nuevos y propuestas marcados explícitamente. **No son las Specs de Kiro.**

**Fuentes:** `assessment-en.pdf` pp.1–6; `series_76_electric_data.pdf` pp.1–4 (única fuente de cifras técnicas); `series_76_summary.pdf` pp.1–2 (contexto); notas originales; `F0_discovery_alignment_v0.6.md`; conversación de aprobación. No añadir números de actuadores no cotejados.

## 1. Política de lectura y control de versiones

- El assessment gobierna obligaciones; el PDF eléctrico gobierna **cifras técnicas de actuadores**; las decisiones explícitas determinan producto. Las hipótesis no se promueven automáticamente.
- Se retienen los IDs US-001…US-032, que el candidato aprobó. Las clasificaciones de abajo no eliminan funcionalidades. Nuevas propuestas US-033…US-035 y preguntas residuales **requieren aprobación**.
- `POST /api/conversation` con `query` y `session_id` opcional, respuesta `session_id` y `answer`, es obligatorio y no puede quedar invalidado por la cola interna ni por una API adicional.
- Trazabilidad completa **mientras existe la conversación**. Al borrarse, se eliminan del almacenamiento activo los mensajes, estado/checkpoints y **trazas detalladas**; no retenerlas para auditoría por defecto. La retención física de backups y copias de terceros se delimitará en F3.
- La búsqueda es **únicamente por título**. La consulta se acota por dueño antes de descifrar, sin índice de cuerpos ni indexado plaintext de títulos compartido.
- Contexto de recomendación: entorno, alimentación, servicio y torque requerido deben verificarse para emitir recomendación documentada. Si falta criterio físico pertinente, resultados PRELIMINARY, aunque el usuario diga «elige tú».
- En Chat: interpretación visible, confirmación condicional, respuesta híbrida, hasta 3 fichas, dual 2, barras relevantes y comparables, prioridad lexicográfica y PN como desempate.

## 2. Estructura del catálogo: ocho capacidades

| Área aprobada | Historias | Resultado de negocio |
|---|---|---|
| Identidad y autorización | US-001..003 | Login y aislamiento por owner/role |
| Conversaciones | US-004..009 | Crear, listar, reabrir, título, eliminar, buscar título |
| Comprensión e intención | US-010..013 | PN, filtros, plan visible, confirmación |
| Recomendaciones | US-014..018 | Completitud física, preliminares, ranking, top1, conjuntos |
| Presentación | US-019..021 | Comparativas, highlights y barras opcionales |
| Contexto y respuesta | US-022..026 | Memoria, conceptos, cálculos, errores, bilingüismo |
| App y resiliencia | US-027..029 | Estados UI, caché, concurrencia |
| Debug y operación evaluable | US-030..032 | Trazas, ingesta reproducible, entrega |

## 3. Auditoría INVEST de las 32 historias

**Criterios:** I = independencia; N = negociabilidad; V = valor; E = estimabilidad; S = tamaño acotado; T = testabilidad. En esta etapa se marca el eje de mayor riesgo para convertir cada capacidad en una unidad implementable; no son evaluaciones cuantitativas fingidas.

**Clasificación:** A = historia de usuario razonablemente acotada; S = requiere dividir escenarios/subcomportamientos conservando ID; T = política/calidad transversal que debe implementarse a través de varias historias; E = habilitador técnico/entregable, no historia de usuario pura.

| ID | Área | Tipo | Diagnóstico INVEST y tratamiento para Kiro |
|---|---|---|---|
| US-001 | Identidad | **A** | I/T: separar login exitoso, inválido y sesión vencida; logout no cubierto (US-033 propuesta). |
| US-002 | Identidad | **T** | I/S: política transversal de autorización para todo recurso; debe mapearse a endpoints y herramientas. |
| US-003 | Identidad | **A** | I: acceso Debug por rol+owner, distinto de inspeccionar contenido (US-030). |
| US-004 | Conversaciones | **A** | T: distinguir crear con query de conversación vacía; contrato fijo requiere query. |
| US-005 | Conversaciones | **A** | E/T: definir paginación/orden sin asumir un endpoint exacto. |
| US-006 | Conversaciones | **A** | S: separar historial visible, slots de dominio y recuperación tras reinicio. |
| US-007 | Conversaciones | **A** | T: definir validación y protección de título en F3. |
| US-008 | Conversaciones | **S** | S/I: separar borrar conversación, cancelación de jobs, cifrado/trazas y sincronización de caché; añadir prueba con turno activo. |
| US-009 | Conversaciones | **A** | I/T: búsqueda solo en títulos propios; resolver límites de descifrado, case-folding y paginación en F3. |
| US-010 | Consulta | **A** | T: PN exacto, condiciones variantes, no encontrado y formato inválido. |
| US-011 | Consulta | **S** | S/E: familias de filtro, OR/AND/NOT, paréntesis, rangos y unidades deben tener subcasos independientes. |
| US-012 | Consulta | **T** | I: exposición de interpretación transversal a todas las intenciones; sin detalles internos. |
| US-013 | Consulta | **S** | S: aclarar/corregir/confirmar plan de versión y su idempotencia. |
| US-014 | Recomendación | **A** | T: cuatro grupos físicos, distinguir desconocimiento de delegación; no usar checklist vacío como verificación. |
| US-015 | Recomendación | **A** | T: etiquetar preliminar, explicar por qué y permitir refinar. |
| US-016 | Recomendación | **S** | S/E: separar elegibilidad, cálculo de ranking, justificación y manejo de datos no comparables. |
| US-017 | Recomendación | **A** | I/T: top1 idéntico a primero del ranking, pero discrepancia con «mostrar todos PN» pendiente de decisión. |
| US-018 | Recomendación | **A** | S: enumeración exhaustiva de PN y tope 3 fichas; definir paginación en F3/F4. |
| US-019 | Visualización | **S** | S: tabla 3, dual 2 y política de comparabilidad; probar cada vista. |
| US-020 | Visualización | **A** | I: highlights derivan semántica de ranking, no de un simple max/min general. |
| US-021 | Visualización | **A** | N: gráficos son condicionales, nunca requisito de mostrar gráfico para todo escenario. |
| US-022 | Contexto | **S** | S/E: referencias, prioridad de contexto, cambio de modelo, ambigüedad, persistencia. |
| US-023 | Contexto | **A** | I: fuente conceptual es PDFs; PDF eléctrico único para números del catálogo. |
| US-024 | Contexto | **S** | S: conversión de unidades, fórmulas autorizadas, precisión y redondeo en pruebas separadas. |
| US-025 | Contexto | **T** | T/S: matriz transversal de categorías de error/abstención para las 3 pantallas. |
| US-026 | Contexto | **T** | T: política de idioma de salida aún abierta, nunca afecta cifras. |
| US-027 | Resiliencia | **T** | T: QA transversal de estados por pantalla; no ANR. |
| US-028 | Resiliencia | **S** | S: caché tras login/logout/switch, historial offline, borrado local. |
| US-029 | Resiliencia | **S** | S/E: experiencia de estado y orden; job queue PostgreSQL es habilitador en F3. |
| US-030 | Debug | **A** | I/T: developer sólo trazas propias y sin secretos; al borrar ya no están. |
| US-031 | Datos | **E** | V: habilitador técnico obligatorio del assessment; mantener evidencia independiente. |
| US-032 | Entrega | **E** | V: habilitador de reproducibilidad, no reducir a una UI story. |

## 4. Inventario funcional y criterios de aceptación preliminares por historia

El usuario aprobó el **comportamiento funcional** de US-001…US-032. Lo que se añade aquí son condiciones de prueba propuestas para dejarlo testable; las que exigen decisiones nuevas quedan señaladas como abiertas.

### US-001 — Iniciar sesión con credenciales
**Actor:** Usuario · **Área:** Identidad · **Clase:** A.  **Resultado:** Credenciales válidas habilitan sesión autorizada; inválidas no autentican; passwords nunca visibles ni en claro.

- **AC-001-01:** Con credenciales válidas, acceso a recursos propios; con inválidas, respuesta neutra y ninguna sesión.
- **AC-001-02:** Un token caducado, revocado o manipulado no autoriza acceso.

### US-002 — Acceder exclusivamente a datos propios
**Actor:** Usuario · **Área:** Identidad · **Clase:** T.  **Resultado:** Endpoints de listar, leer, titular, eliminar y continuar niegan recursos ajenos aun con ID conocido.

- **AC-002-01:** Con ID ajeno, GET/POST/PATCH/DELETE de conversación son denegados sin datos filtrados.
- **AC-002-02:** Un modelo o herramienta no puede saltarse los permisos del endpoint.

### US-003 — Acceder a pantalla Debug propia
**Actor:** Developer · **Área:** Identidad · **Clase:** A.  **Resultado:** UI de dev visible solo rol developer; backend valida rol Y propiedad para cada traza.

- **AC-003-01:** Cuenta normal no ve navegación Debug ni consulta sus endpoints.
- **AC-003-02:** Developer accede a trazas propias; developer A no accede a trazas de B.

### US-004 — Crear conversación
**Actor:** Usuario · **Área:** Conversaciones · **Clase:** A.  **Resultado:** POST sin session_id crea sesión del owner, responde ID estable y asocia primer turno.

- **AC-004-01:** POST sin session_id + query crea conversación/turno del usuario y devuelve session_id + answer en éxito.
- **AC-004-02:** Reintento con la misma clave idempotente no duplica un nuevo diálogo.

### US-005 — Listar conversaciones
**Actor:** Usuario · **Área:** Conversaciones · **Clase:** A.  **Resultado:** Devuelve solamente conversaciones propias con título y fecha; paginación/orden exactos por cerrar.

- **AC-005-01:** Lista sólo propias; títulos y fecha coherentes tras reinicio.
- **AC-005-02:** Los títulos se descifran únicamente después de filtrar por owner.

### US-006 — Reanudar conversación
**Actor:** Usuario · **Área:** Conversaciones · **Clase:** A.  **Resultado:** Tras reinicio, mensajes, contexto confirmado y referencias vigentes se recuperan sin mezclar usuarios.

- **AC-006-01:** Tras restart, pregunta de seguimiento refiere al mismo PN sin repetición de usuario.
- **AC-006-02:** Cambiar de usuario no reutiliza contexto del anterior.

### US-007 — Renombrar conversación
**Actor:** Usuario · **Área:** Conversaciones · **Clase:** A.  **Resultado:** Autoriza al owner, valida título y persiste; título se protege en almacenamiento.

- **AC-007-01:** Owner puede renombrar y ver cambio tras reinicio; usuario ajeno no.
- **AC-007-02:** El nuevo título no aparece en claro en una copia aislada de DB.

### US-008 — Eliminar conversación y contenido asociado
**Actor:** Usuario · **Área:** Conversaciones · **Clase:** S.  **Resultado:** Tras éxito de borrado, desaparecen mensajes, estado, checkpoints, trabajos y trazas detalladas activos; caché sincronizado; proceso pendiente no revive sesión.

- **AC-008-01:** Borrar conversación con ejecución completada elimina mensajes, estado, checkpoints, trazas detalladas activas y caché.
- **AC-008-02:** Borrar durante cola/inferencia cancela o invalida persistencia tardía; la conversación no reaparece.

### US-009 — Buscar conversaciones por título
**Actor:** Usuario · **Área:** Conversaciones · **Clase:** A.  **Resultado:** Sólo títulos propios, protegidos en DB; acceso autorizado antes de descifrado controlado; nunca busca cuerpos.

- **AC-009-01:** Búsqueda por título no retorna conversaciones de otros usuarios ni busca texto de mensajes.
- **AC-009-02:** Caso/tildes/paginación queda abierto; no exponer título en texto claro de DB/logs.

### US-010 — Consultar Base Part Number exacto
**Actor:** Técnico · **Área:** Consulta · **Clase:** A.  **Resultado:** Sin sustituciones automáticas; los valores variantes se etiquetan por servicio/frecuencia o se solicita aclaración.

- **AC-010-01:** PN exacto muestra valores condicionados por servicio/frecuencia cuando corresponde, sin reemplazar PN similar.
- **AC-010-02:** PN bien formado ausente de dataset informa ausencia sin declarar producto inexistente comercialmente.

### US-011 — Buscar actuadores por filtros
**Actor:** Técnico · **Área:** Consulta · **Clase:** S.  **Resultado:** AND/OR/NOT, grupos, intervalos y unidades sin alterar semántica; no incluir equipos fuera de filtros.

- **AC-011-01:** A AND (B OR C) produce el conjunto conforme a la agrupación y NOT preserva exclusiones.
- **AC-011-02:** Un intervalo con unidad diferente se normaliza de forma determinista o se solicita aclaración.

### US-012 — Ver interpretación de consulta
**Actor:** Usuario · **Área:** Consulta · **Clase:** T.  **Resultado:** Muestra intención, criterios, origen, descartados y formato previsto cuando aplique; no expone tool names.

- **AC-012-01:** Consulta no ambigua muestra interpretación sin confirmación bloqueante.
- **AC-012-02:** Criterios ignorados, supuestos o delegados se distinguen de hechos documentados.

### US-013 — Corregir o confirmar un plan
**Actor:** Usuario · **Área:** Consulta · **Clase:** S.  **Resultado:** Aprobación de versión N no aplica a N+1; evita ejecución de plan ambiguo o no autorizado.

- **AC-013-01:** Plan N aprobado no ejecuta N+1 tras corregir criterio.
- **AC-013-02:** Confirmación duplicada no produce dos ejecuciones.

### US-014 — Saber qué falta para recomendar
**Actor:** Ingeniero · **Área:** Recomendación · **Clase:** A.  **Resultado:** Señala ausencias en entorno, alimentación, servicio y torque; delegación de preferencias no verifica condiciones físicas.

- **AC-014-01:** Falta torque requerido: se solicita o reconoce ausencia de dato físico, sin inventarlo tras «elige tú».
- **AC-014-02:** Los cuatro grupos son evaluados individualmente antes de etiquetar recomendación.

### US-015 — Explorar candidatos preliminares
**Actor:** Ingeniero · **Área:** Recomendación · **Clase:** A.  **Resultado:** Los candidatos muestran límites e información pendiente; se pueden refinar sin reiniciar conversación.

- **AC-015-01:** Resultado preliminar identifica criterios no verificados y permite seguimiento para completar.
- **AC-015-02:** No utiliza términos de garantía de compatibilidad integral.

### US-016 — Obtener ranking justificable
**Actor:** Ingeniero · **Área:** Recomendación · **Clase:** S.  **Resultado:** Filtra por restricciones verificables y ordena lexicográficamente según prioridades; evidencia y límites visibles.

- **AC-016-01:** Todos los recomendados cumplen los filtros duros y se aplica prioridad textual explícita incluso al final de frase.
- **AC-016-02:** Igualdad final resuelta por Base Part Number; N/A no se convierte en 0 para ordenar.

### US-017 — Recibir top-1 solicitado
**Actor:** Ingeniero · **Área:** Recomendación · **Clase:** A.  **Resultado:** Aplica el mismo ranking que para N resultados; no escoge otro criterio al pedir uno.

- **AC-017-01:** Top-1 coincide con primer elemento del ranking completo para mismas condiciones.
- **AC-017-02:** La política de mostrar o no otros PN al pedir uno sigue abierta.

### US-018 — Conocer coincidencias y fichas relevantes
**Actor:** Usuario · **Área:** Recomendación · **Clase:** A.  **Resultado:** Para búsquedas lista todos PN elegibles (presentación/scroll por definir) y como máximo tres fichas; cero coincidencias explícito.

- **AC-018-01:** Muestra lista nominal completa del conjunto de coincidencias y máximo 3 fichas en respuesta común.
- **AC-018-02:** Consulta sin coincidencias informa 0 con filtros aplicados.

### US-019 — Comparar productos
**Actor:** Usuario · **Área:** Visualización · **Clase:** S.  **Resultado:** Tabla de hasta tres y vista dual de dos; condiciones y unidades expuestas; no compara como equivalentes métricas heterogéneas.

- **AC-019-01:** Se muestran 3 fichas y selector dual; las cifras y condiciones técnicas coinciden con registros.
- **AC-019-02:** FLA de alimentaciones heterogéneas puede visualizarse sin concluir menor consumo de energía.

### US-020 — Comprender las mejores métricas
**Actor:** Usuario · **Área:** Visualización · **Clase:** A.  **Resultado:** Highlights siguen semántica de criterio y no hacen ganador a datos ausentes o incomparables.

- **AC-020-01:** Menor velocidad en segundos se destaca como más rápido sólo en condiciones compatibles.
- **AC-020-02:** N/A y no documentado no generan «ganadores» ni barras cero.

### US-021 — Ver gráfica relevante
**Actor:** Usuario · **Área:** Visualización · **Clase:** A.  **Resultado:** Barras/multibarras opcionales de misma magnitud y condiciones comparables, con valores accesibles; no tortas ni histogramas.

- **AC-021-01:** Barras se ofrecen sólo para métricas/condiciones homogéneas; valor numérico siempre accesible.
- **AC-021-02:** Si no hay datos comparables, se omite gráfico o se indica motivo.

### US-022 — Continuar preguntas multi-turno
**Actor:** Usuario · **Área:** Contexto · **Clase:** S.  **Resultado:** Referencia el primero/segundo, modelo anterior y criterio previo correctamente; pide aclaración si hay ambigüedad.

- **AC-022-01:** «el segundo de la lista» refiere al orden efectivamente presentado, incluso tras reabrir sesión.
- **AC-022-02:** Si dos referentes plausibles, se pregunta sin cambiar silenciosamente de modelo.

### US-023 — Recibir explicaciones documentadas
**Actor:** Usuario · **Área:** Contexto · **Clase:** A.  **Resultado:** Conceptos acotados a PDFs; información no disponible se reconoce sin invención.

- **AC-023-01:** Consulta sobre precio/temperatura fuera PDF responde abstención sin cifras inventadas.
- **AC-023-02:** Explicación conceptual se fundamenta en documentos suministrados.

### US-024 — Obtener cálculos derivados válidos
**Actor:** Usuario · **Área:** Contexto · **Clase:** S.  **Resultado:** Fórmulas deterministas autorizadas con valor fuente, unidad, precisión, condiciones y etiqueta derivada.

- **AC-024-01:** Conversión in-lbs↔Nm conserva ambas cifras originales cuando están disponibles, sin reescribir la tabla.
- **AC-024-02:** Resultado derivado indica fórmula/precisión y no pasa por dato oficial.

### US-025 — Entender mensajes de error/abstención
**Actor:** Usuario · **Área:** Contexto · **Clase:** T.  **Resultado:** Distingue PN inválido, no listado, N/A, no documentado, falta de dato, cero coincidencias y fallo técnico.

- **AC-025-01:** Mensajes específicos para N/A vs no documentado vs no listado vs fallo temporal.
- **AC-025-02:** Errores muestran salida útil al usuario sin stack trace ni detalles internos.

### US-026 — Conversar en ES/EN
**Actor:** Usuario · **Área:** Contexto · **Clase:** T.  **Resultado:** Interpreta ES/EN sin cambiar identidad de PN, cifras ni unidades; política de idioma final pendiente.

- **AC-026-01:** ES y EN producen filtros equivalentes en golden set.
- **AC-026-02:** Cambiar idioma no altera cifras, PN, unidad ni fuente.

### US-027 — Usar app responsiva
**Actor:** Usuario · **Área:** Resiliencia · **Clase:** T.  **Resultado:** Conversations, Chat y Debug manejan loading/error/empty; acciones de red no bloquean hilo principal.

- **AC-027-01:** Tres pantallas tienen loading, empty, error y retry cuando aplica; sin ANR por red.
- **AC-027-02:** La pantalla Debug no se expone a usuario sin rol.

### US-028 — Consultar mi caché de conversaciones
**Actor:** Usuario · **Área:** Resiliencia · **Clase:** S.  **Resultado:** Offline permite leer historial previo autorizado, no inferir; cambio de usuario purga caché anterior y logout impide lectura.

- **AC-028-01:** A puede consultar su historial cacheado sin conexión; no enviar nuevas preguntas offline.
- **AC-028-02:** Tras switch A→B se purga A; logout no permite leer A.

### US-029 — Enviar mensajes concurrentes sin duplicar
**Actor:** Usuario · **Área:** Resiliencia · **Clase:** S.  **Resultado:** Orden persistido por sesión, idempotencia de reintentos y estados visibles; sesiones distintas procesables concurrentemente.

- **AC-029-01:** T2 no corre con contexto obsoleto anterior a T1 si ambos se aceptan sobre misma sesión.
- **AC-029-02:** Reintento mismo ID no crea doble mensaje; proceso interrumpido sigue política de recuperación a definir.

### US-030 — Inspeccionar ejecución por respuesta
**Actor:** Developer · **Área:** Debug · **Clase:** A.  **Resultado:** Ver llamadas, parámetros saneados, datos devueltos, errores y latencia solo propias; nada de credenciales/tokens.

- **AC-030-01:** Developer ve herramientas/parámetros/resultados/tiempos por answer sin secretos ni datos de otro owner.
- **AC-030-02:** Al borrar conversación, su traza deja de estar disponible.

### US-031 — Reproducir ingesta del PDF oficial
**Actor:** Responsable de datos · **Área:** Datos · **Clase:** E.  **Resultado:** Pipeline versionado y validado contra original, SHA-256, N/A y notas preservados, reingesta sin duplicados.

- **AC-031-01:** Rerun del pipeline no genera duplicados; documento original y versión vinculados a filas.
- **AC-031-02:** 24V AC/DC On/Off vs 24V DC Modulating y asteriscos/notas permanecen diferenciados.

### US-032 — Reproducir proyecto desde repositorio
**Actor:** Evaluador · **Área:** Entrega · **Clase:** E.  **Resultado:** Monorepo backend/app, Dockerfile, Compose, .env.example, README y configuración Kiro, paso a paso.

- **AC-032-01:** Evaluador de entorno limpio inicia backend+Postgres y compila app siguiendo README.
- **AC-032-02:** Repo contiene placeholders y configuración del AI coding assistant; no expone claves.

## 5. Nuevas historias / verificaciones sugeridas (NO aprobadas todavía)

| ID provisional | Por qué falta | Aceptación propuesta | Impacto si se descarta |
|---|---|---|---|
| **US-033** Cierre de sesión y revocación | US-001 sólo describe login, pero el flujo aprobado requiere logout y separación de cachés | Una sesión cerrada no autoriza nuevas operaciones; token y caché quedan inaccesibles; cambio de usuario no expone datos previos | Queda incompleto el ciclo de identidad y protección móvil |
| **US-034** Entrega de respuesta estructurada | El assessment exige `answer` y la app necesita comparar sin parsear texto generado por LLM | Respuesta conserva `session_id`/`answer` y agrega un bloque tipado con referencias a productos/condiciones; Android representa cifras exactas sin extraerlas del texto | Riesgo de parsing frágil o cifras reconstruidas por el cliente |
| **US-035** Borrado frente a trabajos pendientes | US-008 y US-029 no cubren explícitamente la carrera delete ↔ worker | Si se elimina sesión con job aceptado, ningún worker posterior recrea mensajes, sesión ni trazas; cliente recibe estado coherente | Resurrección de datos borrados y violación de privacidad |

**Nota:** US-035 puede terminar como conjunto de pruebas bajo US-008/US-029, en lugar de una historia independiente; conservar la obligación es más importante que el número de historias.

## 6. Habilitadores técnicos separados de historias de usuario (alcance ya aprobado salvo indicación)

| ID | Habilitador | Cubre | Resultado esperado | Fuente |
|---|---|---|---|---|
| EN-01 | Ingesta técnica y Golden Set | US-010/011/016/024/031 | Extracción, verificación humana de tabla, unidades, notas, N/A, idempotencia, SHA-256. | Assessment pp.2–4,6 |
| EN-02 | Herramientas LangChain tipadas | US-010/011/016/030 | ≥1 tool real consulta PostgreSQL, validación de parámetros, sin SQL arbitrario generado. | Assessment pp.3–4 |
| EN-03 | Persistencia de conversaciones y estado | US-004/006/013/022/029 | Separar historial, estado de dominio, checkpoints, trazas y asociar owner. | Assessment pp.3–4 |
| EN-04 | Serialización duradera por sesión | US-008/013/029 | Aceptación durable, orden por sesión, deduplicación, reintento/recuperación; respetar contrato fijo. | Decisión D-019 |
| EN-05 | Cifrado y gestión de claves | US-001/007/008/009/028 | Argon2id/TLS/AES-256-GCM/Keystore; qué datos cifrar, backups, claves y revocación. | Decisión D-027 |
| EN-06 | Protección de endpoints y tools | US-002/003/009/030 | RBAC + propiedad, sanitización de traces y protección de secretos. | Assessment pp.4–5; D-010 |
| EN-07 | Contrato de respuesta y errores | US-010..030; US-034 propuesta | `session_id`/`answer` conservados; estructuras de producto, error/estado y trazas sólo vía endpoint autorizado. | Assessment p.3–4 |
| EN-08 | Android almacenamiento y navegación | US-003/005/019/021/027/028 | Tres pantallas; cache de owner; UI reactiva; comparativas y estados. | Assessment pp.4–5 |
| EN-09 | Observabilidad/evals/precios | US-016/022/025/030 | Golden set, tool traces, pruebas adversariales, costes OpenRouter ≤USD6. | Decisiones D-009/025 |
| EN-10 | Entrega reproducible | US-031/032 | Monorepo, backend+DB Compose, README, .env.example, configuración Kiro; reproducción limpia. | Assessment p.6 |

**Observación de alcance, actualizada v0.3:** login **y autorregistro de cuentas `user` desde Android** son P0 por decisión expresa del candidato. Developers únicamente provisionados fuera de app; voz sigue diferida. Gráficos de barras son condicionales a valor y comparabilidad, no obligatorios en cada consulta.

## 7. Escenarios QA aprobados con forma verificable

| ID | Atributo | Estímulo/entorno | Respuesta esperada | Criterio observable |
|---|---|---|---|---|
| QA-01 | Exactitud técnica | Datos/evals Golden Set cotejado contra tablas | Sin cifras de LLM; valores con condiciones y procedencia | 0 discrepancias de valores técnicos en Golden Set; 0 N/A convertidos a 0 |
| QA-02 | Interpretación ES/EN | Consultas combinadas con negación/pronombres | Interpretación fiel o pregunta | Comparar filtros normalizados con respuestas esperadas; umbral de accuracy pendiente |
| QA-03 | Seguridad funcional | Se pide recomendación sin grupo físico | Candidatos preliminares y límites visibles | 0 recomendaciones verificadas con grupos necesarios no comprobados |
| QA-04 | Consistencia | Reinicio / mensajes simultáneos / reintentos | Turnos ordenados, deduplicados y recuperables | 0 pérdidas/duplicados en suite de reinicio y concurrencia |
| QA-05 | Rendimiento | LLM lento o backend sobrecargado | UI no bloquea y muestra estado | 0 llamadas de red en main thread; objetivos p50/p95/timeouts pendientes |
| QA-06 | Autorización | IDs ajenos/rol falso/client manipulado | Acceso denegado | Todos casos negativos de IDOR/RBAC sin exposición |
| QA-07 | Autenticación | Clave errónea/token vencido/intentos abusivos | Denegar y registrar sin secreto | Argon2id, expiración y revocación validados; límites de abuso pendientes |
| QA-08 | Privacidad cifrado/borrado | Robo copia DB / eliminación / cache | No plaintext sensible; borrar datos activos | Test de cifrado, purga activa y no resurrección por jobs; backups fase F3 |
| QA-09 | Accesibilidad | Móvil pequeño/TalkBack/datos densos | Legibilidad, foco y unidades | UI tests y contraste; Android min SDK pendiente |
| QA-10 | Robustez | PN malo, N/A, vacío, API caída | Errores específicos sin crash | Matriz de categorías cubierta en e2e |
| QA-11 | Trazabilidad | Developer inspecciona turno propio | Tool inputs/outputs/timing saneados; borrado al eliminar | 100% turnos procesados rastreables mientras existen; 0 secretos en logs/trazas |
| QA-12 | Reproducibilidad | Evaluador clona repo limpio | Puede iniciar y probar sin intervención | Checklist README+Docker+ingesta+Android en ambiente limpio |
| QA-13 | Eficiencia | Experimentos y demo | Mide uso OpenRouter y limita gasto | ≤USD6 experimentación; ≥USD4 de reserva al terminar selección |
| QA-14 | Evolutividad | Nueva edición de tabla | Ingesta versionada y regresión | Prueba de cambio de fuente sin alterar contrato cliente; procedimiento pendiente |
| QA-15 | Integridad artefactos | Modificación no aprobada de PDF/manifest | Rechaza mismatch hash | SHA-256 contra hash de referencia confiable y test de alteración |

**Targets no aprobados:** p50/p95, timeouts, accuracy de intención y mínimo SDK. No se inventan números. 0 discrepancias significa **en el conjunto auditado y los casos verificados**, no prueba matemática de infalibilidad del LLM en todo input futuro. Datos de requerimientos suministrados por usuario y derivados se presentan como tales, sin atribuirlos al catálogo oficial.

## 8. Matriz assessment → requisitos → tests/evidencia

| Obligación fuente | Assessment | Historias | Habilitador | Evidencia / test |
|---|---|---|---|---|
| Objetivo: consulta PN exacto | pp.1,3 | US-010, US-022 | EN-01/02/03 | AC-010, AT-01, Golden Set |
| Objetivo: recomendación por requisitos | pp.1–3 | US-014…018 | EN-01/02/07 | AC-014..018, AT-03/04 |
| FastAPI y contrato POST obligatorio | p.3 | US-004, US-006, US-029; US-034 propuesto | EN-03/04/07 | Contract test + restart + respuesta con answer |
| LangChain + herramienta personalizada tabular | p.3–4 | US-010/011/016/030 | EN-02 | Tool call real, argumentos y resultado en Debug |
| Pipeline desde PDF y procesado | pp.3,6 | US-031 | EN-01 | re-run ingesta, cotejo visual y checksum |
| PostgreSQL local/Compose | pp.4,6 | US-006, US-031, US-032 | EN-03/10 | Docker limpio y DB persistida |
| Conversación multi-turno y reinicios | pp.3–4 | US-006, US-022, US-029 | EN-03/04 | AT-09 + reinicio backend |
| PN inválido, missing, ambigüedad, 0 matches | p.3,6 | US-010/011/025 | EN-02/07 | matriz de casos negativos e2e |
| Números técnicos sólo PDF fuente | pp.2,4 | US-010/016/019/020/024 | EN-01/07 | QA-01, AT-01/06/07, Golden Set |
| Conversations screen | p.4 | US-004..009, US-027/028 | EN-08 | navegación lista/nueva/reabrir/estado error |
| Chat screen y datos comparables, sin tools | p.4 | US-012/019/020/021, US-025 | EN-07/08 | UI test 3 columnas, dual 2, sin internals |
| Developer Debug screen herramientas/parámetros/resultados | p.4 | US-003/030 | EN-06/08/09 | rol, owner, visita a traza, redacción de secretos |
| Loading/errors todas pantallas | p.5 | US-025/027 | EN-08 | UI tests empty/loading/error/retry en 3 pantallas |
| Login opcional seleccionado | p.5 | US-001/002/003; US-033 propuesto | EN-05/06 | login, logout, usuarios precargados si se escogen |
| Voz opcional excluida | p.5 | No implementada | — | README explica elección |
| Un repo, Dockerfile, Compose, .env.example, README | p.6 | US-032 | EN-10 | checklist en entorno limpio |
| Config asistente código incluida | p.6 | US-032 | EN-10 | carpeta Kiro y documentación verdadera |
| Una semana, reproducibilidad y casos propios | p.6 | US-025/031/032 | EN-09/10 | plan de entrega y suites sin pasos implícitos |

## 9. Matriz adicional: 15 escenarios QA y su evidencia primaria

| QA | Historias cubiertas | Evidencia prevista |
|---|---|---|
| QA-01 | US-010/011/016/019/024/031 | Golden set con revisión visual e invariantes de fuente |
| QA-02 | US-011/012/022/026 | Evals ES/EN, negación, OR, ambigüedad y cambios de idioma |
| QA-03 | US-014/015/016/017 | Casos preliminar/verified y requisitos delegados |
| QA-04 | US-006/008/013/022/029 | Restart, interrupción, reintento, delete vs job |
| QA-05 | US-027/029 | UI thread/progress y carga con latencia parametrizable |
| QA-06 | US-001/002/003/008/009/030 | Tests IDOR de todos los recursos, RBAC y caché entre usuarios |
| QA-07 | US-001; US-033 propuesto | Credenciales, expiración, revocación, rate limit a definir |
| QA-08 | US-007/008/009/028/030 | DB exfil aislada, ciphertext, purge activa, key separation |
| QA-09 | US-019/020/021/027 | Compose UI tests 3 productos, dual, contraste/TalkBack |
| QA-10 | US-010/011/015/025/027 | Matriz errores sin crash |
| QA-11 | US-003/030 | Traza por respuesta, secretos saneados, eliminación de traces |
| QA-12 | US-031/032 | Reproducir Compose, ingesta, Android y demo desde limpio |
| QA-13 | US-030/032 | Ledger de gasto/modelos, mocks y gate USD6/USD4 |
| QA-14 | US-031 | Ingesta versionada y simulación de segunda edición |
| QA-15 | US-031 | Hash aprobado/alteración de PDF/artefactos |

## 10. Matriz de casos de aceptación clave (Given–When–Then sin código)

| ID | Riesgo | Escenario |
|---|---|---|
| AT-01 | Lookup contextual | Dado PN con dos servicios documentados, cuando pregunto torque sin servicio, entonces ambos resultados se etiquetan o se pregunta si resultan ilegibles. |
| AT-02 | Filtros lógicos | Dado 220 V AND (Weatherproof OR Explosionproof), cuando filtro, entonces no aparecen modelos fuera de 220 V por interpretación errónea. |
| AT-03 | Delegación física | Dado torque de instalación desconocido, cuando pido «elige tú», entonces se muestran sólo candidatos preliminares. |
| AT-04 | Ranking | Dado cuatro grupos verificados y prioridad explícita al final de frase, cuando ordeno, entonces la prioridad explícita precede al orden de aparición textual. |
| AT-05 | Versionado plan | Dado plan N aprobado, cuando lo edito a N+1, entonces su aprobación anterior no ejecuta N+1. |
| AT-06 | Comparación | Dado FLA de alimentaciones no equivalentes, cuando comparo, entonces muestro cifras/condiciones, no «menor consumo energético». |
| AT-07 | N/A | Dado N/A, cuando renderizo tabla/gráfico, entonces no aparece como 0 ni como barra. |
| AT-08 | Fuera documento | Dado consulta precio no documentado, cuando respondo, entonces indico límite de fuente sin inventar cifra. |
| AT-09 | Cola | Dado T1 y T2 simultáneos en la misma sesión, cuando procesan, entonces T2 usa contexto confirmado de T1, sin doble efecto tras reintento. |
| AT-10 | IDOR | Dado owner A y session ID de B, cuando A solicita mensajes/Debug, entonces backend niega recurso. |
| AT-11 | Caché | Dado logout A y login B, cuando B intenta ver historial A, entonces no puede leerlo y la caché anterior se purga. |
| AT-12 | Ingesta 24 V | Dado On/Off 24 V AC/DC y Modulating 24 V DC, cuando se ingesta, entonces el sistema diferencia ambas fuentes. |
| AT-13 | Borrado y trazas | Dado conversación con trazas, cuando owner borra y servidor confirma, entonces mensajes, estado, checkpoints y trazas detalladas ya no son consultables. |
| AT-14 | Carrera borrado/job | Dado job aceptado en conversación, cuando se borra antes de que termine, entonces su ejecución tardía no recrea conversación ni trazas. |
| AT-15 | Búsqueda título | Dado texto del mensaje que no está en título, cuando busco ese texto, entonces no retorna esa conversación; sí retorna por su título autorizado. |
| AT-16 | Cifrado título | Dado copia de PostgreSQL sin claves, cuando se inspeccionan títulos/contenido cifrados, entonces no se obtiene texto claro; no se prometen garantías sobre backups/proveedor. |
| AT-17 | Cifra narrativa | Dado salida de LLM con cifra no respaldada, cuando se construye answer, entonces no se presenta como propiedad técnica del actuador. |
| AT-18 | Top1 | Dado criterios idénticos, cuando pido top-1 y top-3, entonces top-1 coincide con primer ranking. Política de listar otros PN está abierta. |

## 11. Decisiones abiertas que sí necesitan aprobación antes de congelar F0

| ID | Decisión a tomar | Opciones no vinculantes | Efecto sobre Specs |
|---|---|---|---|
| O-01 | ¿US-033 logout/revocación queda como historia formal o subcaso US-001? | Historia aparte / subcaso obligatorio | Alcance del ciclo de sesión y Android |
| O-02 | ¿US-034 contrato estructurado queda formal? | Historia aparte / criterio US-019 + EN-07 | Diseño del REST y de Compose |
| O-03 | ¿US-035 borrado en cola queda formal? | Historia aparte / subcaso US-008+US-029 | Semántica de cancelación, idempotencia y cola |
| O-04 | Si usuario pide «solo uno», ¿listar otros PN elegibles? | Solo ganador + total / ganador + lista nominal de todos | Diseño Chat y backend |
| O-05 | ¿Cuentas precargadas o autogestión registro? | Preloaded test users / registro adicional | Alcance autenticación y documentación |
| O-06 | ¿Idioma de salida? | Seguir idioma de último mensaje / preferencia por conversación | Estado y UX bilingüe |

**No deberían bloquear F1:** política de recuperación de jobs, shape de endpoints extra, minSDK, almacenamiento/cifrado específico de Android, métricas p95, tecnología exacta de OCR: se tratarán en F1/F3/F4/F5 según riesgos, con alternativas y aprobación del candidato.

## 12. Criterios de salida F0.3 (propuestos para aprobación)

- [x] Las ocho áreas funcionales aprobadas están representadas.
- [x] US-001…US-032 conservadas y revisadas bajo INVEST.
- [x] Los habilitadores EN-01…EN-10 están diferenciados del valor para usuario.
- [x] QA-01…QA-15 conectados con evidencias y pruebas.
- [x] Obligaciones de assessment vinculadas a historias y evidencia, incluidas pantalla Debug, OpenRouter, ingesta, backend y reproducibilidad.
- [x] Búsqueda sólo por título y eliminación de trazas detalladas ratificadas y coherentes en la línea base.
- [ ] O-01…O-06 deliberadas/ratificadas por el candidato; no inferir respuestas.
- [ ] Documento de cierre F0 expresamente aprobado antes de pasar a F1.

**Próxima etapa propuesta:** cerrar O-01…O-06 y continuar F1 con inventario/cotejo por página, eligiendo pipeline ETL, modelo de dominio y representación de valores N/A, notas y distintas condiciones de servicio/alimentación/frecuencia. No generar aún las Specs ni escribir código de producto.


---

## 13. Cierre de F0 — registro definitivo de propuestas (v0.3)

**Autorización:** aprobación explícita del candidato. Las secciones §5 y §11 describen **alternativas históricas**, ahora resueltas como sigue:

| Elemento | Estado vigente | Alcance aprobado |
|---|---|---|
| US-033 | **APROBADA — nueva historia** | Logout, expiración/revocación de sesión/tokens y caché inaccesible tras logout/cambio de usuario. |
| US-034 | **APROBADA — nueva historia** | Respuesta estructurada además de `session_id` y `answer`, sin parseo de texto del LLM para cifras técnicas. |
| US-035 | **APROBADO — escenario transversal** | Borrado con trabajo pendiente, vinculante para US-008 y US-029; NO se cuenta como historia independiente. |
| US-036 | **APROBADA — nueva historia** | Usuario se registra desde Android con cuenta **siempre `user`**; no registro/elevación de `developer` por app/API pública. |
| Top-1 | **APROBADO** | Solo ganador + total de elegibles, sin lista nominal de otros en ese modo; ranking común reproducible. |
| Cuentas de prueba | **APROBADO** | Precargar al menos una `user` y una `developer` por procedimiento de demo reproducible; developers solo mediante provisión administrativa. |
| Idioma salida | **APROBADO** | Idioma del último turno, salvo petición explícita de cambio. |

## 14. Historias aprobadas que se añaden (al catálogo inicial US-001…US-032)

### US-033 — Cerrar sesión y revocar acceso
**Actor:** usuario autenticado · **Área:** identidad y acceso · **Prioridad:** P0.

- **AC-033-01:** Una vez confirmada la salida, las credenciales de sesión revocadas no autorizan nuevas solicitudes; definir en F3 el modelo concreto de revocación y expiración.
- **AC-033-02:** El usuario que cerró sesión no puede visualizar conversaciones en caché; al iniciar otro usuario, se purga el caché del usuario anterior.
- **AC-033-03:** La revocación no elimina de forma arbitraria las conversaciones persistidas; pueden recuperarse en un login posterior autorizado.

### US-034 — Recibir respuesta técnica estructurada
**Actor:** usuario final · **Área:** visualización y contratos · **Prioridad:** P0.

- **AC-034-01:** `POST /api/conversation` mantiene en la respuesta los campos contractuales `session_id` y `answer` cuando devuelve la respuesta final.
- **AC-034-02:** Datos oficiales de productos/comparativas se entregan en bloques tipados con unidades, contextos y procedencia; la app no obtiene cifras haciendo parsing de `answer`.
- **AC-034-03:** Internals como nombres de tools, parámetros y resultados sin sanear no aparecen en la respuesta pública del usuario; sólo se exponen por APIs de Debug sujetas a RBAC+owner.

### US-036 — Crear cuenta pública de usuario
**Actor:** visitante no autenticado · **Área:** identidad y acceso · **Prioridad:** P0.

- **AC-036-01:** Desde la app Android, el visitante puede crear una cuenta con credenciales que cumplen las reglas de validación aprobadas en F3.
- **AC-036-02:** El servidor asigna **siempre rol `user`**; un campo de rol o permiso manipulado por cliente no permite obtener `developer`.
- **AC-036-03:** No existe registro o escalamiento a developer desde la app ni desde endpoint público; se documenta el procedimiento administrativo para provisionar un developer de prueba.
- **AC-036-04:** No se almacena una contraseña en texto plano; aplicar Argon2id y política de protección de credenciales.
- **AC-036-05:** El registro soporta errores de forma segura (correo ya registrado, entrada inválida y fallos de backend) sin filtrar información sensible. Política de verificación de email y control antiabuso aún por decidir en F3.

### US-008 / US-029 — Subescenario obligatorio AC-DELETE-RACE
- **Dado** un trabajo de agente aceptado, **cuando** el propietario elimina la conversación, **entonces** cualquier trabajo tardío no la recrea ni vuelve a insertar mensajes, checkpoints o trazas detalladas.
- Las políticas de cancelación, deduplicación y trabajo duradero se diseñarán en F3; la semántica funcional ya está aprobada.

## 15. Matriz de trazabilidad incremental F0 v0.3

| Requisito | Evidencia del assessment / decisión | Historia / habilitador | Prueba de aceptación necesaria |
|---|---|---|---|
| Login opcional elegido y autorregistro adicional | Assessment p.5 + elección expresa | US-001, US-002, US-033, **US-036**, EN-05/06 | Registro `user`; intento de privilegio `developer` denegado; login/logout/revocación; owner cross-account denegado. |
| Cuentas de prueba | Assessment p.5, requisito si hay login según elección | US-001, **US-036**, EN-10 | Seed repetible e idempotente; developer no registrable públicamente; README indica credenciales de demo locales de forma segura. |
| API obligatoria + comparativa estructurada | Assessment pp.3–4 | **US-034**, EN-07 | `session_id`/`answer` conservados; UI renderiza métricas desde campos tipados, con provenance y sin tools. |
| Borrado y colas | Aprobación de candidato; coherencia y privacidad | US-008 + US-029, EN-04 | Carrera delete vs worker sin reinserción ni acceso a trazas eliminadas. |
| Top-1 | Decisión expresa F0 | US-017, US-018 | Igual primer lugar que top-3; incluir total, no enumerar PN restantes. |
| Idioma salida | Decisión expresa F0 | US-026 | Mensajes ES/EN alternados y preferencia explícita sin alterar números. |

## 16. Gate de F0 aprobado

- [x] 8 áreas funcionales y 15 atributos de calidad en línea base.
- [x] US-001…032 preservadas y examinadas bajo INVEST.
- [x] US-033, US-034 y US-036 añadidas; US-035 como escenario transversal bajo historias existentes.
- [x] Enlaces a requisitos obligatorios, pruebas y habilitadores EN-01…EN-10.
- [x] Política de top-1, cuentas precargadas, auto-registro limitado y bilingüismo aprobada.
- [x] El candidato autorizó expresamente cerrar F0 y avanzar a F1.

**Resultado:** 35 historias de identificadores vigentes (`US-001`…`US-034` y `US-036`, con `US-035` reservado para subcaso transversal), 15 QA y habilitadores técnicos definidos a nivel de alineación. Estos son insumos para Kiro, **no Specs**. Las descomposiciones finales en criterios INVEST estrictos serán responsabilidad del trabajo posterior de Kiro bajo las restricciones aprobadas.
