# Local phi3 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive CLI agent that runs entirely locally using phi3 via Ollama, with a calculator, DuckDuckGo web search, and a summarise tool — all wired through a prompt-based ReAct loop with rolling conversation history.

**Architecture:** phi3 does not support native tool calling in Ollama, so the agent uses a prompt-based ReAct loop — it instructs phi3 to emit `Action:` / `Action Input:` lines, parses them with regex, executes the matching tool, and feeds the `Observation:` back into the prompt. Conversation history (prior question + answer pairs) is prepended to each new prompt so phi3 has session context. The REPL wraps this loop in a `while True` that reads from stdin.

**Tech Stack:** Python 3.11+, langchain-ollama (`OllamaLLM`), langchain (`@tool`), duckduckgo-search (`DDGS`), Ollama running phi3 locally.

---

## File Structure

| File | Role |
|------|------|
| `agent.py` | All agent logic: tools, ReAct loop, history, REPL |
| `requirements.txt` | Pinned dependencies |

---

### Task 1: Add `requirements.txt`

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
langchain-ollama>=0.3.0
langchain>=1.0.0
duckduckgo-search>=6.0.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: All packages install without error. Verify with:
```bash
python -c "from duckduckgo_search import DDGS; print('ddg ok')"
```
Expected output: `ddg ok`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requirements.txt for local phi3 agent"
```

---

### Task 2: Add the `web_search` tool

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Write a failing test**

Create `test_agent.py`:

```python
from agent import web_search

def test_web_search_returns_results():
    results = web_search.invoke("Python programming language")
    assert isinstance(results, str)
    assert len(results) > 0
    assert "Error" not in results
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest test_agent.py::test_web_search_returns_results -v
```

Expected: FAIL — `cannot import name 'web_search' from 'agent'`

- [ ] **Step 3: Add the import and tool to agent.py**

At the top of `agent.py`, add the import:

```python
from duckduckgo_search import DDGS
```

After the existing `calculator` tool definition, add:

```python
@tool
def web_search(query: str) -> str:
    """Searches the web using DuckDuckGo and returns the top 3 result snippets."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "No results found."
        return "\n\n".join(
            f"[{r['title']}]\n{r['body']}" for r in results
        )
    except Exception as e:
        return f"Search error: {str(e)}"
```

Also add `web_search` to the `tools` dict:

```python
tools = {calculator.name: calculator, web_search.name: web_search}
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest test_agent.py::test_web_search_returns_results -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent.py test_agent.py
git commit -m "feat: add DuckDuckGo web_search tool"
```

---

### Task 3: Add the `summarise` tool

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Write a failing test**

Append to `test_agent.py`:

```python
from agent import summarise

def test_summarise_returns_shorter_text():
    long_text = "Python is a high-level, general-purpose programming language. " * 10
    result = summarise.invoke(long_text)
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest test_agent.py::test_summarise_returns_shorter_text -v
```

Expected: FAIL — `cannot import name 'summarise' from 'agent'`

- [ ] **Step 3: Add the summarise tool to agent.py**

After the `web_search` tool, add:

```python
@tool
def summarise(text: str) -> str:
    """Summarises a long piece of text into a few concise sentences."""
    prompt = f"Summarise the following text in 2-3 sentences:\n\n{text}"
    return llm.invoke(prompt)
```

Add it to the tools dict:

```python
tools = {
    calculator.name: calculator,
    web_search.name: web_search,
    summarise.name: summarise,
}
```

- [ ] **Step 4: Run the test**

```bash
pytest test_agent.py::test_summarise_returns_shorter_text -v
```

Expected: PASS (may take ~10s while phi3 runs)

- [ ] **Step 5: Commit**

```bash
git add agent.py test_agent.py
git commit -m "feat: add summarise tool backed by phi3"
```

---

### Task 4: Update the ReAct prompt and add rolling conversation history

**Files:**
- Modify: `agent.py`

These two changes land together — the prompt gains a `{history}` placeholder and `run_agent` is updated to fill it in the same commit, so the code is never in a broken state between tasks.

- [ ] **Step 1: Write failing tests**

Append to `test_agent.py`:

```python
from agent import format_history

def test_format_history_empty():
    assert format_history([]) == ""

def test_format_history_with_entries():
    history = [("What is 2+2?", "4"), ("What is 3*3?", "9")]
    result = format_history(history)
    assert "What is 2+2?" in result
    assert "4" in result
    assert "What is 3*3?" in result
    assert "9" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest test_agent.py::test_format_history_empty test_agent.py::test_format_history_with_entries -v
```

Expected: FAIL — `cannot import name 'format_history' from 'agent'`

- [ ] **Step 3: Replace `REACT_PROMPT`, add `format_history`, update `run_agent`**

Replace the existing `REACT_PROMPT` string:

```python
REACT_PROMPT = """You are a helpful local AI assistant. Answer the user's question using the available tools.

