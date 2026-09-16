"""Whole-surface contracts: the OpenAPI document builds, operationIds (= MCP
tool names) are unique, and every operation lives under /api/v1."""

import collections
import warnings

from dollygrip.server import create_app


def _operations():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # FastAPI warns on duplicate operationIds
        spec = create_app().openapi()
    return [(m.upper(), p, o) for p, methods in spec["paths"].items() for m, o in methods.items()]


def test_openapi_builds_with_unique_operation_ids():
    ops = _operations()
    assert len(ops) > 250
    counts = collections.Counter(o["operationId"] for _, _, o in ops)
    assert [n for n, c in counts.items() if c > 1] == []


def test_everything_is_versioned():
    for method, path, _ in _operations():
        assert path.startswith("/api/v1/"), (method, path)


def test_operation_ids_are_snake_case_function_names():
    for _, _, op in _operations():
        oid = op["operationId"]
        assert oid == oid.lower() and " " not in oid and "-" not in oid, oid
