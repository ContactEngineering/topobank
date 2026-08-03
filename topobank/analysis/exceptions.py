class AnalysisTooLargeError(Exception):
    """Predicted memory of a workflow result exceeds what a worker can provide.

    The message is shown to the user in the analysis card, so it says what
    happened and what to do about it rather than quoting internals.
    """

    def __init__(self, estimate, budget):
        self._estimate = estimate
        self._budget = budget
        super().__init__(estimate, budget)

    def __str__(self):
        from django.template.defaultfilters import filesizeformat

        return (
            f"This analysis is predicted to need about {filesizeformat(self._estimate)} "
            f"of memory, more than the {filesizeformat(self._budget)} available to a "
            "single analysis, so it was not started. Running it would have exhausted "
            "the memory of the machine. Consider analysing a smaller region or a "
            "coarser version of this measurement."
        )


class SubjectNotReadyException(Exception):
    """Subject is not in SUCCESS state when triggering a workflow result."""

    def __init__(self, subject):
        self._subject = subject

    def __str__(self):
        return f"The workflow subject {self._subject} is not in SUCCESS state."
