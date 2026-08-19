"""Derive Gemini function declarations from the command registry.

Each command's Pydantic ``input_model`` is converted from its JSON schema into a
``types.Schema`` so the model sees exactly the route's real inputs. Only the
flat scalar/array subset our command inputs use is handled — intentionally, to
keep the surface small and predictable.
"""
from __future__ import annotations

from typing import Dict, Optional

from google.genai import types

from app.modules.assistant.commands import Command

_TYPE_MAP = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
    "object": types.Type.OBJECT,
}


def _to_schema(node: dict, defs: Optional[dict] = None) -> types.Schema:
    defs = defs or {}
    # Pydantic references nested models via $ref into $defs — resolve it so
    # arrays of nested models (e.g. fill_form's fields) become real objects, not
    # a fallback string.
    if "$ref" in node:
        ref_name = node["$ref"].split("/")[-1]
        target = dict(defs.get(ref_name, {}))
        if node.get("description") and "description" not in target:
            target["description"] = node["description"]
        return _to_schema(target, defs)

    # Pydantic renders Optional[X] as {"anyOf": [{...X}, {"type": "null"}]}.
    if "anyOf" in node:
        options = [s for s in node["anyOf"] if s.get("type") != "null"]
        merged = dict(options[0]) if options else {}
        if "description" in node and "description" not in merged:
            merged["description"] = node["description"]
        return _to_schema(merged, defs)

    json_type = node.get("type", "string")
    kwargs: dict = {"type": _TYPE_MAP.get(json_type, types.Type.STRING)}
    if node.get("description"):
        kwargs["description"] = node["description"]
    if node.get("enum"):
        kwargs["enum"] = [str(e) for e in node["enum"]]
    if json_type == "object":
        props = {
            name: _to_schema(sub, defs)
            for name, sub in (node.get("properties") or {}).items()
        }
        if props:
            kwargs["properties"] = props
        if node.get("required"):
            kwargs["required"] = list(node["required"])
    if json_type == "array" and node.get("items"):
        kwargs["items"] = _to_schema(node["items"], defs)
    return types.Schema(**kwargs)


def _constrain_enum(params, prop_name: str, values: Optional[list]) -> None:
    if params is None or not values:
        return
    prop = (params.properties or {}).get(prop_name)
    if prop is not None:
        prop.enum = [str(v) for v in values]


def command_to_declaration(
    command: Command,
    screen_names: Optional[list] = None,
    tour_ids: Optional[list] = None,
    entity_types: Optional[list] = None,
    form_ids: Optional[list] = None,
) -> types.FunctionDeclaration:
    schema = command.input_model.model_json_schema()
    defs = schema.get("$defs") or {}
    has_params = bool(schema.get("properties"))
    params = _to_schema(schema, defs) if has_params else None
    # Constrain choice enums per-turn to the frontend's real catalogs so the
    # model can only pick things that actually exist (no hallucinated targets).
    if command.name == "navigate_to":
        _constrain_enum(params, "screen", screen_names)
    elif command.name == "start_tour":
        _constrain_enum(params, "tour", tour_ids)
    elif command.name == "open_entity":
        _constrain_enum(params, "entity_type", entity_types)
    elif command.name == "fill_form":
        _constrain_enum(params, "form", form_ids)
    return types.FunctionDeclaration(
        name=command.name,
        description=command.description,
        parameters=params,
    )


def build_tool(
    registry: Optional[Dict[str, Command]] = None,
    screen_names: Optional[list] = None,
    tour_ids: Optional[list] = None,
    entity_types: Optional[list] = None,
    form_ids: Optional[list] = None,
) -> types.Tool:
    from app.modules.assistant.commands import REGISTRY

    reg = registry if registry is not None else REGISTRY
    return types.Tool(
        function_declarations=[
            command_to_declaration(c, screen_names, tour_ids, entity_types, form_ids)
            for c in reg.values()
        ]
    )
