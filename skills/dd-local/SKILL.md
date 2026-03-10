# DD Local — Investment Due Diligence (Claude Code Subscription)

Run the full 14-agent due diligence pipeline locally using Claude Code subscription only ($0 API cost).
Mirrors the DD Agent pipeline (LangGraph + Anthropic API) but uses Agent subagents + WebSearch + Bash.

**Context-safe architecture**: Each agent runs as a separate Agent subagent that writes its full output
to disk. The main session NEVER holds full agent outputs in context — only completion confirmations.
Phase-to-phase data flows through disk files, not through the orchestrator's context window.

## Trigger
`/dd-local <company_name> [--url <url>] [--lang Korean|English] [--docs file1.pdf file2.pdf file3.xlsx]`

## Arguments
- `company_name` (required): Target company name
- `--url`: Company website URL
- `--lang`: Output language (default: Korean)
- `--docs`: Paths to uploaded documents for analysis (PDF, Excel supported)

## Architecture

14 agents across 4 phases. Execution pattern matches the API version exactly.

```
Phase 1 (parallel, batches of 3):
  market_analysis, competitor_analysis, financial_analysis
  tech_analysis, legal_regulatory, team_analysis

Phase 1 Aggregator (subagent reads disk, writes _aggregator.json):
  Smart Aggregator → settled_claims, tensions, gaps

Phase 2 (ra_synthesis + risk_assessment parallel, then strategic_insight sequential):
  ra_synthesis, risk_assessment
  strategic_insight

Phase 3 (review sequential, then critique + dd_questions parallel):
  review_agent → (critique_agent + dd_questions)

Phase 4 (section writers → editor, no report_structure):
  6 section_writers (all parallel) → report_editor
```

### Context Isolation Pattern (CRITICAL)

```
Main session context:  only holds "agent X completed" messages (~100 chars each)
                       NEVER reads full agent JSON outputs into main context

Each Agent subagent:   reads system prompt from .py file
                       does research (WebSearch, Bash)
                       writes FULL JSON output to disk
                       returns ONLY: "Completed. Confidence: X. File: path"

Phase-to-phase:        next phase's agents READ prior outputs from disk
                       within THEIR OWN context (not main session)
```

## Step 1: Parse Input and Setup

1. Extract company_name, url, lang, docs from user prompt
2. Create output directory: `dd-local-outputs/<company_slug>/`
3. Detect if company is public:
   ```bash
   python -c "
   import yfinance as yf, json
   t = yf.Ticker('<CANDIDATE>')
   info = t.info
   print(json.dumps({'is_public': bool(info.get('marketCap')), 'ticker': '<CANDIDATE>' if info.get('marketCap') else None}))
   "
   ```
4. If docs provided, verify files exist
5. Check for resume: if `dd-local-outputs/<company_slug>/` already has JSON files, skip completed agents

## Step 2: Phase 1 — Research (6 agents, batches of 3)

Dispatch 6 agents using **Agent tool** with `subagent_type: "general-purpose"`. Run in **batches of 3** (parallel within batch).

### Batch 1: market_analysis + competitor_analysis + financial_analysis (parallel)
### Batch 2: tech_analysis + legal_regulatory + team_analysis (parallel)

Wait for each batch to complete before starting the next.

### Resume Logic
Before dispatching an agent, check if its output file already exists:
```bash
ls dd-local-outputs/<company_slug>/<agent_name>.json 2>/dev/null
```
If the file exists AND is non-empty, SKIP that agent and log "Skipping <agent_name> (already completed)".

### Agent Dispatch Template

For EACH agent, use **Agent tool** with `subagent_type: "general-purpose"`. Each agent prompt must include:

1. The system prompt (from `agents/phase1/<agent>.py` — read the SYSTEM_PROMPT variable)
2. Company context (name, url, is_public, ticker, language)
3. Tool instructions (see Tool Mapping below)
4. Output file path instruction
5. **Return instruction**: "After writing the JSON file, respond with ONLY: `Done. File: <path>`"

**Critical prompt structure for each agent:**

