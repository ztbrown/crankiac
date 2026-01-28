# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Applied migration 005_add_is_free_column.sql to production database
  - Added `is_free` boolean column to episodes table (default: FALSE)
  - Created partial index `idx_episodes_is_free` for efficient free episode queries

### Added
- Automatic version bump system with commit message conventions
- VERSIONING.md documenting version bump policy
- Version bump script for refinery automation (refinery/bump_version.py)
- Refinery instructions for version management (refinery/REFINERY.md)

## [0.1.0] - 2026-01-28

### Added
- Initial release
- Three-tier web application architecture
- Search API endpoints with fuzzy matching
- Transcript search with word-level timestamps
- Speaker diarization support
- YouTube video sync for free episodes
- On This Day feature
- Patreon integration for episode fetching
- Audio processing pipeline with Whisper transcription
- Unit, integration, and acceptance test suites
