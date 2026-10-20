"""
Standalone tests for top_played.py (no pytest in this env - run directly:
    python test_top_played.py
"""
import random
import top_played


def _track(album_id, rank_url, has_image=True):
    return {
        "album": {
            "id": album_id,
            "images": [{"url": rank_url}] if has_image else [],
        }
    }


def test_dedupes_by_album_keeping_best_rank():
    items = [
        _track("album_A", "url_A"),
        _track("album_B", "url_B"),
        _track("album_A", "url_A_dup"),  # same album, lower rank (idx 2)
    ]
    seen_ids = set()
    for _ in range(200):
        picked = top_played.pick_weighted_album(items)
        assert picked is not None
        album_id, url = picked
        seen_ids.add(album_id)
        # album_A must keep the url from its FIRST (highest-ranked) occurrence
        if album_id == "album_A":
            assert url == "url_A"
    # only 2 distinct albums should ever be pickable, not 3 "slots"
    assert seen_ids == {"album_A", "album_B"}
    print("test_dedupes_by_album_keeping_best_rank passed")


def test_skips_tracks_without_images():
    items = [_track("album_A", "url_A", has_image=False)]
    assert top_played.pick_weighted_album(items) is None
    print("test_skips_tracks_without_images passed")


def test_empty_items_returns_none():
    assert top_played.pick_weighted_album([]) is None
    print("test_empty_items_returns_none passed")


def test_higher_ranked_album_chosen_more_often():
    # album_A is rank 0 (most played), album_B is rank 9 (least played of the sample)
    items = [_track("album_A", "url_A")] + [
        _track(f"filler_{i}", f"url_filler_{i}") for i in range(8)
    ] + [_track("album_B", "url_B")]

    random.seed(42)
    counts = {"album_A": 0, "album_B": 0}
    trials = 2000
    for _ in range(trials):
        album_id, _ = top_played.pick_weighted_album(items)
        if album_id in counts:
            counts[album_id] += 1

    assert counts["album_A"] > counts["album_B"] * 3, counts
    print(f"test_higher_ranked_album_chosen_more_often passed {counts}")


def test_should_refresh_respects_disabled_flag():
    class FakeSettings(dict):
        pass

    fake = {"default_wallpaper": {"auto_refresh_enabled": False, "last_refresh": 0.0}}
    assert top_played.should_refresh(fake) is False

    fake2 = {"default_wallpaper": {"auto_refresh_enabled": True, "last_refresh": 0.0}}
    assert top_played.should_refresh(fake2) is True
    print("test_should_refresh_respects_disabled_flag passed")


if __name__ == "__main__":
    test_dedupes_by_album_keeping_best_rank()
    test_skips_tracks_without_images()
    test_empty_items_returns_none()
    test_higher_ranked_album_chosen_more_often()
    test_should_refresh_respects_disabled_flag()
    print("ALL TESTS PASSED")
