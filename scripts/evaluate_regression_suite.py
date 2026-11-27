from __future__ import annotations

import json
import statistics
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_agent import evaluate, rescore_existing_report

SUITES = [
    ("evaluation/benchmark.json", "evaluation/results/latest.json"),
    ("evaluation/benchmark_challenge.json", "evaluation/results/challenge.json"),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or locally rescore the Olist quantitative regression suite."
    )
    parser.add_argument(
        "--rescore-existing",
        action="store_true",
        help="Re-execute all saved SQL locally without model API calls.",
    )
    args = parser.parse_args()

    summaries = []
    all_latencies: list[float] = []
    token_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    mentioned_values = 0
    expected_values = 0

    for benchmark_rel, report_rel in SUITES:
        report_path = PROJECT_ROOT / report_rel
        benchmark_path = PROJECT_ROOT / benchmark_rel
        report = (
            rescore_existing_report(report_path, benchmark_path)
            if args.rescore_existing
            else evaluate(benchmark_path=benchmark_path)
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summaries.append(
            {
                "benchmark": report["benchmark"],
                "total_cases": report["total_cases"],
                "sql_execution_rate": report["sql_execution_rate"],
                "sql_result_match_rate": report["sql_result_match_rate"],
                "median_latency_seconds": report["median_latency_seconds"],
                "report": report_rel,
            }
        )
        all_latencies.extend(
            case["latency_seconds"]
            for case in report["cases"]
            if isinstance(case.get("latency_seconds"), (int, float))
        )
        for key in token_totals:
            token_totals[key] += report["token_usage_total"][key]
        for case in report["cases"]:
            coverage = case.get("gold_value_mention_coverage") or {}
            mentioned_values += int(coverage.get("matched_values", 0))
            expected_values += int(coverage.get("total_values", 0))
        print(
            f"{report['benchmark']}: {report['total_cases']} cases | "
            f"SQL execution {report['sql_execution_rate']:.1%} | "
            f"result match {report['sql_result_match_rate']:.1%}"
        )

    total_cases = sum(item["total_cases"] for item in summaries)
    execution_count = sum(
        round(item["sql_execution_rate"] * item["total_cases"]) for item in summaries
    )
    match_count = sum(
        round(item["sql_result_match_rate"] * item["total_cases"]) for item in summaries
    )
    suite_report = {
        "evaluation_mode": (
            "local_rescore_of_saved_agent_sql"
            if args.rescore_existing
            else "live_agent_run"
        ),
        "suites": summaries,
        "total_cases": total_cases,
        "sql_execution_rate": round(execution_count / total_cases, 4),
        "sql_result_match_rate": round(match_count / total_cases, 4),
        "median_latency_seconds": round(statistics.median(all_latencies), 3)
        if all_latencies
        else None,
        "token_usage_total": token_totals,
        "gold_value_mention_coverage": {
            "matched_values": mentioned_values,
            "total_values": expected_values,
            "coverage": round(mentioned_values / expected_values, 4)
            if expected_values
            else None,
        },
        "note": (
            "A question is counted as a result match when at least one successful "
            "SQL tool result in its trace matches the gold SQL projection; query_attempts "
            "preserves all successful SQL attempts. The 19-item set is hand-written, "
            "not an estimate of accuracy on arbitrary questions. The gold value "
            "mention coverage is a formatting-tolerant presence check, not a semantic "
            "validation of answer text."
        ),
    }
    output = PROJECT_ROOT / "evaluation/results/regression_suite.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(suite_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Combined: {total_cases} cases | SQL execution "
        f"{suite_report['sql_execution_rate']:.1%} | result match "
        f"{suite_report['sql_result_match_rate']:.1%} | median "
        f"{suite_report['median_latency_seconds']}s | tokens "
        f"{token_totals['total_tokens']} | answer-value mentions "
        f"{suite_report['gold_value_mention_coverage']['coverage']:.1%}"
    )
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
