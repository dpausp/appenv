# Installation

## Requirements

- **Python**: 3.9 or later (managed environments require 3.10+)
- **uv**: 0.5.0 or later (auto-installed if not found)

## Which method is right for you?

- **Starting a new project?** → Download appenv directly
- **Want the easiest setup?** → Use uvx (requires PyPI publication)
- **No internet on target machine?** → Copy appenv.py manually
- **Want to develop appenv itself?** → Clone the repository

All methods give you the same `./appenv` file. The only difference is how you get it.

## Download appenv directly

The recommended way. Transparent, no magic, one file:

```console
mkdir myproject && cd myproject
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
./appenv init
```

Pin to a specific version by using a release tag URL:

```console
curl -sL https://github.com/flyingcircusio/appenv/raw/v1.0.0/src/appenv.py -o appenv
```

## uvx (easiest, requires PyPI)

If appenv is published on PyPI, uvx runs it directly without downloading:

```console
mkdir myproject && cd myproject
uvx appenv init
```

This creates `pyproject.toml` and the command symlink. After that, run `./http` as usual.

uvx executes appenv from a temporary environment. You still need to download appenv.py into your project for day-to-day use:

```console
# After init, download for permanent use
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
```

## Copy without network access

```console
# On a machine with internet
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv

# Transfer appenv to target machine (USB, scp, etc.)
scp appenv targethost:~/myproject/

# On the target machine
chmod +x appenv
./appenv init
```

## Cloning the repository

**This is for developing appenv itself, not for creating projects.**

```console
git clone https://github.com/flyingcircusio/appenv.git
cd appenv
```

If you cloned the repo and want to create a new appenv project, you are in the wrong directory. Create a separate project directory and download appenv there instead.


## Verification

Verify appenv is working:

```console
./appenv version
```

## Next Steps

- {doc}`commands` — Command reference
- {doc}`workflows` — Common workflows
- {doc}`locking-behavior` — How dependency locking works
