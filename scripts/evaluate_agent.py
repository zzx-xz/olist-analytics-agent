from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent import OlistAnalyticsAgent
from app.data_store import OlistDataStore

BENCHMARK_PATH = PROJECT_ROOT / "evaluation" / "benchmark.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "evaluation" / "results" / "latest.json"
CHALLENGE_REPORT_PATH = PROJECT_ROOT / "evaluation" / "results" / "challenge.json"

RESULT_FIELDS: dict[str, dict[str, Any]] = {
    "orders_total": {"order_count": {"source": ["order_count", "distinct_orders"]}},
    "gmv_total": {"gmv": {"source": ["gmv"]}},
    "repeat_user_rate": {
        "repeat_user_rate": {
            "source": [
                "repeat_user_rate",
                "repeat_rate_pct",
                "repeat_rate",
                "repeat_customer_rate",
                "repeat_customer_rate_pct",
            ],
            "numerator": ["repeat_users", "repeat_user_count"],
            "denominator": [
                "total_users",
                "users_with_order",
                "purchase_user_count",
                "users_with_any_order",
                "users_with_orders",
            ],
            "factor": 100,
        }
    },
    "late_delivery_rate": {
        "delayed_order_rate": {
            "source": [
                "delayed_order_rate",
                "late_delivery_rate",
                "late_delivery_rate_pct",
                "late_by_calendar_date_pct",
                "late_rate",
            ],
            "factor": 100,
        }
    },
    "review_average": {
        "average_review_score": {
            "source": ["avg_review_score", "average_review_score"],
            "factor": 1,
        }
    },
    "negative_review_rate": {
        "negative_review_rate": {
            "source": [
                "negative_review_rate",
                "negative_rate_pct",
                "negative_review_rate_pct",
            ],
            "numerator": ["negative_orders", "negative_review_orders"],
            "denominator": ["scored_orders", "reviewed_orders", "orders_with_review"],
            "factor": 100,
        }
    },
    "state_gmv_top5": {
        "customer_state": {"source": ["customer_state", "state"]},
        "gmv": {"source": ["gmv"]},
    },
    "monthly_orders_top5": {
        "order_month": {"source": ["order_month", "month", "purchase_month"]},
        "order_count": {"source": ["order_count", "orders"]},
    },
    "payment_type_gmv": {
        "payment_type": {"source": ["payment_type"]},
        "gmv": {"source": ["gmv"]},
    },
    "category_sales_top5": {
        "category": {"source": ["category", "product_category_name_english", "product_category_name"]},
        "product_sales_amount": {"source": ["product_sales_amount", "product_sales", "sales_amount"]},
    },
    "seller_sales_top5": {
        "seller_id": {"source": ["seller_id"]},
        "product_sales_amount": {"source": ["product_sales_amount", "all_status_sales", "sales_amount"]},
    },
    "late_rate_by_month": {
        "order_month": {"source": ["order_month", "month", "purchase_month"]},
        "delayed_order_rate": {
            "source": ["delayed_order_rate", "late_delivery_rate", "late_rate"],
            "factor": 100,
        },
    },
    "state_order_count_top5": {
        "customer_state": {"source": ["customer_state", "state"]},
        "order_count": {"source": ["order_count", "distinct_orders", "orders"]},
    },
    "credit_card_gmv_2018_top3": {
        "order_month": {"source": ["order_month", "month", "purchase_month"]},
        "gmv": {"source": ["gmv", "payment_gmv", "total_gmv"]},
    },
    "delivery_days_by_state_top5": {
        "customer_state": {"source": ["customer_state", "state"]},
        "avg_delivery_days": {
            "source": ["avg_delivery_days", "average_delivery_days", "avg_days"]
        },
    },
    "cancellation_rate_august_2018": {
        "cancellation_rate_pct": {
            "source": ["cancellation_rate_pct", "cancel_rate_pct", "cancellation_rate"],
            "numerator": ["canceled_orders", "cancelled_orders", "canceled_count"],
            "denominator": ["total_orders", "order_count", "all_orders"],
            "factor": 100,
        }
    },
    "category_review_average_top5": {
        "category": {
            "source": ["category", "product_category_name_english", "product_category_name"]
        },
        "avg_review_score": {
            "source": [
                "avg_review_score",
                "average_review_score",
                "review_score_avg",
                "avg_order_review_score",
            ]
        },
    },
    "seller_state_product_sales_top5": {
        "seller_state": {"source": ["seller_state", "state"]},
        "product_sales_amount": {
            "source": ["product_sales_amount", "product_sales", "sales_amount", "total_sales"]
        },
    },
    "payment_type_distinct_orders": {
        "payment_type": {"source": ["payment_type"]},
        "order_count": {"source": ["order_count", "distinct_orders", "orders"]},
    },
    "state_gmv_top1": {
        "customer_state": {"source": ["customer_state", "state"]},
        "gmv": {"source": ["gmv"]},
    },
    "multiturn_state_order_count": {
        "order_count": {"source": ["order_count", "distinct_orders", "orders"]},
    },
}
TOP_K_CASES = {
    "state_gmv_top5",
    "monthly_orders_top5",
    "category_sales_top5",
    "seller_sales_top5",
    "late_rate_by_month",
    "state_order_count_top5",
    "credit_card_gmv_2018_top3",
    "delivery_days_by_state_top5",
    "category_review_average_top5",
    "seller_state_product_sales_top5",
    "state_gmv_top1",
}


def normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {key: normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def pick_value(row: dict[str, Any], candidates: list[str]) -> Any:
    normalized = {key.lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    raise KeyError(
        f"Expected one of these result columns: {', '.join(candidates)}; "
        f"available columns: {', '.join(row.keys()) or '(none)'}"
    )


def compare_rows(
    case_id: str,
    actual_rows: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    field_spec = RESULT_FIELDS[case_id]
    projected_actual: list[dict[str, Any]] = []
    rows_to_compare = (
        actual_rows[: len(expected_rows)] if case_id in TOP_K_CASES else actual_rows
    )
    for row in rows_to_compare:
        projected: dict[str, Any] = {}
        for target, rule in field_spec.items():
            try:
                value = pick_value(row, rule["source"])
            except KeyError:
                if "numerator" not in rule:
                    raise
                numerator = float(pick_value(row, rule["numerator"]))
                denominator = float(pick_value(row, rule["denominator"]))
                value = (numerator / denominator * rule.get("factor", 1)) if denominator else None
            if value is not None and rule.get("factor", 1) != 1:
                numeric_value = float(value)
                value = numeric_value * rule["factor"] if abs(numeric_value) <= 1 else numeric_value
            projected[target] = normalize(value)
        projected_actual.append(projected)

    projected_expected = [
        {target: normalize(row[target]) for target in field_spec}
        for row in expected_rows
    ]
    return (
        projected_actual == projected_expected,
        projected_actual,
        projected_expected,
    )


def compare_sql_candidates(
    case_id: str,
    candidates: list[dict[str, Any]],
    gold_sql: str,
    store: OlistDataStore,
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    expected = store.query(gold_sql)
    attempts: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        try:
            if "rows" in candidate:
                actual_rows = candidate["rows"]
                sql = candidate["sql"]
            else:
                actual = store.query(candidate["sql"])
                actual_rows = actual["rows"]
                sql = actual["sql"]
            matched, projected_actual, projected_expected = compare_rows(
                case_id, actual_rows, expected["rows"]
            )
            attempts.append(
                {
                    "index": index,
                    "sql": sql,
                    "result_match": matched,
                    "actual_rows": actual_rows,
                    "compared_actual_rows": projected_actual,
                    "expected_rows": expected["rows"],
                    "compared_expected_rows": projected_expected,
                    "comparison_error": None,
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "index": index,
                    "sql": candidate.get("sql"),
                    "result_match": False,
                    "actual_rows": candidate.get("rows"),
                    "expected_rows": expected["rows"],
                    "comparison_error": str(exc),
                }
            )

    matching = next((attempt for attempt in attempts if attempt["result_match"]), None)
    selected = matching or (attempts[-1] if attempts else None)
    return bool(matching), selected, attempts, expected["rows"]


_ANSWER_NUMBERS = re.compile(r"(?<!\d)-?\d[\d,，]*(?:\.\d+)?(?!\d)")


def gold_value_mention_coverage(
    answer: str,
    expected_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check whether every expected projected output value appears in the answer."""
    normalized_answer = unicodedata.normalize("NFKC", answer or "").casefold()
    compact_answer = "".join(normalized_answer.split())
    numeric_values = [
        float(token.replace(",", "").replace("，", ""))
        for token in _ANSWER_NUMBERS.findall(normalized_answer)
    ]
    checks: list[dict[str, Any]] = []

    for row_index, row in enumerate(expected_rows):
        for field, value in row.items():
            if value is None:
                continue
            if isinstance(value, str):
                normalized_value = "".join(
                    unicodedata.normalize("NFKC", value).casefold().split()
                )
                found = normalized_value in compact_answer
            elif isinstance(value, (int, float)):
                target = float(value)
                tolerance = 1e-6 if isinstance(value, int) else 0.0051
                found = any(abs(number - target) <= tolerance for number in numeric_values)
            else:
                found = str(value).casefold() in compact_answer
            checks.append(
                {"row": row_index, "field": field, "value": value, "mentioned": found}
            )

    matched = sum(check["mentioned"] for check in checks)
    total = len(checks)
    return {
        "matched_values": matched,
        "total_values": total,
        "coverage": round(matched / total, 4) if total else None,
        "missing": [check for check in checks if not check["mentioned"]],
    }


def evaluate(
    limit: int | None = None,
    benchmark_path: Path = BENCHMARK_PATH,
) -> dict[str, Any]:
    cases = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if limit:
        cases = cases[:limit]

    agent = OlistAnalyticsAgent()
    store = OlistDataStore()
    results: list[dict[str, Any]] = []
    for case in cases:
        item: dict[str, Any] = {"id": case["id"], "question": case["question"]}
        try:
            started_at = time.perf_counter()
            response = agent.answer(case["question"])
            item["tool_steps"] = [
                {
                    "tool": step.get("tool"),
                    "error": step.get("error"),
                    "sql": (step.get("arguments") or {}).get("sql"),
                }
                for step in response.get("tool_trace", [])
            ]
            sql_steps = [
                step for step in response["tool_trace"]
                if step.get("tool") == "run_read_only_sql" and "result" in step
            ]
            if not sql_steps:
                item.update(
                    {
                        "sql_executed": False,
                        "result_match": False,
                        "answer": response.get("answer", ""),
                        "latency_seconds": response.get(
                            "latency_seconds", round(time.perf_counter() - started_at, 3)
                        ),
                        "token_usage": response.get("token_usage", {}),
                    }
                )
            else:
                candidates = [
                    {"sql": step["result"]["sql"], "rows": step["result"]["rows"]}
                    for step in sql_steps
                ]
                result_match, selected, attempts, expected_rows = compare_sql_candidates(
                    case["id"], candidates, case["gold_sql"], store
                )
                item.update(
                    {
                        "sql_executed": True,
                        "result_match": result_match,
                        "compared_actual_rows": (
                            selected.get("compared_actual_rows") if selected else []
                        ),
                        "compared_expected_rows": (
                            selected.get("compared_expected_rows") if selected else []
                        ),
                        "expected_rows": expected_rows,
                        "comparison_error": (
                            selected.get("comparison_error") if selected else "No SQL attempts."
                        ),
                        "generated_sql": selected.get("sql") if selected else None,
                        "query_attempts": attempts,
                        "last_query_result_match": attempts[-1]["result_match"],
                        "answer": response.get("answer", ""),
                        "gold_value_mention_coverage": gold_value_mention_coverage(
                            response.get("answer", ""),
                            selected.get("compared_expected_rows", []) if selected else [],
                        ),
                        "latency_seconds": response.get(
                            "latency_seconds", round(time.perf_counter() - started_at, 3)
                        ),
                        "token_usage": response.get("token_usage", {}),
                    }
                )
        except Exception as exc:
            item.update(
                {
                    "sql_executed": False,
                    "result_match": False,
                    "error": str(exc),
                }
            )
        results.append(item)

    total = len(results)
    executed = sum(bool(item["sql_executed"]) for item in results)
    matched = sum(bool(item["result_match"]) for item in results)
    latencies = [
        item["latency_seconds"]
        for item in results
        if isinstance(item.get("latency_seconds"), (int, float))
    ]
    token_totals = {
        key: sum(
            int((item.get("token_usage") or {}).get(key, 0) or 0)
            for item in results
        )
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    return {
        "benchmark": benchmark_path.name,
        "evaluation_mode": "live_agent_run",
        "total_cases": total,
        "sql_execution_rate": round(executed / total, 4) if total else 0.0,
        "sql_result_match_rate": round(matched / total, 4) if total else 0.0,
        "median_latency_seconds": round(statistics.median(latencies), 3)
        if latencies
        else None,
        "token_usage_total": token_totals,
        "cases": results,
        "note": (
            "A case is a result match when at least one successful SQL tool result "
            "matches its gold SQL projection. query_attempts records every successful "
            "SQL result and last_query_result_match identifies the last one. This does "
            "not prove that the final prose is fully grounded; review answers separately."
        ),
    }


def rescore_existing_report(
    report_path: Path,
    benchmark_path: Path = BENCHMARK_PATH,
) -> dict[str, Any]:
    """Re-run saved Agent SQL locally against gold SQL after evaluator changes."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    benchmark = {
        case["id"]: case
        for case in json.loads(benchmark_path.read_text(encoding="utf-8"))
    }
    store = OlistDataStore()

    for item in report.get("cases", []):
        case = benchmark.get(item["id"])
        saved_steps = [
            step for step in item.get("tool_steps", [])
            if step.get("tool") == "run_read_only_sql" and step.get("sql") and not step.get("error")
        ]
        candidate_sql = [step["sql"] for step in saved_steps]
        if not candidate_sql and item.get("generated_sql"):
            candidate_sql = [item["generated_sql"]]
        if case is None or not candidate_sql:
            item.update(
                {
                    "sql_executed": False,
                    "result_match": False,
                    "comparison_error": "No saved generated SQL to rescore.",
                }
            )
            continue

        try:
            matched, selected, attempts, expected_rows = compare_sql_candidates(
                case["id"],
                [{"sql": sql} for sql in candidate_sql],
                case["gold_sql"],
                store,
            )
            item.update(
                {
                    "sql_executed": True,
                    "result_match": matched,
                    "compared_actual_rows": (
                        selected.get("compared_actual_rows") if selected else []
                    ),
                    "compared_expected_rows": (
                        selected.get("compared_expected_rows") if selected else []
                    ),
                    "expected_rows": expected_rows,
                    "comparison_error": (
                        selected.get("comparison_error") if selected else "No SQL attempts."
                    ),
                    "generated_sql": selected.get("sql") if selected else None,
                    "query_attempts": attempts,
                    "last_query_result_match": attempts[-1]["result_match"] if attempts else False,
                    "gold_value_mention_coverage": gold_value_mention_coverage(
                        item.get("answer", ""),
                        selected.get("compared_expected_rows", []) if selected else [],
                    ),
                }
            )
        except Exception as exc:
            item.update(
                {
                    "sql_executed": False,
                    "result_match": False,
                    "comparison_error": str(exc),
                }
            )

    total = len(report.get("cases", []))
    executed = sum(bool(item.get("sql_executed")) for item in report["cases"])
    matched = sum(bool(item.get("result_match")) for item in report["cases"])
    report.update(
        {
            "sql_execution_rate": round(executed / total, 4) if total else 0.0,
            "sql_result_match_rate": round(matched / total, 4) if total else 0.0,
            "evaluation_mode": "local_rescore_of_saved_agent_sql",
            "note": (
                "Every saved successful Agent SQL query was re-executed locally "
                "against the gold SQL. A case is a result match when at least one "
                "successful query matches. No model API calls were made during this "
                "rescore. gold_value_mention_coverage checks whether expected values "
                "appear in final text; it is a mention check, not semantic answer validation."
            ),
        }
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Olist benchmark using the configured model API."
    )
    parser.add_argument("--limit", type=int, help="Evaluate only the first N cases.")
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=BENCHMARK_PATH,
        help="Path to a JSON benchmark set.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path for the JSON result report.",
    )
    parser.add_argument(
        "--rescore-existing",
        action="store_true",
        help="Re-execute saved Agent SQL locally without model API calls.",
    )
    args = parser.parse_args()

    report = (
        rescore_existing_report(args.output, args.benchmark)
        if args.rescore_existing
        else evaluate(args.limit, args.benchmark)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Cases: {report['total_cases']} | "
        f"SQL execution: {report['sql_execution_rate']:.1%} | "
        f"SQL result match: {report['sql_result_match_rate']:.1%}"
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
