"""Optional end-to-end tests for the native ReAct graph.

Run with ``RUN_LIVE_TESTS=true``.  Assertions target observable agent
behavior and tool evidence, rather than the retired router's internal fields.
"""

import asyncio
import os
import unittest
import uuid

from langchain_core.messages import HumanMessage

from app.native_agent import graph


LIVE_TESTS_ENABLED = os.getenv("RUN_LIVE_TESTS", "false").strip().lower() == "true"


def run(coro):
    return asyncio.run(coro)


@unittest.skipUnless(
    LIVE_TESTS_ENABLED,
    "Set RUN_LIVE_TESTS=true to run tests with real models and NBA API",
)
class LiveReactAgentTests(unittest.TestCase):
    def invoke(self, message: str, thread_id: str | None = None):
        return run(
            graph.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config={
                    "configurable": {
                        "thread_id": thread_id or f"live-test-{uuid.uuid4()}"
                    },
                    "tags": ["automated-test", "live", "react"],
                },
            )
        )

    def test_react_answers_an_objective_boxscore_question(self):
        result = self.invoke("2000 NBA Finals Game 1 player statistics")
        answer = str(result["messages"][-1].content)

        self.assertTrue(answer.strip())
        self.assertTrue(result.get("retrieval_ok"))
        self.assertTrue(result.get("player_data_used"))
        self.assertEqual(result.get("retrieval_game_id"), "0049900083")

    def test_react_uses_play_by_play_for_an_explicit_possession_request(self):
        result = self.invoke("2010 NBA Finals Game 5 first possession")
        answer = str(result["messages"][-1].content)

        self.assertTrue(answer.strip())
        self.assertTrue(result.get("play_by_play_used"))
        self.assertEqual(result.get("retrieval_game_id"), "0040900405")

    def test_react_reuses_the_same_game_in_a_follow_up(self):
        thread_id = f"live-multi-{uuid.uuid4()}"
        first = self.invoke("2000 NBA Finals Game 1 score", thread_id)
        second = self.invoke("Analyze this game", thread_id)

        self.assertEqual(first.get("retrieval_game_id"), "0049900083")
        self.assertEqual(second.get("retrieval_game_id"), "0049900083")
        self.assertTrue(str(second["messages"][-1].content).strip())


if __name__ == "__main__":
    unittest.main()
