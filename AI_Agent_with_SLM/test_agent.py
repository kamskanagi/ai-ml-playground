from agent import web_search

def test_web_search_returns_results():
    results = web_search.invoke("Python programming language")
    assert isinstance(results, str)
    assert len(results) > 0
    assert "Error" not in results
