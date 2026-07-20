# HVAC Toolkit (working title)

Subscription HVAC engineering toolkit for engineers, designers and contractors.
SI + imperial. Brand name TBC — set via `BRAND_NAME` config, nothing else to change.

## Structure

```
specs/      Functional specs per engine module — written from public standards
            (ASHRAE HOF, CIBSE guides) BEFORE implementation. The clean-room trail.
engine/     hvac_engine — standalone, pure-Python calculation package.
            No Flask imports. Independently tested against published values.
web/        Flask application (app factory + blueprints) consuming the engine.
```

## Development

```bash
# Engine tests
cd engine && pip install -e .[dev] && pytest

# Web app (local)
cd web && pip install -r requirements.txt && flask --app wsgi run --debug

# Full stack
docker compose up --build
```

## First commit (run locally — once)

Git can't run inside the Cowork sandbox, and commits authored on your own machine
are better evidence of own-time work anyway:

```bash
cd C:\CoWork\hvac-toolkit
git init -b main
git add -A
git commit -m "Clean-room scaffold: psychrometrics engine + Flask shell"
# then create a PRIVATE repo on your personal GitHub and:
git remote add origin git@github.com:<you>/<repo>.git
git push -u origin main
```

## Provenance

All calculation methods are implemented from the functional specs in `specs/`,
which cite public engineering standards (ASHRAE Handbook — Fundamentals, CIBSE
Guides, NIST SP 811). Developed on personal equipment in personal time.
