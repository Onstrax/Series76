# Series 76 — paquete de alineación para Kiro (v1.0)

**Propósito:** documentos de arquitectura y requisitos para que **Kiro genere sus propias Specs y después implemente** cuando el usuario lo autorice. **No contiene código del proyecto ni Specs generadas.**

## Empezar aquí

1. Leer `01_CANONICAL_F0_F6/F6_kiro_master_alignment_v1.0.md` (precedencia, alcance, riesgos, gate).
2. Leer `02_ORIGINAL_SOURCES/assessment-en.pdf` para requisitos externos y `series_76_electric_data.pdf` para **datos numéricos autorizados**; `series_76_summary.pdf` aporta contexto.
3. Leer los siete documentos en `01_CANONICAL_F0_F6/` en orden F0→F6. El resumen F6 se puede consultar antes y después de las fases.
4. Consultar `03_SUPPORTING_REFERENCES/` para detalle del esquema, las alternativas de agentes, patrones e historia ADR. **No considerar sus propuestas preliminares superiores a la línea base canónica.** Las notas originales son históricas, no mandatos.
5. Leer `00_START_HERE/AUDIT_REPORT.md` y, una vez autorizado el trabajo con Kiro, utilizar `KIRO_START_PROMPT.md`.

## Preguntas frecuentes

**¿Hay siete documentos para pasar a Kiro?** Sí, siete canónicos, **pero se adjuntan también los tres PDFs originales**; entregar solamente los siete privaría al agente de las fuentes de requisitos y de las cifras que debe reproducir.

**¿Están cerradas F4/F5?** Sí como **diseño y plan de QA**. No existen pruebas reales ni app, backend o ETL implementados. La última decisión de UX offline está incluida en F4 v1.1 y su validación en F5 v1.1.

**¿Puedo pegar inmediatamente el prompt en Kiro?** La transferencia está preparada. La fase de **ejecución** requiere tu autorización explícita; preparar estos documentos no equivale a dicha autorización.

**¿Qué es fuente de verdad para las cifras?** Solo `series_76_electric_data.pdf`. Ningún resumen de este paquete reemplaza su extracción y auditoría.

**¿Qué ha quedado para Kiro?** Especificaciones propias, DDL/migraciones, OCR/digitalización y revisión inicial, código, pruebas/evals (con límites de gasto), README y demostración. Las decisiones esenciales ya están orientadas y justificadas.

## Integridad

`MANIFEST.json` inventaría rutas, bytes y huellas SHA-256. `SHA256SUMS.txt` contiene los hashes verificables para los archivos **de contenido** de este paquete. El manifiesto se autoexcluye de sus propias huellas para evitar ciclos de hash.
