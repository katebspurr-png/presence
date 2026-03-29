import random


def gaussian_duration(
    mean_s: float,
    stddev_s: float,
    min_s: float = 1.0,
    max_s: float = 3600.0,
) -> float:
    """Sample a duration from a Gaussian distribution, clamped to [min_s, max_s]."""
    return float(max(min_s, min(max_s, random.gauss(mean_s, stddev_s))))


def exponential_duration(
    lambda_: float,
    min_s: float = 1.0,
    max_s: float = 600.0,
) -> float:
    """Sample a duration from an Exponential distribution, clamped to [min_s, max_s].

    lambda_ is the rate parameter (events per second). Higher lambda_ = shorter durations.
    """
    return float(max(min_s, min(max_s, random.expovariate(lambda_))))