Available tools:
- calculator: Evaluates a Python math expression (e.g. "245 * 18 / 5")
- web_search: Searches the web for current information (e.g. "latest Python release")
- summarise: Summarises a long piece of text into a few sentences

Respond in this loop until you have the answer:
Thought: <your reasoning>
Action: <tool name>
Action Input: <input for the tool>
Observation: <tool result will be inserted here>

When you have enough information, output:
Thought: I now know the final answer.
Final Answer: <your answer>

{history}Question: {question}
"""
```

Immediately after the prompt, add `format_history`:

```python
def format_history(history: list[tuple[str, str]]) -> str:
    if not history:
        return ""
    lines = []
    for question, answer in history:
        lines.append(f"Previous Q: {question}\nPrevious A: {answer}\n")
    return "\n".join(lines) + "\n"
```

Update `run_agent` to accept and use history:

```python
def run_agent(question: str, history: list[tuple[str, str]], max_steps: int = 6) -> str:
    prompt = REACT_PROMPT.format(
        history=format_history(history),
        question=question,
    )

    for step in range(max_steps):
        output = llm.invoke(prompt)
        print(f"\n[Step {step + 1}]\n{output}")

        if "Final Answer:" in output:
            return output.split("Final Answer:")[-1].strip()

        action_match = re.search(r"Action:\s*(.+)", output)
        input_match = re.search(r"Action Input:\s*(.+)", output)

        if action_match and input_match:
            action = action_match.group(1).strip()
            action_input = input_match.group(1).strip()

            observation = (
                tools[action].invoke(action_input)
                if action in tools
                else f"Unknown tool: {action}"
            )
            print(f"[Tool] {action}({action_input!r}) → {observation}")
            prompt += output + f"\nObservation: {observation}\n"
        else:
            return output

    return "Max steps reached without a final answer."
```

- [ ] **Step 4: Run the tests**

```bash
pytest test_agent.py::test_format_history_empty test_agent.py::test_format_history_with_entries -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent.py test_agent.py
git commit -m "feat: update ReAct prompt and add rolling conversation history"
```

---

### Task 5: Add the interactive REPL and wire everything together

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Replace the `if __name__ == "__main__"` block**

Find the current block:

```python
if __name__ == "__main__":
    question = "What is 245 multiplied by 18, and then divided by 5?"
    print(f"\nQuestion: {question}")
    answer = run_agent(question)
    print(f"\n--- Agent Response ---\n{answer}")
```

Replace it with:

```python
if __name__ == "__main__":
    print("Local phi3 Agent — type 'exit' or press Ctrl-C to quit.\n")
    history: list[tuple[str, str]] = []

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        answer = run_agent(question, history)
        print(f"\nAgent: {answer}\n")
        history.append((question, answer))
```

- [ ] **Step 2: Run the agent and verify the REPL works**

```bash
python agent.py
```

At the prompt, type:
```
You: What is 245 multiplied by 18, then divided by 5?
```

Expected: Agent reasons through steps, prints `Agent: ... 882 ...`

Then type:
```
You: Search the web for the latest phi3 model release
```

Expected: Agent uses `web_search`, returns snippets about phi3.

Then type:
```
You: exit
```

Expected: `Goodbye.` and clean exit.

- [ ] **Step 3: Commit**

```bash
git add agent.py
git commit -m "feat: add interactive REPL with rolling conversation history"
```

---

### Task 6: Smoke test — full end-to-end session

**Files:**
- No file changes — verification only.

- [ ] **Step 1: Run all unit tests**

```bash
pytest test_agent.py -v
```

Expected: All tests PASS.

- [ ] **Step 2: Run the full agent**

```bash
python agent.py
```

Ask three questions in sequence:

1. `What is 99 multiplied by 7?` → expect `693`
2. `Search the web for phi3 small language model` → expect web snippets
3. `Summarise what you just found` → expect a short summary using prior context

- [ ] **Step 3: Verify Ctrl-C exits cleanly**

Press `Ctrl-C` during a run. Expected: `Goodbye.` printed, no traceback.
