"""
Tests for issue #1346: AnalysisController._get_unique_kwargs must return the
true intersection of kwargs across analyses (dropping keys absent from or
differing in any analysis) without mutating any analysis's stored kwargs.
"""

from types import SimpleNamespace

from topobank.analysis.controller import AnalysisController


def _controller_with(kwargs_list):
    ctrl = AnalysisController.__new__(AnalysisController)
    ctrl._analyses = [SimpleNamespace(kwargs=k) for k in kwargs_list]
    return ctrl


def test_unique_kwargs_drops_keys_absent_from_a_later_analysis():
    unique, has_nonunique = _controller_with([{"a": 1, "b": 2}, {"a": 1}])._get_unique_kwargs()
    assert unique == {"a": 1}
    assert has_nonunique is True


def test_unique_kwargs_drops_differing_values():
    unique, has_nonunique = _controller_with(
        [{"a": 1, "b": 2}, {"a": 9, "b": 2}]
    )._get_unique_kwargs()
    assert unique == {"b": 2}
    assert has_nonunique is True


def test_unique_kwargs_keeps_all_when_identical():
    unique, has_nonunique = _controller_with([{"a": 1}, {"a": 1}])._get_unique_kwargs()
    assert unique == {"a": 1}
    assert has_nonunique is False


def test_unique_kwargs_empty_when_no_analyses():
    unique, has_nonunique = _controller_with([])._get_unique_kwargs()
    assert unique == {}
    assert has_nonunique is False


def test_unique_kwargs_does_not_mutate_source_dicts():
    first = {"a": 1, "b": 2}
    second = {"a": 9, "b": 2}
    _controller_with([first, second])._get_unique_kwargs()
    # The stored kwargs must be untouched (no aliasing / in-place deletion).
    assert first == {"a": 1, "b": 2}
    assert second == {"a": 9, "b": 2}
