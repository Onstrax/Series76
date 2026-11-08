"""series76_data — Spec 1: data-and-ingestion.

The dependency root of the Series 76 Technical Assistant. Owns the published
catalog, the provenance/evidence model, the Pipe-and-Filter ingestion pipeline
(verified_replay + fresh_extraction), the manual-audit workflow, the 13-code
error taxonomy, and the versioned golden dataset artifact.

No module in this package invents a technical number: every published value
traces to an authorized-source cell of ``series_76_electric_data.pdf``.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
