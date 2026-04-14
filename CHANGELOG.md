# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `mode` option for `subaru_ssm2` with `normal` and `sniff` variants.
- Sniff-mode buffering and grouped RX hex logging.
- New docs:
  - `README.md` with quickstart and minimal YAML
  - `docs/hardware.md`
  - `docs/loopback_and_sniff.md`
  - `docs/protocol.md`

### Changed
- Improved response diagnostics (status-byte check and richer checksum mismatch logs).
- Example config now includes sniff-mode guidance comment.

### Fixed
- SSM2 checksum handling uses 8-bit sum (`sum & 0xFF`) matching protocol expectations.

## [0.1.0] - 2026-04-13

### Added
- Initial external component scaffold and example configuration.
