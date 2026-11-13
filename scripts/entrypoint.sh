#!/usr/bin/env sh
# Build the index on first start (persisted in ./data), then run the requested service.
set -e
if ! python -c "from copilot.store import get_collection; import sys; sys.exit(0 if get_collection().count() else 1)" 2>/dev/null; then
  echo "No index found: ingesting ROS 2 docs (first run takes a few minutes on CPU)..." >&2
  copilot-ingest >&2
fi
case "$1" in
  web)    exec env HOST=0.0.0.0 copilot-web ;;
  mcp)    exec copilot-mcp ;;
  ingest) exec copilot-ingest --reset ;;
  eval)   shift; exec python evals/run_evals.py "$@" ;;
  *)      exec "$@" ;;
esac
