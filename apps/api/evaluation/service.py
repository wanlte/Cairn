from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models.extraction import Fragment
from apps.api.db.models.review import ReviewItem, ReviewReport
from apps.api.errors import AppError
from apps.api.evaluation.schemas import (
    DatasetInfo,
    EvaluationRunRequest,
    ExtractionEvalResponse,
    RetrievalEvalResponse,
    ReviewEvalResponse,
)
from apps.api.extraction.schemas import (
    FRAGMENT_JSON_SCHEMA,
    ExtractionOutput,
)
from apps.api.gateway.factory import build_gateway_for_user
from apps.api.gateway.schemas import GatewayOptions, GatewayRequest, ResponseFormat
from apps.api.retrieval.schemas import RetrievalSearchRequest
from apps.api.retrieval.service import RetrievalService

LABELS_ROOT = Path(__file__).resolve().parents[3] / "eval" / "labels"
EXTRACTION_PROMPT = Path(__file__).resolve().parents[3] / "prompts" / "extraction" / "v1.txt"

DATASETS = {
    "extraction_50.jsonl": "抽取字段准确率合成标签集",
    "retrieval_30.jsonl": "检索 Recall@5 合成标签集",
    "review_30.jsonl": "复盘一致率合成标签集",
}


def load_dataset(name: str, limit: int | None = None) -> list[dict]:
    if name not in DATASETS:
        raise AppError("DATASET_NOT_FOUND", f"未知数据集：{name}", 404)
    path = LABELS_ROOT / name
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows[:limit] if limit else rows


def list_datasets() -> list[DatasetInfo]:
    return [
        DatasetInfo(
            name=name,
            rows=len(load_dataset(name)),
            synthetic=True,
            description=description,
        )
        for name, description in DATASETS.items()
    ]


def _flatten_expected(expected: dict) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in ("events", "knowledge", "traits"):
        items = expected.get(key) or []
        if items:
            for field, value in items[0].items():
                fields[f"{key}.{field}"] = value
    state = expected.get("state") or {}
    for field, value in state.items():
        fields[f"state.{field}"] = value
    return fields


def _flatten_actual(output: ExtractionOutput) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if output.events:
        for field, value in output.events[0].model_dump(mode="json").items():
            fields[f"events.{field}"] = value
    if output.knowledge:
        for field, value in output.knowledge[0].model_dump(mode="json").items():
            fields[f"knowledge.{field}"] = value
    if output.traits:
        for field, value in output.traits[0].model_dump(mode="json").items():
            fields[f"traits.{field}"] = value
    for field, value in output.state.model_dump(mode="json").items():
        fields[f"state.{field}"] = value
    return fields


def _values_equal(key: str, expected: Any, actual: Any) -> bool:
    if key == "events.confidence":
        try:
            return abs(float(expected) - float(actual)) <= 0.1
        except (TypeError, ValueError):
            return False
    return str(expected).strip() == str(actual).strip()


