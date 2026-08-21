"""Authentication and account API tests using an isolated SQLite file."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

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

    def test_conversation_and_messages_are_persisted_per_user(self):
        owner_id = auth.create_user("owner", "secret12")
        other_id = auth.create_user("other", "secret12")

        auth.append_message(owner_id, "thread-1", "user", "第一条问题")
        auth.append_message(owner_id, "thread-1", "assistant", "第一条回答")

        conversations = auth.list_conversations(owner_id)
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["thread_id"], "thread-1")
        self.assertEqual(conversations[0]["title"], "第一条问题")
        self.assertEqual(
            auth.get_conversation_messages(owner_id, "thread-1"),
            [
                {"role": "user", "content": "第一条问题", "created_at": ANY},
                {"role": "assistant", "content": "第一条回答", "created_at": ANY},
            ],
        )
        with self.assertRaises(LookupError):
            auth.get_conversation_messages(other_id, "thread-1")
        with self.assertRaises(PermissionError):
            auth.append_message(other_id, "thread-1", "user", "越权写入")

        auth.rename_conversation(owner_id, "thread-1", "重命名后的标题")
        self.assertEqual(auth.list_conversations(owner_id)[0]["title"], "重命名后的标题")
        self.assertTrue(auth.delete_conversation(owner_id, "thread-1"))
        self.assertEqual(auth.list_conversations(owner_id), [])

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

    def test_conversation_management_api(self):
        user_id = auth.create_user("api_owner", "secret12")
        auth.append_message(user_id, "thread-api", "user", "服务端对话")
        auth.append_message(user_id, "thread-api", "assistant", "已保存")
        token = auth.create_session(user_id)

        with patch.object(main, "AUTH_REQUIRED", True), TestClient(main.app) as client:
            client.cookies.set("nba_session", token)
            listing = client.get("/api/conversations")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json()["conversations"][0]["thread_id"], "thread-api")

            detail = client.get("/api/conversations/thread-api")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual([item["content"] for item in detail.json()["messages"]], ["服务端对话", "已保存"])

            renamed = client.patch("/api/conversations/thread-api", json={"title": "新的标题"})
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(client.get("/api/conversations").json()["conversations"][0]["title"], "新的标题")

            cleared = client.delete("/api/conversations")
            self.assertEqual(cleared.status_code, 200)
            self.assertEqual(cleared.json()["deleted"], 1)
            self.assertEqual(client.get("/api/conversations").json()["conversations"], [])


if __name__ == "__main__":
    unittest.main()
