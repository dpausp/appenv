# Software Design Description
## For LSP Symbol Cache with SQLite

**Feature ID:** F-001-lsp-symbol-cache  
**Version:** 1.0-draft  
**Date:** 2026-03-03

## Table of Contents
<!-- TOC -->
* [1. Introduction](#1-introduction)
  * [1.1 Document Purpose](#11-document-purpose)
  * [1.2 Subject Scope](#12-subject-scope)
  * [1.3 Definitions, Acronyms, and Abbreviations](#13-definitions-acronyms-and-abbreviations)
  * [1.4 References](#14-references)
  * [1.5 Document Overview](#15-document-overview)
* [2. Design Overview](#2-design-overview)
  * [2.1 Stakeholder Concerns](#21-stakeholder-cons)
  * [2.2 Selected Viewpoints](#22-selected-viewpoints)
* [3. Design Views](#3-design-views)
* [4. Decisions](#4-decisions)
* [5. Appendixes](#5-appendixes)
<!-- TOC -->

## 1. Introduction

### 1.1 Document Purpose

This Software Design Description (SDD) documents the key technical decisions for implementing SQLite-based caching in the ty_symbols.py CLI tool. The intended audiences are developers implementing the feature and future maintainers who need to understand the architectural choices.

This SDD focuses on critical design decisions rather than providing a complete implementation blueprint. It captures the "why" behind technical choices and their consequences.

### 1.2 Subject Scope

**Subject:** SQLite-based LSP Symbol Cache  
**Version:** 1.1.0 (target release)

This design covers the addition of a caching system to the ty_symbols.py tool to avoid repeated LSP queries. The cache uses SQLite for persistence and git commit hashes for invalidation.

**Inclusions:**
- Cache database schema and access patterns
- Git integration for cache invalidation
- Command integration architecture
- Error handling and fallback strategies

**Exclusions:**
- Detailed implementation of each function
- UI/UX design (covered in SRS)
- Testing strategy (covered in test plans)

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| DAO | Data Access Object - Pattern for abstracting database access |
| LSP | Language Server Protocol |
| MADR | Markdown Architecture Decision Record |
| ORM | Object-Relational Mapping - Not used in this design (raw SQLite) |

### 1.4 References

| Reference | Type | Description |
|-----------|------|-------------|
| F-001 SRS | Normative | Requirements specification for this feature |
| ty_symbols.py source | Informative | Current implementation |
| SQLite documentation | Informative | SQLite features and best practices |

### 1.5 Document Overview

This document is organized into:
- **Section 2: Design Overview** - High-level architecture and stakeholder concerns
- **Section 3: Design Views** - Detailed architectural views (when needed)
- **Section 4: Decisions** - Key technical decisions using MADR pattern
- **Section 5: Appendixes** - Supporting materials

The primary focus is Section 4 (Decisions), which captures the critical architectural choices.

## 2. Design Overview

### 2.1 Stakeholder Concerns

| Stakeholder | Concerns | Addressed By |
|-------------|----------|--------------|
| Developers | Maintainability, code clarity | Clear separation of concerns, simple architecture |
| Users | Performance, reliability | Fast cache hits, graceful degradation |
| Operators | Debugging, troubleshooting | Clear error messages, fallback behavior |
| Future maintainers | Understanding design rationale | MADR decisions with full context |

### 2.2 Selected Viewpoints

The following viewpoints are relevant to this design:

**Composition Viewpoint** - Shows how the caching system integrates with existing components

**Information Viewpoint** - Describes the SQLite database schema and data organization

**Algorithm Viewpoint** - Details the cache validation and fallback logic

**State Dynamics Viewpoint** - Shows the states of the cache (empty, valid, stale) and transitions

**Dependency Viewpoint** - Illustrates dependencies between cache module and other components

Most concerns are addressed through the MADR decisions in Section 4, making detailed design views optional.

## 3. Design Views

No detailed design views are required. The architecture is straightforward and well-described by the MADR decisions in Section 4. The following high-level component structure applies:

**Components:**
- **CacheManager** - Handles cache database operations (CRUD for symbols/references)
- **GitIntegration** - Provides git status and commit hash information
- **ScanCommand** - Orchestrates cache population via LSP queries
- **CommandIntegrations** - Enhance existing list/show commands with cache support

**Data Flow:**
1. User invokes list/show command
2. GitIntegration checks working tree status
3. If clean: CacheManager retrieves from cache or returns miss
4. If cache miss or dirty tree: Fall back to LSP queries
5. Display results with appropriate warnings

## 4. Decisions

### Decision 001: SQLite for Cache Storage

**Context:**
The system needs persistent storage for symbol and reference data to avoid repeated LSP queries. The cache must be fast, reliable, and require minimal setup.

**Options:**

1. **SQLite database** - Embedded SQL database, serverless, single file
   - Pros: Zero configuration, ACID transactions, fast reads, widely supported, single file
   - Cons: Less flexible schema changes, file-based locking

2. **JSON files** - Simple key-value storage in JSON format
   - Pros: Human-readable, easy to debug, no database knowledge needed
   - Cons: Slower for large datasets, no query capabilities, manual consistency management

3. **Pickle files** - Python object serialization
   - Pros: Simple Python integration, fast for Python objects
   - Cons: Security risks, version compatibility issues, not human-readable

4. **Key-value store (e.g., Redis, LevelDB)** - External database system
   - Pros: Fast, scalable, feature-rich
   - Cons: Requires external dependency, complex setup, overkill for single-user CLI tool

**Decision:**
Choose **SQLite database**.

**Consequences:**
- **Positive:** 
  - Zero configuration - works out of the box with Python's sqlite3 module
  - ACID compliance ensures cache integrity
  - Fast query performance for cache lookups
  - Single `.ty-symbols.db` file is easy to manage and ignore in .gitignore
  - SQL enables flexible queries (e.g., "find all symbols in file X")
  
- **Negative:**
  - Requires SQL schema design upfront
  - Schema migrations needed if structure changes
  - File-based locking limits concurrent writes (acceptable for CLI use case)

- **Risks:**
  - Database corruption (mitigated by SQLite's robustness and graceful degradation to LSP)
  - Schema version compatibility (mitigated by including schema version in metadata table)

**Related Requirements:** REQ-FUNC-001-001, REQ-FUNC-001-002, REQ-FUNC-001-003

### Decision 002: Git Commit Hash for Cache Invalidation

**Context:**
The cache must detect when cached data is stale and needs refresh. The system needs a reliable way to determine if the codebase has changed since the last scan.

**Options:**

1. **Git commit hash** - Use current HEAD commit SHA-1 as cache key
   - Pros: Precise invalidation, handles all changes (code, config, dependencies)
   - Cons: Requires git repository, doesn't work with uncommitted changes

2. **File modification timestamps** - Track last modified time of Python files
   - Pros: Works without git, handles uncommitted changes
   - Cons: Unreliable (clock skew, file copies), doesn't detect content changes, OS-dependent

3. **Content hashes** - Hash file contents and compare
   - Pros: Precise change detection, works without git
   - Cons: Expensive to compute for large codebases, must hash all files on every query

4. **Hybrid approach** - Commit hash + file timestamps
   - Pros: Handles both committed and uncommitted changes
   - Cons: Complex logic, two sources of truth

**Decision:**
Choose **git commit hash** as primary invalidation mechanism, with **dirty working tree detection** to trigger fallback.

**Consequences:**
- **Positive:**
  - Simple, reliable invalidation - different commit = different cache
  - Fast to check (single git command)
  - Aligns with typical developer workflow (commit before major work)
  - Clear semantic: cache is valid for a specific codebase state
  
- **Negative:**
  - Doesn't cache data for dirty working trees (uncommitted changes)
  - Requires git repository (non-negotiable per constraints)
  - Users must scan after commits to update cache
  
- **Trade-offs accepted:**
  - **No incremental caching:** Full scan per commit is simpler to implement and reason about
  - **Dirty tree penalty:** Acceptable because developers typically work in clean states or want live data during active development

**Fallback behavior:** When working tree is dirty, system falls back to live LSP queries with a warning. This ensures users always get accurate data, just slower.

**Related Requirements:** REQ-FUNC-001-004, REQ-FUNC-001-007, REQ-FUNC-001-008, Constraint C-004, C-006

### Decision 003: Full Project Scan (No Incremental Updates)

**Context:**
When populating the cache, the system needs to decide between scanning the entire project or only changed files.

**Options:**

1. **Full project scan** - Scan all Python files on each `scan` command
   - Pros: Simple implementation, guaranteed consistency, no complex change tracking
   - Cons: Slower for large projects, redundant work for small changes

2. **Incremental scan** - Only scan files changed since last commit
   - Pros: Faster for small changes, less LSP server load
   - Cons: Complex implementation, must track file-level changes, merge logic for symbol updates

3. **Hybrid approach** - Full scan initially, incremental for subsequent scans
   - Pros: Best of both worlds for performance
   - Cons: Most complex implementation, two code paths

**Decision:**
Choose **full project scan** for initial implementation.

**Consequences:**
- **Positive:**
  - Simple, predictable behavior
  - Guaranteed cache consistency - no stale symbols from deleted files
  - Easier to implement and test
  - Clear mental model: one scan = one consistent cache state
  
- **Negative:**
  - Slower for large projects (mitigated by running scan in background or during downtime)
  - Wasted work for small changes (acceptable trade-off for simplicity)
  
- **Rationale for deferring incremental scan:**
  - Incremental scanning adds significant complexity (tracking file changes, merging symbol updates, handling deletions)
  - Performance optimization can be added later if full scan proves too slow
  - Premature optimization - better to measure actual performance first

**Future consideration:** If scan performance becomes a bottleneck, implement incremental scanning as a future enhancement.

**Related Requirements:** REQ-FUNC-001-011, Constraint C-005

### Decision 004: Cache Location in Project Root

**Context:**
The cache database file needs a location that is discoverable, project-specific, and doesn't interfere with version control.

**Options:**

1. **Project root as `.ty-symbols.db`** - Single file in project root
   - Pros: Discoverable, easy to ignore in .gitignore, project-specific
   - Cons: Visible in project directory (unless ignored)

2. **Hidden directory `.ty-symbols/cache.db`** - Dedicated hidden directory
   - Pros: Keeps project root clean, room for additional cache files
   - Cons: More complex path, directory creation needed

3. **User home directory `~/.cache/ty-symbols/<project-hash>/cache.db`** - Centralized cache
   - Pros: Keeps projects clean, shared cache across clones
   - Cons: Complex invalidation, harder to debug, cache cleanup issues

4. **System temp directory** - Ephemeral cache
   - Pros: No cleanup needed
   - Cons: Cache lost on reboot, not persistent

**Decision:**
Choose **project root as `.ty-symbols.db`**.

**Consequences:**
- **Positive:**
  - Simple, predictable location
  - Easy to find and inspect (debugging)
  - Easy to delete (cache reset: `rm .ty-symbols.db`)
  - Project-specific (no cross-project contamination)
  - Standard pattern (similar to `.tox`, `.venv`, etc.)
  
- **Negative:**
  - Visible in project directory (mitigated by adding to .gitignore)
  - Duplicated across git clones (acceptable - cache is disposable)
  
- **Implementation note:** The system should suggest adding `.ty-symbols.db` to `.gitignore` if not present.

**Related Requirements:** REQ-FUNC-001-001, Constraint C-001

### Decision 005: Transparent Cache Integration (No API Changes)

**Context:**
The caching system needs to integrate with existing `list` and `show` commands. The integration approach affects backward compatibility and user experience.

**Options:**

1. **Transparent integration** - Cache works automatically, no command changes
   - Pros: Backward compatible, zero learning curve, automatic performance improvement
   - Cons: Less control for users, harder to debug cache issues

2. **Explicit cache flags** - Require `--use-cache` flag to enable caching
   - Pros: Explicit user control, easier to debug
   - Cons: Breaking change, extra typing, users may not discover feature

3. **New cached commands** - Add `cached-list`, `cached-show` commands
   - Pros: Clear separation, no impact on existing commands
   - Cons: Command proliferation, confusing for users

**Decision:**
Choose **transparent integration with optional `--no-cache` flag**.

**Consequences:**
- **Positive:**
  - Backward compatible - existing commands work unchanged
  - Automatic performance benefit for all users
  - Zero learning curve - cache "just works"
  - `--no-cache` flag for users who need fresh data
  
- **Negative:**
  - Users may not realize caching is happening (mitigated by status messages)
  - Cache issues harder to debug (mitigated by `--no-cache` and verbose logging)
  
- **User experience:**
  - Default behavior: Try cache → fall back to LSP with warning if dirty
  - `--no-cache` flag: Always use live LSP queries
  - Clear warnings when fallback occurs

**Related Requirements:** REQ-FUNC-001-014 to 001-019, NFR-USE-001-002

### Decision 006: Raw SQLite (No ORM)

**Context:**
The system needs to interact with the SQLite database. The choice of database access approach affects code complexity and maintainability.

**Options:**

1. **Raw sqlite3 module** - Direct SQL queries via Python's sqlite3
   - Pros: Zero dependencies, full SQL power, transparent performance
   - Cons: More boilerplate, manual connection management, SQL in code

2. **SQLAlchemy ORM** - Object-relational mapping library
   - Pros: Pythonic API, automatic connection management, database-agnostic
   - Cons: Heavy dependency, learning curve, overkill for simple schema

3. **SQLite ORM (e.g., peewee, dataset)** - Lightweight ORM
   - Pros: Simpler than SQLAlchemy, less boilerplate
   - Cons: Additional dependency, limited compared to SQLAlchemy

**Decision:**
Choose **raw sqlite3 module with context managers**.

**Consequences:**
- **Positive:**
  - Zero external dependencies (sqlite3 is in Python stdlib)
  - Full control over SQL queries and performance
  - Transparent - easy to understand what's happening
  - Lightweight - appropriate for CLI tool
  - Context managers ensure proper connection cleanup
  
- **Negative:**
  - More boilerplate than ORM
  - SQL embedded in Python code (mitigated by centralizing queries in CacheManager)
  - Manual schema migrations (mitigated by simple schema and version tracking)
  
- **Design pattern:**
  - Use Data Access Object (DAO) pattern via CacheManager class
  - Context manager for database connections (`with CacheManager(db_path) as cache:`)
  - Centralize all SQL in CacheManager methods

**Related Requirements:** Constraint C-002 (existing patterns - Python stdlib preferred)

### Decision 007: Dirty Tree Fallback Strategy

**Context:**
When the git working tree has uncommitted changes, the cache is potentially stale. The system needs a strategy for handling this situation.

**Options:**

1. **Always fallback to LSP** - Never use cache when tree is dirty
   - Pros: Always accurate data, simple logic
   - Cons: No performance benefit during active development

2. **Use cache with warning** - Use cache but warn it may be stale
   - Pros: Performance benefit, user awareness
   - Cons: Potentially inaccurate data, confusing UX

3. **Allow force flag** - Let user decide with `--force` flag
   - Pros: User control, handles edge cases
   - Cons: Requires user intervention, easy to forget

4. **Hybrid: fallback + force** - Default to LSP, allow force override
   - Pros: Safe default, escape hatch for experts
   - Cons: Two behaviors to understand

**Decision:**
Choose **fallback to LSP with warning, support `--force` flag for scan command**.

**Consequences:**
- **Positive:**
  - Safe default - users always get accurate data
  - Clear warning explains why cache isn't used
  - `--force` flag for experts who understand the trade-offs
  - Aligns with "fail safe" principle
  
- **Negative:**
  - No performance benefit during active development (acceptable - developers expect slower feedback during active coding)
  - Users must commit or use `--force` to use cache
  
- **Rationale:**
  - Accurate data is more important than speed during active development
  - Warning raises awareness of cache invalidation model
  - `--force` provides escape hatch for power users

**Related Requirements:** REQ-FUNC-001-012, REQ-FUNC-001-015, REQ-FUNC-001-018, REQ-FUNC-001-020, Constraint C-006

## 5. Appendixes

### Appendix A: Database Schema

```sql
-- Cache metadata
CREATE TABLE cache_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Schema version
INSERT INTO cache_metadata (key, value) VALUES ('schema_version', '1');
INSERT INTO cache_metadata (key, value) VALUES ('commit_hash', '');

-- Files table (for path resolution)
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Symbols table
CREATE TABLE symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    kind_id INTEGER NOT NULL,
    line_start INTEGER NOT NULL,
    col_start INTEGER NOT NULL,
    line_end INTEGER,
    col_end INTEGER,
    parent_symbol TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id),
    UNIQUE(file_id, name, line_start, col_start)
);

-- References table
CREATE TABLE references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER NOT NULL,
    enclosing_symbol TEXT,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
    FOREIGN KEY (file_id) REFERENCES files(id)
);

-- Indexes for common queries
CREATE INDEX idx_symbols_name ON symbols(name);
CREATE INDEX idx_symbols_file ON symbols(file_id);
CREATE INDEX idx_references_symbol ON references(symbol_id);
CREATE INDEX idx_references_file ON references(file_id);
```

### Appendix B: Component Responsibilities

**CacheManager (cache_manager.py):**
- Database connection management (context manager)
- Symbol CRUD operations
- Reference CRUD operations
- Cache validation (check commit hash)
- Cache clearing/reset

**GitIntegration (git_integration.py):**
- Get current commit hash
- Check if working tree is clean/dirty
- Verify git repository exists
- Get specific revision hash (--rev support)

**ScanCommand (integrated into ty_symbols.py):**
- Orchestrate full project scan
- Display progress
- Store results in cache
- Handle --force and --rev flags

**Command Enhancements (integrated into existing functions):**
- list: Check cache first, fallback to LSP
- show: Check cache first, fallback to LSP
- Display warnings on fallback
- Support --no-cache flag

### Appendix C: Error Handling Strategy

**Database errors:**
- Corruption: Fall back to LSP, suggest cache reset
- Locking: Retry with timeout, then fall back to LSP
- Schema mismatch: Fall back to LSP, suggest cache reset

**Git errors:**
- Not a repository: Fall back to LSP, no caching available
- Git not found: Fall back to LSP, no caching available
- Command failure: Fall back to LSP, display warning

**LSP errors:**
- Existing error handling preserved
- Cache doesn't change LSP error behavior

**User communication:**
- Warnings go to stderr (distinguishable from data output)
- Errors include actionable suggestions
- Verbose mode available for debugging

### Appendix D: Future Enhancements

**Not in scope for v1.1.0, but considered for future releases:**

1. **Incremental scanning** - Only scan changed files
2. **Background scanning** - Scan in background process
3. **Cache sharing** - Share cache across team members
4. **Multi-project support** - Single cache for monorepos
5. **Cache statistics** - Show hit/miss rates, space usage
6. **Cache compression** - Reduce disk usage for large projects
7. **Stale reference cleanup** - Remove references to deleted symbols
8. **Partial cache** - Cache only high-value symbols (e.g., frequently queried)
