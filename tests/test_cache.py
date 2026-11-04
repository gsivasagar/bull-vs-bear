from src.cache import ttl_cache


def make(now_box, ttl=10):
    calls = []

    @ttl_cache(ttl, now=lambda: now_box[0])
    def fn(x):
        calls.append(x)
        return {"v": x}

    return fn, calls


def test_hit_then_expiry():
    t = [0.0]
    fn, calls = make(t)
    assert fn("a") == fn("a") == {"v": "a"}
    assert calls == ["a"]
    t[0] = 10.0
    fn("a")
    assert calls == ["a", "a"]


def test_keys_are_separate_and_cache_clear_works():
    t = [0.0]
    fn, calls = make(t)
    fn("a"), fn("b"), fn("a")
    assert calls == ["a", "b"]
    fn.cache_clear()
    fn("a")
    assert calls == ["a", "b", "a"]


def test_failures_and_empty_results_are_not_cached():
    n = {"i": 0}

    @ttl_cache(10, now=lambda: 0.0)
    def flaky(x):
        n["i"] += 1
        return {"error": "down"} if n["i"] == 1 else ([] if n["i"] == 2 else {"ok": True})

    assert flaky("a") == {"error": "down"}
    assert flaky("a") == []
    assert flaky("a") == {"ok": True}
    assert flaky("a") == {"ok": True}
    assert n["i"] == 3


def test_ttl_can_be_a_callable_and_zero_disables_caching():
    calls = []

    @ttl_cache(lambda: 0, now=lambda: 0.0)
    def fn(x):
        calls.append(x)
        return x

    fn("a"), fn("a")
    assert calls == ["a", "a"]
