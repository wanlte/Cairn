from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "labels"
ROOT.mkdir(parents=True, exist_ok=True)

TOPICS = [
    ("游标分页", "backend", "稳定排序键替代 offset", "先问排序稳定性"),
    ("JWT 刷新令牌", "auth", "短 access token 配长 refresh token", "先确认过期策略"),
    ("pgvector HNSW", "rag", "用向量索引替代全表扫描", "先看召回质量"),
    ("幂等键", "api", "写接口用幂等键防重复", "先检查重复提交"),
    ("结构化输出", "llm", "用 JSON Schema 约束模型输出", "先确认能力矩阵"),
]


def extraction_labels() -> list[dict]:
    rows = []
    for index in range(50):
        concept, domain, summary, evidence = TOPICS[index % len(TOPICS)]
        rows.append(
            {
                "id": f"ext-{index + 1:03d}",
                "user": f"我在做第 {index + 1} 个实验，关于{concept}，我决定采用这个方案。",
                "assistant": f"可以。{summary}。",
                "expected": {
                    "events": [
                        {
                            "what": f"决定采用{concept}",
                            "domain": domain,
                            "decision": summary,
                            "outcome_status": "UNVERIFIED",
                            "confidence": 0.8,
                        }
                    ],
                    "knowledge": [
                        {
                            "concept": concept,
                            "summary": summary,
                            "category": "concept",
                            "mastery_hint": "used",
                        }
                    ],
                    "traits": [
                        {
                            "trait": "先确认约束",
                            "polarity": "POSITIVE",
                            "evidence": evidence,
                        }
                    ],
                    "state": {"frustration": "LOW", "curiosity": "HIGH", "clarity": "HIGH"},
                },
            }
        )
    return rows


def retrieval_labels() -> list[dict]:
    rows = []
    for index in range(30):
        concept, _domain, _summary, _evidence = TOPICS[index % len(TOPICS)]
        rows.append(
            {
                "id": f"ret-{index + 1:03d}",
                "query": f"{concept}应该怎么用？",
                "expected_concepts": [concept],
            }
        )
    return rows


def review_labels() -> list[dict]:
    rows = []
    for index in range(30):
        concept, _domain, _summary, _evidence = TOPICS[index % len(TOPICS)]
        rows.append(
            {
                "id": f"rev-{index + 1:03d}",
                "fragment_key": concept,
                "expected_verdict": "UNVERIFIED" if index % 3 == 0 else "CORRECT",
            }
        )
    return rows


def write_jsonl(name: str, rows: list[dict]) -> None:
    path = ROOT / name
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(path)


if __name__ == "__main__":
    write_jsonl("extraction_50.jsonl", extraction_labels())
    write_jsonl("retrieval_30.jsonl", retrieval_labels())
    write_jsonl("review_30.jsonl", review_labels())
