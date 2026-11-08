"""The Pipe-and-Filter ingestion pipeline (Spec 1).

Stages: SourceInventory -> Extractor -> Reconciler -> Normalizer ->
EvidenceMapper -> Verifier -> Publisher, with ManifestBuilder and
GoldenDatasetExporter. Each stage has a typed input->output contract and emits
classified :class:`~series76_data.errors.IngestionFailure` codes rather than
silently completing.
"""