```
## Role
<paste SYSTEM_PROMPT from the corresponding agent .py file>

## Company
- Name: <company_name>
- URL: <url>
- Public: <is_public> | Ticker: <ticker>
- Language: <lang>

## Tools Available
You have WebSearch and Bash. For data tools, run Python via Bash:
<tool-specific instructions — see Tool Mapping>

## Research Quality Rules (MANDATORY)
1. TOOL CALL BUDGET (HARD LIMIT — STOP if exceeded):
   - Total tool calls per agent: MAX 15 (including PDF reads, searches, data tools, Write)
   - Search calls (Tavily + WebSearch combined): MAX 5
   - Plan ALL queries BEFORE searching. Write them out, then execute.
   - Do NOT repeat queries with slightly different wording (e.g., "Upstage funding"
     and "업스테이지 투자 유치" counts as 2 — pick the better one).
   - If you hit 15 tool calls, STOP searching and write your output with current data.
2. CROSS-VERIFY: Every key claim must be verified with 3+ independent sources.
   If you can only find 1 source, mark confidence as "low".
3. BLACKLISTED SOURCES (HARD BLOCK — ZERO TOLERANCE):
   NEVER cite, reference, or use data from: Grand View Research, Allied Market Research,
   Mordor Intelligence, Verified Market Research, Fortune Business Insights, or ANY
   "market research aggregator" that sells reports. If a search result comes from these
   sources, SKIP IT entirely — do not even mention the number. If no credible source
   exists for a market size claim, say "no credible source available" instead of using
   a blacklisted one. Credible sources ONLY: Gartner, IDC, Forrester, McKinsey,
   Bloomberg, official filings (DART/SEC), company IR, Reuters, reputable news outlets.
4. [DATA] vs [INFERENCE] LABELING: In your output, prefix every major statement with:
   - [DATA] = directly from a source (tool result, document, filing). Include the source.
   - [INFERENCE] = your own analysis or interpretation based on data.
   This is CRITICAL for downstream agents to know what's verified vs. speculative.
4. RECENCY: Prefer newest sources. Anything >6 months old should be re-verified.
   Newer source always wins over older on conflict.
5. Use actual numbers, not vague summaries. "Revenue grew 23% YoY to $4.2B" not "strong growth".
6. LATEST PRODUCTS: Always search for the company's MOST RECENT product releases,
   model versions, and announcements (within last 3 months). Include one search query
   specifically for "<company> latest release OR new product OR launch 2025 OR 2026".
   Missing the latest flagship product is a critical failure.
7. EXCHANGE RATE: When converting currencies (e.g., KRW↔USD), fetch the rate from
   yfinance at analysis time. Use this snippet:
   python -c "import yfinance as yf; print(yf.Ticker('USDKRW=X').info.get('regularMarketPrice','N/A'))"
   Always state the rate and date used. Do NOT use hardcoded or estimated rates.

## Documents
<if docs provided, read ALL docs in a SINGLE Bash call to save tool calls:
python -c "
import fitz, openpyxl
for path in ['<path1>', '<path2>']:
    print(f'=== {path} ===')
    if path.endswith(('.xlsx', '.xls')):
        wb = openpyxl.load_workbook(path, data_only=True)
        for sn in wb.sheetnames:
            ws = wb[sn]
            print(f'--- Sheet: {sn} ---')
            for row in ws.iter_rows(values_only=True):
                vals = [str(c) if c is not None else '' for c in row]
                print('\t'.join(vals))
    else:
        doc = fitz.open(path)
        for i in range(min(len(doc), 50)):
            print(doc[i].get_text()[:3000])
"
This counts as 1 tool call instead of N. NEVER read docs separately.
>

## Output
Write your complete JSON result to: dd-local-outputs/<company_slug>/<agent_name>.json
Use the Write tool. Include ALL fields from the schema above.

IMPORTANT: After writing the file, your final message must be ONLY:
"Done. File: dd-local-outputs/<company_slug>/<agent_name>.json"
Do NOT include the JSON content in your response. The file IS the deliverable.
```

### Tool Mapping by Agent

Matches `tools/executor.py:get_tools_for_agent()` exactly. Each agent gets **two search channels**:

1. **Tavily** (via Bash -> Python): Higher quality, domain filtering, news search with date range. Uses TAVILY_API_KEY from .env.
2. **WebSearch** (Claude Code built-in): Free fallback. Use when Tavily quota is exhausted or for quick lookups.

