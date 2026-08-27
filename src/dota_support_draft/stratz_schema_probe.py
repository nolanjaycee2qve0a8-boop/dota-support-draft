"""Compact opt-in STRATZ GraphQL schema probe; no schema payload is persisted."""

from __future__ import annotations

from collections.abc import Iterable

from dota_support_draft.config import Settings
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.stratz import StratzProvider

MAX_ROOT_FIELDS = 12
MAX_SECONDARY_TYPES = 8
MAX_TYPE_FIELDS = 12
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
)

ROOT_PROBE_QUERY = """
query DotaSupportDraftRootSchemaProbe {
  __schema { queryType { name } }
  __type(name: "Query") {
    fields {
      name
      args { name type { kind name ofType { kind name ofType { kind name } } } }
      type { kind name ofType { kind name ofType { kind name } } }
    }
  }
}
"""

TYPE_PROBE_QUERY = """
query DotaSupportDraftTypeSchemaProbe($name: String!) {
  __type(name: $name) {
    kind name
    inputFields { name type { kind name ofType { kind name ofType { kind name } } } }
    fields { name type { kind name ofType { kind name ofType { kind name } } } }
  }
}
"""


def render_type(node: object) -> str:
    """Render a bounded GraphQL type reference, including NON_NULL and LIST."""
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
    """Return named leaves reachable from an introspection type reference."""
    if not isinstance(node, dict):
        return ()
    name = node.get("name")
    return (name,) if isinstance(name, str) else named_types(node.get("ofType"))


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
    types = tuple(
        dict.fromkeys(
            type_name
            for field in relevant
            for type_name in (*named_types(field.get("type")),)
            + tuple(
                type_name
                for arg in field.get("args", [])
                if isinstance(arg, dict)
                for type_name in named_types(arg.get("type"))
            )
            if _is_relevant(type_name)
        )
    )
    lines = (f"Query type: {query_name}", *(f"  {_field_signature(field)}" for field in relevant))
    return lines if relevant else (
        f"Query type: {query_name}",
        "Relevant query fields: none",
    ), types


def summarize_type(type_name: str, data: dict[str, object]) -> tuple[str, ...]:
    detail = data.get("__type")
    if not isinstance(detail, dict):
        return (f"Type {type_name}: unavailable",)
    kind = detail.get("kind")
    fields: object = detail.get("inputFields") if kind == "INPUT_OBJECT" else detail.get("fields")
    if not isinstance(fields, list):
        return (f"Type {type_name} ({kind or '?'}): no fields",)
    rendered = tuple(
        f"  {field.get('name', '?')}: {render_type(field.get('type'))}"
        for field in fields[:MAX_TYPE_FIELDS]
        if isinstance(field, dict)
    )
    return (f"Type {type_name} ({kind or '?'}):", *rendered)


def _limited(values: Iterable[str], limit: int) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))[:limit]


def main() -> int:
    settings = Settings.from_environment()
    if not settings.stratz_api_token:
        print("STRATZ schema probe: NOT RUN / TOKEN NOT CONFIGURED")
        return 2
    provider = StratzProvider(DiskJsonCache(settings.cache_directory), settings.stratz_api_token)
    try:
        root_lines, type_names = summarize_root(provider.probe_query(ROOT_PROBE_QUERY))
        for line in root_lines:
            print(line)
        for type_name in _limited(type_names, MAX_SECONDARY_TYPES):
            for line in summarize_type(
                type_name, provider.probe_query(TYPE_PROBE_QUERY, {"name": type_name})
            ):
                print(line)
    except ProviderError as error:
        print(f"STRATZ schema probe: FAILED / {error}")
        return 1
    print("STRATZ schema probe: completed; inspect fields before enabling production capability.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
