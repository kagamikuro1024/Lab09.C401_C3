#!/usr/bin/env python3
"""
Sprint 4: LLM-as-Judge Evaluation & Scorecard
==============================================
Chạy 10 test questions qua dense baseline + hybrid variant.
Chấm điểm theo 4 metrics dùng gpt-4-turbo:
  - Faithfulness: Có grounded trong context không?
  - Answer Relevance: Có trả lời đúng câu hỏi không?
  - Context Recall: Có retrieve đủ expected sources không?
  - Completeness: Có bao phủ đủ thông tin không?

So sánh baseline vs variant & ghi kết quả scorecard.
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Load environment
load_dotenv()

# Add lab dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from rag_answer import rag_answer


# =============================================================================
# CẤU HÌNH
# =============================================================================

TEST_QUESTIONS_PATH = Path(__file__).parent / "data" / "test_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

# OpenAI config
EVAL_MODEL = "gpt-4-turbo"
EVAL_TEMPERATURE = 0.5  # Hơi cao cho reasoning nuanced
EVAL_MAX_TOKENS = 128

# Initialize OpenAI client
_openai_client = None

def _get_openai_client():
    """Lấy hoặc tạo OpenAI client"""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

# Cấu hình Baseline (Sprint 2 — Dense only)
BASELINE_CONFIG = {
    "retrieval_mode": "dense",
    "top_k_search": 10,
    "label": "baseline_dense",
}

# Cấu hình Variant (Sprint 3 — Hybrid RRF + Rerank)
VARIANT_CONFIG = {
    "retrieval_mode": "hybrid",
    "top_k_search": 10,
    "dense_weight": 0.7,
    "sparse_weight": 0.3,
    "use_rerank": True,
    "label": "variant_hybrid",
}


# =============================================================================
# SCORING FUNCTIONS — Dùng LLM-as-Judge (gpt-4-turbo)
# =============================================================================

def score_faithfulness(answer: str, context: str, query: str) -> float:
    """
    Faithfulness: Câu trả lời có grounded trong context không?
    LLM-as-Judge: gpt-4-turbo chấm 0-5
    
    Returns: float 0-5
    """
    prompt = f"""You are a factuality checker. Score how faithfully the answer is grounded in the provided context.

QUERY: {query}

CONTEXT (retrieved chunks):
{context[:500]}

ANSWER: {answer}

Score on scale 0-5:
5 = Completely grounded in context, no hallucination
4 = Mostly grounded, minor inferences acceptable
3 = Mixed, some info possibly outside context
1 = Mostly not grounded
0 = Complete hallucination

Respond with ONLY the number (0-5), no explanation."""

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=EVAL_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=EVAL_TEMPERATURE,
            max_tokens=10
        )
        score = int(response.choices[0].message.content.strip())
        return min(5, max(0, score))
    except Exception as e:
        print(f"      [ERROR in score_faithfulness: {e}]")
        return 2.5  # Default


def score_answer_relevance(answer: str, query: str) -> float:
    """
    Answer Relevance: Điều gì có trả lời đúng câu hỏi không?
    LLM-as-Judge: gpt-4-turbo chấm 0-5
    
    Returns: float 0-5
    """
    prompt = f"""You are a relevance judge. Score how well the answer addresses the query.

QUERY: {query}

ANSWER: {answer}

Score on scale 0-5:
5 = Directly and completely answers the query
4 = Answers most aspects of the query
3 = Partially addresses the query
1 = Tangentially related
0 = Completely irrelevant

