# Local AI Agent with phi3 (SLM)

An interactive CLI agent that runs **entirely locally** using [phi3](https://ollama.com/library/phi3) via [Ollama](https://ollama.com). No cloud APIs, no API keys — just a small language model on your machine reasoning through tasks using a ReAct loop.

## How it works

phi3 does not support native tool calling, so the agent uses a **prompt-based ReAct loop**:

1. The question (plus any prior conversation) is injected into a structured prompt
2. phi3 emits `Thought` / `Action` / `Action Input` lines
3. The agent parses those, executes the matching tool, and feeds the `Observation` back
4. The loop repeats until phi3 outputs `Final Answer:`

```
You: What is 245 multiplied by 18, then divided by 5?

[Step 1]
Thought: I need to compute 245 * 18 first.
Action: calculator
Action Input: 245 * 18
[Tool] calculator('245 * 18') → 4410

Thought: Now divide by 5.
Action: calculator
Action Input: 4410 / 5
[Tool] calculator('4410 / 5') → 882

Final Answer: 882

Agent: 882
```

## Tools

| Tool | What it does |
|------|-------------|
| `calculator` | Evaluates a Python math expression — `245 * 18 / 5` |
| `web_search` | DuckDuckGo search, returns top 3 result snippets |
| `summarise` | Uses phi3 to summarise a long piece of text in 2–3 sentences |

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- phi3 model pulled

## Setup

```bash
# 1. Pull phi3 (if you haven't already)
ollama pull phi3

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Run the agent
python agent.py
```

## Usage

```
Local phi3 Agent,  type 'exit' or press Ctrl-C to quit.

You: Search the web for the latest phi3 release
You: Summarise what you just found
You: What is 1024 divided by 32?
You: exit
```

The agent remembers the full conversation within a session, so follow-up questions work naturally.

## Project structure

```
AI_Agent_with_SLM/
├── agent.py          # All agent logic: tools, ReAct loop, REPL
├── requirements.txt  # Python dependencies
└── test_agent.py     # Unit tests for tools and history formatting
```

## Running tests

```bash
pytest test_agent.py -v
```
