"""
Warnings emitted during the weaver flow.
"""


class WeaverWarning(Warning):
    """
    Base class of :class:`Warning` defined by :mod:`weaver` package.
    """


class WeaverConfigurationWarning(WeaverWarning, UserWarning):
    """
    Base class of :class:`Warning` defined by :mod:`weaver` package.
    """


class UndefinedContainerWarning(WeaverConfigurationWarning):
    """
    Warn when settings or the registry could not be resolved from an explicit container reference.
    """


class TimeZoneInfoAlreadySetWarning(WeaverWarning):
    """
    Warn when trying to obtain a localized time with already defined time-zone info.
    """


class DisabledSSLCertificateVerificationWarning(WeaverWarning):
    """
    Warn when an option to disable SSL certificate verification is employed for some operations.
    """


class UnsupportedOperationWarning(WeaverWarning):
    """
    Warn about an operation not yet implemented or unsupported according to context.
    """


class NonBreakingExceptionWarning(WeaverWarning):
    """
    Warn about an exception that is handled (ex: caught in try/except block) but still unexpected.
    """


class MissingParameterWarning(WeaverWarning):
    """
    Warn about an expected but missing parameter.
    """
