from dataclasses import dataclass


@dataclass
class PersonaParams:
    name: str
    typing_mean_s: float
    typing_stddev_s: float
    mouse_lambda: float
    idle_lambda: float
    wpm: int


_BUILTIN_PERSONAS: dict[str, PersonaParams] = {
    "focused_writer": PersonaParams(
        name="focused_writer",
        typing_mean_s=180,
        typing_stddev_s=30,
        mouse_lambda=0.05,
        idle_lambda=0.2,
        wpm=70,
    ),
    "distracted_multitasker": PersonaParams(
        name="distracted_multitasker",
        typing_mean_s=40,
        typing_stddev_s=15,
        mouse_lambda=0.3,
        idle_lambda=0.8,
        wpm=55,
    ),
    "slow_and_steady": PersonaParams(
        name="slow_and_steady",
        typing_mean_s=120,
        typing_stddev_s=10,
        mouse_lambda=0.1,
        idle_lambda=0.3,
        wpm=35,
    ),
    "power_user": PersonaParams(
        name="power_user",
        typing_mean_s=90,
        typing_stddev_s=20,
        mouse_lambda=0.15,
        idle_lambda=0.1,
        wpm=90,
    ),
    # "custom" is not in _BUILTIN_PERSONAS — it is always loaded from config
}


def get_persona(name: str, config: dict) -> PersonaParams:
    """Return PersonaParams for the given persona name.

    For "custom", parameters are read directly from config["personas"]["custom"].
    For all others, built-in values are used.
    """
    if name == "custom":
        p = config["personas"]["custom"]
        return PersonaParams(
            name="custom",
            typing_mean_s=float(p["typing_mean_s"]),
            typing_stddev_s=float(p["typing_stddev_s"]),
            mouse_lambda=float(p["mouse_lambda"]),
            idle_lambda=float(p["idle_lambda"]),
            wpm=int(p["wpm"]),
        )
    if name not in _BUILTIN_PERSONAS:
        raise ValueError(f"Unknown persona: {name!r}")
    return _BUILTIN_PERSONAS[name]
