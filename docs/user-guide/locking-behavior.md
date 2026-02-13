# Locking Behavior

Understanding how appenv manages dependencies through UV's locking mechanism is crucial for reproducible builds and effective dependency management.

## How UV Locking Works

**Lockfiles are deterministic by default.** UV won't automatically upgrade packages when new versions are released. Once `uv.lock` exists, UV prefers the locked versions unless you explicitly request an upgrade. This ensures reproducible builds across machines and time.

### Three Sync Modes

UV operates in three different modes that affect how it handles the lockfile:

| Flag | Behavior | When to Use |
|------|----------|-------------|
| (none) | May update `uv.lock` if `pyproject.toml` changed | Default behavior for most operations |
| `--frozen` | Uses existing lockfile, fails if missing | Production deployments, CI/CD |
| `--locked` | Uses existing lockfile, fails if outdated | When you want to ensure lockfile is current |

### Key Insight

A lockfile is considered "outdated" when `pyproject.toml` dependencies changed, **NOT** when new package versions are available upstream. This means:
- Changing a dependency version in `pyproject.toml` → lockfile becomes outdated
- A new version of a package being released on PyPI → lockfile is NOT outdated (unless you explicitly upgrade)

## appenv Command Mapping

Different appenv commands use different UV sync modes, which determines when lockfiles are updated:

| Command | Lockfile Mode | UV Command | Description |
|---------|---------------|------------|-------------|
| `./mycommand` (running your app) | Frozen | `uv sync --no-dev --frozen` | Production run, exact versions from lockfile |
| `prepare` | Frozen | `uv sync --no-dev --frozen` | Production deps only, requires existing lockfile |
| `develop` | May update | `uv sync` | With dev deps, updates lockfile if `pyproject.toml` changed |
| `update-lockfile` | Updates | `uv lock` | Regenerates lockfile from `pyproject.toml` |

### Important Notes

1. **Running the application or `prepare` requires an existing `uv.lock`**
   - These commands use `--frozen` mode which fails if the lockfile is missing
   - Always run `update-lockfile` first after changing dependencies

2. **`develop` may update the lockfile if `pyproject.toml` changed**
   - Since it doesn't use `--frozen`, it will re-sync dependencies when needed
   - This is useful during development when you frequently change dependencies

3. **Always commit `uv.lock` to version control**
   - This ensures all developers and deployment environments use identical dependency versions
   - Without the lockfile, you lose reproducibility

## Handling Missing Lockfiles

If you try to run your application or use `prepare` without a lockfile:

```
$ ./http
No uv.lock found. Run: ./appenv update-lockfile
```

The solution is simple: generate the lockfile first:

```text
$ ./appenv update-lockfile
✓ Created (+273 lines)

$ ./http  # Now works
```

## Practical Examples

### Setting Up a New Project

```text
# After creating pyproject.toml (via init or migrate)
$ ./appenv update-lockfile   # Create initial lockfile
$ ./appenv prepare           # Create production environment
$ ./mycommand --help         # Run your application
```

### Adding Dependencies

```text
# Add a new dependency
$ ./appenv uv add requests   # Updates both pyproject.toml and uv.lock

# Or add a dev dependency
$ ./appenv uv add --group dev pytest

# No need to run update-lockfile separately - uv add does it automatically
```

### Upgrading Dependencies

```text
# Upgrade a specific package
$ ./appenv uv lock --upgrade-package requests

# Upgrade all packages (within version constraints)
$ ./appenv uv lock --upgrade

# Then test your application
$ ./appenv develop
$ ./appenv run pytest
```

### Checking for Changes Without Applying

```text
# See what would change without actually writing to uv.lock
$ ./appenv update-lockfile --diff
- requests==2.31.0
+ requests==2.32.3
   urllib3==1.26.15
   charset-normalizer==3.1.0
   idna==3.4
   certifi==2023.7.22

# If satisfied with changes, apply them
$ ./appenv update-lockfile
```

## Best Practices

1. **Always commit `uv.lock`** - This is essential for reproducibility
2. **Run `update-lockfile` after changing `pyproject.toml`** - Keeps lockfile in sync
3. **Use `prepare` in production/CI** - Guarantees exact dependency versions
4. **Use `develop` for local development** - Automatically handles dependency changes
5. **Check for updates periodically** - Use `uv lock --upgrade` to get newer versions
6. **Use `--diff` to review changes** - Especially important before upgrading

## Troubleshooting

### "No uv.lock found" Error

This occurs when you try to run your application or use `prepare` without first creating a lockfile.

**Solution:** Run `./appenv update-lockfile` to generate the lockfile.

### Lockfile Conflicts in Git

If you get merge conflicts in `uv.lock`:
1. Resolve the conflicts in `pyproject.toml` first
2. Then run `./appenv update-lockfile` to regenerate a clean lockfile
3. Commit the resolved `uv.lock`

### "Lockfile is outdated" Error

This means `pyproject.toml` has changed since the lockfile was generated.

**Solution:** Run `./appenv update-lockfile` to synchronize the lockfile with `pyproject.toml`.

## UV Universal Resolution

When generating `uv.lock`, UV uses **universal resolution**: all dependencies are resolved to be compatible with the *entire* `requires-python` range. This means you don't need to worry about creating lockfiles with the minimal Python version - UV handles this automatically.

For `requires-python = ">=3.11,<3.14"`, UV ensures every package works on Python 3.11, 3.12, and 3.13.

This is different from pip's approach where you typically generate lockfiles for a specific Python version.
