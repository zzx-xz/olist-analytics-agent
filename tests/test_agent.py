from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from app.agent import OlistAnalyticsAgent
from app.data_store import DataStoreError, OlistDataStore


def tool_call_response(sql: str, call_id: str) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": "run_read_only_sql",
                                "arguments": json.dumps({"sql": sql}),
                            },
                        }
                    ]
                }
            }
        ],
        "usage": {},
    }


class AgentRetryTests(unittest.TestCase):
    def test_allows_one_sql_correction_then_stops_querying(self) -> None:
        data_store = Mock(spec=OlistDataStore)
        data_store.query.side_effect = DataStoreError("SQL syntax error")
        agent = OlistAnalyticsAgent(data_store=data_store)
        responses = [
            tool_call_response("SELECT broken", "call-1"),
            tool_call_response("SELECT still_broken", "call-2"),
            tool_call_response("SELECT keep_trying", "call-3"),
            {"choices": [{"message": {"content": "I could not complete the query."}}], "usage": {}},
        ]

        with patch("app.agent.create_chat_completion", side_effect=responses):
            result = agent.answer("Count orders")

        self.assertEqual(data_store.query.call_count, 2)
        sql_steps = [
            step for step in result["tool_trace"]
            if step["tool"] == "run_read_only_sql"
        ]
        self.assertEqual(len(sql_steps), 3)
        self.assertIn("correction limit", sql_steps[2]["error"].lower())
        self.assertEqual(result["answer"], "I could not complete the query.")


if __name__ == "__main__":
    unittest.main()
