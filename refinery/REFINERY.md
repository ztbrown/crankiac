# Refinery Instructions

The refinery processes merge requests and handles automated tasks on merges to main.

## Version Bumping

On every merge to main, the refinery should bump the version automatically.

### Automatic Version Bump Workflow

After a successful merge to main:

1. **Analyze commits** to determine the bump level:
   ```bash
   python3 refinery/bump_version.py auto
   ```

2. **Commit the version bump**:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore: Bump version to <new_version>"
   ```

3. **Tag the release**:
   ```bash
   git tag v<new_version>
   git push origin main --tags
   ```

### Commit Message Rules

The version bump level is determined by commit messages:

| Commit Prefix | Bump Level | Example |
|--------------|------------|---------|
| `BREAKING:` | MAJOR | Breaking API changes |
| `feat:` | MINOR | New features |
| `fix:` | PATCH | Bug fixes |
| `docs:`, `test:`, `chore:` | PATCH | Maintenance |

### Manual Override

If automatic detection isn't appropriate, force a specific level:

```bash
# Force patch bump
python3 refinery/bump_version.py patch

# Force minor bump
python3 refinery/bump_version.py minor

# Force major bump
python3 refinery/bump_version.py major
```

## Integration with Merge Queue

The refinery's merge workflow should include version bumping:

1. Receive merge request from polecat
2. Verify tests pass
3. Merge to main
4. Run version bump script
5. Push version commit and tag

## Files Updated

The bump script modifies:
- `pyproject.toml` - Updates the `version` field
- `CHANGELOG.md` - Adds entry for new version with categorized changes

## Troubleshooting

### No commits to analyze
If "No commits found since last tag", either:
- There truly are no changes (skip bump)
- The tag is missing; manually specify bump level

### Version format errors
The script expects versions in `MAJOR.MINOR.PATCH` format.
Pre-release suffixes like `-alpha.1` are supported for reading but will be stripped on bump.