Respond with ONLY the number (0-5), no explanation."""

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=EVAL_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=EVAL_TEMPERATURE,
            max_tokens=10
        )
        score = int(response.choices[0].message.content.strip())
        return min(5, max(0, score))
    except Exception as e:
        print(f"      [ERROR in score_answer_relevance: {e}]")
        return 2.5


def score_context_recall(chunks_used: List[Dict], expected_sources: List[str]) -> float:
    """
    Context Recall: Retriever có lấy được expected sources không?
    Binary/scaled: 0-1.0
    
    Returns: float 0-1.0
    """
    if not expected_sources:
        # Out-of-domain case: expected_sources rỗng
        # Chấm cao nếu model abstain (ít chunks) hoặc thấp nếu bịa
        return 1.0 if len(chunks_used) <= 3 else 0.3

    # Lấy source từ chunks
    retrieved_sources = set()
    for chunk in chunks_used:
        metadata = chunk.get("metadata", {})
        source = metadata.get("source", "")
        if source:
            # Normalize: lấy tên file
            source_name = source.split("/")[-1].lower().replace(".pdf", "").replace(".txt", "").replace(".md", "")
            retrieved_sources.add(source_name)

    # Check expected sources
    found = 0
    for expected in expected_sources:
        expected_name = expected.split("/")[-1].lower().replace(".pdf", "").replace(".txt", "").replace(".md", "")
        if expected_name in retrieved_sources or any(expected_name in rs for rs in retrieved_sources):
            found += 1

    recall = found / len(expected_sources) if expected_sources else 1.0
    return min(1.0, max(0, recall))


def score_completeness(answer: str, expected_answer: str) -> float:
    """
    Completeness: Có bao phủ đủ thông tin như expected_answer không?
    LLM-as-Judge: gpt-4-turbo (0-1.0 scale)
    
    Returns: float 0-1.0
    """
    prompt = f"""You are a completeness evaluator. Compare expected answer with actual answer.
Rate how complete the actual answer is.

EXPECTED ANSWER:
{expected_answer}

ACTUAL ANSWER:
{answer}

Score on scale 0-1.0:
1.0 = Comprehensive, covers all key points
0.7 = Mostly complete, minor omissions
0.5 = Covers core but missing details
0.3 = Incomplete, gaps
0 = Missing key information

Respond with ONLY a float (0-1.0), no explanation."""

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=EVAL_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=EVAL_TEMPERATURE,
            max_tokens=10
        )
        score = float(response.choices[0].message.content.strip())
        return min(1.0, max(0, score))
    except Exception as e:
        print(f"      [ERROR in score_completeness: {e}]")
        return 0.5



# =============================================================================
# SCORECARD RUNNER
# =============================================================================

def run_scorecard(
    config: Dict[str, Any],
    test_questions: Optional[List[Dict]] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Chạy toàn bộ test questions qua pipeline và chấm điểm (gpt-4-turbo).
    
    Args:
        config: Pipeline config
        test_questions: List questions hoặc load từ JSON
        verbose: In kết quả
    
    Returns:
        scorecard dict: {"config", "questions": [...], "averages": {...}}
    """
    if test_questions is None:
        with open(TEST_QUESTIONS_PATH, "r", encoding="utf-8") as f:
            test_questions = json.load(f)

    label = config.get("label", "unnamed")
    scorecard = {
        "config": config,
        "label": label,
        "timestamp": datetime.now().isoformat(),
        "questions": [],
        "averages": {}
    }

    metrics = ["faithfulness", "answer_relevance", "context_recall", "completeness"]
    aggregates = {m: [] for m in metrics}

    print(f"\n{'='*70}")
    print(f"SCORECARD: {label}")
    print('='*70)

    for i, q_obj in enumerate(test_questions, 1):
        q_id = q_obj.get("id", f"q{i:02d}")
        query = q_obj["question"]
        expected_answer = q_obj.get("expected_answer", "")
        expected_sources = q_obj.get("expected_sources", [])
        category = q_obj.get("category", "")

        if verbose:
            print(f"\n[{i}/{len(test_questions)}] {q_id}: {query[:60]}...")

        # --- Call RAG pipeline ---
        try:
            result = rag_answer(
                query=query,
                retrieval_mode=config.get("retrieval_mode", "dense"),
                use_rerank=config.get("use_rerank", False),
                verbose=False
            )
            answer = result["answer"]
            chunks_used = result.get("chunks_used", [])
        except Exception as e:
            if verbose:
                print(f"      ERROR: {e}")
            answer = f"PIPELINE ERROR: {str(e)[:50]}"
            chunks_used = []

        # --- Build context for faithfulness ---
        context_text = "\n".join([
            f"[{j}] {chunk.get('text', '')[:1200]}"
            for j, chunk in enumerate(chunks_used[:3], 1)
        ]) if chunks_used else "[No context retrieved]"

        # --- Score all 4 metrics (LLM-as-Judge) ---
        if verbose:
            print(f"      Computing scores (gpt-4-turbo)...", end=" ", flush=True)

        faith_score = score_faithfulness(answer, context_text, query)
        relev_score = score_answer_relevance(answer, query)
        recall_score = score_context_recall(chunks_used, expected_sources)
        complet_score = score_completeness(answer, expected_answer)

        if verbose:
            print(f"\n      Scores: Faith={faith_score:.1f} | Relev={relev_score:.1f} | "
                  f"Recall={recall_score:.2f} | Complet={complet_score:.2f}")

        # Save result
        q_result = {
            "id": q_id,
            "category": category,
            "query": query,
            "expected_answer": expected_answer,
            "expected_sources": expected_sources,
            "actual_answer": answer[:200],  # Truncate for JSON
            "chunks_used": len(chunks_used),
            "scores": {
                "faithfulness": round(faith_score, 2),
                "answer_relevance": round(relev_score, 2),
                "context_recall": round(recall_score, 2),
                "completeness": round(complet_score, 2)
            }
        }
        scorecard["questions"].append(q_result)

        # Aggregate
        aggregates["faithfulness"].append(faith_score)
        aggregates["answer_relevance"].append(relev_score)
        aggregates["context_recall"].append(recall_score)
        aggregates["completeness"].append(complet_score)

    # Calculate averages
    for metric in metrics:
        scores = aggregates[metric]
        avg = sum(scores) / len(scores) if scores else 0
        scorecard["averages"][metric] = round(avg, 3)

    # Print summary
    print(f"\n{'='*70}")
    print("AVERAGES:")
    print('='*70)
    for metric, avg in scorecard["averages"].items():
        print(f"  {metric.replace('_', ' ').title():<20} {avg:.3f}")

    return scorecard


