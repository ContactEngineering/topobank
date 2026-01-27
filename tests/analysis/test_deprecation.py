import warnings

import pytest

from topobank.analysis.workflows import WorkflowImplementation


class MockSubject:
    pass


class MockAnalysis:
    def __init__(self, subject):
        self.subject = subject
        self.kwargs = {}


class DictionaryReturningWorkflow(WorkflowImplementation):
    class Meta:
        name = "dict_returning_workflow"
        implementations = {MockSubject: "mock_implementation"}

    def mock_implementation(self, analysis, **kwargs):
        return {"result": "some data"}


class NoneReturningWorkflow(WorkflowImplementation):
    class Meta:
        name = "none_returning_workflow"
        implementations = {MockSubject: "mock_implementation"}

    def mock_implementation(self, analysis, **kwargs):
        return None


def test_workflow_deprecation_warning():
    subject = MockSubject()
    analysis = MockAnalysis(subject)

    workflow = DictionaryReturningWorkflow()

    with pytest.warns(DeprecationWarning, match="Returning results from workflows is deprecated"):
        result = workflow.eval(analysis)

    assert result == {"result": "some data"}


def test_workflow_no_warning_for_none():
    subject = MockSubject()
    analysis = MockAnalysis(subject)

    workflow = NoneReturningWorkflow()

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        result = workflow.eval(analysis)

    assert result is None
