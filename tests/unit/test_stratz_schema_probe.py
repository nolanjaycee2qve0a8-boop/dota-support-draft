from dota_support_draft.stratz_schema_probe import (
    MAX_SECONDARY_TYPES,
    MAX_TYPE_FIELDS,
    ROOT_PROBE_QUERY,
    TYPE_PROBE_QUERY,
    discover_types,
    render_type,
    summarize_root,
    summarize_type,
)


def _wrapped(name: str, depth: int) -> dict[str, object]:
    node: dict[str, object] = {"kind": "OBJECT", "name": name}
    for kind in ("NON_NULL", "LIST") * depth:
        node = {"kind": kind, "name": None, "ofType": node}
    return node


def _field(name: str, type_node: dict[str, object], args=()):
    return {"name": name, "args": list(args), "type": type_node}


def test_actual_queries_request_sufficient_nested_type_reference_depth() -> None:
    assert ROOT_PROBE_QUERY.count("ofType") >= 5
    assert TYPE_PROBE_QUERY.count("ofType") >= 5
    assert render_type(_wrapped("HeroStats", 3)) == "[[[HeroStats!]!]!]"


def test_constants_is_relevant_and_signatures_include_types() -> None:
    lines, type_names = summarize_root(
        {
            "__schema": {"queryType": {"name": "Query"}},
            "__type": {
                "fields": [
                    _field("constants", {"kind": "OBJECT", "name": "Constants"}),
                    _field("viewer", {"kind": "OBJECT", "name": "Viewer"}),
                ]
            },
        }
    )
    assert lines == ("Query type: Query", "  constants() -> Constants")
    assert type_names == ("Constants",)


class FakeProbeProvider:
    def __init__(self, responses) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def probe_query(self, query, variables=None):
        del query
        name = variables["name"]
        self.calls.append(name)
        return self.responses[name]


def test_bounded_bfs_discovers_multi_hop_types_once() -> None:
    responses = {
        "HeroStats": {
            "__type": {
                "kind": "OBJECT",
                "fields": [_field("winWeek", {"kind": "OBJECT", "name": "HeroStatsWinWeek"})],
            }
        },
        "HeroStatsWinWeek": {
            "__type": {
                "kind": "OBJECT",
                "fields": [
                    _field("heroFilter", {"kind": "INPUT_OBJECT", "name": "HeroFilterInput"})
                ],
            }
        },
        "HeroFilterInput": {
            "__type": {
                "kind": "INPUT_OBJECT",
                "inputFields": [{"name": "rank", "type": {"kind": "ENUM", "name": "RankBracket"}}],
            }
        },
    }
    provider = FakeProbeProvider(responses)
    lines = discover_types(provider, ("HeroStats", "HeroStats"))
    assert provider.calls == ["HeroStats", "HeroStatsWinWeek", "HeroFilterInput"]
    assert any("HeroStatsWinWeek" in line for line in lines)
    assert any("HeroFilterInput" in line for line in lines)


def test_discovery_and_type_output_are_bounded_and_malformed_safe() -> None:
    names = tuple(f"HeroType{index}" for index in range(MAX_SECONDARY_TYPES + 5))
    provider = FakeProbeProvider(
        {name: {"__type": {"kind": "OBJECT", "fields": []}} for name in names}
    )
    discover_types(provider, names)
    assert len(provider.calls) == MAX_SECONDARY_TYPES
    lines, children = summarize_type("BrokenHero", {"__type": {"kind": "OBJECT"}})
    assert lines == ("Type BrokenHero (OBJECT): no fields",) and children == ()
    many_fields = {
        "__type": {
            "kind": "OBJECT",
            "fields": [
                _field("hero", {"kind": "OBJECT", "name": "Hero"})
                for _ in range(MAX_TYPE_FIELDS + 2)
            ],
        }
    }
    assert len(summarize_type("HeroStats", many_fields)[0]) == MAX_TYPE_FIELDS + 1


def test_rendered_probe_output_never_contains_fake_token() -> None:
    lines, _ = summarize_root(
        {"__schema": {"queryType": {"name": "Query"}}, "__type": {"fields": []}}
    )
    assert "secret-token" not in "\n".join(lines)
