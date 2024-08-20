from topobank.authorization.models import levels_with_access


def test_levels_with_access():
    assert levels_with_access("full") == {"full"}
    assert levels_with_access("edit") == {"edit", "full"}
    assert levels_with_access("view") == {"view", "edit", "full"}
