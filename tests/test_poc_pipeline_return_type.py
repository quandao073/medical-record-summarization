"""Smoke test: run_poc return type is (FinalSummary, list[SourceChunk])."""
import typing
from poc.poc_pipeline import run_poc
from src.schemas import FinalSummary, SourceChunk


def test_run_poc_return_annotation():
    # typing.get_type_hints evaluates string annotations (from __future__ import annotations)
    hints = typing.get_type_hints(run_poc)
    ret = hints.get("return")
    # Should be tuple[FinalSummary, list[SourceChunk]]
    assert ret is not None, "run_poc must have a return type annotation"
    # Check it's a tuple type
    origin = getattr(ret, "__origin__", None)
    assert origin is tuple, f"Expected tuple origin, got {origin}"
    args = getattr(ret, "__args__", ())
    assert len(args) == 2
    assert args[0] is FinalSummary
    # list[SourceChunk] is a generic alias — use == not is
    assert args[1] == list[SourceChunk], f"Expected list[SourceChunk], got {args[1]}"
