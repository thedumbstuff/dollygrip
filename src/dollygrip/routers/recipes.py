"""POST /recipes/run - one call, a whole pipeline (see dollygrip.recipes)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..recipes import run_recipe_sync, tool_specs

router = APIRouter(prefix="/recipes", tags=["recipes"])


class RecipeStep(BaseModel):
    op: str = Field(description="Operation name = operationId in /docs (e.g. 'create_timeline', 'append_items', 'text_plus', 'add_job')")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments: path params, query params and body fields flattened together")
    name: Optional[str] = Field(default=None, description="Handle for templates in later steps: {{ steps.<name>.<path> }}")


class Recipe(BaseModel):
    steps: List[RecipeStep]
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Values the steps reference as {{ inputs.<key> }} (paths, names, ranges)")
    dry_run: bool = Field(default=False, description="Resolve templates and validate ops without calling Resolve")
    stop_on_error: bool = True


@router.get("/operations")
def recipe_operations(request: Request):
    """Every operation a recipe step may call, with its argument names."""
    specs = tool_specs(request.app)
    return {
        "operations": [
            {"op": s.name, "method": s.method, "path": s.path, "args": sorted(s.input_schema.get("properties", {})), "required": s.input_schema.get("required", [])}
            for s in specs.values()
        ]
    }


@router.post("/run")
def run(body: Recipe, request: Request):
    """Run steps in order; each step's result is available to later steps as
    `{{ steps.<name>... }}` (or `{{ last... }}`); the `inputs` block is
    `{{ inputs.<key> }}`. Steps run through the gateway
    itself, so the Resolve lock is taken per step, never across the recipe."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    return run_recipe_sync(request.app, [s.model_dump() for s in body.steps], body.dry_run, body.stop_on_error, token, body.inputs)
