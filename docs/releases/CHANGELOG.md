# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versioning: [SemVer](https://semver.org).
Newest first. Every line cites the IDs it moved — see `DOCS-CONVENTIONS.md` §6.

## [Unreleased]

### Added

- Context header on every chunk, apart from its text: `python -m src.enrich` writes
  `data/enriched/chunks.jsonl`; chunks and articles carry `chapter_title`. FR-CORE-003, AC-003,
  ADR-0001.

### Changed

### Deprecated

### Removed

### Fixed
