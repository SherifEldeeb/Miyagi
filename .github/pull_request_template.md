## What & why

<!-- What changed and why. Link the INTENT.md decision if one was made. -->

## How it was tested

<!-- uv run pytest output, browser check, real-camera notes -->

## Checklist

- [ ] `uv run pytest` passes (incl. `tests/test_docs.py`)
- [ ] `uv run ruff check .` passes
- [ ] Tests added/updated (positive and negative cases for detector changes)
- [ ] **README.md** updated (usage, config, env vars, habits table) if user-visible
- [ ] **DESIGN.md** updated (modules, zones, detectors, thresholds, protocol, storage) if behaviour changed
- [ ] **INTENT.md** decision log appended if a product/tech decision was made; focus/open questions current
- [ ] **AGENTS.md** updated if commands, conventions or invariants changed
- [ ] No frames/images/landmarks persisted or sent off-device
- [ ] Changes to `learned.feature_vector` called out (invalidates saved personal models)
