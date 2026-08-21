"""Optional end-to-end tests for the native ReAct graph.

Run with ``RUN_LIVE_TESTS=true``.  Assertions target observable agent
behavior and tool evidence, rather than the retired router's internal fields.
"""

import json
import os
import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


LIVE_TESTS_ENABLED = os.getenv("RUN_LIVE_TESTS", "false").strip().lower() == "true"

@unittest.skipUnless(
    LIVE_TESTS_ENABLED,
    "Set RUN_LIVE_TESTS=true to run tests with real models and NBA API",
)
class LiveReactAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()
        response = cls.client.post("/api/auth/login", json={"username": "nbachat", "password": "nbachat"})
        if response.status_code != 200:
            raise RuntimeError(f"live test login failed: {response.status_code} {response.text}")

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def invoke(self, message: str, thread_id: str | None = None):
        response = self.client.post(
            "/api/chat",
            json={"message": message, "thread_id": thread_id or f"live-test-{uuid.uuid4()}"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        error = next((event for event in events if event.get("type") == "error"), None)
        self.assertIsNone(error, error)
        metadata = next((event for event in reversed(events) if event.get("type") == "metadata"), None)
        self.assertIsNotNone(metadata, response.text)
        return metadata

    def test_react_answers_an_objective_boxscore_question(self):
        result = self.invoke("2000 NBA Finals Game 1 player statistics")
        answer = str(result["answer"])

        self.assertTrue(answer.strip())
        self.assertTrue(result.get("retrieval_ok"))
        self.assertTrue(result.get("player_data_used"))
        self.assertEqual(result.get("retrieval_game_id"), "0049900083")

    def test_react_uses_play_by_play_for_an_explicit_possession_request(self):
        result = self.invoke("2010 NBA Finals Game 5 first possession")
        answer = str(result["answer"])

        self.assertTrue(answer.strip())
        self.assertTrue(result.get("play_by_play_used"))
        self.assertEqual(result.get("retrieval_game_id"), "0040900405")

    def test_react_reuses_the_same_game_in_a_follow_up(self):
        thread_id = f"live-multi-{uuid.uuid4()}"
        first = self.invoke("2000 NBA Finals Game 1 score", thread_id)
        second = self.invoke("Analyze this game", thread_id)

        self.assertEqual(first.get("retrieval_game_id"), "0049900083")
        self.assertEqual(second.get("retrieval_game_id"), "0049900083")
        self.assertTrue(str(second["answer"]).strip())


if __name__ == "__main__":
    unittest.main()
