# Installation

appenv is a self-contained Python application bootstrapper that manages virtual environments using uv.

## Requirements

- **Python**: 3.10 or later
- **uv**: 0.5.0 or later (auto-installed if not found)

## Getting appenv

### Option 1: Bootstrap Script (Recommended)

```text
# Create project directory
mkdir myproject && cd myproject

# Download and run bootstrap
curl -sL https://github.com/flyingcircusio/appenv/raw/master/bootstrap | sh
```

### Option 2: Clone the Repository

```text
git clone https://github.com/flyingcircusio/appenv.git
cd appenv
```

### Option 3: Copy appenv.py

Since appenv is a single-file application, you can simply copy `appenv.py` to your project:

```text
curl -sL https://github.com/flyingcircusio/appenv/raw/master/src/appenv.py -o appenv
chmod +x appenv
```

## uv Installation

appenv requires uv for virtual environment management. If uv is not found, appenv will attempt to install it automatically using one of these methods:

1. **PATH uv**: If a suitable uv (≥0.5.0) is in PATH, use it
2. **Nix**: Build uv with `nix build nixpkgs#uv`
3. **pip**: Install with `pip install uv`

### Manual uv Installation

```text
# Official installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pip
pip install uv

# Or with nix
nix profile install nixpkgs#uv
```

## Verification

Verify appenv is working:

```text
./appenv version
```

## Next Steps

- {doc}`quickstart` - Create your first project
- {doc}`commands` - Learn about available commands
