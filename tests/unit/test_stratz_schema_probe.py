from dota_support_draft.stratz_schema_probe import (
    MAX_ROOT_FIELDS,
    MAX_TYPE_FIELDS,
    render_type,
    summarize_root,
    summarize_type,
)


def _non_null_list(name: str) -> dict[str, object]:
    return {
        "kind": "NON_NULL",
        "name": None,
        "ofType": {
            "kind": "LIST",
            "name": None,
            "ofType": {
                "kind": "NON_NULL",
                "name": None,
                "ofType": {"kind": "OBJECT", "name": name},
            },
        },
    }


def test_type_renderer_handles_nested_non_null_and_list() -> None:
    assert render_type(_non_null_list("HeroStats")) == "[HeroStats!]!"


def test_root_summary_renders_argument_and_return_types_and_filters_irrelevant() -> None:
    lines, type_names = summarize_root(
        {
            "__schema": {"queryType": {"name": "Query"}},
            "__type": {
                "fields": [
                    {
                        "name": "heroStats",
                        "args": [{"name": "positionIds", "type": _non_null_list("Int")}],
                        "type": {"kind": "OBJECT", "name": "HeroStats"},
                    },
                    {"name": "viewer", "args": [], "type": {"kind": "OBJECT", "name": "Viewer"}},
                ]
            },
        }
    )
    assert lines == ("Query type: Query", "  heroStats(positionIds: [Int!]!) -> HeroStats")
    assert type_names == ("HeroStats",)


def test_type_summary_handles_input_and_object_with_bounds() -> None:
    input_lines = summarize_type(
        "HeroFilterInput",
        {
            "__type": {
                "kind": "INPUT_OBJECT",
                "inputFields": [{"name": "rank", "type": {"kind": "ENUM", "name": "RankBracket"}}],
            }
        },
    )
    object_lines = summarize_type(
        "HeroStats",
        {
            "__type": {
                "kind": "OBJECT",
                "fields": [
                    {
                        "name": "matchUp",
                        "type": {"kind": "LIST", "ofType": {"kind": "OBJECT", "name": "MatchUp"}},
                    }
                    for _ in range(MAX_TYPE_FIELDS + 2)
                ],
            }
        },
    )
    assert input_lines == ("Type HeroFilterInput (INPUT_OBJECT):", "  rank: RankBracket")
    assert len(object_lines) == MAX_TYPE_FIELDS + 1


def test_root_summary_is_bounded_malformed_safe_and_token_free() -> None:
    lines, type_names = summarize_root(
        {
            "__schema": {"queryType": {"name": "Query"}},
            "__type": {
                "fields": [
                    {
                        "name": f"hero{index}",
                        "args": [],
                        "type": {"kind": "OBJECT", "name": f"Hero{index}"},
                    }
                    for index in range(MAX_ROOT_FIELDS + 5)
                ]
            },
        }
    )
    assert len(lines) == MAX_ROOT_FIELDS + 1
    assert len(type_names) <= MAX_ROOT_FIELDS
    assert "secret-token" not in "\n".join(lines)
    assert (
        summarize_root({"__schema": {}, "__type": {}})[0][-1]
        == "Relevant query fields: unavailable"
    )
