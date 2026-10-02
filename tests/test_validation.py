import unittest
from datetime import date

from validation import valid_date, valid_guests, valid_time, normalize_phone


class ValidationTests(unittest.TestCase):
    def test_accepts_supported_date_formats_and_rejects_past_dates(self):
        today = date(2026, 10, 2)
        self.assertTrue(valid_date("02.10.2026", today))
        self.assertTrue(valid_date("2026-10-03", today))
        self.assertFalse(valid_date("01.10.2026", today))
        self.assertFalse(valid_date("31.02.2026", today))

    def test_time_requires_valid_24_hour_value(self):
        self.assertTrue(valid_time("19:30"))
        self.assertFalse(valid_time("24:00"))
        self.assertFalse(valid_time("7:30"))

    def test_guest_count_is_bounded(self):
        self.assertTrue(valid_guests("1"))
        self.assertTrue(valid_guests("200"))
        self.assertFalse(valid_guests("0"))
        self.assertFalse(valid_guests("201"))
        self.assertFalse(valid_guests("много"))

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("8 (900) 123-45-67"), "+79001234567")
        self.assertEqual(normalize_phone("9001234567"), "+79001234567")
        self.assertIsNone(normalize_phone("123"))


if __name__ == "__main__":
    unittest.main()
