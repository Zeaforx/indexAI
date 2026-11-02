"""Reproducible search benchmark over actual seeded asset links and source routes."""

from sqlalchemy.orm import Session

from .catalog import find_sources, search_resources


def run_evaluation(session: Session, cases: list[dict]) -> dict:
    if not cases or len(cases) > 500:
        raise ValueError("Benchmark must contain 1–500 cases")
    report = []
    for case in cases:
        if not isinstance(case, dict) or not all(case.get(key) for key in ("query", "expected_type", "expected")):
            raise ValueError("Each evaluation case needs query, expected_type and expected")
        kind = case.get("kind")
        dimension = case.get("dimension")
        hits = search_resources(session, case["query"], dimension=dimension, kind=kind, limit=5)
        if case["expected_type"] == "asset":
            passed = any(item["title"] == case["expected"] for item in hits)
            actual = [item["title"] for item in hits]
        elif case["expected_type"] == "source":
            routes = find_sources(session, case["query"], dimension=dimension, kind=kind)
            passed = not hits and any(item["name"] == case["expected"] for item in routes)
            actual = [item["name"] for item in routes] if not hits else [item["title"] for item in hits]
        else:
            raise ValueError(f"Unknown expected_type: {case['expected_type']}")
        report.append({
            "query": case["query"], "expected": case["expected"],
            "type": case["expected_type"], "passed": passed, "top_results": actual,
        })
    direct = [case for case in report if case["type"] == "asset"]
    routed = [case for case in report if case["type"] == "source"]
    return {
        "cases": len(report), "passed": sum(case["passed"] for case in report),
        "asset_hit_at_5": sum(case["passed"] for case in direct) / len(direct) if direct else None,
        "source_fallback_rate": sum(case["passed"] for case in routed) / len(routed) if routed else None,
        "details": report,
    }