class EvaluationService:
    async def evaluate_extraction(
        self, session: AsyncSession, user_id: int, request: EvaluationRunRequest
    ) -> ExtractionEvalResponse:
        dataset = request.dataset or "extraction_50.jsonl"
        rows = load_dataset(dataset, request.limit)
        settings = get_settings()
        gateway, _credential_id, _model, _provider = await build_gateway_for_user(
            session,
            user_id,
            **request.gateway_kwargs(),
        )
        prompt = EXTRACTION_PROMPT.read_text(encoding="utf-8")
        correct_fields = 0
        total_fields = 0
        failures: list[dict] = []

        for row in rows:
            expected = _flatten_expected(row["expected"])
            response = await gateway.complete(
                GatewayRequest(
                    task="extract",
                    messages=[
                        {"role": "system", "content": prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"user": row["user"], "assistant": row["assistant"]},
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    options=GatewayOptions(
                        response_format=ResponseFormat.JSON_SCHEMA,
                        output_schema=FRAGMENT_JSON_SCHEMA,
                        timeout_seconds=settings.gateway_read_timeout_review,
                    ),
                    user_id=user_id,
                )
            )
            try:
                actual = _flatten_actual(ExtractionOutput.model_validate(response.data or {}))
            except Exception:  # noqa: BLE001 - 评测样本失败计入错误
                actual = {}
            for key, expected_value in expected.items():
                total_fields += 1
                if key in actual and _values_equal(key, expected_value, actual[key]):
                    correct_fields += 1
                else:
                    failures.append(
                        {
                            "sample_id": row["id"],
                            "field": key,
                            "expected": expected_value,
                            "actual": actual.get(key),
                        }
                    )
        accuracy = correct_fields / total_fields if total_fields else 0.0
        return ExtractionEvalResponse(
            dataset=dataset,
            sample_count=len(rows),
            correct_fields=correct_fields,
            total_fields=total_fields,
            accuracy=round(accuracy, 4),
            threshold=settings.eval_extraction_accuracy_threshold,
            passed=accuracy >= settings.eval_extraction_accuracy_threshold,
            failures=failures[:50],
        )

    async def evaluate_review(
        self, session: AsyncSession, user_id: int, request: EvaluationRunRequest
    ) -> ReviewEvalResponse:
        dataset = request.dataset or "review_30.jsonl"
        rows = load_dataset(dataset, request.limit)
        report = (
            await session.execute(
                select(ReviewReport)
                .where(ReviewReport.user_id == user_id)
                .order_by(ReviewReport.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not report:
            raise AppError("REVIEW_NOT_FOUND", "没有可评测的复盘报告", 404)

        fragments = (
            await session.execute(
                select(Fragment).where(Fragment.user_id == user_id)
            )
        ).scalars().all()
        by_id = {item.id: item for item in fragments}
        judgments = (
            await session.execute(
                select(ReviewItem).where(
                    ReviewItem.report_id == report.id,
                    ReviewItem.section == "judgment",
                )
            )
        ).scalars().all()

        matched = 0
        consistent = 0
        failures: list[dict] = []
        for row in rows:
            key = row["fragment_key"]
            candidates = [
                item
                for item in judgments
                if any(
                    key in json.dumps(by_id[fid].payload_json, ensure_ascii=False)
                    for fid in item.evidence_fragment_ids
                    if fid in by_id
                )
            ]
            if not candidates:
                failures.append({"sample_id": row["id"], "reason": "未找到对应判断"})
                continue
            matched += 1
            actual = candidates[0].verdict
            if actual == row["expected_verdict"]:
                consistent += 1
            else:
                failures.append(
                    {
                        "sample_id": row["id"],
                        "expected": row["expected_verdict"],
                        "actual": actual,
                    }
                )
        settings = get_settings()
        score = consistent / matched if matched else 0.0
        return ReviewEvalResponse(
            dataset=dataset,
            sample_count=len(rows),
            matched=matched,
            consistent=consistent,
            consistency=round(score, 4),
            threshold=settings.eval_review_consistency_threshold,
            passed=score >= settings.eval_review_consistency_threshold,
            failures=failures[:50],
        )

    async def evaluate_retrieval(
        self, session: AsyncSession, user_id: int, request: EvaluationRunRequest
    ) -> RetrievalEvalResponse:
        dataset = request.dataset or "retrieval_30.jsonl"
        rows = load_dataset(dataset, request.limit)
        service = RetrievalService()
        hit = 0
        failures: list[dict] = []
        for row in rows:
            result = await service.search(
                session,
                user_id,
                RetrievalSearchRequest(
                    query=row["query"],
                    top_k=5,
                    credential_id=request.credential_id,
                    provider=request.provider,
                    model=request.model,
                ),
            )
            retrieved = "\n".join(
                json.dumps(item.payload, ensure_ascii=False) for item in result.items
            )
            keywords = row.get("expected_concepts") or []
            if any(keyword in retrieved for keyword in keywords):
                hit += 1
            else:
                failures.append({"sample_id": row["id"], "query": row["query"]})
        settings = get_settings()
        recall = hit / len(rows) if rows else 0.0
        return RetrievalEvalResponse(
            dataset=dataset,
            sample_count=len(rows),
            hit_at_5=hit,
            recall_at_5=round(recall, 4),
            threshold=settings.eval_retrieval_recall_threshold,
            passed=recall >= settings.eval_retrieval_recall_threshold,
            failures=failures[:50],
        )


evaluation_service = EvaluationService()
