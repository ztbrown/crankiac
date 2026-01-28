# Versioning Policy

This project follows [Semantic Versioning 2.0.0](https://semver.org/).

## Version Format

Versions are in the format `MAJOR.MINOR.PATCH`:

- **MAJOR**: Breaking changes that require migration or are not backwards compatible
- **MINOR**: New features and enhancements that are backwards compatible
- **PATCH**: Bug fixes, minor improvements, and documentation updates

## Commit Message Conventions

Version bumps are determined by commit message prefixes:

| Prefix | Version Bump | Example |
|--------|-------------|---------|
| `feat:` | MINOR | `feat: Add speaker search endpoint` |
| `fix:` | PATCH | `fix: Correct timestamp calculation` |
| `docs:` | PATCH | `docs: Update API documentation` |
| `refactor:` | PATCH | `refactor: Simplify search logic` |
| `test:` | PATCH | `test: Add integration tests` |
| `chore:` | PATCH | `chore: Update dependencies` |
| `BREAKING:` | MAJOR | `BREAKING: Change API response format` |

### Breaking Changes

For breaking changes, use the `BREAKING:` prefix OR include `BREAKING CHANGE:` in the commit body:

```
feat: Change search API response format

BREAKING CHANGE: The search endpoint now returns results in a different structure.
Migration required for clients using the old format.
```

## Automatic Version Bumps

The refinery automatically bumps versions on merges to main:

1. Analyzes commit messages since the last version tag
2. Determines the highest bump level needed (MAJOR > MINOR > PATCH)
3. Updates `pyproject.toml` with the new version
4. Updates `CHANGELOG.md` with the changes
5. Creates a version tag

## Manual Version Bumps

If needed, versions can be bumped manually:

```bash
# Bump patch version (0.1.0 -> 0.1.1)
python3 refinery/bump_version.py patch

# Bump minor version (0.1.0 -> 0.2.0)
python3 refinery/bump_version.py minor

# Bump major version (0.1.0 -> 1.0.0)
python3 refinery/bump_version.py major
```

## Changelog

All notable changes are documented in [CHANGELOG.md](CHANGELOG.md). The changelog follows the [Keep a Changelog](https://keepachangelog.com/) format.

## Pre-release Versions

For pre-release versions, append a suffix:

- Alpha: `1.0.0-alpha.1`
- Beta: `1.0.0-beta.1`
- Release candidate: `1.0.0-rc.1`