**IMPORTANT: All Python snippets must call `from dotenv import load_dotenv; load_dotenv()`
BEFORE accessing `os.environ` for API keys. Without this, .env keys are not loaded.**

**Tavily helper snippets** (use via Bash tool):
```bash
# web_search (general)
python -c "
from dotenv import load_dotenv; load_dotenv()
from tavily import TavilyClient
import os, json
client = TavilyClient(api_key=os.environ['TAVILY_API_KEY'])
result = client.search('QUERY', search_depth='advanced', max_results=5, include_answer=True)
print(json.dumps(result, ensure_ascii=False, indent=2))
"

# news_search (recent news, last 14 days)
python -c "
from dotenv import load_dotenv; load_dotenv()
from tavily import TavilyClient
import os, json
client = TavilyClient(api_key=os.environ['TAVILY_API_KEY'])
result = client.search('QUERY', search_depth='advanced', topic='news', days=14, max_results=5, include_answer=True)
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

**Per-agent tool allocation** (mirrors API version):

| Agent | Tavily web | Tavily news | yfinance | DART | SEC EDGAR | GitHub | Patents | Google Trends | FRED | PDF |
|-------|-----------|-------------|----------|------|-----------|--------|---------|---------------|------|-----|
| market_analysis | Y | Y | info | | | | | interest+related | | Y |
| competitor_analysis | Y | | info | | | | | | | Y |
| financial_analysis | Y | | info+financials+analyst | finstate+company+list | filings+facts | | | | | Y |
| tech_analysis | Y | Y | | | | search+stats | search | | | Y |
| legal_regulatory | Y | Y | | list | | | | | | Y |
| team_analysis | Y | | | | | | | | | Y |
| risk_assessment | Y | Y | | | | | | | | |
| review_agent | Y | | info | finstate | | | | | | |

**Agents with NO tools** (receive prior phase data via disk reads): ra_synthesis, strategic_insight, critique_agent, dd_questions, report_writer (section writers).

**Data tool snippets** (via Bash — ALL include `load_dotenv()`):

**IMPORTANT: Combine related data calls into SINGLE Bash calls to save tool budget.**

```bash
# yfinance ALL-IN-ONE (info + financials + balance sheet + exchange rate = 1 tool call)
python -c "
import yfinance as yf, json, sys
sys.stdout.reconfigure(encoding='utf-8')
t = yf.Ticker('TICKER')
print('=== INFO ===')
print(json.dumps({k:str(v) for k,v in t.info.items()}))
print('=== FINANCIALS ===')
print(t.financials.to_json())
print('=== BALANCE SHEET ===')
print(t.balance_sheet.to_json())
print('=== EXCHANGE RATE ===')
fx = yf.Ticker('USDKRW=X').info.get('regularMarketPrice','N/A')
print(f'USDKRW={fx}')
"

# DART ALL-IN-ONE (company info + finstate/audit report = 1 tool call)
python -c "
from dotenv import load_dotenv; load_dotenv()
import OpenDartReader, json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
dart = OpenDartReader(os.environ.get('DART_API_KEY',''))
# Company info
print('=== COMPANY INFO ===')
info = dart.company('CORP_CODE')
print(json.dumps(info, ensure_ascii=False, default=str))
# Try finstate
print('=== FINSTATE ===')
fs = dart.finstate('CORP_CODE', 2024)
if isinstance(fs, dict) and fs.get('status') == '013':
    print('NO_DATA: trying audit report fallback')
    # Fallback: fetch 감사보고서
    print('=== AUDIT REPORT ===')
    filings = dart.list('CORP_CODE', start='2023-01-01', end='2025-12-31')
    audit = [f for _, f in filings.iterrows() if '감사보고서' in str(f.get('report_nm',''))]
    if audit:
        doc = dart.document(audit[0]['rcept_no'])
        summary = {}
        for code, label in [('TOT_ASSETS','총자산'),('TOT_DEBTS','총부채'),('TOT_SALES','매출액'),('TOT_EMPL','직원수')]:
            m = re.search(f'ACODE=\"{code}\"[^>]*>([^<]+)<', doc)
            if m: summary[label] = m.group(1)
        print(json.dumps(summary, ensure_ascii=False))
        body_start = doc.find('<BODY')
        if body_start > 0: print(doc[body_start:body_start+8000])
