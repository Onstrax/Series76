# Auditoría documental F6 — resultado de transferencia v1.0

**Clase de revisión:** coherencia y completitud de documentos existentes, no prueba de código o de la exactitud de la extracción.

| Hallazgo | Estado | Acción y razón |
|---|---|---|
| F4 no exigía de forma inequívoca deshabilitar Enviar offline | **Corregido** | F4 v1.1: aviso persistente ES/EN, envío bloqueado, conservar borrador, sin envío automático; distinto de caída HTTP 503. |
| F5 no comprobaba explícitamente todos los comportamientos offline | **Corregido** | F5 v1.1: siete escenarios F5-OFF-01…07. |
| F0 v0.3 preservaba en secciones anteriores propuestas históricas marcadas abiertas | **Mitigado** | F0 v1.0 añade portada de precedencia; la aprobación vigente está en §13–16 y fases posteriores. El histórico se mantiene para la defensa oral. |
| Exigencia externa vs funciones adicionales aprobadas (registro, auth, cifrado, jobs) | **Delimitado** | Assessment prevalece como obligaciones externas, decisiones explícitas del usuario se mantienen como compromisos adicionales; no deben degradar la entrega mínima. |
| F1 identificadores/cifras no digitalizados ni auditados automáticamente | **Pendiente empírico** | La fuente original acompaña al paquete; extracción, 100% revisión inicial y pruebas numéricas son tarea obligatoria de implementación. |
| Compatibilidad AES-256-GCM / LangGraph / Room | **Pendiente empírico** | No afirmar compatibilidad hasta demostrar cifrado, fail-closed, restauración y borrado; no cambiar a AES-EAX silenciosamente. |
| Herramientas especializadas vs general y candidatos LLM | **Pendiente empírico** | Preferencia B y matriz multi-modelo documentadas; seleccionar ganador por pruebas con presupuesto acotado. |
| Endpoints de jobs, JSON, SQL DDL, navigation Compose | **Diseño de detalle delegado** | Kiro concretará contratos sin alterar semánticas y criterios aprobados. |
| F5 pruebas reales y cold start | **Pendiente empírico** | F5 está cerrada como plan, no ejecutada; no existen resultados que puedan calificarse como aprobados. |
| ¿F6 aprobado para iniciar ejecución? | **NO** | Paquete listo para revisión/entrega; esperar luz verde explícita. |

## Auditoría de entregables exigidos por el assessment

| Requisito | Documento de decisión | Obligación futura de evidencia |
|---|---|---|
| FastAPI/POST sync `session_id?`, `answer` | F3/F6 | OpenAPI + integración REST + restart |
| LangChain custom tool y persistencia | F2/F3 | Tests tool, integración y checkpoints |
| Ingest PDF → PostgreSQL | F1/F5 | Golden completo, replay y migraciones |
| Android tres pantallas | F4/F5 | Build + emulador + rutas Debug protegidas |
| Productos visibles estructurados | F2/F4 | Comparación y métricas condicionadas |
| Edge cases y trazas por respuesta | F0/F2/F5 | Evals, errores, abstención y Debug |
| Docker/README/repo/config de Kiro | F3/F5/F6 | Clonado y arranque reproducibles |

## Hallazgos deliberadamente NO resueltos desde el escritorio

- No se ha inspeccionado programáticamente ni corregido cada una de las 68 filas técnicas contra el PDF. No se ha certificado la unicidad global de 68 PNs; sí se dejó expresamente un gate de auditoría.
- No se ha verificado a través de ejecuciones el proveedor/modelo OpenRouter, latencia o coste. Los nombres en F2/F5 son **candidatos**, no selección final.
- No se ha probado cifrado del disco o Keystore en host Android, ni realizado análisis de vulnerabilidades real. Son exigencias a demostrar o declarar como limitaciones de infraestructura.

**Conclusión:** la línea base F0–F6 es suficiente para iniciar la especificación por Kiro una vez autorizado, siempre que el usuario acepte las verificaciones empíricas pendientes propias de la implementación.
