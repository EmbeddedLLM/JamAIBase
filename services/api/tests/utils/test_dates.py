import unittest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from owl.utils.dates import (
    date_to_utc,
    date_to_utc_iso,
    ensure_utc_timezone,
    now,
    now_iso,
    utc_iso_from_datetime,
    utc_iso_from_string,
    utc_iso_from_uuid7,
    utc_iso_from_uuid7_draft2,
)


class TestDateTimeFunctions(unittest.TestCase):
    @freeze_time("2023-05-01 12:00:00+00:00")
    def test_now_iso(self):
        self.assertEqual(now_iso(), "2023-05-01T12:00:00+00:00")
        self.assertEqual(now_iso("America/New_York"), "2023-05-01T08:00:00-04:00")

    @freeze_time("2023-05-01 12:00:00+00:00")
    def test_now(self):
        self.assertEqual(now(), datetime(2023, 5, 1, 12, 0, 0, tzinfo=timezone.utc))
        expected_ny_time = datetime(2023, 5, 1, 12, 0, 0, tzinfo=timezone.utc).astimezone(
            ZoneInfo("America/New_York")
        )
        self.assertEqual(
            now("America/New_York"),
            expected_ny_time,
        )

    def test_utc_iso_from_string(self):
        self.assertEqual(
            utc_iso_from_string("2023-05-01T12:00:00+02:00"), "2023-05-01T10:00:00+00:00"
        )
        with self.assertRaises(ValueError):
            utc_iso_from_string("2023-05-01T12:00:00")  # No timezone

    def test_utc_iso_from_datetime(self):
        dt = datetime(2023, 5, 1, 12, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertEqual(utc_iso_from_datetime(dt), "2023-05-01T10:00:00+00:00")

    def test_utc_iso_from_uuid7(self):
        uuid7_str = "018859e1-6a62-7f60-b6e1-f6e4b8ec6b66"
        result = utc_iso_from_uuid7(uuid7_str)
        self.assertTrue(result.startswith("2023-"))  # Check if it's at least from 2023

    # def test_utc_iso_from_uuid7_draft2(self):
    #     uuid7_str = "018859e1-6a62-7f60-b6e1-f6e4b8ec6b66"
    #     result = utc_iso_from_uuid7_draft2(uuid7_str)
    #     self.assertTrue(result.startswith("2023-"))  # Check if it's at least from 2023

    def test_date_to_utc_iso(self):
        d = date(2023, 5, 1)
        self.assertEqual(date_to_utc_iso(d), "2023-05-01T00:00:00+00:00")
        self.assertEqual(date_to_utc_iso(d, "America/New_York"), "2023-05-01T04:00:00+00:00")

    def test_date_to_utc(self):
        d = date(2023, 5, 1)
        self.assertEqual(date_to_utc(d), datetime(2023, 5, 1, 0, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(
            date_to_utc(d, "America/New_York"),
            datetime(2023, 5, 1, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )

    def test_ensure_utc_timezone(self):
        self.assertEqual(
            ensure_utc_timezone("2023-05-01T12:00:00+00:00"), "2023-05-01T12:00:00+00:00"
        )
        with self.assertRaises(ValueError):
            ensure_utc_timezone("2023-05-01T12:00:00+02:00")

    # Edge cases
    def test_utc_iso_from_string_edge_cases(self):
        with self.assertRaises(ValueError):
            utc_iso_from_string("invalid_datetime")
        with self.assertRaises(ValueError):
            utc_iso_from_string("2023-05-01")  # No time

    def test_utc_iso_from_datetime_edge_cases(self):
        with self.assertRaises(ValueError):
            utc_iso_from_datetime(datetime(2023, 5, 1))  # No timezone

    def test_utc_iso_from_uuid7_edge_cases(self):
        with self.assertRaises(ValueError):
            utc_iso_from_uuid7("invalid_uuid")

    def test_utc_iso_from_uuid7_draft2_edge_cases(self):
        with self.assertRaises(ValueError):
            utc_iso_from_uuid7_draft2("invalid_uuid")

    def test_date_to_utc_iso_edge_cases(self):
        with self.assertRaises(ValueError):
            date_to_utc_iso(date(2023, 5, 1), "Invalid/Timezone")

    def test_ensure_utc_timezone_edge_cases(self):
        with self.assertRaises(ValueError):
            ensure_utc_timezone("invalid_datetime")
        with self.assertRaises(ValueError):
            ensure_utc_timezone("2023-05-01T12:00:00")  # No timezone


if __name__ == "__main__":
    unittest.main()
