"""Authentication and account API tests using an isolated SQLite file."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth
from app import main


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth.sqlite3"
        self.db_patch = patch.object(auth, "DB_PATH", self.db_path)
        self.db_patch.start()
        auth.init_auth_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_create_authenticate_and_session_lookup(self):
        user_id = auth.create_user("New_User", "secret12")

        self.assertEqual(auth.authenticate("new_user", "secret12"), user_id)
        self.assertEqual(auth.authenticate("NEW_USER", "wrong-password"), None)

        token = auth.create_session(user_id)
        self.assertEqual(
            auth.user_from_session(token),
            {"id": user_id, "username": "new_user"},
        )

        auth.delete_session(token)
        self.assertIsNone(auth.user_from_session(token))

    def test_username_is_unique_ignoring_case(self):
        auth.create_user("Case_User", "secret12")
        with self.assertRaises(sqlite3.IntegrityError):
            auth.create_user("case_user", "another12")

    def test_register_login_me_and_logout_api(self):
        with (
            patch.object(main, "AUTH_REQUIRED", True),
            patch.object(main, "REGISTRATION_ENABLED", True),
            TestClient(main.app) as client,
        ):
            registered = client.post(
                "/api/auth/register",
                json={"username": "Api_User", "password": "secret12"},
            )
            self.assertEqual(registered.status_code, 200)
            self.assertEqual(registered.json()["username"], "api_user")
            self.assertIn("nba_session", registered.cookies)

            me = client.get("/api/auth/me")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["username"], "api_user")

            duplicate = client.post(
                "/api/auth/register",
                json={"username": "API_USER", "password": "secret12"},
            )
            self.assertEqual(duplicate.status_code, 409)

            logged_out = client.post("/api/auth/logout")
            self.assertEqual(logged_out.status_code, 200)
            self.assertEqual(client.get("/api/auth/me").status_code, 401)

            logged_in = client.post(
                "/api/auth/login",
                json={"username": "API_USER", "password": "secret12"},
            )
            self.assertEqual(logged_in.status_code, 200)
            self.assertEqual(logged_in.json()["username"], "api_user")


if __name__ == "__main__":
    unittest.main()
