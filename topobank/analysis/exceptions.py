from rest_framework.exceptions import APIException

class SubjectNotReadyException(APIException):
    """Subject is not in SUCCESS state when triggering a workflow result."""

    def __init__(self, subject):
        self._subject = subject

    def __str__(self):
        return f"The workflow subject {self._subject} is not in SUCCESS state."