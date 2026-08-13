"""Optional live contract test for the schedule time tool."""

import os
import unittest


@unittest.skipUnless(
    os.getenv("RUN_LIVE_TESTS", "false").strip().lower() == "true",
    "Set RUN_LIVE_TESTS=true to call the NBA ScheduleLeagueV2 endpoint",
)
class ScheduleGameTimeTests(unittest.TestCase):
    def test_schedule_returns_time_fields_for_known_game(self):
        from nba_api.stats.endpoints import scheduleleaguev2

        game_id = "0049900088"
        try:
            frames = scheduleleaguev2.ScheduleLeagueV2(season="1999-00").get_data_frames()
        except Exception as exc:
            self.fail(f"ScheduleLeagueV2 request failed: {type(exc).__name__}: {exc}")

        self.assertTrue(frames, "ScheduleLeagueV2 returned no data frames")

        found = []
        for frame in frames:
            game_id_column = next(
                (column for column in ("gameId", "GAME_ID") if column in frame.columns),
                None,
            )
            if game_id_column is not None:
                matches = frame[frame[game_id_column].astype(str) == game_id]
                if not matches.empty:
                    found.extend(matches.to_dict(orient="records"))

        self.assertTrue(found, f"ScheduleLeagueV2 did not find game_id={game_id}")

        time_keys = {
            "gameDate", "gameDateEst", "gameTimeEst", "gameDateTimeEst",
            "gameDateUTC", "gameTimeUTC", "gameDateTimeUTC", "awayTeamTime",
            "homeTeamTime", "GAME_TIME", "GAME_TIME_UTC", "GAME_TIME_LOCAL",
            "GAME_ET", "GAME_DATE_EST", "GAME_DATE",
        }
        time_values = {
            key: record.get(key)
            for record in found
            for key in time_keys
            if key in record and record.get(key) not in (None, "", "nan")
        }
        self.assertTrue(time_values, "The schedule record has no usable time fields")


if __name__ == "__main__":
    unittest.main()
