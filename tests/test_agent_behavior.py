"""Fast contract tests for the native ReAct agent.

These tests deliberately do not exercise the retired classifier/retrieval
state machine.  Live model/API behavior belongs in ``test_live_agent.py``.
"""

import json
import unittest

from app.cache.manager import cache_get, cache_set, clear_cache
from app.native_agent import NATIVE_AGENT_INSTRUCTIONS
from app.tools import get_tool_registry
from app.tools.contracts import normalize_tool_result
from app.tools.game import list_cached_data
from app.tools.game import lookup_game_data
from app.tools.support import beijing_time
from app.renderers import render_objective_response
from app.evidence import evaluate_tool_evidence
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class ReactAgentContractTests(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_registry_exposes_only_registered_react_tools(self):
        tools = get_tool_registry()
        names = [item.name for item in tools]

        self.assertEqual(len(names), len(set(names)))
        self.assertIn("list_cached_data", names)
        self.assertIn("lookup_game_data", names)
        self.assertIn("lookup_series_data", names)
        self.assertIn("lookup_game_log_data", names)
        self.assertIn("lookup_boxscore_data", names)
        self.assertIn("lookup_play_by_play_data", names)
        self.assertIn("lookup_game_time_data", names)
        self.assertIn("lookup_standings", names)
        self.assertIn("lookup_player_season_stats", names)
        self.assertIn("lookup_player_career_stats", names)
        self.assertIn("lookup_team_season_stats", names)
        self.assertIn("search_web", names)

    def test_every_registered_tool_has_model_facing_description(self):
        for registered_tool in get_tool_registry():
            self.assertTrue(registered_tool.name)
            self.assertTrue(registered_tool.description.strip(), registered_tool.name)

    def test_react_instructions_describe_tool_selection_and_cache_reuse(self):
        self.assertIn("choose the registered tools", NATIVE_AGENT_INSTRUCTIONS)
        self.assertIn("list_cached_data", NATIVE_AGENT_INSTRUCTIONS)
        self.assertIn("do not fetch the same payload again", NATIVE_AGENT_INSTRUCTIONS)
        self.assertIn("must come exclusively from NBA data tools", NATIVE_AGENT_INSTRUCTIONS)
        self.assertIn("Never use search_web", NATIVE_AGENT_INSTRUCTIONS)

    def test_cache_index_returns_structured_labels_and_game_ids(self):
        cache_set(
            "boxscore",
            "0049900088",
            json.dumps(
                {
                    "source": "nba_api",
                    "game_id": "0049900088",
                    "players": [{"player_name": "Shaquille O'Neal"}],
                }
            ),
        )

        result = json.loads(list_cached_data.invoke({"query": "0049900088", "data_type": "boxscore"}))

        self.assertTrue(result["ok"])
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["game_ids"], ["0049900088"])
        self.assertEqual(result["records"][0]["data_type"], "boxscore")

    def test_cache_entries_are_isolated_by_namespace_and_key(self):
        cache_set("game", "0049900083", "g1")
        cache_set("game", "0049900088", "g6")
        cache_set("boxscore", "0049900083", "g1-boxscore")

        self.assertEqual(cache_get("game", "0049900083", 60), "g1")
        self.assertEqual(cache_get("game", "0049900088", 60), "g6")
        self.assertEqual(cache_get("boxscore", "0049900083", 60), "g1-boxscore")
        self.assertIsNone(cache_get("game", "0049900001", 60))

    def test_tool_result_contract_normalizes_common_payload_shapes(self):
        game = normalize_tool_result(
            '{"source":"nba_api","matches":[{"game_id":"0049900083"}]}',
            "game",
        )
        boxscore = normalize_tool_result(
            '{"source":"nba_api","players":[{"player_name":"Kobe Bryant"}]}',
            "boxscore",
        )
        invalid = normalize_tool_result("not-json", "game")

        self.assertEqual(game["game_ids"], ["0049900083"])
        self.assertEqual(game["records"][0]["game_id"], "0049900083")
        self.assertEqual(boxscore["records"][0]["player_name"], "Kobe Bryant")
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["error_type"], "parse_error")

    def test_finals_scope_requires_series_evidence(self):
        result = evaluate_tool_evidence(
            "2000 NBA Finals scores",
            [{
                "source": "nba_api",
                "matches": [{"game_id": "0049900083"}],
                "coverage": {"scope": "full_playoffs", "complete": False},
                "ok": True,
            }],
        )
        self.assertFalse(result["complete"])
        self.assertIn("finals_series_scope", result["missing"])

    def test_series_scope_evidence_can_complete_finals_request(self):
        result = evaluate_tool_evidence(
            "2000 NBA Finals scores",
            [{
                "source": "nba_api",
                "records": [{"game_id": "0049900083", "game_label": "NBA Finals"}],
                "coverage": {"scope": "NBA Finals", "complete": True},
                "ok": True,
            }],
        )
        self.assertTrue(result["complete"])

    def test_game_lookup_is_bound_to_nba_api(self):
        result = json.loads(lookup_game_data.invoke({"query": "总决赛比分"}))
        self.assertEqual(result["source"], "nba_api")
        self.assertEqual(result["error"], "missing_year")

    def test_web_tool_is_reserved_for_current_information(self):
        web_tool = next(item for item in get_tool_registry() if item.name == "search_web")
        self.assertIn("never use for historical scores", web_tool.description.lower())

    def test_tool_schemas_require_the_locator_for_player_and_schedule_queries(self):
        tools = {item.name: item for item in get_tool_registry()}

        self.assertIn("year", tools["lookup_player_season_stats"].args)
        self.assertIn("game_id", tools["lookup_boxscore_data"].args)
        self.assertIn("game_id", tools["lookup_play_by_play_data"].args)
        self.assertIn("game_id", tools["lookup_game_time_data"].args)
        self.assertIn("year", tools["lookup_standings"].args)

    def test_utc_time_is_converted_to_beijing_time(self):
        self.assertEqual(
            beijing_time("2000-06-20T01:00:00Z"),
            "2000-06-20T09:00:00+08:00",
        )

    def test_objective_boxscore_uses_fixed_markdown_table(self):
        content = json.dumps({
            "source": "nba_api",
            "game_id": "0049900083",
            "players": [{
                "name": "Kobe Bryant",
                "teamTricode": "LAL",
                "minutes": "38:12",
                "points": 14,
                "reboundsTotal": 3,
                "assists": 5,
            }],
        })
        result = render_objective_response([
            HumanMessage(content="2000 NBA Finals G1 player statistics"),
            ToolMessage(content=content, tool_call_id="1", name="lookup_boxscore_data"),
            AIMessage(content="model draft"),
        ])
        self.assertIsNotNone(result)
        self.assertIn("| 球员 |", result)
        self.assertIn("Kobe Bryant", result)
        self.assertIn("| 14 |", result)

    def test_boxscore_renderer_separates_teams_and_drops_blank_roster_rows(self):
        result = render_objective_response([
            HumanMessage(content="2000 NBA Finals G1 player statistics"),
            ToolMessage(content=json.dumps({
                "source": "nba_api",
                "game_id": "0049900083",
                "players": [
                    {"nameI": "S. O'Neal", "teamTricode": "LAL", "points": 43},
                    {"nameI": "J. Rose", "teamTricode": "IND", "points": 12},
                    {"nameI": None, "teamTricode": "LAL", "points": 0},
                ],
            }), tool_call_id="1", name="lookup_boxscore_data"),
        ])
        self.assertIn("### LAL", result)
        self.assertIn("### IND", result)
        self.assertIn("S. O'Neal", result)
        self.assertNotIn("\n| - |", result)

    def test_subjective_question_keeps_model_answer_path(self):
        result = render_objective_response([
            HumanMessage(content="为什么湖人在 G1 能赢？"),
            ToolMessage(
                content=json.dumps({"matches": [{"home_score": 104}]}),
                tool_call_id="1",
                name="lookup_game_data",
            ),
        ])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
