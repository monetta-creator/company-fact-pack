"""Schema loading + validation. All schemas share a registry so cross-file $refs resolve."""

from __future__ import annotations

import functools
import json

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from . import config


@functools.cache
def _registry() -> Registry:
    reg = Registry()
    for path in config.SCHEMAS.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        reg = reg.with_resource(path.name, Resource.from_contents(schema))
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema))
    return reg


@functools.cache
def validator(name: str) -> Draft202012Validator:
    """name: 'manifest', 'entity', 'event', 'metric_definition', 'metric_observation',
    'product', 'brief'."""
    schema = json.loads((config.SCHEMAS / f"{name}.schema.json").read_text())
    return Draft202012Validator(schema, registry=_registry())


def validate(obj: dict, name: str) -> None:
    """Raises jsonschema.ValidationError on the first failure."""
    errs = sorted(validator(name).iter_errors(obj), key=lambda e: list(e.absolute_path))
    if errs:
        e = errs[0]
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        raise ValueError(f"{name} schema violation at {loc}: {e.message}")
