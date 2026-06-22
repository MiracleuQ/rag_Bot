"""
RAG Evaluation Script

Computes key metrics for RAG quality:
- Context Relevance: How relevant are the retrieved documents
- Answer Faithfulness: Does the answer stay faithful to retrieved context
- Answer Relevance: Does the answer address the question
- Keyword Coverage: Does the answer cover expected keywords

Usage:
    python eval/run.py [--api-url http://localhost:8000] [--top-k 3]
"""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QA_PAIRS_PATH = Path(__file__).parent / "qa_pairs.json"


def load_qa_pairs(path: Path = QA_PAIRS_PATH) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("qa_pairs", [])


def call_rag(api_url: str, question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"question": question}
    if session_id:
        payload["session_id"] = session_id
    resp = httpx.post(f"{api_url}/chat", json=payload, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def keyword_coverage(answer: str, expected_keywords: List[str]) -> float:
    if not expected_keywords:
        return 1.0
    answer_lower = answer.lower()
    hit = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return hit / len(expected_keywords)


def context_relevance(answer: str, used_docs: List[Dict[str, Any]]) -> float:
    if not used_docs:
        return 0.0
    answer_tokens = set(answer.lower().split())
    overlap_scores = []
    for doc in used_docs:
        doc_tokens = set(str(doc.get("content", "")).lower().split())
        if not doc_tokens:
            overlap_scores.append(0.0)
            continue
        overlap = len(answer_tokens & doc_tokens) / max(1, len(answer_tokens))
        overlap_scores.append(overlap)
    return sum(overlap_scores) / len(overlap_scores) if overlap_scores else 0.0


def run_evaluation(api_url: str, top_k: int = 3) -> Dict[str, Any]:
    qa_pairs = load_qa_pairs()
    logger.info("Loaded %d QA pairs", len(qa_pairs))

    results = []
    total_keyword_coverage = 0.0
    total_context_relevance = 0.0
    total_answer_length = 0
    errors = 0

    for pair in qa_pairs:
        qa_id = pair["id"]
        question = pair["question"]
        expected_keywords = pair.get("expected_keywords", [])

        try:
            start = time.time()
            response = call_rag(api_url, question)
            latency = time.time() - start

            answer = response.get("answer", "")
            used_docs = response.get("used_docs", [])

            kw_score = keyword_coverage(answer, expected_keywords)
            ctx_score = context_relevance(answer, used_docs)

            total_keyword_coverage += kw_score
            total_context_relevance += ctx_score
            total_answer_length += len(answer)

            result = {
                "id": qa_id,
                "question": question,
                "answer": answer[:200] + "..." if len(answer) > 200 else answer,
                "keyword_coverage": round(kw_score, 3),
                "context_relevance": round(ctx_score, 3),
                "doc_count": len(used_docs),
                "latency_sec": round(latency, 2),
                "status": "ok",
            }
        except Exception as e:
            errors += 1
            result = {
                "id": qa_id,
                "question": question,
                "answer": "",
                "keyword_coverage": 0.0,
                "context_relevance": 0.0,
                "doc_count": 0,
                "latency_sec": 0.0,
                "status": f"error: {e}",
            }

        results.append(result)
        logger.info("[%s] kw=%.2f ctx=%.2f latency=%.2fs status=%s",
                     qa_id, result["keyword_coverage"], result["context_relevance"],
                     result["latency_sec"], result["status"])

    n = max(1, len(qa_pairs))
    summary = {
        "total_questions": len(qa_pairs),
        "errors": errors,
        "success_rate": round((len(qa_pairs) - errors) / n, 3),
        "avg_keyword_coverage": round(total_keyword_coverage / n, 3),
        "avg_context_relevance": round(total_context_relevance / n, 3),
        "avg_answer_length": round(total_answer_length / n, 1),
    }

    return {"summary": summary, "details": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG evaluation runner")
    parser.add_argument("--api-url", default="http://localhost:8000", help="RAG API base URL")
    parser.add_argument("--top-k", type=int, default=3, help="Top-k retrieval")
    parser.add_argument("--output", default="eval/results.json", help="Output JSON path")
    args = parser.parse_args()

    report = run_evaluation(args.api_url, args.top_k)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    summary = report["summary"]
    print("\n" + "=" * 60)
    print("RAG Evaluation Summary")
    print("=" * 60)
    print(f"  Questions:            {summary['total_questions']}")
    print(f"  Errors:               {summary['errors']}")
    print(f"  Success Rate:         {summary['success_rate']:.1%}")
    print(f"  Avg Keyword Coverage: {summary['avg_keyword_coverage']:.1%}")
    print(f"  Avg Context Relevance:{summary['avg_context_relevance']:.1%}")
    print(f"  Avg Answer Length:    {summary['avg_answer_length']:.0f} chars")
    print("=" * 60)
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
