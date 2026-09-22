"""Run an evaluation over the held-out alarms.

    python -m app.eval.run --predictor baseline-majority-by-code
    python -m app.eval.run --predictor agent

Cases come from the database rather than a checked-in file: alarm ids are assigned at
seed time, so a pinned file would go stale on every reseed. The resolved case list is
written into the report, so any run can be audited after the fact.

Ground truth is read straight from the `alarms` table. It never travels through the API
or the MCP tools, which is what keeps it out of the agent's reach.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Alarm
from app.db.session import get_engine, get_sessionmaker
from app.eval.metrics import CaseResult, score, to_markdown
from app.eval.predictors import AlwaysEscalate, MajorityByCode, Predictor, TriageAgent

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "eval" / "reports"


async def load_cases(session, limit: int | None = None) -> list[Alarm]:
    query = select(Alarm).where(Alarm.is_eval_case.is_(True)).order_by(Alarm.id)
    if limit:
        query = query.limit(limit)
    return list((await session.execute(query)).scalars())


async def build_predictor(name: str, session) -> Predictor:
    if name == "baseline-always-escalate":
        return AlwaysEscalate()
    if name == "baseline-majority-by-code":
        predictor = MajorityByCode()
        await predictor.fit(session)
        return predictor
    if name == "agent":
        return TriageAgent(get_settings().groq_model)
    raise SystemExit(f"Unknown predictor: {name}")


async def evaluate(predictor_name: str, limit: int | None, out_dir: Path) -> dict:
    sessionmaker = get_sessionmaker()
    results: list[CaseResult] = []

    async with sessionmaker() as session:
        predictor = await build_predictor(predictor_name, session)
        cases = await load_cases(session, limit)
        if not cases:
            raise SystemExit("No eval alarms found. Run the seeder first.")

        print(f"Scoring {len(cases)} held-out alarms with {predictor.name}\n")
        for i, alarm in enumerate(cases, 1):
            prediction = await predictor.predict(session, alarm)
            result = CaseResult(
                alarm_id=alarm.id,
                alarm_code=alarm.alarm_code,
                scenario=alarm.scenario or "unknown",
                expected_action=alarm.truth_action or "",
                expected_root_cause=alarm.truth_root_cause or "",
                predicted_action=prediction.action,
                predicted_root_cause=prediction.root_cause,
                confidence=prediction.confidence,
                evidence_count=prediction.evidence_count,
                tool_calls=prediction.tool_calls,
                latency_ms=prediction.latency_ms,
                fallback=prediction.fallback,
                error=prediction.error,
            )
            results.append(result)
            mark = "ok " if result.action_correct else "MISS"
            note = f"  [{prediction.error}]" if prediction.error else ""
            print(
                f"  {i:>3}/{len(cases)}  {mark}  {alarm.alarm_code:<19} "
                f"expected={result.expected_action:<9} got={result.predicted_action}{note}"
            )

    report = score(results, predictor.name)

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = predictor.name.replace("/", "-")
    (out_dir / f"{stamp}-{slug}.json").write_text(json.dumps(report.to_dict(), indent=2))
    (out_dir / f"{stamp}-{slug}.md").write_text(to_markdown(report))
    (out_dir / "latest.json").write_text(json.dumps(report.to_dict(), indent=2))

    print("\n" + to_markdown(report))
    print(f"Written to {out_dir}/{stamp}-{slug}.json")

    await get_engine().dispose()
    return report.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate triage on held-out alarms.")
    parser.add_argument(
        "--predictor",
        default="baseline-majority-by-code",
        choices=["agent", "baseline-majority-by-code", "baseline-always-escalate"],
    )
    parser.add_argument("--limit", type=int, default=None, help="score only the first N cases")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    asyncio.run(evaluate(args.predictor, args.limit, args.out))


if __name__ == "__main__":
    main()
