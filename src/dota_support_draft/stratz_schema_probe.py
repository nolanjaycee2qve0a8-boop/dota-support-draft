"""Compact opt-in STRATZ schema probe; no schema payload is persisted."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from dota_support_draft.config import Settings
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.stratz import StratzProvider

MAX_ROOT_FIELDS = 12
MAX_SECONDARY_TYPES = 12
MAX_TYPE_FIELDS = 14
MAX_TYPE_DEPTH = 3
RELEVANT_TERMS = (
    "hero",
    "game",
    "version",
    "patch",
    "stat",
    "match",
    "position",
    "rank",
    "bracket",
    "synergy",
    "counter",
    "advantage",
    "constant",
    "constants",
)
NON_TRAVERSABLE_KINDS = frozenset({"SCALAR", "ENUM"})

# Six fixed wrapper levels reconstruct normal forms through [[Type!]!]!.
TYPE_REFERENCE = """
kind name ofType {
  kind name ofType {
    kind name ofType {
      kind name ofType {
        kind name ofType {
          kind name
        }
      }
    }
  }
}
"""

ROOT_PROBE_QUERY = f"""
query DotaSupportDraftRootSchemaProbe {{
  __schema {{ queryType {{ name }} }}
  __type(name: "Query") {{
    fields {{
      name
      args {{ name type {{ {TYPE_REFERENCE} }} }}
      type {{ {TYPE_REFERENCE} }}
    }}
  }}
}}
"""

TYPE_PROBE_QUERY = f"""
query DotaSupportDraftTypeSchemaProbe($name: String!) {{
  __type(name: $name) {{
    kind name
    inputFields {{ name type {{ {TYPE_REFERENCE} }} }}
    fields {{
      name
      args {{ name type {{ {TYPE_REFERENCE} }} }}
      type {{ {TYPE_REFERENCE} }}
    }}
  }}
}}
"""


def render_type(node: object) -> str:
    if not isinstance(node, dict):
        return "?"
    kind = node.get("kind")
    if kind == "NON_NULL":
        return f"{render_type(node.get('ofType'))}!"
    if kind == "LIST":
        return f"[{render_type(node.get('ofType'))}]"
    name = node.get("name")
    return name if isinstance(name, str) else "?"


def named_types(node: object) -> tuple[str, ...]:
    if not isinstance(node, dict):
        return ()
    name = node.get("name")
    return (name,) if isinstance(name, str) else named_types(node.get("ofType"))


def _named_type_kind(node: object) -> tuple[str, str] | None:
    if not isinstance(node, dict):
        return None
    name, kind = node.get("name"), node.get("kind")
    if isinstance(name, str) and isinstance(kind, str):
        return name, kind
    return _named_type_kind(node.get("ofType"))


def _is_relevant(name: str) -> bool:
    return any(term in name.casefold() for term in RELEVANT_TERMS)


def _field_signature(field: dict[str, object]) -> str:
    name = field.get("name")
    safe_name = name if isinstance(name, str) else "?"
    args = field.get("args")
    rendered_args = (
        ", ".join(
            f"{arg.get('name', '?')}: {render_type(arg.get('type'))}"
            for arg in args
            if isinstance(arg, dict)
        )
        if isinstance(args, list)
        else ""
    )
    return f"{safe_name}({rendered_args}) -> {render_type(field.get('type'))}"


def _discovered_types(fields: Iterable[object]) -> tuple[str, ...]:
    discovered: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        result_type = _named_type_kind(field.get("type"))
        if (
            result_type
            and result_type[1] not in NON_TRAVERSABLE_KINDS
            and _is_relevant(result_type[0])
        ):
            discovered.append(result_type[0])
        args = field.get("args")
        if isinstance(args, list):
            for arg in args:
                if isinstance(arg, dict):
                    argument_type = _named_type_kind(arg.get("type"))
                    if (
                        argument_type
                        and argument_type[1] not in NON_TRAVERSABLE_KINDS
                        and _is_relevant(argument_type[0])
                    ):
                        discovered.append(argument_type[0])
    return tuple(dict.fromkeys(discovered))


def summarize_root(data: dict[str, object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    schema = data.get("__schema")
    query_type = schema.get("queryType") if isinstance(schema, dict) else None
    query_name = query_type.get("name") if isinstance(query_type, dict) else "unknown"
    query = data.get("__type")
    fields = query.get("fields") if isinstance(query, dict) else None
    if not isinstance(fields, list):
        return (f"Query type: {query_name}", "Relevant query fields: unavailable"), ()
    relevant = [
        field
        for field in fields
        if isinstance(field, dict)
        and isinstance(field.get("name"), str)
        and _is_relevant(field["name"])
    ][:MAX_ROOT_FIELDS]
    lines = (f"Query type: {query_name}", *(f"  {_field_signature(field)}" for field in relevant))
    return (
        lines if relevant else (f"Query type: {query_name}", "Relevant query fields: none"),
        _discovered_types(relevant),
    )


def summarize_type(
    type_name: str, data: dict[str, object]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    detail = data.get("__type")
    if not isinstance(detail, dict):
        return (f"Type {type_name}: unavailable",), ()
    kind = detail.get("kind")
    fields: object = detail.get("inputFields") if kind == "INPUT_OBJECT" else detail.get("fields")
    if not isinstance(fields, list):
        return (f"Type {type_name} ({kind or '?'}): no fields",), ()
    bounded = fields[:MAX_TYPE_FIELDS]
    if kind == "INPUT_OBJECT":
        lines = tuple(
            f"  {field.get('name', '?')}: {render_type(field.get('type'))}"
            for field in bounded
            if isinstance(field, dict)
        )
        return (f"Type {type_name} ({kind}):", *lines), _discovered_types(bounded)
    lines = tuple(f"  {_field_signature(field)}" for field in bounded if isinstance(field, dict))
    return (f"Type {type_name} ({kind or '?'}):", *lines), _discovered_types(bounded)


def _limited(values: Iterable[str], limit: int) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))[:limit]


def discover_types(provider: StratzProvider, root_types: Iterable[str]) -> tuple[str, ...]:
    """Bounded breadth-first type traversal, returning compact safe report lines."""
    queue = deque((type_name, 1) for type_name in _limited(root_types, MAX_SECONDARY_TYPES))
    seen: set[str] = set()
    lines: list[str] = []
    while queue and len(seen) < MAX_SECONDARY_TYPES:
        type_name, depth = queue.popleft()
        if type_name in seen:
            continue
        seen.add(type_name)
        summary, children = summarize_type(
            type_name, provider.probe_query(TYPE_PROBE_QUERY, {"name": type_name})
        )
        lines.extend(summary)
        if depth < MAX_TYPE_DEPTH:
            for child in _limited(children, MAX_SECONDARY_TYPES):
                if child not in seen and len(seen) + len(queue) < MAX_SECONDARY_TYPES:
                    queue.append((child, depth + 1))
    return tuple(lines)


def main() -> int:
    settings = Settings.from_environment()
    if not settings.stratz_api_token:
        print("STRATZ schema probe: NOT RUN / TOKEN NOT CONFIGURED")
        return 2
    provider = StratzProvider(DiskJsonCache(settings.cache_directory), settings.stratz_api_token)
    try:
        root_lines, root_types = summarize_root(provider.probe_query(ROOT_PROBE_QUERY))
        for line in (*root_lines, *discover_types(provider, root_types)):
            print(line)
    except ProviderError as error:
        print(f"STRATZ schema probe: FAILED / {error}")
        return 1
    print("STRATZ schema probe: completed; inspect fields before enabling production capability.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
