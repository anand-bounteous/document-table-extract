"""Post-detection PII redaction pipeline.

Generates same-length realistic mock data for every detected PII span,
writes redacted text + redacted page image + an encrypted mock→original
mapping. The encrypted mapping is preserved so a downstream restore step
(out of scope for this round) can stitch real values back onto an LLM's
output.
"""

__all__ = ["RedactionArtifacts", "redact_cell"]


def __getattr__(name: str):
    if name in __all__:
        from app.pii_v2.redaction import redactor as _r
        return getattr(_r, name)
    raise AttributeError(name)
