"""Human manual-audit workflow and correction records (Spec 1, Req 3).

Captures reviewer identity, prior/verified values, justification, source cell
reference, and source document hash per confirmed/corrected fact, and refuses
stale-hash corrections (CORRECTION_STALE).
"""