else:
    print(fs.to_json(force_ascii=False))
# Filing list
print('=== FILING LIST ===')
fl = dart.list('CORP_CODE', start='2023-01-01', end='2025-12-31')
if fl is not None and len(fl) > 0: print(fl[['rcept_no','report_nm','rcept_dt']].to_string())
"

# SEC EDGAR ALL-IN-ONE (filings + facts = 1 tool call)
python -c "
from edgar import Company
c = Company('COMPANY_NAME')
print('=== 10-K FILINGS ===')
print(c.get_filings(form='10-K').latest(1))
print('=== COMPANY FACTS ===')
print(c.get_facts())
"

# GitHub ALL-IN-ONE (search + top repo stats = 1 tool call)
python -c "
from dotenv import load_dotenv; load_dotenv()
import requests, json, os
token = os.environ.get('GITHUB_TOKEN','')
headers = {'Authorization': f'token {token}'} if token else {}
print('=== REPO SEARCH ===')
r = requests.get('https://api.github.com/search/repositories?q=QUERY', headers=headers)
data = r.json()
print(json.dumps(data, indent=2))
if data.get('items'):
    top = data['items'][0]
    print('=== TOP REPO STATS ===')
    r2 = requests.get(f'https://api.github.com/repos/{top[\"full_name\"]}', headers=headers)
    print(json.dumps(r2.json(), indent=2))
"

# Google Trends ALL-IN-ONE (interest + related = 1 tool call)
python -c "
from pytrends.request import TrendReq
import json
pt = TrendReq()
pt.build_payload(['KEYWORD'])
print('=== INTEREST OVER TIME ===')
print(pt.interest_over_time().to_json())
print('=== RELATED QUERIES ===')
print(json.dumps(pt.related_queries(), default=str))
"

# Patents (USPTO PatentsView) — 1 tool call
python -c "
import requests, json
r = requests.post('https://api.patentsview.org/patents/query',
    json={'q':{'_text_any':{'patent_abstract':'KEYWORD'}}, 'f':['patent_number','patent_title','patent_date','patent_abstract'], 'o':{'per_page':10}})
print(json.dumps(r.json(), indent=2))
"

# FRED macro data — 1 tool call
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from fredapi import Fred
fred = Fred(api_key=os.environ.get('FRED_API_KEY',''))
print(fred.get_series('GDP').tail(10).to_json())
"
```

**PDF extraction** (all agents if docs provided):
```bash
python -c "
import fitz, json
doc = fitz.open('PATH')
for i in range(min(len(doc), 50)):
    print(doc[i].get_text())
"
```

**Excel extraction** (all agents if .xlsx/.xls docs provided):
```bash
python -c "
import openpyxl, json
wb = openpyxl.load_workbook('PATH', data_only=True)
for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    print(f'=== Sheet: {sheet_name} ===')
    for row in ws.iter_rows(values_only=True):
        vals = [str(c) if c is not None else '' for c in row]
        print('\t'.join(vals))
"
```

## Step 3: Phase 1 Aggregator (Smart Aggregator)

After all 6 Phase 1 agents complete, dispatch a **single Agent subagent** to do aggregation.

**DO NOT read Phase 1 JSONs into the main session context.** The aggregator agent reads them.

Agent prompt for aggregator:
```
## Task: Smart Aggregator

Read ALL 6 Phase 1 agent outputs from disk and produce a cross-pollination analysis.

## Input Files (read each with the Read tool)
- dd-local-outputs/<company_slug>/market_analysis.json
- dd-local-outputs/<company_slug>/competitor_analysis.json
- dd-local-outputs/<company_slug>/financial_analysis.json
- dd-local-outputs/<company_slug>/tech_analysis.json
- dd-local-outputs/<company_slug>/legal_regulatory.json
- dd-local-outputs/<company_slug>/team_analysis.json

## Analysis Steps
1. Extract summary, red_flags, strengths, confidence_score from each agent
2. Build compact phase1_context (max 1500 chars per agent)
3. Identify cross-pollination signals:
   - settled_claims: 5-8 facts that MULTIPLE agents agree on (with specific numbers)
   - tensions: 3-5 CONTRADICTIONS between agents
   - gaps: 2-3 important questions that NO agent answered

