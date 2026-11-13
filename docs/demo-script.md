# Demo GIF script (~30 s total)

Record with [Peek](https://github.com/phw/peek) or `ffmpeg -f x11grab`. Output: `docs/demo.gif`, 1280×720, ≤ 8 MB.
Set the terminal font to 16 pt or larger and use a dark theme.

| # | Time | Screen | Action | Caption overlay (optional) |
|---|---|---|---|---|
| 1 | 0–4 s | Terminal | `docker compose up` with the logs scrolling to "Uvicorn running" | "One command" |
| 2 | 4–12 s | Browser at localhost:8000 | Click the example chip "How do I record a bag of only one topic?" and the answer appears | "Grounded in docs.ros.org" |
| 3 | 12–16 s | Same | Hover a `[1]` citation, click the source link, and the docs.ros.org section opens | "Every claim cited" |
| 4 | 16–26 s | Claude Desktop | Type *"Use ros2-docs: how do I make turtle_teleop_key control turtle2?"*. The tool-call chip `ask` expands and the answer shows the `--remap` command | "Works as an MCP server" |
| 5 | 26–30 s | Terminal | `cat evals/results/summary_hybrid.json` with hit@5 and accuracy highlighted | "Evaluated: 30 hand-written Q&A" |

Tips: record each shot separately, trim with `ffmpeg -ss`, and join them with
`ffmpeg -f concat`. Then convert with
`ffmpeg -i demo.mp4 -vf "fps=12,scale=1280:-1:flags=lanczos" -loop 0 docs/demo.gif`.
