#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APOC_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"
cd "${BACKEND_DIR}"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
fi

: "${APOC_PORT:=8800}"
: "${APOC_GROUNDING:=searxng}"
: "${APOC_SEARXNG_URL:=http://localhost:8080}"
export APOC_GROUNDING APOC_SEARXNG_URL

grounding_lc="$(printf '%s' "${APOC_GROUNDING}" | tr '[:upper:]' '[:lower:]')"

missing_deps="$("${PYTHON_BIN}" - "${grounding_lc}" <<'PY'
import importlib.util
import sys

grounding = sys.argv[1]
required = ["fastapi", "uvicorn", "httpx"]
if grounding != "anthropic_native":
    required.extend(["crawl4ai", "trafilatura"])
missing = [name for name in required if importlib.util.find_spec(name) is None]
print(" ".join(missing))
PY
)"

if [[ -n "${missing_deps}" ]]; then
  echo "Missing Python dependencies: ${missing_deps}" >&2
  echo "Run from apoc/backend: ${PYTHON_BIN} -m pip install -r requirements.txt" >&2
  if [[ "${grounding_lc}" != "anthropic_native" ]]; then
    echo "After installing dependencies, run: crawl4ai-setup" >&2
  fi
  exit 1
fi

searxng_ready() {
  "${PYTHON_BIN}" - "${APOC_SEARXNG_URL}" <<'PY' >/dev/null 2>&1
import sys
import urllib.parse
import urllib.request

base = sys.argv[1].rstrip("/")
url = base + "/search?" + urllib.parse.urlencode({"q": "apoc health", "format": "json"})
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        raise SystemExit(0 if response.status < 500 else 1)
except Exception:
    raise SystemExit(1)
PY
}

if [[ "${grounding_lc}" != "anthropic_native" && "${APOC_SKIP_SEARXNG_START:-0}" != "1" ]]; then
  if ! searxng_ready; then
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
      echo "Starting SearXNG for APoc research grounding..."
      (cd "${APOC_ROOT}" && docker compose up -d searxng)
      sleep 3
    elif command -v podman-compose >/dev/null 2>&1; then
      echo "Starting SearXNG for APoc research grounding with podman-compose..."
      (cd "${APOC_ROOT}" && podman-compose up -d searxng)
      sleep 3
    else
      echo "SearXNG is not reachable at ${APOC_SEARXNG_URL}, and docker compose was not found." >&2
      echo "Start it manually from apoc/: docker compose up -d searxng" >&2
    fi
  fi

  if ! searxng_ready; then
    echo "Warning: SearXNG is still not reachable at ${APOC_SEARXNG_URL}." >&2
    echo "The backend will start, but research may fall back if discovery is unavailable." >&2
  fi
fi

echo "Starting APoc backend on http://localhost:${APOC_PORT}"
exec "${PYTHON_BIN}" -m uvicorn app.main:app --reload --port "${APOC_PORT}"
