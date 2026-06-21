# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `mode` option for `subaru_ssm2` with `normal` and `sniff` variants.
- Sniff-mode buffering and grouped RX hex logging.
- GitHub Actions CI (`.github/workflows/ci.yaml`): `esphome config` plus a real
  `esphome compile`, driven by `tests/test-minimal.yaml` against the local
  sources.
- `examples/minimal.yaml`: clean minimal starting point (no personal network
  topology).
- New docs:
  - `README.md` with quickstart and minimal YAML
  - `docs/hardware.md`
  - `docs/loopback_and_sniff.md`
  - `docs/protocol.md` (now also covers multi-byte reads, length-byte
    semantics and K-line echo)

### Changed
- Multi-byte parameters (RPM, MAP, MAF, boost …) are now requested via N
  consecutive 3-byte addresses in one `0xA8` frame (one byte per address),
  instead of a single address that could never return more than one byte.
- Response handling is now an incremental frame parser driven by the frame's
  own length field; it scans for the ECU header `80 F0 10` and therefore skips
  the half-duplex request echo and tolerates trailing bytes.
- Improved response diagnostics (status-byte check and richer checksum mismatch logs).
- Trimmed unused `device_class`/`state_class` fields from the internal
  `SSM2Parameter` table (presentation comes from YAML).
- Example config now includes sniff-mode guidance comment.
- **Breaking:** Parameter entries now use `address:` instead of `id:` for the
  SSM2 address byte. The old key collided with ESPHome's reserved `CONF_ID`
  from `sensor.sensor_schema()` and would have broken codegen.

### Fixed
- `AUTO_LOAD` now includes `binary_sensor`; configs without a separate
  binary_sensor platform (e.g. the README minimal example) previously failed
  to compile because `subaru_ssm2.h` includes `binary_sensor.h`.
- Removed the off-by-one in the response-length expectation (it assumed a
  5-byte header; SSM2 uses 4) that could make exact-length responses time out
  and be discarded.
- Guarded signed sign-extension against 32-bit shift UB for 4-byte values.
- SSM2 checksum handling uses 8-bit sum (`sum & 0xFF`) matching protocol expectations.

### Removed
- `components/lin_bus/`, `components/onewire_auto/` and `examples/lin-sniffer.yaml`
  — out of scope for this repo, per `HANDOVER.md`.

## [0.1.0] - 2026-04-13

### Added
- Initial external component scaffold and example configuration.
