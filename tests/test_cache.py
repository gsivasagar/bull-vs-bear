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


def test_single_flight_computes_once_for_concurrent_callers():
    import threading
    import time as _time

    from src.cache import ttl_cache

    calls = {"n": 0}

    @ttl_cache(60, single_flight=True)
    def slow(key):
        calls["n"] += 1
        _time.sleep(0.2)
        return {"value": key}

    results = []
    threads = [threading.Thread(target=lambda: results.append(slow("A"))) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] == 1 and all(r == {"value": "A"} for r in results) and len(results) == 5


def test_single_flight_does_not_share_a_failure():
    from src.cache import ttl_cache

    calls = {"n": 0}

    @ttl_cache(60, single_flight=True)
    def flaky(key):
        calls["n"] += 1
        return {"error": "down"} if calls["n"] == 1 else {"value": key}

    assert flaky("A") == {"error": "down"}
    assert flaky("A") == {"value": "A"} and calls["n"] == 2


def test_without_single_flight_concurrent_callers_each_compute():
    import threading
    import time as _time

    from src.cache import ttl_cache

    calls = {"n": 0}

    @ttl_cache(60)
    def slow(key):
        calls["n"] += 1
        _time.sleep(0.1)
        return {"value": key}

    threads = [threading.Thread(target=lambda: slow("A")) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] >= 2                                       # shows why the option exists
