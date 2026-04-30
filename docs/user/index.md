# User Guide

## Quick Start

```text
$ ./appenv init
Let's create a new appenv project in /home/user/myproject
I'll ask a few questions, then create pyproject.toml here

Binary to expose (creates ./<name> symlink) [app] http
Enter dependencies (one per line, empty line to finish):
  Default: http
  Dependency: httpie
  Dependency:
Project name [myproject]:
Description []:
Minimum Python version [3.13]:
Created pyproject.toml
Generating new lock file ...
✓ Created (+273 lines)

=== Appenv project initialized ===

Use `./http` to run the http binary
```

Then run the exposed binary:

```bash
./http GET https://httpbin.org/get
```

## Topics

```{toctree}
:titlesonly:
installation
workflows
commands
locking-behavior
```
