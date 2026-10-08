"""Expected extraction failures that must not enter JSON repair/retry loops."""


class UnreadableReceiptError(Exception):
    """The model cannot read the receipt reliably enough to extract it."""


class AnalysisTimeoutError(TimeoutError):
    """An extraction exceeded its configured deadline."""
