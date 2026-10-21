from __future__ import annotations

import pytest

from sandboxd.manager import _container_path


def test_maps_relative_and_absolute_workspace_paths():
    assert _container_path(".") == "/workspace"
    assert _container_path("notes/a.txt") == "/workspace/notes/a.txt"
    assert _container_path("/workspace/notes/a.txt") == "/workspace/notes/a.txt"
    assert _container_path("notes/../a.txt") == "/workspace/a.txt"


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "/workspace/../../etc"])
def test_rejects_escape(path):
    with pytest.raises(ValueError):
        _container_path(path)
