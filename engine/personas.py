from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaParams:
    name: str
    typing_mean_s: float
    typing_stddev_s: float
    mouse_lambda: float
    idle_lambda: float
    wpm: int
    typo_rate: float
    thinking_pause_p: float
    thinking_pause_mean_s: float


_BUILTIN_PERSONAS: dict[str, PersonaParams] = {
    "focused_writer": PersonaParams(
        name="focused_writer",
        typing_mean_s=180,
        typing_stddev_s=30,
        mouse_lambda=0.05,
        idle_lambda=0.2,
        wpm=70,
        typo_rate=0.01,
        thinking_pause_p=0.05,
        thinking_pause_mean_s=3.0,
    ),
    "distracted_multitasker": PersonaParams(
        name="distracted_multitasker",
        typing_mean_s=40,
        typing_stddev_s=15,
        mouse_lambda=0.3,
        idle_lambda=0.8,
        wpm=55,
        typo_rate=0.025,
        thinking_pause_p=0.20,
        thinking_pause_mean_s=1.5,
    ),
    "steady": PersonaParams(
        name="steady",
        typing_mean_s=120,
        typing_stddev_s=10,
        mouse_lambda=0.1,
        idle_lambda=0.3,
        wpm=35,
        typo_rate=0.005,
        thinking_pause_p=0.03,
        thinking_pause_mean_s=2.5,
    ),
    "power_user": PersonaParams(
        name="power_user",
        typing_mean_s=90,
        typing_stddev_s=20,
        mouse_lambda=0.15,
        idle_lambda=0.1,
        wpm=90,
        typo_rate=0.03,
        thinking_pause_p=0.05,
        thinking_pause_mean_s=1.0,
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
            typo_rate=float(p["typo_rate"]),
            thinking_pause_p=float(p["thinking_pause_p"]),
            thinking_pause_mean_s=float(p["thinking_pause_mean_s"]),
        )
    if name not in _BUILTIN_PERSONAS:
        raise ValueError(f"Unknown persona: {name!r}")
    return _BUILTIN_PERSONAS[name]
