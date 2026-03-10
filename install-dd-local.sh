#!/bin/bash
# DD Local 설치 스크립트
# Claude Code에서 /dd-local 스킬을 사용할 수 있도록 설정합니다.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SOURCE="$SCRIPT_DIR/skills/dd-local"
SKILL_TARGET="$HOME/.claude/skills/dd-local"

echo "=== DD Local 설치 ==="
echo ""

# 1. Claude Code 설치 확인
if ! command -v claude &> /dev/null; then
    echo "[ERROR] Claude Code가 설치되어 있지 않습니다."
    echo "  설치: npm install -g @anthropic-ai/claude-code"
    exit 1
fi
echo "[OK] Claude Code 확인"

# 2. Python 패키지 설치
echo ""
echo "필요한 Python 패키지를 설치합니다..."
pip install -q tavily-python opendartreader yfinance pytrends fredapi PyMuPDF reportlab openpyxl python-dotenv requests
echo "[OK] Python 패키지 설치 완료"

# 3. 스킬 심볼릭 링크 생성
echo ""
mkdir -p "$HOME/.claude/skills"

if [ -L "$SKILL_TARGET" ]; then
    echo "[INFO] 기존 심볼릭 링크를 업데이트합니다."
    rm "$SKILL_TARGET"
elif [ -d "$SKILL_TARGET" ]; then
    echo "[INFO] 기존 스킬 디렉토리를 백업합니다."
    mv "$SKILL_TARGET" "${SKILL_TARGET}.bak.$(date +%Y%m%d%H%M%S)"
fi

# Windows (Git Bash/MSYS) vs Unix
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    # Windows: copy instead of symlink (symlinks need admin)
    cp -r "$SKILL_SOURCE" "$SKILL_TARGET"
    echo "[OK] 스킬 파일 복사 완료: $SKILL_TARGET"
    echo "[NOTE] Windows에서는 업데이트 시 install 재실행 또는 수동 복사 필요"
else
    ln -s "$SKILL_SOURCE" "$SKILL_TARGET"
    echo "[OK] 심볼릭 링크 생성: $SKILL_TARGET -> $SKILL_SOURCE"
fi

# 4. .env 파일 확인
echo ""
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "[WARNING] .env 파일이 없습니다. .env.example을 참고하여 생성하세요."
    echo "  cp .env.example .env"
    echo "  그 후 API 키를 입력하세요."
else
    echo "[OK] .env 파일 확인"
    # 필수 키 확인
    for key in TAVILY_API_KEY; do
        if grep -q "^${key}=" "$SCRIPT_DIR/.env"; then
            echo "  [OK] $key 설정됨"
        else
            echo "  [WARNING] $key 미설정 — Tavily 검색이 작동하지 않습니다."
        fi
    done
    # 선택 키 확인
    for key in DART_API_KEY FRED_API_KEY GITHUB_TOKEN; do
        if grep -q "^${key}=" "$SCRIPT_DIR/.env"; then
            echo "  [OK] $key 설정됨"
        else
            echo "  [INFO] $key 미설정 (선택사항)"
        fi
    done
fi

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "사용법:"
echo "  1. Claude Code 실행: claude"
echo "  2. 프로젝트 디렉토리에서: /dd-local 삼성전자 --url https://samsung.com"
echo "  3. 문서 첨부: /dd-local 업스테이지 --url https://upstage.ai --docs report.pdf data.xlsx"
echo ""
