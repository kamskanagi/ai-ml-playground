import re
from langchain_ollama import OllamaLLM
from langchain.tools import tool
from duckduckgo_search import DDGS

# Step 1: Load phi3 via Ollama (text model — no native tool calling required)
llm = OllamaLLM(model="phi3")

# Step 2: Define tools
@tool
def calculator(expression: str) -> str:
    """Evaluates a basic math expression. Input should be a valid Python math expression."""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"Error: {str(e)}"

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

tools = {calculator.name: calculator, web_search.name: web_search}

# Step 3: ReAct prompt — instructs phi3 to output Thought/Action/Action Input pattern
REACT_PROMPT = """You are a reasoning agent. Answer the question using the available tools.

Available tools:
- calculator: Evaluates a Python math expression (e.g. "245 * 18 / 5")
- web_search: Searches the web using DuckDuckGo and returns the top 3 result snippets.

Respond strictly in this loop until you have the answer:
Thought: <your reasoning>
Action: calculator
Action Input: <math expression>
Observation: <tool result will be inserted here>

When done, output:
Thought: I now know the final answer.
Final Answer: <your answer>

Question: {question}
"""

def run_agent(question: str, max_steps: int = 6) -> str:
    prompt = REACT_PROMPT.format(question=question)

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
            # Model gave a direct answer without following the format
            return output

    return "Max steps reached without a final answer."


if __name__ == "__main__":
    question = "What is 245 multiplied by 18, and then divided by 5?"
    print(f"\nQuestion: {question}")
    answer = run_agent(question)
    print(f"\n--- Agent Response ---\n{answer}")
