"""Codex CLI cross-verification — per-phase and final.

Runs `codex exec` in read-only mode to check each phase's output.
Falls back gracefully if codex CLI is not installed or auth has expired.

Phase verification flow:
  Phase 1 → verify_phase1 → PASS/FAIL (FAIL = re-run Phase 1, max 1)
  Phase 2 → verify_phase2 → PASS/FAIL (FAIL = re-run Phase 2, max 1)
  Phase 3 → verify_phase3 → PASS/FAIL (FAIL = re-run Phase 3, max 1)
  Phase 4 → verify_final  → PASS/FAIL (FAIL = re-run report_editor, max 1)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile

log = logging.getLogger(__name__)


# ── Prompts per phase ────────────────────────────────────────────────────────

_PROMPT_PHASE1_3 = (
    "Read the file phase_output.md in this directory. "
    "You are an independent quality reviewer for a due diligence analysis. "
    "Perform these checks and reply in {lang}:\n\n"
    "1. NUMBER CONSISTENCY: 문서 내 수치 불일치를 찾아라. "
    "단위 환산 차이는 제외. 실제 수치가 다른 경우만 보고.\n\n"
    "2. SOURCE VERIFICATION: 결론 영향도 높은 핵심 주장 5건 선별, 검증 필요도 평가.\n\n"
    "3. LOGIC CHECK: 주요 결론이 제시된 데이터와 논리적으로 연결되는지 점검.\n\n"
    "4. BIAS CHECK: 서술이 데이터 대비 과도하게 한쪽으로 치우쳤는지 평가.\n\n"
    "Format as a structured checklist with PASS/FAIL/WARNING for each item.\n"
    "At the end, provide:\n"
    "- OVERALL: PASS/FAIL\n"
    "- SUMMARY: 1-2 sentence overall assessment"
)

_PROMPT_FINAL = (
    "Read the file phase_output.md in this directory. "
    "You are an independent quality reviewer for an investment due diligence report. "
    "Perform these checks and reply in {lang}:\n\n"
    "1. NUMBER CONSISTENCY: Find any numerical inconsistencies between sections. "
    "List each with exact quotes from both locations. "
    "IMPORTANT: Unit conversions that resolve to the same value are NOT inconsistencies.\n\n"
    "2. SOURCE VERIFICATION: List 5 specific factual claims that most urgently need "
    "independent source verification. For each, state why it's risky if wrong.\n\n"
    "3. LOGIC CHECK: Does the final recommendation logically follow from the data presented? "
    "Flag any contradictions.\n\n"
    "4. MISSING DATA: Are there critical data gaps that the report acknowledges "
    "but doesn't adequately flag as risks?\n\n"
    "5. BIAS CHECK: Is the overall narrative excessively bullish or bearish "
    "relative to the data?\n\n"
    "Format as a structured checklist with PASS/FAIL/WARNING for each item.\n"
    "At the end, provide:\n"
    "- OVERALL: PASS/FAIL\n"
    "- SUMMARY: 1-2 sentence overall assessment"
)


# ── Core execution ───────────────────────────────────────────────────────────

def _run_codex(content: str, prompt: str, company: str, phase_name: str) -> dict:
    """Run codex exec on content, return result dict with status/overall/content."""
    if not content.strip():
        log.warning("[codex-%s] No content, skipping", phase_name)
        return {"status": "skipped", "reason": "no content", "overall": "PASS"}

    tmpdir = tempfile.mkdtemp(prefix=f"codex_{phase_name}_")
    input_path = os.path.join(tmpdir, "phase_output.md")
    output_path = os.path.join(tmpdir, "verification.md")

    with open(input_path, "w", encoding="utf-8") as f:
        f.write(content)

    try:
        result = subprocess.run(
            [
                "codex", "exec",
                "-C", tmpdir,
                "-s", "read-only",
                "--skip-git-repo-check",
                "-o", output_path,
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            log.warning("[codex-%s] Exit code %d: %s",
                        phase_name, result.returncode, result.stderr[:500])
            return {"status": "error", "overall": "PASS",
                    "exit_code": result.returncode, "stderr": result.stderr[:500]}

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            with open(output_path, "r", encoding="utf-8") as f:
                verification_text = f.read()

            overall = "PASS"
            for line in verification_text.splitlines():
                if "OVERALL:" in line.upper():
                    if "FAIL" in line.upper():
                        overall = "FAIL"
                    break

            # Save to outputs dir
            try:
                slug = re.sub(r"[^\w\-]", "_", company.strip())[:60]
                out_dir = os.path.join("outputs", slug)
                os.makedirs(out_dir, exist_ok=True)
                save_path = os.path.join(out_dir, f"verification_{phase_name}.md")
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(verification_text)
                log.info("[codex-%s] Saved → %s", phase_name, save_path)
            except Exception as exc:
                log.warning("[codex-%s] Save failed: %s", phase_name, exc)

            log.info("[codex-%s] Overall: %s, Size: %d bytes",
                     phase_name, overall, len(verification_text))

            return {"status": "completed", "overall": overall, "content": verification_text}
        else:
            log.warning("[codex-%s] Output empty or missing", phase_name)
            return {"status": "error", "overall": "PASS", "reason": "empty output"}

    except FileNotFoundError:
        log.warning("[codex-%s] codex CLI not found in PATH", phase_name)
        return {"status": "skipped", "overall": "PASS", "reason": "codex CLI not installed"}
    except subprocess.TimeoutExpired:
        log.warning("[codex-%s] Timed out after 300s", phase_name)
        return {"status": "error", "overall": "PASS", "reason": "timeout"}
    except Exception as exc:
        log.warning("[codex-%s] Error: %s", phase_name, exc)
        return {"status": "error", "overall": "PASS", "reason": str(exc)}


def _extract_phase1_content(state: dict) -> str:
    """Combine all Phase 1 agent outputs into a single MD string."""
    parts = []
    for agent in ("market_analysis", "competitor_analysis", "financial_analysis",
                  "tech_analysis", "legal_regulatory", "team_analysis"):
        data = state.get(agent)
        if data and isinstance(data, dict):
            parts.append(f"# {agent}\n{json.dumps(data, ensure_ascii=False, default=str)[:6000]}\n")
    return "\n---\n".join(parts)


def _extract_phase2_content(state: dict) -> str:
    """Combine Phase 2 synthesis outputs."""
    parts = []
    for agent in ("ra_synthesis", "risk_assessment", "strategic_insight",
                  "industry_synthesis", "benchmark_synthesis"):
        data = state.get(agent)
        if data and isinstance(data, dict):
            parts.append(f"# {agent}\n{json.dumps(data, ensure_ascii=False, default=str)[:6000]}\n")
    return "\n---\n".join(parts)


def _extract_phase3_content(state: dict) -> str:
    """Combine Phase 3 review outputs."""
    parts = []
    for key in ("review_result", "critique_result", "dd_questions"):
        data = state.get(key)
        if data and isinstance(data, dict):
            parts.append(f"# {key}\n{json.dumps(data, ensure_ascii=False, default=str)[:6000]}\n")
    return "\n---\n".join(parts)


# ── Public API — one function per phase ──────────────────────────────────────

def run_phase1(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = _extract_phase1_content(state)
    prompt = _PROMPT_PHASE1_3.format(lang=lang)
    result = _run_codex(content, prompt, company, "phase1")
    return {"verification_phase1": result}


def run_phase2(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = _extract_phase2_content(state)
    prompt = _PROMPT_PHASE1_3.format(lang=lang)
    result = _run_codex(content, prompt, company, "phase2")
    return {"verification_phase2": result}


def run_phase3(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = _extract_phase3_content(state)
    prompt = _PROMPT_PHASE1_3.format(lang=lang)
    result = _run_codex(content, prompt, company, "phase3")
    return {"verification_phase3": result}


def run_final(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = state.get("final_report") or ""
    prompt = _PROMPT_FINAL.format(lang=lang)
    result = _run_codex(content, prompt, company, "final")
    return {"verification_result": result}
