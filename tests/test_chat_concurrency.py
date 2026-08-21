"""Tests for per-conversation chat concurrency protection."""

import unittest

from app import main


class ChatConcurrencyTests(unittest.TestCase):
    def setUp(self):
        main._active_chat_threads.clear()

    def tearDown(self):
        main._active_chat_threads.clear()

    def test_same_conversation_is_locked(self):
        self.assertTrue(main._try_acquire_chat_slot(1, "thread-a"))
        self.assertFalse(main._try_acquire_chat_slot(1, "thread-a"))

    def test_other_conversations_and_users_are_independent(self):
        self.assertTrue(main._try_acquire_chat_slot(1, "thread-a"))
        self.assertTrue(main._try_acquire_chat_slot(1, "thread-b"))
        self.assertTrue(main._try_acquire_chat_slot(2, "thread-a"))

    def test_releasing_allows_next_request(self):
        self.assertTrue(main._try_acquire_chat_slot(1, "thread-a"))
        main._release_chat_slot(1, "thread-a")
        self.assertTrue(main._try_acquire_chat_slot(1, "thread-a"))


if __name__ == "__main__":
    unittest.main()