def compare_ab(baseline_scorecard: Dict, variant_scorecard: Dict) -> str:
    """
    So sánh baseline vs variant, trả về formatted table.
    """
    baseline_avg = baseline_scorecard.get("averages", {})
    variant_avg = variant_scorecard.get("averages", {})

    metrics = ["faithfulness", "answer_relevance", "context_recall", "completeness"]
    scales = [5, 5, 1, 1]  # Max scales

    lines = []
    lines.append("\n" + "="*90)
    lines.append("BASELINE vs VARIANT COMPARISON")
    lines.append("="*90)
    lines.append(f"{'Metric':<25} {'Baseline':<15} {'Variant':<15} {'Delta':<20} {'Improvement %':<15}")
    lines.append("-"*90)

    total_baseline = 0
    total_variant = 0

    for metric, max_scale in zip(metrics, scales):
        baseline_val = baseline_avg.get(metric, 0)
        variant_val = variant_avg.get(metric, 0)
        delta = variant_val - baseline_val

        # Delta percentage relative to max scale
        if max_scale > 0:
            delta_pct = (delta / max_scale) * 100
        else:
            delta_pct = 0

        delta_str = f"{delta:+.3f}" if abs(delta) > 0 else "0.000"
        
        # Winner indicator
        winner = "↑ VARIANT" if delta > 0.05 else ("↓ BASELINE" if delta < -0.05 else "TIE")

        lines.append(
            f"{metric.replace('_', ' ').title():<25} "
            f"{baseline_val:>6.3f}/{max_scale:<7} "
            f"{variant_val:>6.3f}/{max_scale:<7} "
            f"{delta_str:>10} "
            f"{delta_pct:>+7.1f}%         {winner:<10}"
        )

        total_baseline += baseline_val / max_scale
        total_variant += variant_val / max_scale

    lines.append("-"*90)
    total_delta = total_variant - total_baseline
    total_pct = (total_delta / len(metrics)) * 100 if len(metrics) > 0 else 0
    lines.append(
        f"{'TOTAL (avg)':<25} "
        f"{total_baseline/len(metrics):>6.3f}        "
        f"{total_variant/len(metrics):>6.3f}         "
        f"{total_delta/len(metrics):>+.3f}      "
        f"{total_pct:>+7.1f}%"
    )
    lines.append("="*90)

    return "\n".join(lines)



