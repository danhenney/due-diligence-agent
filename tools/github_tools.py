"""GitHub API tools — free (60 req/hr without token, 5000/hr with free token)."""
from __future__ import annotations

import json
from typing import Any

import requests

from config import GITHUB_TOKEN

_BASE = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _get(url: str, params: dict | None = None) -> dict | list | None:
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    if resp.status_code == 403:
        raise RuntimeError(
            "GitHub rate limit exceeded. "
            "Add a free GITHUB_TOKEN in settings to get 5000 req/hr."
        )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def github_search_repos(org_or_user: str, limit: int = 10) -> dict[str, Any]:
    """Find the top public repositories for a GitHub organisation or user.

    Returns repo names, descriptions, stars, forks, primary language,
    open issues, and last push date — useful for gauging engineering activity.
    """
    try:
        # Try as org first, fall back to user
        data = _get(f"{_BASE}/orgs/{org_or_user}/repos",
                    params={"type": "public", "sort": "stars", "per_page": limit})
        if data is None:
            data = _get(f"{_BASE}/users/{org_or_user}/repos",
                        params={"type": "public", "sort": "stars", "per_page": limit})
        if not data:
            return {"error": f"No public repos found for '{org_or_user}'"}

        repos = []
        for r in (data or [])[:limit]:
            repos.append({
                "name":          r.get("name"),
                "description":   r.get("description"),
                "stars":         r.get("stargazers_count"),
                "forks":         r.get("forks_count"),
                "language":      r.get("language"),
                "open_issues":   r.get("open_issues_count"),
                "last_pushed":   (r.get("pushed_at") or "")[:10],
                "url":           r.get("html_url"),
                "topics":        r.get("topics", []),
            })

        total_stars = sum(r["stars"] or 0 for r in repos)
        return {
            "org_or_user": org_or_user,
            "public_repos_shown": len(repos),
            "total_stars_top_repos": total_stars,
            "repos": repos,
        }

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find the company's GitHub activity instead.",
        }


def github_repo_stats(owner: str, repo: str) -> dict[str, Any]:
    """Return detailed stats for a specific GitHub repository.

    Includes stars, forks, contributors, commit activity (last 52 weeks),
    open issues, license, and language breakdown.
    """
    try:
        r = _get(f"{_BASE}/repos/{owner}/{repo}")
        if r is None:
            return {"error": f"Repo '{owner}/{repo}' not found"}

        result: dict[str, Any] = {
            "name":        r.get("name"),
            "description": r.get("description"),
            "stars":       r.get("stargazers_count"),
            "forks":       r.get("forks_count"),
            "watchers":    r.get("subscribers_count"),
            "open_issues": r.get("open_issues_count"),
            "language":    r.get("language"),
            "license":     (r.get("license") or {}).get("spdx_id"),
            "created":     (r.get("created_at") or "")[:10],
            "last_pushed": (r.get("pushed_at") or "")[:10],
            "url":         r.get("html_url"),
            "topics":      r.get("topics", []),
        }

        # Contributor count
        try:
            contribs = _get(f"{_BASE}/repos/{owner}/{repo}/contributors",
                            params={"per_page": 1, "anon": "false"})
            # GitHub returns contributor list; we just want the count
            # Use the Link header trick for total count
            resp = requests.get(
                f"{_BASE}/repos/{owner}/{repo}/contributors",
                headers=_headers(),
                params={"per_page": 1},
                timeout=10,
            )
            link = resp.headers.get("Link", "")
            if 'rel="last"' in link:
                import re
                m = re.search(r'page=(\d+)>; rel="last"', link)
                result["total_contributors"] = int(m.group(1)) if m else None
            elif contribs:
                result["total_contributors"] = len(contribs)
        except Exception:
            pass

        # Weekly commit activity (last 52 weeks)
        try:
            activity = _get(f"{_BASE}/repos/{owner}/{repo}/stats/commit_activity")
            if activity:
                weeks = [w.get("total", 0) for w in activity]
                result["commit_activity_52w"] = {
                    "total_commits":   sum(weeks),
                    "avg_per_week":    round(sum(weeks) / len(weeks), 1) if weeks else 0,
                    "last_4w_commits": sum(weeks[-4:]) if len(weeks) >= 4 else sum(weeks),
                    "trend":           "active" if sum(weeks[-8:]) > sum(weeks[:8]) else "declining",
                }
        except Exception:
            pass

        # Language breakdown
        try:
            langs = _get(f"{_BASE}/repos/{owner}/{repo}/languages")
            if langs:
                total_bytes = sum(langs.values())
                result["languages"] = {
                    lang: f"{round(bytes_ / total_bytes * 100, 1)}%"
                    for lang, bytes_ in sorted(langs.items(), key=lambda x: -x[1])
                }
        except Exception:
            pass

        return result

    except Exception as exc:
        return {
            "error": str(exc),
            "action": "Use web_search to find GitHub repository information instead.",
        }


# ── Anthropic tool definitions ────────────────────────────────────────────────

GITHUB_SEARCH_REPOS_TOOL = {
    "name": "github_search_repos",
    "description": (
        "Find the top public GitHub repositories for a company or developer organisation. "
        "Returns star counts, languages, recent activity, and open issues. "
        "Use this to assess a tech company's open-source presence, engineering culture, "
        "and product development activity. Pass the GitHub org name (e.g. 'openai', 'stripe')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "org_or_user": {
                "type": "string",
                "description": "GitHub organisation or username, e.g. 'openai', 'stripe', 'vercel'.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of top repos to return (default 10).",
                "default": 10,
            },
        },
        "required": ["org_or_user"],
    },
}

GITHUB_REPO_STATS_TOOL = {
    "name": "github_repo_stats",
    "description": (
        "Get detailed stats for a specific GitHub repository: stars, forks, contributor count, "
        "52-week commit activity trend, open issues, license, and language breakdown. "
        "Use after github_search_repos to deep-dive into the most important repo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "GitHub organisation or username, e.g. 'openai'.",
            },
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. 'whisper'.",
            },
        },
        "required": ["owner", "repo"],
    },
}


def execute_tool(name: str, inputs: dict) -> str:
    if name == "github_search_repos":
        result = github_search_repos(**inputs)
    elif name == "github_repo_stats":
        result = github_repo_stats(**inputs)
    else:
        raise ValueError(f"Unknown GitHub tool: {name}")
    return json.dumps(result, ensure_ascii=False, default=str)
