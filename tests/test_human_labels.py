import re
import unittest

import app
from backend import workspace


class HumanLabelTests(unittest.TestCase):
    def test_generated_suite_has_readable_timestamp_label(self):
        suite = app.build_fallback_suite(
            {
                "bot_name": "JFL AskHR",
                "suite_request": "Cover payroll, PF, leave, attendance, and HR handoff.",
                "chat_case_count": "2",
            }
        )

        self.assertIn("JFL AskHR", suite["name"])
        self.assertIn("Custom Suite", suite["name"])
        self.assertRegex(suite["name"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        self.assertRegex(suite["generated_at_label"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

    def test_report_chat_titles_are_actionable(self):
        title = workspace.make_chat_title(
            "Pinpoint failures in report report_4d49db7f48. Do not give a generic summary first."
        )

        self.assertEqual(title, "Pinpoint report report_4d49db7f48")


if __name__ == "__main__":
    unittest.main()
