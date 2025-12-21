import threading
import time
from unittest.mock import Mock

from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile, ProfileCache


def test_cache_hit_miss():
    cache = ProfileCache()
    profile = Mock(spec=BehaviorProfile)

    # Test miss
    assert cache.get("key1") is None
    assert cache.stats["misses"] == 1
    assert cache.stats["hits"] == 0

    # Test hit
    cache.put("key1", profile)
    assert cache.get("key1") == profile
    assert cache.stats["misses"] == 1
    assert cache.stats["hits"] == 1


def test_cache_ttl():
    cache = ProfileCache(ttl=0.1)
    profile = Mock(spec=BehaviorProfile)

    cache.put("key1", profile)
    assert cache.get("key1") == profile

    time.sleep(0.2)
    assert cache.get("key1") is None


def test_cache_eviction():
    cache = ProfileCache(maxsize=2)
    p1 = Mock(spec=BehaviorProfile)
    p2 = Mock(spec=BehaviorProfile)
    p3 = Mock(spec=BehaviorProfile)

    cache.put("k1", p1)
    cache.put("k2", p2)

    assert cache.get("k1") == p1
    assert cache.get("k2") == p2

    cache.put("k3", p3)

    # Check size
    assert cache.stats["size"] == 2
    assert cache.get("k3") == p3

    # Check that one of the others is gone
    k1_present = cache.get("k1") is not None
    k2_present = cache.get("k2") is not None

    assert not (k1_present and k2_present), "Cache should have evicted one item"


def test_thread_safety():
    cache = ProfileCache()
    profile = Mock(spec=BehaviorProfile)

    def worker():
        for i in range(100):
            cache.put(f"k{i}", profile)
            cache.get(f"k{i}")

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cache.stats["size"] <= 100
    assert cache.stats["hits"] >= 0
