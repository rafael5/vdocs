import sys
from pathlib import Path

# Make src/ importable without requiring `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Hypothesis profile for the property suite (§12 / toolchain mandate). deadline=None keeps the
# pure-transform invariants from flaking under coverage + random test order (timing, not logic);
# max_examples is a sane breadth for CI.
from hypothesis import settings  # noqa: E402

settings.register_profile("vdocs", max_examples=200, deadline=None)
settings.load_profile("vdocs")

# Shared pytest fixtures go here