## Output
Write result to: dd-local-outputs/<company_slug>/_aggregator.json
JSON structure:
{
  "phase1_context": "<compact summary of all 6 agents, max 9000 chars total>",
  "settled_claims": ["...", "..."],
  "tensions": ["...", "..."],
  "gaps": ["...", "..."]
}

After writing the file, respond with ONLY: "Done. File: dd-local-outputs/<company_slug>/_aggregator.json"
```

## Step 4: Phase 2 — Synthesis (3 agents)

All Phase 2 agents read their inputs from disk within their own subagent context.

### Batch 1: ra_synthesis + risk_assessment (parallel Agent calls)

Each agent's prompt instructs it to:
1. Read `_aggregator.json` from disk (for phase1_context + cross-pollination)
2. Read individual Phase 1 JSONs as needed for detail
3. Read its SYSTEM_PROMPT from the .py file reference (paste it in the prompt)
4. Write output to disk
5. Return only completion confirmation

**Agent prompt template for Phase 2:**
```
## Role
<paste SYSTEM_PROMPT from agents/phase2/<agent>.py>

## Input (read from disk with Read tool)
- dd-local-outputs/<company_slug>/_aggregator.json (contains phase1_context + cross-pollination)
- Individual Phase 1 JSONs as needed for deeper detail

## Cross-pollination (MANDATORY)
After reading _aggregator.json, use the settled_claims, tensions, and gaps:
- Do NOT restate settled_claims - build on top of them
- RESOLVE or explain each tension
- FILL gaps where possible

## Company
- Name: <company_name>
- URL: <url>
- Language: <lang>

<additional agent-specific instructions - see below>

## Output
Write your complete JSON result to: dd-local-outputs/<company_slug>/<agent_name>.json

