# Project instructions

## Commit messages: Conventional Commits, always

Every commit message (yours, suggested ones, PR titles) MUST follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>)<optional !>: <description>

<optional body>

<optional footer, e.g. BREAKING CHANGE: ...>
```

- Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `style`, `revert`.
- Scopes used here: `api`, `admin`, `accounts`, `gallery`, `config`, `deploy`, `ci`.
- Header ≤ 150 chars, lower-case type, no trailing period.
- Breaking API/contract change: `!` after the type/scope **and** a `BREAKING CHANGE:` footer explaining the migration.

Why it matters: messages drive automatic releases on `main` (python-semantic-release, `pyproject.toml`):
`fix`/`perf` → patch, `feat` → minor, breaking → major (minor while the version is `0.x`). Other types don't release.
CI rejects non-conforming commits on push and pull requests to `main` (`commitlint.config.mjs`).
Check a message locally: `echo "feat(api): ..." | npx -p @commitlint/cli@21 -p @commitlint/config-conventional@21 commitlint`.

Commit or push only when the user explicitly asks for it.
