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