After writing the file, respond with ONLY: "Done. File: <path>"
```

**risk_assessment additional instruction:**
After completing the risk matrix, also output `unresolved_objections`:
2-3 of the HARDEST challenges to this investment that CANNOT be fully rebutted.
Rate each by `kill_potential`: high/medium/low.

**risk_assessment has tools**: WebSearch + Tavily (web + news) for verification.

### Sequential: strategic_insight

After ra_synthesis and risk_assessment complete, dispatch strategic_insight.

Its prompt instructs it to read from disk:
- `_aggregator.json`
- `ra_synthesis.json`
- `risk_assessment.json`

**strategic_insight additional instruction:**
Develop 2-3 DISTINCT FRAMINGS (scenarios) before rendering recommendation.
Pick the STRONGEST framing and name runners-up.

**strategic_insight has NO tools** - works from disk data only.

## Step 5: Phase 3 — Review & Quality (review sequential, then critique + dd_questions parallel)

### 5a. review_agent (sequential — must complete first)
Agent subagent that reads ALL Phase 1 + Phase 2 outputs from disk. Has WebSearch + Tavily tools.

**Reality check (MANDATORY):**
If overall narrative is heavily bullish or bearish, actively search for CONTRADICTING data.
Stress-test the narrative, don't confirm it.

Prompt instructs it to read these files from disk:
- All 6 Phase 1 JSONs
- `_aggregator.json`
- `ra_synthesis.json`, `risk_assessment.json`, `strategic_insight.json`

### 5b + 5c. critique_agent + dd_questions (PARALLEL — both launch after review_agent completes)

**critique_agent:**
Read SYSTEM_PROMPT from `agents/phase3/critique_agent.py`.
Agent subagent reads all prior outputs from disk. NO tools.
Scores 5 criteria (logic, completeness, accuracy, narrative_bias, insight_effectiveness) 1-10.

**Feedback loop logic** (orchestrator decides based on critique_agent's returned scores):
- total >= 35 AND all criteria >= 7 -> PASS -> continue to Phase 4
- Any criterion < 5 OR total < 25 -> FAIL -> restart Phase 1 (max 1 restart)
- Otherwise -> CONDITIONAL -> identify weak agents, re-run only those, then re-run Phase 2+3

**IMPORTANT for feedback loop**: critique_agent's response must include the scores in parseable format.
Instruct it: "In your final response (not just the JSON file), include the line:
SCORES: logic=X completeness=X accuracy=X narrative_bias=X insight_effectiveness=X total=X"
The orchestrator parses this line to decide pass/conditional/fail WITHOUT reading the full JSON.

**dd_questions:**
Read SYSTEM_PROMPT from `agents/phase3/dd_questions.py`.
Agent subagent reads all prior outputs from disk. NO tools.
Generates unresolved issues and DD questionnaire.
(Does NOT depend on critique_agent — reads Phase 1+2 outputs only.)

## Step 6: Phase 4 — Report (2 steps: section writers → editor, NO report_structure)

Section assignments are already defined below — no separate report_structure agent needed.

### 6b. section_writers (6 parallel agents)

Split the report into 6 sections, each written by a dedicated Agent subagent.
Each section writer reads ONLY the relevant JSON files, keeping context lean.

**Dispatch all 6 section writers in parallel (single batch):**

#### All 6 sections (parallel):

**section_1_market** — 시장 및 산업 개괄 (5+ pages)
- Reads: market_analysis.json, legal_regulatory.json (regulatory parts), _aggregator.json
- Covers: TAM/SAM/SOM, CAGR, growth drivers, regulatory environment, Sovereign AI policy
- Writes to: `dd-local-outputs/<slug>/_section_1.md`

**section_2_target** — 타겟 개요 및 사업 구조 (5+ pages)
- Reads: tech_analysis.json, team_analysis.json, _aggregator.json
- Covers: Business models, products, tech stack, IP/patents, R&D, EVERY leader profile, org structure
- Writes to: `dd-local-outputs/<slug>/_section_2.md`

**section_3_financial** — 재무 성과 분석 (4+ pages)
- Reads: financial_analysis.json, _aggregator.json
- Covers: 5-year revenue, profitability, balance sheet, cash flow, ratios, burn rate
- Writes to: `dd-local-outputs/<slug>/_section_3.md`

**section_4_competition** — 경쟁 구도 (4+ pages)
- Reads: competitor_analysis.json, tech_analysis.json (competitive comparison), _aggregator.json
- Covers: EVERY competitor individually, market share, moat assessment, head-to-head tables
- Writes to: `dd-local-outputs/<slug>/_section_4.md`

**section_5_valuation** — 가치평가 (5+ pages)
- Reads: financial_analysis.json (valuation section), ra_synthesis.json, _aggregator.json
- Covers: DCF, comps, investment rounds, fair value range, source claims verification
- Writes to: `dd-local-outputs/<slug>/_section_5.md`

**section_6_risk** — 리스크 및 최종 의견 (5+ pages)
- Reads: risk_assessment.json, legal_regulatory.json, strategic_insight.json, dd_questions.json, review_agent.json, critique_agent.json
- Covers: Risk matrix, legal/regulatory, recommendation, conditions, FULL DD questionnaire
- Writes to: `dd-local-outputs/<slug>/_section_6.md`

**Section writer prompt template:**
```
## Role
You are a senior investment analyst writing Section N of a Due Diligence Report.
Language: <lang>. Write in detail — this section must be 4-5+ pages (2,500+ words).

## Section: <section_title>
<specific coverage instructions from above>

## Format Rules
- Structure for every subsection: HEADLINE → **[INSIGHT]** → TABLE → detailed body
- The [INSIGHT] block comes IMMEDIATELY after the heading, BEFORE any data/tables.
  It is the analyst's interpretive takeaway — bold the entire block. Example:

  ### 한국 AI 시장 규모와 전망
  **[INSIGHT] 한국 LLM 시장의 39.4% CAGR은 글로벌 LLM 시장 CAGR(20~37%)보다 높다.
  이는 정부의 소브린 AI 이니셔티브가 수요 창출 역할을 하고 있기 때문이다. 그러나 절대 규모는
  글로벌 시장의 약 2.5%에 불과하며, 국내 시장만으로는 성장 천장이 될 수 있다.**

  (then tables and detailed data follow)

