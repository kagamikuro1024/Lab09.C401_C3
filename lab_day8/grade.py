#!/usr/bin/env python3
"""
Lab Day 08: Grading Script — Score phương án của team vitest grading_questions
==============================================================================
Chạy 10 grading questions (gq01-gq10), dùng gpt-4-turbo để:
  1. So sánh answer với grading_criteria
  2. Detect hallucination từ failure_modes
  3. Chấm điểm: Full (100%) / Partial (50%) / Zero (0) / Penalty (-50%)
  4. Tính tổng điểm raw và convert sang 30 điểm nhóm

Output:
  - logs/grading_run.json: Log detail (id, question, answer, sources, timestamp)
  - logs/grading_scores.json: Scoring details (criteria check, hallucination, score)
  - logs/grading_report.md: Human-readable report với tính toán điểm
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Load environment
load_dotenv()

# Add lab dir to path
sys.path.insert(0, str(Path(__file__).parent))
from rag_answer import rag_answer

# =============================================================================
# CẤU HÌNH
# =============================================================================

GRADING_QUESTIONS_PATH = Path(__file__).parent / "grading_questions.json"
LOGS_DIR = Path(__file__).parent / "logs"
RESULTS_DIR = Path(__file__).parent / "results"

# OpenAI config
GRADING_MODEL = "gpt-4-turbo"
GRADING_TEMPERATURE = 0.5  # Hơi cao cho reasoning
GRADING_MAX_TOKENS = 256

# Initialize OpenAI client
_openai_client = None

def _get_openai_client():
    """Lấy hoặc tạo OpenAI client"""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

# =============================================================================
# GRADING FUNCTIONS
# =============================================================================

def check_criteria_met(
    answer: str,
    expected_answer: str,
    context: str,
    query: str,
    criteria: List[str],
) -> Tuple[List[bool], str]:
    """
    Dùng gpt-4-turbo để check xem answer đáp ứng mỗi criterion trong grading_criteria.
    
    Returns:
        (list[bool], reasoning_string)
        Mỗi boolean = True nếu criterion được đáp ứng
    """
    criteria_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(criteria))
    
    prompt = f"""You are a grading assistant. Check if the answer meets each grading criterion.

QUERY: {query}

EXPECTED ANSWER (for reference):
{expected_answer[:500]}

STUDENT ANSWER:
{answer[:500]}

GRADING CRITERIA:
{criteria_text}

For each criterion, respond with ONLY:
criterion_1: YES / NO
criterion_2: YES / NO
...

Be strict: answer only YES if criterion is clearly met."""

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=GRADING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=GRADING_TEMPERATURE,
            max_tokens=GRADING_MAX_TOKENS
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse YES/NO for each criterion
        met = []
        lines = response_text.split("\n")
        for i, criterion in enumerate(criteria):
            # Look for pattern "criterion_X: YES" or just last "YES/NO"
            yesno_found = "NO"  # Default to NO (strict)
            for line in lines:
                if "YES" in line.upper() and f"criterion_{i+1}" in line.lower():
                    yesno_found = "YES"
                    break
                elif "YES" in line.upper() and i < len(lines) - 1:
                    # Check if this line is roughly at right position
                    if lines.index(line) == i or lines.index(line) == i + 1:
                        yesno_found = "YES"
                        break
            met.append(yesno_found == "YES")
        
        return met, response_text
    
    except Exception as e:
        print(f"      [ERROR in check_criteria_met: {e}]")
        # Return all False if error
        return [False] * len(criteria), str(e)


def detect_hallucination(
    answer: str,
    context: str,
    expected_answer: str,
    failure_modes: List[str],
) -> Tuple[bool, str]:
    """
    Detect hallucination: answer contains info không có trong context hoặc failure modes.
    
    Returns:
        (is_hallucinating, reasoning)
    """
    failure_text = "\n".join(f"- {fm}" for fm in failure_modes)
    
    prompt = f"""You are a hallucination detector for RAG systems.

CONTEXT (retrieved documents):
{context[:500]}

STUDENT ANSWER:
{answer[:500]}

COMMON FAILURE MODES (things that would count as hallucination):
{failure_text}

Detect if answer contains information that:
1. Is NOT supported by the context
2. Matches any of the failure modes (bịa ra con số, tên, quy trình, kết luận)

