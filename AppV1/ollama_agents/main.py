# Runnable demo: python -m ollama_agents.main  (from AppV1)

from __future__ import annotations

import os
import sys

import httpx


def main() -> None:
    base = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")

    from ollama_agents.functions import agent_run, default_agent1, default_agent2

    sample = os.getenv(
        "OLLAMA_DEMO_INPUT",
        "Headline: Here’s How Major Markets Are Moving\n\n"
        "Lede: Stocks moved sharply after officials signaled a slower path for rate cuts, with energy names leading.",
    )

    print("Ollama:", base)
    print("Model:", model)
    print("Input:", sample.replace("\n", " ")[:120] + ("…" if len(sample) > 120 else ""))
    print()
    result = agent_run(
        agent1=default_agent1(model),
        agent2=default_agent2(model),
        user_input=sample,
        ollama_base=base,
    )
    print("=" * 60)
    print("AGENT 1 — uses custom tool (wikipedia_summary) to fetch context")
    print("=" * 60)
    print(result.agent1_output)
    print()
    print("=" * 60)
    print("AGENT 2 — report / analysis (no tools; uses Agent 1 output)")
    print("=" * 60)
    print(result.agent2_output)


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        print(
            "Could not reach Ollama. Start the server (e.g. `ollama serve`) and pull a model:\n"
            "  ollama pull llama3.2\n"
            f"Default URL: {os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')}",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
