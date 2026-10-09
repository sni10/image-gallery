Write the commit message strictly in Conventional Commits format. Any other format is wrong.

The first line MUST be: `<type>(<optional scope>)<optional !>: <summary>`

Allowed types (choose exactly one, the most specific):
- feat: new user-facing functionality
- fix: bug fix in application behavior
- perf: performance improvement
- refactor: code change without behavior change
- docs: documentation only
- test: tests only
- build: build system, Docker, compose, dependencies
- ci: CI/CD workflows and release configuration
- style: formatting only
- chore: other maintenance
- revert: revert of a previous commit

Release impact (automatic releases on `main`, python-semantic-release, `pyproject.toml`):
- fix, perf -> patch release
- feat -> minor release
- `!` / `BREAKING CHANGE:` -> major release (minor while the version is 0.x)
- refactor, docs, test, build, ci, style, chore, revert -> NO release
- Never use fix or feat for config, Docker, compose, CI or tooling changes: use build, ci or chore. A wrong type publishes a needless version.

Scopes (optional, use only these): `api`, `admin`, `accounts`, `gallery`, `config`, `deploy`, `ci`.

Rules:
- The type is lowercase and always comes first. NEVER start with a capitalized verb like "Add", "Update", "Fix".
- Summary: English, imperative mood, lowercase first letter, no trailing period. Header at most 150 characters (CI limit); aim for 72.
- If changes span several areas, pick the dominant type for the header and list the details as bullet points in the body.
- Breaking change: add `!` after the type/scope and a `BREAKING CHANGE: <description>` footer.
- No `Co-Authored-By` or "Generated with" lines.

Examples:
- `ci: add coverage and junit reports`
- `build(deploy): add caddy service to compose.prod.yaml`
- `fix(api): return 404 for numeric gallery ids`
- `feat(accounts): add email change confirmation`

Wrong: `Add CI configuration, coverage reporting, and update Docker setup`
Right: `ci: add coverage reporting and junit reports to tests`