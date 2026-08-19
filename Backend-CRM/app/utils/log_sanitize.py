"""Log-injection (CWE-117) guard: neutralise CR/LF in user-controlled values
before they are interpolated into log lines."""


def sfmt(value) -> str:
    """Return `value` as a single-line string safe for log interpolation."""
    return str(value).replace("\r", "\\r").replace("\n", "\\n")
