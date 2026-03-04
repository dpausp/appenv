# Software Requirements Specification
## For LSP Symbol Cache with SQLite

**Feature ID:** F-001-lsp-symbol-cache  
**Version:** 1.0-draft  
**Date:** 2026-03-03

## Table of Contents
<!-- TOC -->
* [1. Introduction](#1-introduction)
  * [1.1 Document Purpose](#11-document-purpose)
  * [1.2 Product Scope](#12-product-scope)
  * [1.3 Definitions, Acronyms, and Abbreviations](#13-definitions-acronyms-and-abbreviations)
  * [1.4 References](#14-references)
  * [1.5 Document Overview](#15-document-overview)
* [2. Product Overview](#2-product-overview)
  * [2.1 Product Perspective](#21-product-perspective)
  * [2.2 Product Functions](#22-product-functions)
  * [2.3 Product Constraints](#23-product-constraints)
  * [2.4 User Characteristics](#24-user-characteristics)
  * [2.5 Assumptions and Dependencies](#25-assumptions-and-dependencies)
  * [2.6 Apportioning of Requirements](#26-apportioning-of-requirements)
* [3. Requirements](#3-requirements)
  * [3.1 External Interfaces](#31-external-interfaces)
  * [3.2 Functional](#32-functional)
  * [3.3 Quality of Service](#33-quality-of-service)
  * [3.4 Compliance](#34-compliance)
  * [3.5 Quality of Use](#35-quality-of-use)
* [4. Verification](#4-verification)
* [5. Appendixes](#5-appendixes)
<!-- TOC -->

## 1. Introduction

### 1.1 Document Purpose

This Software Requirements Specification (SRS) defines the requirements for adding a SQLite-based caching system to the ty_symbols.py CLI tool. The primary audience includes developers implementing the caching feature and QA engineers verifying compliance with requirements.

The SRS specifies what the caching system must do (functional behavior) and the quality attributes it must exhibit, without prescribing implementation details.

### 1.2 Product Scope

**Product:** ty_symbols.py CLI tool with LSP Symbol Cache  
**Version:** 1.1.0 (target release)

The ty_symbols.py tool is a command-line interface for exploring Python symbols and references using Language Server Protocol (LSP) via the lsp-client library. This specification covers the addition of a caching system to avoid repeated LSP queries, significantly improving performance for repeated queries on the same codebase state.

**Inclusions:**
- SQLite-based cache storage and retrieval
- Git-based cache invalidation using commit hashes
- Integration with existing `list` and `show` commands
- New `scan` subcommand for pre-populating cache
- Dirty working tree detection and fallback behavior

**Exclusions:**
- Incremental cache updates (deferred to future work)
- Cache sharing across different projects
- LSP server configuration or management

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| CLI | Command-Line Interface - Text-based user interface for running programs |
| Git | Distributed version control system for tracking code changes |
| LSP | Language Server Protocol - Protocol for communication between editors and language servers |
| SQLite | Lightweight, serverless SQL database engine |
| Working Tree | Current state of files in a git repository |
| Dirty Working Tree | Git working tree with uncommitted changes |
| Clean Working Tree | Git working tree with no uncommitted changes |
| Commit Hash | SHA-1 identifier for a specific git commit |

### 1.4 References

| Reference | Type | Description |
|-----------|------|-------------|
| ty_symbols.py source | Informative | Current implementation of the CLI tool |
| lsp-client library documentation | Informative | LSP client library API reference |
| PEP 723 | Normative | Inline script metadata specification |
| SQLite documentation | Informative | SQLite SQL dialect and features |

### 1.5 Document Overview

This document is organized into:
- **Section 2: Product Overview** - Context, functions, constraints, and assumptions
- **Section 3: Requirements** - Functional and non-functional requirements with unique IDs
- **Section 4: Verification** - Methods to validate requirement compliance
- **Section 5: Appendixes** - Supporting materials

Requirements use unique identifiers (REQ-FUNC-001-### for functional, NFR-CAT-001-### for non-functional) to enable traceability.

## 2. Product Overview

### 2.1 Product Perspective

The ty_symbols.py tool is a standalone PEP 723 script that uses the Typer CLI framework to provide symbol exploration capabilities. It integrates with Language Servers (specifically the ty/pyright LSP) via the lsp-client library.

The caching system is a new capability that enhances the existing tool by reducing LSP query overhead for repeated operations on the same codebase state. The cache operates transparently to users, automatically selecting between cached data and live LSP queries based on git working tree state.

**Key relationships:**
- **Upstream:** Git repository (provides commit hash for cache invalidation)
- **Downstream:** LSP server (provides symbol/reference data, bypassed when cache is valid)
- **Peer:** SQLite database file (persists cached data)

### 2.2 Product Functions

The system provides the following major functions:

1. **Cache Storage** - Store symbol and reference data in SQLite database
2. **Cache Retrieval** - Retrieve cached data when valid (clean working tree)
3. **Cache Invalidation** - Detect stale cache using git commit hash
4. **Scan Command** - Pre-populate cache with comprehensive symbol/reference data
5. **Fallback Behavior** - Use live LSP queries when cache is invalid (dirty tree)
6. **User Notification** - Inform users when fallback occurs

### 2.3 Product Constraints

The following constraints shape the system design:

**Technical Constraints:**
- **C-001:** Cache database MUST be stored as `.ty-symbols.db` in the project root directory
- **C-002:** System MUST use existing patterns: Typer CLI, PEP 723 metadata, lsp-client library
- **C-003:** System MUST work with git repositories only (no support for non-git projects)
- **C-004:** Cache invalidation MUST be based on git commit hash, not file modification times

**Operational Constraints:**
- **C-005:** Scanning MUST perform full project scan (not incremental) for each commit
- **C-006:** Dirty working tree MUST trigger fallback to live LSP queries with warning
- **C-007:** System MUST maintain backward compatibility with existing `list` and `show` commands

### 2.4 User Characteristics

The primary users are:

**Python Developers:**
- Technical expertise: High (familiar with CLI tools, git, Python)
- Access level: Read/write access to project repository
- Usage frequency: Multiple times per day during development
- Goals: Quickly explore codebase symbols and references without waiting for LSP queries

**Code Reviewers:**
- Technical expertise: Medium to high
- Access level: Read access to project repository
- Usage frequency: During code review sessions
- Goals: Understand codebase structure and symbol dependencies

### 2.5 Assumptions and Dependencies

**Assumptions:**
- A-001: Users work within git repositories
- A-002: Git is installed and accessible in PATH
- A-003: LSP server (ty/pyright) is properly configured
- A-004: SQLite is available via Python standard library
- A-005: Users understand the trade-off between cache freshness and query speed

**Dependencies:**
- D-001: Git executable must be available
- D-002: Python 3.12+ with sqlite3 module
- D-003: lsp-client library
- D-004: Typer CLI framework
- D-005: Language Server (ty or pyright)

**Impact if assumptions prove false:**
- If A-001 is false: System cannot function (no commit hash for invalidation)
- If A-002 is false: Cache invalidation fails, system falls back to LSP on every query
- If A-003 is false: LSP queries fail regardless of cache state

### 2.6 Apportioning of Requirements

Requirements are allocated to the following components:

| Component | Requirement IDs | Notes |
|-----------|----------------|-------|
| Cache Manager | REQ-FUNC-001-001 to 001-006 | Core cache operations |
| Git Integration | REQ-FUNC-001-007 to 001-009 | Git state detection |
| Scan Command | REQ-FUNC-001-010 to 001-013 | Cache population |
| List Command Integration | REQ-FUNC-001-014 to 001-016 | Cache usage in list |
| Show Command Integration | REQ-FUNC-001-017 to 001-019 | Cache usage in show |

No requirements are deferred to future increments.

## 3. Requirements

### 3.1 External Interfaces

#### 3.1.1 User Interfaces

**CLI Interface:**
The system provides command-line interface through Typer framework.

**Cache-related commands:**
- `scan` - New subcommand for cache population
- `list` - Existing command enhanced with cache integration
- `show` - Existing command enhanced with cache integration

**Output conventions:**
- Progress indicators during scanning
- Warning messages when falling back to LSP
- Success/error messages for cache operations

#### 3.1.2 Hardware Interfaces

No direct hardware interfaces. System runs on standard development workstations.

#### 3.1.3 Software Interfaces

**Git Interface:**
- Purpose: Retrieve commit hash and working tree status
- Protocol: Command-line execution via subprocess
- Data exchanged: Commit hash (SHA-1), working tree status (clean/dirty)

**SQLite Interface:**
- Purpose: Persistent cache storage
- Protocol: Python sqlite3 module
- Data exchanged: Symbol metadata, reference data, commit hash

**LSP Interface (via lsp-client):**
- Purpose: Retrieve symbol and reference data
- Protocol: Language Server Protocol
- Data exchanged: Document symbols, references, hover information

### 3.2 Functional

#### Cache Storage and Retrieval

**REQ-FUNC-001-001: Cache Database Location**
The system SHALL store the cache database as `.ty-symbols.db` in the project root directory.
- Rationale: Constraint C-001
- Verification: Test

**REQ-FUNC-001-002: Cache Schema**
The system SHALL store symbol data including name, kind, location (file, line, column), and associated metadata in the cache database.
- Rationale: Support all data returned by LSP documentSymbol
- Verification: Test

**REQ-FUNC-001-003: Reference Data Storage**
The system SHALL store reference data (locations where symbols are used) in the cache database.
- Rationale: Support reference queries without LSP calls
- Verification: Test

**REQ-FUNC-001-004: Commit Hash Storage**
The system SHALL store the git commit hash with cached data to enable cache validation.
- Rationale: Constraint C-004
- Verification: Test

**REQ-FUNC-001-005: Cache Retrieval**
The system SHALL retrieve cached symbol and reference data when the cache is valid (clean working tree and matching commit hash).
- Rationale: Improve query performance
- Verification: Test, Demonstration

**REQ-FUNC-001-006: Cache Miss Handling**
The system SHALL fall back to live LSP queries when cached data is not available or invalid.
- Rationale: Ensure functionality even without valid cache
- Verification: Test

#### Git Integration

**REQ-FUNC-001-007: Commit Hash Retrieval**
The system SHALL retrieve the current git commit hash from the repository.
- Rationale: Required for cache invalidation (Constraint C-004)
- Verification: Test

**REQ-FUNC-001-008: Working Tree Status Detection**
The system SHALL detect whether the git working tree is clean (no uncommitted changes) or dirty (has uncommitted changes).
- Rationale: Required for fallback decision (Constraint C-006)
- Verification: Test

**REQ-FUNC-001-009: Git Repository Validation**
The system SHALL verify that the project directory is a git repository before attempting cache operations.
- Rationale: Assumption A-001
- Verification: Test

#### Scan Command

**REQ-FUNC-001-010: Scan Command Availability**
The system SHALL provide a `scan` subcommand to pre-populate the cache with symbol and reference data.
- Rationale: Enable proactive cache population
- Verification: Test

**REQ-FUNC-001-011: Full Project Scan**
The system SHALL perform a full scan of all Python files in the project (excluding configured directories) when the `scan` command is executed.
- Rationale: Constraint C-005
- Verification: Test

**REQ-FUNC-001-012: Dirty Tree Scan Prevention**
The system SHALL refuse to scan when the working tree is dirty, unless the `--force` flag is provided.
- Rationale: Prevent caching potentially inconsistent data
- Verification: Test

**REQ-FUNC-001-013: Revision-Specific Scan**
The system SHALL support a `--rev` parameter to scan a specific git revision (commit, branch, or tag).
- Rationale: Enable cache population for different codebase states
- Level: SHOULD
- Verification: Test

#### List Command Integration

**REQ-FUNC-001-014: List Command Cache Usage**
The `list` command SHALL use cached data when available and valid, instead of performing live LSP queries.
- Rationale: Performance improvement for list operations
- Verification: Test, Demonstration

**REQ-FUNC-001-015: List Command Fallback**
The `list` command SHALL fall back to live LSP queries when the cache is invalid or unavailable, and SHALL display a warning message to the user.
- Rationale: Constraint C-006
- Verification: Test

**REQ-FUNC-001-016: List Command No-Cache Option**
The `list` command SHALL support a `--no-cache` flag to bypass the cache and use live LSP queries.
- Rationale: Enable users to force fresh data when needed
- Verification: Test

#### Show Command Integration

**REQ-FUNC-001-017: Show Command Cache Usage**
The `show` command SHALL use cached data when available and valid, instead of performing live LSP queries.
- Rationale: Performance improvement for show operations
- Verification: Test, Demonstration

**REQ-FUNC-001-018: Show Command Fallback**
The `show` command SHALL fall back to live LSP queries when the cache is invalid or unavailable, and SHALL display a warning message to the user.
- Rationale: Constraint C-006
- Verification: Test

**REQ-FUNC-001-019: Show Command No-Cache Option**
The `show` command SHALL support a `--no-cache` flag to bypass the cache and use live LSP queries.
- Rationale: Enable users to force fresh data when needed
- Verification: Test

#### Error Handling and User Communication

**REQ-FUNC-001-020: Warning on Fallback**
The system SHALL display a clear warning message when falling back from cache to live LSP queries due to a dirty working tree.
- Rationale: User awareness of performance impact and cache state
- Verification: Test, Inspection

**REQ-FUNC-001-021: Scan Progress Feedback**
The system SHALL display progress information during the scan operation, showing the number of files processed.
- Rationale: User feedback during potentially long operations
- Verification: Test, Demonstration

**REQ-FUNC-001-022: Error Handling for Git Operations**
The system SHALL handle git command failures gracefully and fall back to live LSP queries with an appropriate error message.
- Rationale: Robustness when git is unavailable or misconfigured
- Verification: Test

### 3.3 Quality of Service

#### 3.3.1 Performance

**NFR-PERF-001-001: Cache Hit Performance**
The system SHALL retrieve cached symbol data in less than 100 milliseconds for projects with up to 1000 symbols.
- Rationale: Significant performance improvement over live LSP queries
- Verification: Test, Analysis

**NFR-PERF-001-002: Cache Miss Overhead**
The system SHALL add no more than 50 milliseconds overhead to detect cache invalidity before falling back to LSP queries.
- Rationale: Minimize performance penalty when cache is not usable
- Verification: Test, Analysis

**NFR-PERF-001-003: Scan Performance**
The scan operation SHALL process at least 10 files per second on standard development hardware.
- Rationale: Acceptable user experience during cache population
- Verification: Test, Demonstration

#### 3.3.2 Reliability

**NFR-REL-001-001: Cache Integrity**
The system SHALL ensure cache database integrity through SQLite transaction support.
- Rationale: Prevent data corruption
- Verification: Test, Analysis

**NFR-REL-001-002: Graceful Degradation**
The system SHALL continue to function correctly when the cache database is corrupted or unavailable, falling back to live LSP queries.
- Rationale: System resilience
- Verification: Test

**NFR-REL-001-003: Concurrent Access Safety**
The system SHALL handle concurrent read access to the cache database safely (SQLite reader-writer locks).
- Rationale: Support multiple terminal sessions or parallel operations
- Verification: Test

#### 3.3.3 Observability

**NFR-OBS-001-001: Cache Status Visibility**
The system SHALL provide visibility into cache status through appropriate CLI output (hit/miss, cache validity).
- Rationale: User understanding of cache behavior
- Verification: Test, Inspection

**NFR-OBS-001-002: Scan Summary**
The scan operation SHALL provide a summary including number of files scanned, symbols found, and references collected.
- Rationale: User confirmation of cache population success
- Verification: Test, Inspection

### 3.4 Compliance

No specific compliance requirements apply to this feature.

### 3.5 Quality of Use

**NFR-USE-001-001: Discoverability**
The `scan` command and cache-related options SHALL be discoverable through the CLI help system.
- Rationale: User awareness of available features
- Verification: Inspection

**NFR-USE-001-002: Transparent Operation**
Cache usage SHALL be transparent to users - existing commands work without modification, with automatic cache integration.
- Rationale: Backward compatibility and ease of use
- Verification: Test, Demonstration

**NFR-USE-001-003: Clear Warning Messages**
Warning messages about cache fallback SHALL be clear, actionable, and explain why the fallback occurred.
- Rationale: User understanding and ability to resolve issues
- Verification: Inspection

## 4. Verification

| Requirement ID | Verification Method | Test/Artifact Link | Status | Evidence |
|----------------|---------------------|--------------------|--------|----------|
| REQ-FUNC-001-001 | Test | tests/test_cache.py::test_cache_location | Planned | |
| REQ-FUNC-001-002 | Test | tests/test_cache.py::test_cache_schema | Planned | |
| REQ-FUNC-001-003 | Test | tests/test_cache.py::test_reference_storage | Planned | |
| REQ-FUNC-001-004 | Test | tests/test_cache.py::test_commit_hash_storage | Planned | |
| REQ-FUNC-001-005 | Test, Demonstration | tests/test_cache.py::test_cache_retrieval | Planned | |
| REQ-FUNC-001-006 | Test | tests/test_cache.py::test_cache_miss | Planned | |
| REQ-FUNC-001-007 | Test | tests/test_git.py::test_commit_hash_retrieval | Planned | |
| REQ-FUNC-001-008 | Test | tests/test_git.py::test_working_tree_status | Planned | |
| REQ-FUNC-001-009 | Test | tests/test_git.py::test_git_validation | Planned | |
| REQ-FUNC-001-010 | Test | tests/test_scan.py::test_scan_command | Planned | |
| REQ-FUNC-001-011 | Test | tests/test_scan.py::test_full_scan | Planned | |
| REQ-FUNC-001-012 | Test | tests/test_scan.py::test_dirty_tree_prevention | Planned | |
| REQ-FUNC-001-013 | Test | tests/test_scan.py::test_rev_specific_scan | Planned | |
| REQ-FUNC-001-014 | Test, Demonstration | tests/test_list.py::test_list_cache_usage | Planned | |
| REQ-FUNC-001-015 | Test | tests/test_list.py::test_list_fallback | Planned | |
| REQ-FUNC-001-016 | Test | tests/test_list.py::test_list_no_cache | Planned | |
| REQ-FUNC-001-017 | Test, Demonstration | tests/test_show.py::test_show_cache_usage | Planned | |
| REQ-FUNC-001-018 | Test | tests/test_show.py::test_show_fallback | Planned | |
| REQ-FUNC-001-019 | Test | tests/test_show.py::test_show_no_cache | Planned | |
| REQ-FUNC-001-020 | Test, Inspection | tests/test_warnings.py::test_fallback_warning | Planned | |
| REQ-FUNC-001-021 | Test, Demonstration | tests/test_scan.py::test_progress_feedback | Planned | |
| REQ-FUNC-001-022 | Test | tests/test_error_handling.py::test_git_failure | Planned | |
| NFR-PERF-001-001 | Test, Analysis | tests/test_performance.py::test_cache_hit_perf | Planned | |
| NFR-PERF-001-002 | Test, Analysis | tests/test_performance.py::test_cache_miss_overhead | Planned | |
| NFR-PERF-001-003 | Test, Demonstration | tests/test_performance.py::test_scan_perf | Planned | |
| NFR-REL-001-001 | Test, Analysis | tests/test_reliability.py::test_cache_integrity | Planned | |
| NFR-REL-001-002 | Test | tests/test_reliability.py::test_graceful_degradation | Planned | |
| NFR-REL-001-003 | Test | tests/test_reliability.py::test_concurrent_access | Planned | |
| NFR-OBS-001-001 | Test, Inspection | tests/test_observability.py::test_cache_status | Planned | |
| NFR-OBS-001-002 | Test, Inspection | tests/test_observability.py::test_scan_summary | Planned | |
| NFR-USE-001-001 | Inspection | Manual: Run `ty_symbols.py --help` | Planned | |
| NFR-USE-001-002 | Test, Demonstration | tests/test_integration.py::test_transparent_operation | Planned | |
| NFR-USE-001-003 | Inspection | Manual: Verify warning message clarity | Planned | |

## 5. Appendixes

### Appendix A: Cache Database Schema

The cache database uses the following logical schema (implementation details in SDD):

**Tables:**
- `cache_metadata` - Stores commit hash and scan timestamp
- `symbols` - Stores symbol information (name, kind, location)
- `references` - Stores reference locations for symbols
- `files` - Stores file metadata for path resolution

### Appendix B: Git Integration Details

**Commands Used:**
- `git rev-parse HEAD` - Get current commit hash
- `git status --porcelain` - Check working tree status
- `git rev-parse --is-inside-work-tree` - Verify git repository

### Appendix C: Performance Baseline

Current performance (without cache):
- `list` command: 5-15 seconds for medium-sized projects (~100 files)
- `show` command: 2-5 seconds per symbol
- Reference queries: Major contributor to latency

Target performance (with cache):
- `list` command: <1 second for cache hits
- `show` command: <100ms for cache hits
- Cache miss overhead: <50ms added latency