- 2+ tables minimum per section
- Max 4 sentences per paragraph
- Include ALL data from the source files — do not summarize or skip items
- EVERY item (competitor/leader/risk/metric) gets its own detailed treatment
- [DATA] tags go in the detailed body (after tables), NOT in the [INSIGHT] block
- **용어 평이화 (MANDATORY)**: 전문 용어를 처음 사용할 때 괄호로 쉬운 설명을 붙일 것.
  예시: "TAM(전체 시장 규모)", "CAGR(연평균 성장률)", "DCF(미래 현금흐름 할인 가치)",
  "영업이익률(매출 대비 실제 벌어들인 이익 비율)", "PSR(주가매출비율, 매출 대비 기업가치)",
  "모트(경쟁자가 쉽게 넘볼 수 없는 경쟁 우위)", "런웨이(현재 현금으로 버틸 수 있는 기간)",
  "ratchet(투자자 보호 조항, 가치 하락 시 지분 보전)", "엑시트(투자금 회수 방법: IPO, M&A 등)"
  두 번째 사용부터는 용어만 써도 됨. 일반인이 읽어도 이해 가능한 수준으로 작성할 것.

## Input Files (read with Read tool)
<list of relevant JSON files>

## Context
Company: <company_name> | URL: <url> | Private/Public: <status>
This is Section N of a 6-section report. Other sections cover:
<brief 1-line description of other 5 sections so writer knows what NOT to duplicate>

