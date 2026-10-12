---
id: tailor-cv
name: TailorCV
type: personal
year: 2026
url: github.com/NikolasTola/tailor-cv
tech: [Python, LangGraph, LangChain, LLMs, Sistemas Multiagentes, Pydantic, pytest, GitHub]
---

## Context
Personal project: command-line tool that generates a resume tailored to each job posting from a Markdown knowledge base.

## Achievements
- [tailorcv-grafo] Built a multi-agent system in LangGraph with 13 nodes in 4 waves, running independent agents in parallel, with a live terminal panel to follow each agent.
  - tech: Python, LangGraph, Sistemas Multiagentes
  - metric: 13 nodes in 4 waves
- [tailorcv-validacao] Implemented two-layer validation of LLM output: deterministic rules (numbers, technologies, source IDs) and an LLM-as-a-judge fidelity validator from a different provider, with an automatic correction loop that re-runs only the failing agents.
  - tech: LLMs, Pydantic, LangGraph
- [tailorcv-provedores] Made the system provider-agnostic: each agent's model is set in configuration, with retries and quota handling per error type.
  - tech: LangChain, LLMs
- [tailorcv-testes] Covered the system with 144 automated tests using a fake LLM, running with no network and no API quota.
  - tech: pytest, Python
  - metric: 144 automated tests
