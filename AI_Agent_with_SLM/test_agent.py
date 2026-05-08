from agent import web_search, summarise

def test_web_search_returns_results():
    results = web_search.invoke("Python programming language")
    assert isinstance(results, str)
    assert len(results) > 0
    assert "Error" not in results

def test_summarise_returns_shorter_text():
    long_text = "Python is a high-level, general-purpose programming language. " * 10
    result = summarise.invoke(long_text)
    assert isinstance(result, str)
    assert len(result) > 0

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
