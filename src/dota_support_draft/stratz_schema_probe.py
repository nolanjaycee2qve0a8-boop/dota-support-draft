"""Compact opt-in STRATZ GraphQL schema probe; no response payload is persisted."""

from __future__ import annotations

from dota_support_draft.config import Settings
from dota_support_draft.providers.cache import DiskJsonCache
from dota_support_draft.providers.errors import ProviderError
from dota_support_draft.providers.stratz import StratzProvider

PROBE_QUERY = """
query DotaSupportDraftSchemaProbe {
  __schema { queryType { name } }
  __type(name: "Query") {
    fields { name args { name } }
  }
}
"""


def summarize(data: dict[str, object]) -> tuple[str, ...]:
    schema = data.get("__schema")
    query_type = schema.get("queryType") if isinstance(schema, dict) else None
    query_name = query_type.get("name") if isinstance(query_type, dict) else "unknown"
    query = data.get("__type")
    fields = query.get("fields") if isinstance(query, dict) else None
    if not isinstance(fields, list):
        return (f"Query type: {query_name}", "Query fields: unavailable")
    relevant: list[str] = []
    for field in fields:
        if not isinstance(field, dict) or not isinstance(field.get("name"), str):
            continue
        name = field["name"]
        if any(term in name.casefold() for term in ("hero", "game", "stat", "match", "version")):
            args = field.get("args")
            arg_names = (
                ", ".join(arg["name"] for arg in args if isinstance(arg, dict) and "name" in arg)
                if isinstance(args, list)
                else ""
            )
            relevant.append(f"{name}({arg_names})")
    return (
        f"Query type: {query_name}",
        f"Relevant query fields: {', '.join(relevant[:20]) or 'none'}",
    )


def main() -> int:
    settings = Settings.from_environment()
    if not settings.stratz_api_token:
        print("STRATZ schema probe: NOT RUN / TOKEN NOT CONFIGURED")
        return 2
    provider = StratzProvider(DiskJsonCache(settings.cache_directory), settings.stratz_api_token)
    try:
        for line in summarize(provider.probe_query(PROBE_QUERY)):
            print(line)
    except ProviderError as error:
        print(f"STRATZ schema probe: FAILED / {error}")
        return 1
    print("STRATZ schema probe: completed; inspect fields before enabling production capability.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
