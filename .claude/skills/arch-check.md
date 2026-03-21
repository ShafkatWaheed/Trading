---
name: arch-check
description: Verify that all code follows the architecture rules in ARCHITECTURE.md
user_invocable: true
---

# Architecture Check

Scan the entire codebase and verify compliance with ARCHITECTURE.md rules.

## Steps

1. Read ARCHITECTURE.md and CLAUDE.md to understand the rules

2. For every Python file in `src/`, check its import statements:
   - `src/models/` files must NOT import from any other `src/` module
   - `src/analysis/` files must NOT import from `data/`, `reports/`, `utils/db`, or `app.py`
   - `src/sentiment/` files must NOT import from `data/`, `reports/`, or `app.py`
   - `src/screener/` files must NOT import from `data/`, `reports/`, or `app.py`
   - `src/data/` files must NOT import from `analysis/`, `reports/`, or `app.py`
   - `src/utils/db.py` must NOT import from `models/`
   - `src/reports/` may import from `analysis/`, `sentiment/`, `data/`, `models/`, `utils/`
   - `src/app.py` may import from `reports/`, `utils/`

3. Check that all price/financial values use `Decimal`, not `float`

4. Check that all functions have type hints

5. Check that no API keys are hardcoded (search for patterns like strings starting with common key prefixes)

6. Check that all external API calls go through the cache (cache_get/cache_set)

## Output

Present results as:
- **PASS** or **FAIL** for each rule
- List any violations with file:line references
- Overall status: COMPLIANT or VIOLATIONS FOUND
