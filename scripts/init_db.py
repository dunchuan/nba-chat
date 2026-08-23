"""Initialize the application's PostgreSQL schema once, outside the web app."""

import asyncio
import os

import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{database}".format(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "nba-chat-db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.environ["POSTGRES_DB"],
    )
)

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
"""


def init_auth_schema() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(AUTH_SCHEMA)


async def init_checkpoint_schema() -> None:
    owner = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
    checkpointer = await owner.__aenter__()
    try:
        await checkpointer.setup()
    finally:
        await owner.__aexit__(None, None, None)


async def main() -> None:
    init_auth_schema()
    await init_checkpoint_schema()
    print("Database schema initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())
