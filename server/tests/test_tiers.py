from ailing.tiers import note_tier


def test_no_cards_reviewed_is_unreviewed() -> None:
    assert note_tier([(0, 0), (0, 0)]) == "unreviewed"


def test_all_cards_mature() -> None:
    assert note_tier([(2, 320), (2, 286)]) == "mature"


def test_weakest_card_sets_the_tier() -> None:
    assert note_tier([(2, 320), (2, 10)]) == "young"


def test_unreviewed_sibling_does_not_drag_a_reviewed_card_down() -> None:
    assert note_tier([(2, 100), (0, 0)]) == "mature"


def test_boundary_is_21_days() -> None:
    assert note_tier([(2, 21)]) == "mature"
    assert note_tier([(2, 20)]) == "young"
