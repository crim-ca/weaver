"""
Warnings emitted during the weaver flow.
"""


class TimeZoneInfoAlreadySetWarning(Warning):
    """Warn when trying to obtain a localized time with already defined time-zone info."""
    pass


class DisabledSSLCertificateVerificationWarning(Warning):
    """Warn when an option to disable SSL certificate verification is employed for some operations."""
    pass


class UnsupportedOperationWarning(Warning):
    """Warn about an operation not yet implemented or unsupported according to context."""
    pass


class NonBreakingExceptionWarning(Warning):
    """Warn about an exception that is handled (ex: caught in try/except block) but still unexpected."""


class MissingParameterWarning(Warning):
    """Warn about an expected but missing parameter."""
    pass
