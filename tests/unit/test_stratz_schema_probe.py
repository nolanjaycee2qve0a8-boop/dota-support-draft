from dota_support_draft.stratz_schema_probe import summarize


def test_schema_probe_summary_is_compact_and_filters_relevant_fields() -> None:
    summary = summarize(
        {
            "__schema": {"queryType": {"name": "Query"}},
            "__type": {
                "fields": [
                    {"name": "heroStats", "args": [{"name": "positionIds"}]},
                    {"name": "viewer", "args": []},
                    {"name": "gameVersions", "args": []},
                ]
            },
        }
    )
    assert summary == (
        "Query type: Query",
        "Relevant query fields: heroStats(positionIds), gameVersions()",
    )
