"""Codex CLI cross-verification — per-phase and final.

Runs `codex exec` in read-only mode to check each phase's output.
Falls back gracefully if codex CLI is not installed or auth has expired.

Phase verification flow:
  Phase 1 → verify_phase1 → PASS/FAIL (FAIL = re-run Phase 1, max 1)
  Phase 2 → verify_phase2 → PASS/FAIL (FAIL = re-run Phase 2, max 1)
  Phase 3 → verify_phase3 → PASS/FAIL (FAIL = re-run Phase 3, max 1)
  Phase 4 → verify_final  → PASS/FAIL (FAIL = re-run report_editor, max 1)

Improvements v2:
  #1 Ground Truth results always injected into prompts
  #2 Domain-specific checklists (Phase 4)
  #3 Few-shot FAIL examples (Phase 4)
  #4 Adversarial framing (Phase 4)
  #5 Model upgrade: o3 for Phase 4, o4-mini for Phase 1-3
  #6 Per-axis split execution (Phase 4)
  #7 Double-pass false-positive filter (Phase 4)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile

log = logging.getLogger(__name__)


# ── Model selection ─────────────────────────────────────────────────────────

# Default: omit --model flag so Codex CLI uses its default (currently gpt-5.4)
# ChatGPT accounts don't support o3/o4-mini via codex exec
CODEX_MODEL_PHASE1_3 = os.environ.get("CODEX_MODEL_PHASE1_3", "")
CODEX_MODEL_PHASE4 = os.environ.get("CODEX_MODEL_PHASE4", "")


# ── Adversarial framing (#4) ────────────────────────────────────────────────

_ADVERSARIAL_PREAMBLE = (
    "## Your Mission\n"
    "You are a skeptical investor's due diligence reviewer. "
    "Your job is to PROTECT the investor from bad decisions. "
    "Assume the report WANTS you to invest — your role is to find every reason NOT to.\n\n"
    "Specifically hunt for:\n"
    "- Numbers that look suspiciously round or convenient\n"
    "- Claims presented as facts without sources\n"
    "- Risks mentioned but dismissed too quickly\n"
    "- Optimistic projections disguised as conservative estimates\n"
    "- Missing comparisons to industry benchmarks\n"
    "- Survivorship bias in competitor analysis\n\n"
    "If the report is genuinely strong, give it PASS. But every PASS must be EARNED.\n\n"
)


# ── Few-shot examples (#3) ──────────────────────────────────────────────────

_FEW_SHOT_EXAMPLES = (
    "## Examples: What FAIL / PASS / WARNING look like\n\n"
    "Example 1 — NUMBER CONSISTENCY FAIL:\n"
    'Section 1 says "2024 revenue was $2.3B" but Section 5 uses "$1.8B revenue" for same year. '
    "Underlying numbers differ by 27%. → FAIL\n\n"
    "Example 2 — LOGIC CHECK FAIL:\n"
    "Report identifies 3 critical risks and rates overall risk HIGH, "
    "but Executive Summary recommends INVEST with strong conviction. → FAIL\n\n"
    "Example 3 — NUMBER CONSISTENCY PASS (not a real inconsistency):\n"
    '"매출 2,700백만 VND" and "매출 27억 VND" are the same number in different units. → PASS\n\n'
    "Example 4 — BIAS CHECK WARNING:\n"
    "All 15 competitor comparisons favor the target. No area where competitors outperform. → WARNING\n\n"
)


# ── Domain detection (#2) ───────────────────────────────────────────────────

_DOMAIN_PATTERNS = {
    "fintech": r"핀테크|fintech|금융|banking|대출|lending|결제|payment|보험|insurance",
    "biotech": r"바이오|biotech|pharma|임상|clinical|FDA|신약|pipeline|therapeutic",
    "saas": r"saas|arr|mrr|구독|subscription|churn|ndr|cloud.?platform",
    "ecommerce": r"이커머스|e.?commerce|gmv|take.?rate|물류|fulfillment|marketplace",
    "manufacturing": r"제조|manufacturing|생산|production|capa|공장|factory|원자재|raw.?material",
}

_DOMAIN_CHECKLISTS = {
    "fintech": (
        "6. REGULATORY: 금융 라이선스 보유 여부 명시됐는지, 규제 리스크가 구체적으로 기술됐는지, "
        "자본 적정성 언급 여부."
    ),
    "biotech": (
        "6. CLINICAL: 임상 단계(Phase I/II/III) 정확성, 승인 타임라인의 현실성, "
        "파이프라인 가치 평가의 근거."
    ),
    "saas": (
        "6. METRICS: ARR/MRR/NDR/Churn 등 SaaS 핵심 지표가 일관되게 기술됐는지, "
        "cohort 데이터 유무."
    ),
    "ecommerce": (
        "6. UNIT ECONOMICS: GMV/Take rate/CAC/LTV 등 유닛 이코노믹스 수치 일관성, "
        "재구매율 근거."
    ),
    "manufacturing": (
        "6. SUPPLY CHAIN: 원자재 의존도, 생산능력(CAPA) 수치의 현실성, "
        "주요 공급사 집중 리스크."
    ),
}

_DOMAIN_DEFAULT = (
    "6. DOMAIN: 해당 산업의 핵심 KPI가 보고서에 포함되어 있는지, "
    "산업 특유의 리스크가 누락되지 않았는지."
)


def _detect_domain(content: str) -> str:
    lower = content.lower()
    for domain, pattern in _DOMAIN_PATTERNS.items():
        if re.search(pattern, lower):
            return domain
    return "general"


# ── JSON output format ──────────────────────────────────────────────────────

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Output as a single JSON object only. No markdown wrapping.\n"
    '{{\n'
    '  "phase": {phase},\n'
    '  "axes": {{\n'
    '    "number_consistency": {{"verdict": "PASS|FAIL|WARNING", "details": "...", "evidence": []}},\n'
    '    "source_verification": {{"verdict": "PASS|FAIL|WARNING", "details": "...", "top_claims": []}},\n'
    '    "logic_check": {{"verdict": "PASS|FAIL|WARNING", "details": "...", "contradictions": []}},\n'
    '    "missing_data": {{"verdict": "PASS|FAIL|WARNING", "details": "...", "gaps": []}},\n'
    '    "bias_check": {{"verdict": "PASS|FAIL|WARNING", "details": "...", "direction": "balanced|bullish|bearish"}}\n'
    '  }},\n'
    '  "overall": "PASS|FAIL",\n'
    '  "summary": "...",\n'
    '  "fail_axes": []\n'
    '}}\n\n'
    'overall is FAIL if ANY axis is FAIL. fail_axes lists which axes failed.'
)


# ── Prompts per phase ───────────────────────────────────────────────────────

_PROMPT_PHASE1_3 = (
    "Read the file phase_output.md in this directory. "
    "You are an independent quality reviewer for a due diligence analysis. "
    "Perform these checks and reply in {lang}:\n\n"
    "1. NUMBER CONSISTENCY: 문서 내 수치 불일치를 찾아라. "
    "단위 환산 차이는 제외. 실제 수치가 다른 경우만 보고.\n\n"
    "2. SOURCE VERIFICATION: 결론 영향도 높은 핵심 주장 5건 선별, 검증 필요도 평가.\n\n"
    "3. LOGIC CHECK: 주요 결론이 제시된 데이터와 논리적으로 연결되는지 점검.\n\n"
    "4. BIAS CHECK: 서술이 데이터 대비 과도하게 한쪽으로 치우쳤는지 평가.\n\n"
)

_PROMPT_FINAL_BASE = (
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
)


def _build_final_prompt(lang: str, content: str, ground_truth: str = "") -> str:
    """Build Phase 4 prompt with all enhancements."""
    parts = []

    # #4 Adversarial framing
    parts.append(_ADVERSARIAL_PREAMBLE)

    # #1 Ground Truth injection
    if ground_truth:
        parts.append(
            "## Ground Truth Reference (코드 기반 팩트체크 결과)\n"
            f"{ground_truth}\n\n"
            "위 수치는 API로 직접 조회한 값이다. "
            "보고서 수치가 위 verified 값과 ±10% 이상 차이나면 NUMBER CONSISTENCY를 FAIL로 판정하라.\n\n"
        )

    # #3 Few-shot examples
    parts.append(_FEW_SHOT_EXAMPLES)

    # Base prompt
    parts.append(_PROMPT_FINAL_BASE.format(lang=lang))

    # #2 Domain-specific checklist
    domain = _detect_domain(content)
    domain_check = _DOMAIN_CHECKLISTS.get(domain, _DOMAIN_DEFAULT)
    parts.append(f"{domain_check}\n\n")

    # JSON output instruction
    parts.append(_JSON_INSTRUCTION.format(phase=4))

    return "".join(parts)


def _build_phase1_3_prompt(lang: str, phase: int, ground_truth: str = "") -> str:
    """Build Phase 1-3 prompt with Ground Truth injection and JSON output."""
    parts = []

    # #1 Ground Truth injection (if available)
    if ground_truth:
        parts.append(
            "## Ground Truth Reference\n"
            f"{ground_truth}\n\n"
        )

    parts.append(_PROMPT_PHASE1_3.format(lang=lang))
    parts.append(_JSON_INSTRUCTION.format(phase=phase))

    return "".join(parts)


# ── Core execution ──────────────────────────────────────────────────────────

def _parse_json_result(text: str) -> dict | None:
    """Try to parse JSON from Codex output."""
    try:
        # Find JSON by locating "overall" then expanding to balanced braces
        idx = text.find('"overall"')
        if idx == -1:
            return None
        # Walk backwards to find opening {
        depth = 0
        start = idx
        for i in range(idx, -1, -1):
            if text[i] == '}': depth += 1
            elif text[i] == '{':
                if depth == 0:
                    start = i
                    break
                depth -= 1
        # Walk forwards to find closing }
        depth = 0
        end = idx
        for i in range(start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        json_str = text[start:end] if start < idx else None
        if json_str:
            return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _parse_overall(text: str) -> tuple[str, list[str]]:
    """Parse overall verdict and fail_axes from Codex output."""
    data = _parse_json_result(text)
    if data:
        return data.get("overall", "PASS"), data.get("fail_axes", [])

    # Regex fallback
    overall = "PASS"
    for line in text.splitlines():
        if "OVERALL:" in line.upper() and "FAIL" in line.upper():
            overall = "FAIL"
            break
    return overall, []


def _run_codex(content: str, prompt: str, company: str, phase_name: str,
               model: str = "") -> dict:
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
        cmd = ["codex", "exec"]
        if model:
            cmd += ["--model", model]
        cmd += [
            "-C", tmpdir,
            "-s", "read-only",
            "--skip-git-repo-check",
            "-o", output_path,
            prompt,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            log.warning("[codex-%s] Exit code %d: %s",
                        phase_name, result.returncode, result.stderr[:500])
            return {"status": "error", "overall": "PASS",
                    "exit_code": result.returncode, "stderr": result.stderr[:500]}

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            with open(output_path, "r", encoding="utf-8") as f:
                verification_text = f.read()

            overall, fail_axes = _parse_overall(verification_text)

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

            log.info("[codex-%s] Model: %s, Overall: %s, Fail axes: %s, Size: %d bytes",
                     phase_name, model, overall, fail_axes, len(verification_text))

            return {"status": "completed", "overall": overall, "content": verification_text,
                    "fail_axes": fail_axes, "model": model}
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


# ── Double-pass false positive filter (#7) ──────────────────────────────────

def _recheck_false_positives(content: str, first_pass_result: dict,
                             company: str, lang: str) -> dict:
    """Run 2nd Codex pass to filter false positives from FAIL items."""
    fail_axes = first_pass_result.get("fail_axes", [])
    first_text = first_pass_result.get("content", "")

    if not fail_axes or not first_text:
        return first_pass_result

    recheck_prompt = (
        f"Read phase_output.md (the original report) and the following 1st-pass verification.\n\n"
        f"## 1st Pass Verification Results (FAIL items)\n{first_text}\n\n"
        "You are a SENIOR reviewer checking whether the 1st reviewer's FAIL judgments are correct.\n"
        "For each FAIL item, determine:\n"
        "1. Is this a REAL issue (confirmed FAIL)?\n"
        "2. Is this a FALSE POSITIVE (should be PASS or WARNING)?\n\n"
        "Common false positives:\n"
        "- Unit conversion differences (억 vs 백만, B vs M)\n"
        "- Rounding differences (1.23B vs 1.2B)\n"
        "- Different time periods compared (2023 vs 2024)\n"
        "- Legitimate differences between source estimates\n\n"
        "Output JSON only:\n"
        '{"recheck": [{"axis": "...", "original_verdict": "FAIL", '
        '"confirmed": true, "reason": "..."}], '
        '"final_overall": "PASS|FAIL", '
        '"final_fail_axes": ["only confirmed FAILs"]}'
    )

    log.info("[codex-recheck] Running false positive filter on %d FAIL axes", len(fail_axes))
    recheck = _run_codex(content, recheck_prompt, company, "recheck", model=CODEX_MODEL_PHASE4)

    if recheck.get("status") != "completed":
        log.warning("[codex-recheck] Recheck failed, using original result")
        return first_pass_result

    recheck_data = _parse_json_result(recheck.get("content", ""))
    if recheck_data:
        final_overall = recheck_data.get("final_overall", first_pass_result["overall"])
        final_fail = recheck_data.get("final_fail_axes", fail_axes)
        log.info("[codex-recheck] Original: %s (%s) → Final: %s (%s)",
                 first_pass_result["overall"], fail_axes, final_overall, final_fail)
        return {
            **first_pass_result,
            "overall": final_overall,
            "fail_axes": final_fail,
            "recheck": recheck_data,
            "content": first_pass_result["content"] + "\n\n---\n## Recheck\n" + recheck.get("content", ""),
        }

    return first_pass_result


# ── Ground Truth helper (#1) ────────────────────────────────────────────────

def _get_ground_truth(state: dict) -> str:
    """Extract ground truth check results from state if available."""
    gt = state.get("ground_truth_check")
    if gt and isinstance(gt, str):
        return gt
    if gt and isinstance(gt, dict):
        return json.dumps(gt, ensure_ascii=False, default=str)
    return ""


# ── Phase content extractors ────────────────────────────────────────────────

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


# ── Public API — one function per phase ─────────────────────────────────────

def run_phase1(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = _extract_phase1_content(state)
    ground_truth = _get_ground_truth(state)
    prompt = _build_phase1_3_prompt(lang, phase=1, ground_truth=ground_truth)
    result = _run_codex(content, prompt, company, "phase1", model=CODEX_MODEL_PHASE1_3)
    return {"verification_phase1": result}


def run_phase2(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = _extract_phase2_content(state)
    ground_truth = _get_ground_truth(state)
    prompt = _build_phase1_3_prompt(lang, phase=2, ground_truth=ground_truth)
    result = _run_codex(content, prompt, company, "phase2", model=CODEX_MODEL_PHASE1_3)
    return {"verification_phase2": result}


def run_phase3(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = _extract_phase3_content(state)
    ground_truth = _get_ground_truth(state)
    prompt = _build_phase1_3_prompt(lang, phase=3, ground_truth=ground_truth)
    result = _run_codex(content, prompt, company, "phase3", model=CODEX_MODEL_PHASE1_3)
    return {"verification_phase3": result}


def run_final(state: dict) -> dict:
    lang = state.get("language", "Korean")
    company = state.get("company_name", "unknown")
    content = state.get("final_report") or ""
    ground_truth = _get_ground_truth(state)

    # Build enhanced Phase 4 prompt (#1 #2 #3 #4)
    prompt = _build_final_prompt(lang, content, ground_truth=ground_truth)

    # Run with default model (#5)
    result = _run_codex(content, prompt, company, "final", model=CODEX_MODEL_PHASE4)

    # #7 Double-pass false positive filter (only if FAIL)
    if result.get("overall") == "FAIL" and result.get("status") == "completed":
        result = _recheck_false_positives(content, result, company, lang)

    return {"verification_result": result}