## Output
Write the section markdown to: dd-local-outputs/<slug>/_section_N.md
Start with the section heading (## N. <title>). Do NOT include report title or executive summary.
After writing, respond ONLY: "Done. File: <path>"
```

### 6c. report_editor (fast assembly — concat + additions only)

After all 6 sections complete, dispatch a single Agent subagent to:
1. Read all 6 section files (`_section_1.md` through `_section_6.md`)
2. Read `strategic_insight.json` and `critique_agent.json`
3. **Write report.md using Bash concat + Write for additions only:**

**FAST ASSEMBLY METHOD (saves ~30 min vs full rewrite):**

The editor does NOT rewrite the sections. Instead:

Step A: Use Bash to concatenate the 6 sections into a base file:
```bash
cat dd-local-outputs/<slug>/_section_1.md dd-local-outputs/<slug>/_section_2.md \
    dd-local-outputs/<slug>/_section_3.md dd-local-outputs/<slug>/_section_4.md \
    dd-local-outputs/<slug>/_section_5.md dd-local-outputs/<slug>/_section_6.md \
    > dd-local-outputs/<slug>/_sections_combined.md
```

Step B: Write ONLY the front matter + executive summary to `_front.md`:
- Report title, date, recommendation header
- Private company disclaimer
- **목차 (TABLE OF CONTENTS) — MANDATORY, Executive Summary 앞에 배치:**
  ```
  ## 목차
  1. [시장 및 산업 개괄](#1-시장-및-산업-개괄)
  2. [타겟 개요 및 사업 구조](#2-타겟-개요-및-사업-구조)
  3. [재무 성과 분석](#3-재무-성과-분석)
  4. [경쟁 구도](#4-경쟁-구도)
  5. [가치평가](#5-가치평가)
  6. [리스크 및 최종 의견](#6-리스크-및-최종-의견)
  ```
- Executive Summary (1-2 page overview with key metrics table, synthesizing all 6 sections)
- **Investment Framings Table** (MANDATORY): Read `strategic_insight.json` and include
  a table showing ALL framings (scenarios) the strategic_insight agent developed.
  Format:
  | 프레이밍 | 핵심 논리 | 추천 | 확신도 |
  |----------|-----------|------|--------|
  | 프레이밍 1 (채택) | ... | INVEST/WATCH/PASS | X/10 |
  | 프레이밍 2 | ... | ... | X/10 |
  | 프레이밍 3 | ... | ... | X/10 |
  Mark the selected framing with (채택/Selected). This gives the reader immediate
  visibility into alternative interpretations considered before the final recommendation.

Step C: Write ONLY the appendix to `_appendix.md`:
- Critique scores
- Source list
- Glossary

Step D: Concatenate final report:
```bash
cat dd-local-outputs/<slug>/_front.md dd-local-outputs/<slug>/_sections_combined.md \
    dd-local-outputs/<slug>/_appendix.md > dd-local-outputs/<slug>/report.md
```

Step E: Use Edit tool to insert cross-references into report.md (10+ edits):
- Find key claims and add "(Section X 참조)" annotations
- Ensure no number contradictions between sections

This approach writes ~5K chars (front + appendix) instead of ~120K chars (full report),
reducing the editor step from ~38 min to ~5-10 min.

**Editor prompt must include:**
```
## CRITICAL — FAST ASSEMBLY
- Do NOT rewrite the sections. Use Bash cat to concatenate them.
- Write ONLY: front matter + executive summary (_front.md) and appendix (_appendix.md)
- Then use Edit tool to insert cross-references into the assembled report.md
- This is a speed optimization — sections are already complete and correct.
- Output language: <lang>
```

## Step 7: Final Output

After all phases complete:
1. Generate PDF from report.md via Bash:
   ```bash
   python dd_local_pdf.py dd-local-outputs/<company_slug>/report.md
   ```
   This creates `dd-local-outputs/<company_slug>/report.pdf` with styled cover page, tables, and formatting.
2. Read ONLY `dd-local-outputs/<company_slug>/report.md` and display to user
3. Summarize: recommendation (INVEST/WATCH/PASS), confidence score, top 3 risks
4. List all output files in `dd-local-outputs/<company_slug>/` (including report.pdf)

## Context Management Rules

### The Golden Rule
**The main orchestrator session NEVER reads full agent JSON outputs.**
All data flows through disk. The main session only tracks completion status.

### Agent Return Protocol
Every agent subagent MUST end with a short confirmation message, NOT full output:
- Good: "Done. File: dd-local-outputs/Apple/market_analysis.json"
- Bad: returning 30KB of JSON in the agent's response

### Disk-Based Context Flow
```
Phase 1 agents    --> write JSONs to disk
Aggregator agent  --> reads Phase 1 JSONs from disk, writes _aggregator.json
Phase 2 agents    --> read _aggregator.json + Phase 1 JSONs from disk
Phase 3 agents    --> read Phase 1 + Phase 2 JSONs from disk
Phase 4 agents    --> read all prior JSONs from disk
```

Each agent has its OWN context window. The main session context stays lean.

### PDF Document Handling
- **Cap per extraction**: Max 18,000 characters per PDF. If a doc is longer, extract in pages:
  ```bash
  python -c "import fitz; doc=fitz.open('PATH'); [print(doc[i].get_text()[:3000]) for i in range(min(len(doc), 6))]"
  ```
- **PDF data is PROTECTED**: Never summarize or discard extracted PDF content in favor of web results.
- **Source hierarchy**: Uploaded docs (exact figures) > official filings (DART/EDGAR) > yfinance > web search.

### Context Budget per Agent Subagent
- Each agent's total input (prompt + documents + web results) should stay under **50,000 characters**.
- If an agent has docs + web results exceeding this, TRIM web results first (oldest first), never docs.
- Web search results: cap each at **4,000 characters**. Truncate with "[...truncated]".
- PDF results: cap each at **18,000 characters**. Higher limit because docs are authoritative.

## Important Rules

- **Read SYSTEM_PROMPTs from actual .py files** — do NOT hardcode prompts. Use Read tool on `agents/phase1/*.py`, `agents/phase2/*.py`, etc. to get the latest prompts.
- **Batch Phase 1 in triplets** — 3 agents at a time, 2 batches total.
- **Disk persistence** — every agent writes JSON to disk. If a crash happens, completed agents don't need re-running.
- **Cross-pollination** — settled_claims/tensions/gaps MUST be passed to Phase 2 agents via _aggregator.json on disk.
- **[확인사항]/[추론사항] labeling** — ALL agents must prefix major statements.
- **Cross-verify 3+ sources** — key claims need 3+ independent sources. 1 source = low confidence.
- **Search budget 4-6 calls** — plan queries before searching, no near-duplicate queries.
- **Recency** — prefer newest sources, re-verify anything >6 months old.
- **Language** — if `--lang Korean`, instruct all agents to respond in Korean.
- **No Anthropic API calls** — everything runs through Agent subagents (subscription) + Bash (Python tools) + WebSearch.
- **No separate terminal needed** — everything runs within the current Claude Code session.
