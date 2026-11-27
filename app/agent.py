from __future__ import annotations

import json
import time
from typing import Any

from app.data_store import DataStoreError, OlistDataStore
from app.llm_client import create_chat_completion
from app.metrics import get_metric_definitions

SYSTEM_PROMPT = """You are an analytics agent for the Brazilian Olist e-commerce dataset.
Answer in the user's language. Use the metric catalog for business definitions and
the database tools for any answer that needs data. Never invent figures or claim
that correlation proves causation. State relevant filters and denominator.
For KPI questions, consult the metric catalog before writing SQL. Check the schema
and relationship metadata before joining tables.
The query tool is read-only, has a time limit, and returns at most 100 rows. The
CSV loader stores numeric columns as text and normalizes date columns to ISO
YYYY-MM-DD HH:MM:SS; cast numbers to REAL and use SQLite date functions for
date grouping. Do not add unrequested status filters or extra metrics. For a
top-N request, return exactly N rows when available. If a query fails,
inspect the error and make one correction attempt; if it still fails, explain the
limitation instead of making up a result. Keep answers concise and identify the
data or query used as evidence. Use relationship metadata; aggregate geolocation
by zip prefix before joining it into an analysis. For follow-up questions, use
conversation history only to resolve references; choose the minimum tables needed
for the new metric, and do not carry over joins from the previous metric unless
they are required. For a plain order count with a customer-state filter, the
canonical source is orders joined to customers. Do not join payments or order_items
for that count: either table can have multiple rows per order, and payments can
omit orders that have no payment record. Count distinct orders.order_id."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_metric_definitions",
            "description": "Return the approved definitions and scope notes for Olist business metrics.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "List local Olist tables, columns, relationships, and join cautions.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_read_only_sql",
            "description": (
                "Run one read-only SELECT query against the local SQLite Olist database. "
                "Use only tables and columns returned by get_database_schema."
            ),
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "A single SELECT query."}},
                "required": ["sql"],
                "additionalProperties": False,
            },
        },
    },
]

MAX_CONSECUTIVE_SQL_FAILURES = 2  # initial attempt plus one correction attempt


class OlistAnalyticsAgent:
    def __init__(self, data_store: OlistDataStore | None = None) -> None:
        self.data_store = data_store or OlistDataStore()

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "get_metric_definitions":
            return get_metric_definitions()
        if name == "get_database_schema":
            return self.data_store.schema()
        if name == "run_read_only_sql":
            sql = arguments.get("sql")
            if not isinstance(sql, str):
                raise DataStoreError("The sql argument must be a string.")
            return self.data_store.query(sql)
        raise ValueError(f"Unknown tool: {name}")

    def answer(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for message in history or []:
            if message.get("role") in {"user", "assistant"}:
                messages.append(
                    {"role": message["role"], "content": message.get("content", "")}
                )
        messages.append({"role": "user", "content": question})
        trace: list[dict[str, Any]] = []
        consecutive_sql_failures = 0

        for _ in range(8):
            response = create_chat_completion(messages, TOOLS)
            usage = response.get("usage") or {}
            for key in token_usage:
                token_usage[key] += int(usage.get(key, 0) or 0)
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("Model API returned no choices.")
            assistant_message = choices[0].get("message", {})
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                return {
                    "answer": assistant_message.get("content") or "",
                    "tool_trace": trace,
                    "latency_seconds": round(time.perf_counter() - started_at, 3),
                    "token_usage": token_usage,
                }

            messages.append(assistant_message)
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                name = function.get("name", "")
                arguments: Any = {}
                try:
                    if (
                        name == "run_read_only_sql"
                        and consecutive_sql_failures >= MAX_CONSECUTIVE_SQL_FAILURES
                    ):
                        raise DataStoreError(
                            "SQL correction limit reached after one correction attempt. "
                            "Explain the limitation instead of trying another query."
                        )
                    arguments = json.loads(function.get("arguments") or "{}")
                    if not isinstance(arguments, dict):
                        raise DataStoreError("Tool arguments must be a JSON object.")
                    result = self._call_tool(name, arguments)
                    if name == "run_read_only_sql":
                        consecutive_sql_failures = 0
                    tool_content = {"ok": True, "result": result}
                    trace.append({"tool": name, "arguments": arguments, "result": result})
                except (DataStoreError, ValueError, json.JSONDecodeError) as exc:
                    if (
                        name == "run_read_only_sql"
                        and consecutive_sql_failures < MAX_CONSECUTIVE_SQL_FAILURES
                    ):
                        consecutive_sql_failures += 1
                    tool_content = {"ok": False, "error": str(exc)}
                    trace.append({"tool": name, "arguments": arguments, "error": str(exc)})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": json.dumps(tool_content, ensure_ascii=False),
                    }
                )

        raise RuntimeError("Agent reached the eight-round limit before producing a final answer.")
