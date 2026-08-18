"""Unit tests for the shared NBA browser-session manager."""

import unittest
from unittest.mock import patch

import app.nba_client as nba_client


class NbaClientTests(unittest.TestCase):
    def setUp(self):
        self.previous_session = nba_client._session
        nba_client._session = None

    def tearDown(self):
        nba_client._session = self.previous_session

    def test_timeout_refreshes_session_and_retries_once(self):
        sessions = []
        calls = 0

        def make_session():
            session = object()
            sessions.append(session)
            return session

        def operation():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("NBA request timed out")
            return "ok"

        with patch.object(nba_client, "_new_session", side_effect=make_session):
            self.assertEqual(nba_client.run_nba_api(operation), "ok")

        self.assertEqual(calls, 2)
        self.assertEqual(len(sessions), 2)

    def test_non_transport_error_is_not_retried(self):
        with patch.object(nba_client, "_new_session", return_value=object()):
            with self.assertRaises(ValueError):
                nba_client.run_nba_api(lambda: (_ for _ in ()).throw(ValueError("bad input")))


if __name__ == "__main__":
    unittest.main()
