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
- **Breaking:** Parameter entries now use `address:` instead of `id:` for the
  SSM2 address byte. The old key collided with ESPHome's reserved `CONF_ID`
  from `sensor.sensor_schema()` and would have broken codegen.

### Fixed
- SSM2 checksum handling uses 8-bit sum (`sum & 0xFF`) matching protocol expectations.

### Removed
- `components/lin_bus/`, `components/onewire_auto/` and `examples/lin-sniffer.yaml`
  — out of scope for this repo, per `HANDOVER.md`.

## [0.1.0] - 2026-04-13

### Added
- Initial external component scaffold and example configuration.
