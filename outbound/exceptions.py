class TransientError(Exception):
    """Retryable error."""


class PermanentError(Exception):
    """Fatal error, no retry."""


class AlreadyProcessingError(Exception):
    """Concurrent access."""


class TransitionNotAllowed(Exception):
    """Invalid state transition attempted on OutboundMessageRequest."""
