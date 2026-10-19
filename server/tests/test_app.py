from ailing.app import app


def test_app_has_health_route() -> None:
    assert "/health" in {route.path for route in app.routes}  # type: ignore[attr-defined]