Respond with ONLY:
HALLUCINATION: YES/NO
REASON: (one-line explanation)"""

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=GRADING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=GRADING_TEMPERATURE,
            max_tokens=64
        )
        
        response_text = response.choices[0].message.content.strip()
        is_hallucinating = "YES" in response_text.upper()
        
        return is_hallucinating, response_text
    
    except Exception as e:
        print(f"      [ERROR in detect_hallucination: {e}]")
        return False, str(e)  # Conservative: assume not hallucinating if error


def calculate_score(
    criteria_met: List[bool],
    is_hallucinating: bool,
) -> Tuple[str, float]:
    """
    Tính điểm theo rubric:
    - Full (100%): tất cả criteria met, không hallucinate
    - Partial (50%): ≥50% criteria met, không hallucinate
    - Zero (0): <50% criteria met, không hallucinate
    - Penalty (-50%): hallucinate
    
    Returns:
        (level: "FULL"/"PARTIAL"/"ZERO"/"PENALTY", score_multiplier: 1.0/0.5/0.0/-0.5)
    """
    if is_hallucinating:
        return "PENALTY", -0.5
    
    pct_met = sum(criteria_met) / len(criteria_met) if criteria_met else 0.0
    
    if pct_met == 1.0:
        return "FULL", 1.0
    elif pct_met >= 0.5:
        return "PARTIAL", 0.5
    else:
        return "ZERO", 0.0


# =============================================================================
# GRADING RUNNER
# =============================================================================

def run_grading(verbose: bool = True) -> Dict[str, Any]:
    """
    Chạy grading_questions.json qua pipeline và chấm điểm.
    
    Returns:
        grading_report dict: {
            "timestamp",
            "questions": [...scoring detail...],
            "summary": {"raw_score", "total_points", "grades_by_level"},
            "log": [...]  # For logs/grading_run.json
        }
    """
    
    # Load grading questions
    if not GRADING_QUESTIONS_PATH.exists():
        raise FileNotFoundError(f"grading_questions.json not found: {GRADING_QUESTIONS_PATH}")
    
    with open(GRADING_QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)
    
    print(f"\n{'='*80}")
    print(f"GRADING SESSION: {len(questions)} questions")
    print(f"{'='*80}\n")
    
    grading_report = {
        "timestamp": datetime.now().isoformat(),
        "questions": [],
        "summary": {},
        "log": [],
    }
    
    total_raw = 0
    total_possible = 0
    level_counts = {"FULL": 0, "PARTIAL": 0, "ZERO": 0, "PENALTY": 0}
    
    for i, q in enumerate(questions, 1):
        q_id = q["id"]
        query = q["question"]
        expected_answer = q.get("expected_answer", "")
        expected_sources = q.get("expected_sources", [])
        difficulty = q.get("difficulty", "medium")
        category = q.get("category", "")
        criteria = q.get("grading_criteria", [])
        failure_modes = q.get("failure_modes", [])
        points = q.get("points", 10)
        
        if verbose:
            print(f"[{i}/{len(questions)}] {q_id}: {query[:60]}...")
            print(f"         Difficulty: {difficulty} | Category: {category} | Points: {points}")
        
        # --- Run RAG pipeline ---
        try:
            result = rag_answer(query, retrieval_mode="hybrid", verbose=False)
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            chunks_used = result.get("chunks_used", [])
            
            if verbose:
                print(f"         Answer: {answer[:80]}...")
                print(f"         Sources: {sources}")
        except Exception as e:
            print(f"         [ERROR running pipeline: {e}]")
            answer = ""
            sources = []
            chunks_used = []
        
        # --- Build context from chunks ---
        context = "\n".join([c.get("text", "") for c in chunks_used[:3]])
        
        # --- Check criteria ---
        if verbose:
            print(f"         Checking {len(criteria)} criteria...")
        criteria_met, criteria_reasoning = check_criteria_met(
            answer, expected_answer, context, query, criteria
        )
        
        # --- Detect hallucination ---
        is_hallucinating, hallucination_reasoning = detect_hallucination(
            answer, context, expected_answer, failure_modes
        )
        
        # --- Calculate score ---
        level, multiplier = calculate_score(criteria_met, is_hallucinating)
        raw_score = points * multiplier
        
        if verbose:
            print(f"         Criteria met: {sum(criteria_met)}/{len(criteria_met)}")
            print(f"         Hallucination: {is_hallucinating}")
            print(f"         Score level: {level}")
            print(f"         Raw score: {raw_score:+.1f}/{points}\n")
        
        # --- Record result ---
        question_result = {
            "id": q_id,
            "question": query,
            "answer": answer,
            "expected_answer": expected_answer,
            "sources": sources,
            "chunks_retrieved": len(chunks_used),
            "difficulty": difficulty,
            "category": category,
            "points_max": points,
            "criteria": criteria,
            "criteria_met": criteria_met,
            "criteria_reasoning": criteria_reasoning,
            "failure_modes": failure_modes,
            "hallucination_detected": is_hallucinating,
            "hallucination_reasoning": hallucination_reasoning,
            "score_level": level,
            "score_multiplier": multiplier,
            "raw_score": raw_score,
            "timestamp": datetime.now().isoformat(),
        }
        
        grading_report["questions"].append(question_result)
        grading_report["log"].append({
            "id": q_id,
            "question": query,
            "answer": answer,
            "sources": sources,
            "chunks_retrieved": len(chunks_used),
            "retrieval_mode": "hybrid",
            "timestamp": datetime.now().isoformat(),
        })
        
        total_raw += raw_score
        total_possible += points
        level_counts[level] += 1
    
    # Summary
    grading_report["summary"] = {
        "total_questions": len(questions),
        "total_raw_score": total_raw,
        "total_possible_score": total_possible,
        "percentage_raw": (total_raw / total_possible * 100) if total_possible > 0 else 0,
        "group_score_30": (total_raw / total_possible * 30) if total_possible > 0 else 0,
        "by_level": level_counts,
    }
    
    print(f"{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total raw score: {total_raw:+.1f}/{total_possible}")
    print(f"Percentage: {grading_report['summary']['percentage_raw']:.1f}%")
    print(f"Group score (30 điểm): {grading_report['summary']['group_score_30']:.1f}/30")
    print(f"Level distribution: {level_counts}")
    print(f"{'='*80}\n")
    
    return grading_report


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_grading_report_md(grading_report: Dict) -> str:
    """Generate markdown report from grading_report"""
    
    lines = [
        "# Grading Report — Lab Day 08",
        f"Generated: {grading_report['timestamp']}",
        "",
        "## Summary",
        "",
        f"- **Total Raw Score**: {grading_report['summary']['total_raw_score']:+.1f}/{grading_report['summary']['total_possible_score']}",
        f"- **Percentage**: {grading_report['summary']['percentage_raw']:.1f}%",
        f"- **Group Score (30 điểm)**: {grading_report['summary']['group_score_30']:.1f}/30",
        "",
        "### By Level",
        "",
        "| Level | Count |",
        "|-------|-------|",
    ]
    
    for level, count in grading_report['summary']['by_level'].items():
        lines.append(f"| {level} | {count} |")
    
    lines.extend([
        "",
        "## Per-Question Results",
        "",
    ])
    
    for q in grading_report["questions"]:
        lines.extend([
            f"### {q['id']} — {q['question'][:60]}... ({q['difficulty']})",
            f"**Points**: {q['points_max']} | **Score Level**: {q['score_level']} | **Raw Score**: {q['raw_score']:+.1f}",
            "",
            "#### Grading Criteria",
            "",
        ])
        
        for i, (criterion, met) in enumerate(zip(q['criteria'], q['criteria_met'])):
            status = "✅" if met else "❌"
            lines.append(f"{status} {criterion}")
        
        lines.extend([
            "",
            f"#### Hallucination Check",
            f"**Detected**: {'🚨 YES' if q['hallucination_detected'] else '✅ NO'}",
            f"**Reasoning**: {q['hallucination_reasoning'][:200]}",
            "",
            f"#### Student Answer",
            f"```\n{q['answer']}\n```",
            "",
            f"#### Sources Retrieved",
            "",
        ])
        
        for source in q['sources']:
            lines.append(f"- {source}")
        
        lines.extend([
            "",
            "---",
            "",
        ])
    
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run full grading session"""
    
    # Create directories
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Run grading
    grading_report = run_grading(verbose=True)
    
    # Save results
    
    # 1. logs/grading_run.json — required by SCORING.md
    grading_log_path = LOGS_DIR / "grading_run.json"
    with open(grading_log_path, "w", encoding="utf-8") as f:
        json.dump(grading_report["log"], f, ensure_ascii=False, indent=2)
    print(f"✓ Grading log: {grading_log_path}")
    
    # 2. logs/grading_scores.json — detailed scoring
    grading_scores_path = LOGS_DIR / "grading_scores.json"
    with open(grading_scores_path, "w", encoding="utf-8") as f:
        json.dump(grading_report["questions"], f, ensure_ascii=False, indent=2)
    print(f"✓ Grading scores: {grading_scores_path}")
    
    # 3. logs/grading_report.md — human-readable
    grading_report_path = LOGS_DIR / "grading_report.md"
    with open(grading_report_path, "w", encoding="utf-8") as f:
        f.write(generate_grading_report_md(grading_report))
    print(f"✓ Grading report: {grading_report_path}")
    
    print(f"\n{'='*80}")
    print("Grading Session Complete ✓")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
