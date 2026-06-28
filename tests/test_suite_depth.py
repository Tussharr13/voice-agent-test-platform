import unittest

import app


class SuiteDepthTests(unittest.TestCase):
    def test_generated_suite_script_expands_generic_cases_to_turn_budget(self):
        suite = app.build_fallback_suite(
            {
                "bot_name": "Generic Employee Support Bot",
                "business_goal": "Help users resolve benefits, payroll, policy, document, and live support requests.",
                "flow_docs": "Main menu quick replies: Benefits, Payroll, Policy, Documents, Live Support.",
                "chat_case_count": "1",
                "goal_max_turns": "8",
            }
        )

        script = app.suite_to_chat_automation_script(suite)
        user_turns = script.count("**User:**")

        self.assertGreaterEqual(user_turns, 6)
        self.assertLessEqual(user_turns, 8)
        self.assertIn("Please continue with the same request.", script)

    def test_selected_twenty_turn_budget_creates_deeper_generated_scripts(self):
        suite = app.build_fallback_suite(
            {
                "bot_name": "Generic Support Bot",
                "business_goal": "Help users resolve multi-step support requests.",
                "flows": [{"name": "Account Support", "description": "User account support journey."}],
                "chat_case_count": "1",
                "goal_max_turns": "20",
            }
        )

        script = app.suite_to_chat_automation_script(suite)
        user_turns = script.count("**User:**")

        self.assertGreaterEqual(user_turns, 10)
        self.assertLessEqual(user_turns, 20)


if __name__ == "__main__":
    unittest.main()