# =============================================================================
# REPORT GENERATOR
# =============================================================================

def generate_scorecard_md(scorecard: Dict) -> str:
    """Tạo markdown report từ scorecard dict"""
    label = scorecard.get("label", "unknown")
    timestamp = scorecard.get("timestamp", "")
    questions = scorecard.get("questions", [])
    averages = scorecard.get("averages", {})

    md_lines = [
        f"# Scorecard: {label}",
        f"Generated: {timestamp}",
        "",
        "## Summary",
        "",
        "| Metric | Score |",
        "|--------|-------|"
    ]

    for metric, score in averages.items():
        max_scale = 5 if "recall" not in metric else 1
        md_lines.append(f"| {metric.replace('_', ' ').title()} | {score:.3f}/{max_scale} |")

    md_lines.extend([
        "",
        "## Per-Question Results",
        "",
        "| ID | Category | Faith | Relevance | Recall | Complete | Chunks |",
        "|-------|----------|-------|-----------|--------|----------|--------|"
    ])

    for q in questions:
        scores = q.get("scores", {})
        md_lines.append(
            f"| {q['id']} | {q['category']} | "
            f"{scores.get('faithfulness', 0):.1f} | "
            f"{scores.get('answer_relevance', 0):.1f} | "
            f"{scores.get('context_recall', 0):.2f} | "
            f"{scores.get('completeness', 0):.2f} | "
            f"{q['chunks_used']} |"
        )

    return "\n".join(md_lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run full evaluation: baseline (dense) vs variant (hybrid)"""

    print("="*70)
    print("SPRINT 4: LLM-as-Judge Evaluation & Scorecard")
    print("="*70)

    # Load test questions
    print(f"\nLoading test questions from: {TEST_QUESTIONS_PATH}")
    try:
        with open(TEST_QUESTIONS_PATH, "r", encoding="utf-8") as f:
            test_questions = json.load(f)
        print(f"✓ Loaded {len(test_questions)} test questions")
    except FileNotFoundError:
        print("✗ File not found!")
        return

    # Baseline: Dense retrieval
    print("\n" + "="*70)
    print("EVALUATING BASELINE: Dense Retrieval")
    print("="*70)
    baseline_scorecard = run_scorecard(
        BASELINE_CONFIG,
        test_questions,
        verbose=True
    )

    # Variant: Hybrid RRF
    print("\n" + "="*70)
    print("EVALUATING VARIANT: Hybrid Retrieval (RRF)")
    print("="*70)
    variant_scorecard = run_scorecard(
        VARIANT_CONFIG,
        test_questions,
        verbose=True
    )

    # Comparison
    comparison_table = compare_ab(baseline_scorecard, variant_scorecard)
    print(comparison_table)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Save JSON results
    baseline_json = RESULTS_DIR / "scorecard_baseline.json"
    variant_json = RESULTS_DIR / "scorecard_variant.json"
    comparison_txt = RESULTS_DIR / "comparison.txt"

    with open(baseline_json, "w", encoding="utf-8") as f:
        json.dump(baseline_scorecard, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Baseline scorecard: {baseline_json}")

    with open(variant_json, "w", encoding="utf-8") as f:
        json.dump(variant_scorecard, f, indent=2, ensure_ascii=False)
    print(f"✓ Variant scorecard: {variant_json}")

    with open(comparison_txt, "w", encoding="utf-8") as f:
        f.write(comparison_table)
    print(f"✓ Comparison: {comparison_txt}")

    # Save markdown reports
    baseline_md = RESULTS_DIR / "scorecard_baseline.md"
    variant_md = RESULTS_DIR / "scorecard_variant.md"

    with open(baseline_md, "w", encoding="utf-8") as f:
        f.write(generate_scorecard_md(baseline_scorecard))
    print(f"✓ Baseline markdown: {baseline_md}")

    with open(variant_md, "w", encoding="utf-8") as f:
        f.write(generate_scorecard_md(variant_scorecard))
    print(f"✓ Variant markdown: {variant_md}")

    print("\n" + "="*70)
    print("Sprint 4 Evaluation Complete ✓")
    print("="*70)


if __name__ == "__main__":
    main()
