"""Single source of truth for analyst-backend provider classes.

FIXTURE: synthetic/fixture data paths - never production-deliverable.
DETERMINISTIC: real validated data, template narrative, rule-based verdict -
deliverable only with explicit opt-in and a visible disclosure banner.
"""

FIXTURE_BACKEND_PROVIDERS: frozenset[str] = frozenset(
    {"fixture", "deterministic_fixture", "local_fixture"}
)
DETERMINISTIC_BACKEND_PROVIDERS: frozenset[str] = frozenset({"codex_native"})
