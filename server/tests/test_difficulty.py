from ailing.difficulty import Difficulty, adapt


def test_too_hard_raises_the_floor_and_cuts_a_stretch_word() -> None:
    assert adapt(Difficulty(0.95, 2), "too_hard") == Difficulty(0.96, 1)


def test_too_easy_does_the_reverse() -> None:
    assert adapt(Difficulty(0.97, 2), "too_easy") == Difficulty(0.96, 3)


def test_about_right_and_no_rating_change_nothing() -> None:
    assert adapt(Difficulty(0.96, 2), "about_right") == Difficulty(0.96, 2)
    assert adapt(Difficulty(0.96, 2), None) == Difficulty(0.96, 2)


def test_limits_hold() -> None:
    assert adapt(Difficulty(0.99, 1), "too_hard") == Difficulty(0.99, 1)
    assert adapt(Difficulty(0.95, 3), "too_easy") == Difficulty(0.95, 3)


def test_repeated_steps_land_on_round_numbers() -> None:
    d = Difficulty()
    for _ in range(3):
        d = adapt(d, "too_hard")
    assert d.floor == 0.98
