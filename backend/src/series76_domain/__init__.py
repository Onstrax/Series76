"""series76_domain — Spec 2: the deterministic domain-and-tools layer.

This package sits on top of the Spec 1 published catalog (`series76_data`) and
exposes:

* the pure domain model (:mod:`series76_domain.model`);
* a read-only typed repository port + PostgreSQL adapter
  (:mod:`series76_domain.repository`);
* the three domain operations (:mod:`series76_domain.operations`);
* the four deterministic services (:mod:`series76_domain.services`);
* the custom LangChain tool assemblies A and B (:mod:`series76_domain.tools`);
* the verified-figure-set contract consumed by Spec 4
  (:mod:`series76_domain.figures`).

Every returned number resolves to a published source cell or a deterministic
derivation over published values — this layer never invents a number. All
arithmetic is ``Decimal``; every defined non-success business outcome returns
exactly one ``SemanticFailureCode``.
"""

__version__ = "0.2.0"
