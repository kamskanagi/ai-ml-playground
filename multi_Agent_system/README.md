# Multi-Agent System

A multi-agent AI system built with [LangGraph](https://github.com/langchain-ai/langgraph) that processes user queries through a three stage pipeline: **Planner → Worker → Reviewer**.

## How It Works

1. **Planner Agent** — Reads the user query and creates a short actionable plan
2. **Worker Agent** — Generates a draft response based on the plan (and incorporates reviewer feedback on revisions)
3. **Reviewer Agent** — Evaluates the draft for concrete examples, implementation details, tradeoffs, clarity, and actionable recommendations
4. **Revision Loop** — If the reviewer requests revisions, the worker refines the response (up to 2 revision cycles)

```
User Query → Planner → Worker ⇄ Reviewer → Final Output
```

## Setup

### Prerequisites

- Python 3.10+
- A [Groq API key](https://console.groq.com)

### Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirement.txt
```

### Configuration

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_api_key_here
```

## Usage

```bash
python app.py
```

You will be prompted to enter a query. The system processes it through all three agents and prints the final response.

## Output

All intermediate and final outputs are saved to the `logs/` directory:

- `planner_output.txt` — the generated plan
- `worker_output_N.txt` — draft response per iteration
- `reviewer_output_N.txt` — review decision and reasoning per iteration
- `final_output.txt` — the approved final response
- `execution.log` — full execution log with timestamps

## Tech Stack

- **LangGraph** — state graph orchestration for the agent pipeline
- **LangChain + Groq** — LLM integration using Llama 3.3 70B
- **python-dotenv** — environment variable management
