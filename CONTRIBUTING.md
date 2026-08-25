# Contributing to SentinelX

Thank you for your interest in contributing to SentinelX! This document outlines the guidelines for contributing to this project.

## Getting Started

1. **Fork the repository** and clone your fork locally
2. **Create a virtual environment** and install dependencies:
   ```bash
   cd gateway
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
3. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Guidelines

### Code Style

- Follow **PEP 8** for all Python code
- Use **type hints** for function signatures
- Use **Pydantic models** for data validation (not raw dicts)
- Keep functions focused — single responsibility principle
- Write docstrings for public functions and classes

### Architecture Rules

- **Scoring pipeline components are independent** — feature extraction, rules, ML engine, and decision engine should not import each other directly
- **State store interface is abstract** — never reference Redis directly outside `state_store.py`
- **Dashboard has zero dependencies** — vanilla HTML/CSS/JS only, no npm/build step
- **All config via environment variables** — no hardcoded URLs, credentials, or thresholds

### Testing

- Run the E2E pipeline test before submitting:
  ```bash
  python test_pipeline.py  # All 9 stages must pass
  ```
- Add unit tests for new scoring logic in `gateway/tests/`
- Tests must be **idempotent** — use randomized identity IDs, never depend on clean state

### Commit Messages

Use clear, descriptive commit messages:
```
feat: add payload entropy feature to extraction pipeline
fix: prevent false positive on cold-start identity geo check
docs: add troubleshooting section for Docker networking
test: add unit tests for privilege escalation rule
```

## Pull Request Process

1. Ensure all tests pass (both E2E and unit)
2. Update documentation if you changed any API surface or configuration
3. Add a clear description of what your PR does and why
4. Request review from at least one team member

## Areas for Contribution

- **New feature extraction signals** — see `features.py` for the pattern
- **Additional hard-trigger rules** — see `rules.py`
- **Dashboard improvements** — maintain vanilla JS, no framework dependencies
- **Documentation** — fix typos, improve explanations, add examples
- **Test coverage** — add unit tests for edge cases

## Code of Conduct

Be respectful, constructive, and collaborative. We're building security tools — trust within the team matters as much as trust in the system.

---

*SentinelX Team — NexHack 2.0*
