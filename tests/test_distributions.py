from engine.distributions import exponential_duration, gaussian_duration


def test_gaussian_stays_within_bounds():
    for _ in range(1000):
        result = gaussian_duration(mean_s=60.0, stddev_s=10.0)
        assert 1.0 <= result <= 3600.0


def test_gaussian_respects_custom_bounds():
    for _ in range(500):
        result = gaussian_duration(mean_s=10.0, stddev_s=5.0, min_s=5.0, max_s=30.0)
        assert 5.0 <= result <= 30.0


def test_gaussian_floor_at_one_second():
    for _ in range(500):
        result = gaussian_duration(mean_s=0.5, stddev_s=0.1)
        assert result >= 1.0


def test_exponential_stays_within_bounds():
    for _ in range(1000):
        result = exponential_duration(lambda_=0.1)
        assert 1.0 <= result <= 600.0


def test_exponential_respects_custom_bounds():
    for _ in range(500):
        result = exponential_duration(lambda_=0.5, min_s=2.0, max_s=20.0)
        assert 2.0 <= result <= 20.0


def test_exponential_floor_at_one_second():
    for _ in range(500):
        result = exponential_duration(lambda_=1000.0)
        assert result >= 1.0


def test_gaussian_returns_float():
    assert isinstance(gaussian_duration(60.0, 10.0), float)


def test_exponential_returns_float():
    assert isinstance(exponential_duration(0.1), float)
