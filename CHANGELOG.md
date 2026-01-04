# CHANGELOG

<!-- version list -->

## v0.4.0 (2026-01-04)

### Bug Fixes

- Use dynamic version from package metadata
  ([`c09a706`](https://github.com/eschnitzler/EmpireCore/commit/c09a70661bc1f110a260bf599aa22b781b2bc0d6))

### Features

- Add troop filtering, alliance names, and recall detection
  ([`803ac07`](https://github.com/eschnitzler/EmpireCore/commit/803ac079a682528dc6339e0efd8d2d8cf021c26c))


## v0.3.1 (2026-01-04)

### Bug Fixes

- Use dynamic version from package metadata ([#4](https://github.com/eschnitzler/EmpireCore/pull/4),
  [`4efe3d5`](https://github.com/eschnitzler/EmpireCore/commit/4efe3d51cbc0d8fc0b2ae69190205ed3c9b3434f))


## v0.3.0 (2026-01-04)

### Bug Fixes

- **cd**: Pass built artifacts from release job to publish job
  ([#3](https://github.com/eschnitzler/EmpireCore/pull/3),
  [`615483d`](https://github.com/eschnitzler/EmpireCore/commit/615483d71c6a879f6f06b8f7036ef58fbf3542d6))

- **cd**: Trigger release on push to master instead of CI workflow_run
  ([#3](https://github.com/eschnitzler/EmpireCore/pull/3),
  [`615483d`](https://github.com/eschnitzler/EmpireCore/commit/615483d71c6a879f6f06b8f7036ef58fbf3542d6))

- **cd**: Use no-commit mode for semantic-release to work with branch protection
  ([#3](https://github.com/eschnitzler/EmpireCore/pull/3),
  [`615483d`](https://github.com/eschnitzler/EmpireCore/commit/615483d71c6a879f6f06b8f7036ef58fbf3542d6))

- **cd**: Use RELEASE_TOKEN PAT for semantic-release
  ([#3](https://github.com/eschnitzler/EmpireCore/pull/3),
  [`615483d`](https://github.com/eschnitzler/EmpireCore/commit/615483d71c6a879f6f06b8f7036ef58fbf3542d6))

- **ci**: Align job names with branch protection rules
  ([#2](https://github.com/eschnitzler/EmpireCore/pull/2),
  [`0957f15`](https://github.com/eschnitzler/EmpireCore/commit/0957f15ed3580334f88d3019504b8dfcd11d8ad6))

- **ci**: Only run CI on pull requests ([#3](https://github.com/eschnitzler/EmpireCore/pull/3),
  [`615483d`](https://github.com/eschnitzler/EmpireCore/commit/615483d71c6a879f6f06b8f7036ef58fbf3542d6))

- **ci**: Only run CI on pull requests, not on merge to master
  ([#3](https://github.com/eschnitzler/EmpireCore/pull/3),
  [`615483d`](https://github.com/eschnitzler/EmpireCore/commit/615483d71c6a879f6f06b8f7036ef58fbf3542d6))

### Chores

- Remove stale documentation and empty test ([#2](https://github.com/eschnitzler/EmpireCore/pull/2),
  [`0957f15`](https://github.com/eschnitzler/EmpireCore/commit/0957f15ed3580334f88d3019504b8dfcd11d8ad6))

### Features

- Add protocol models and service layer ([#2](https://github.com/eschnitzler/EmpireCore/pull/2),
  [`0957f15`](https://github.com/eschnitzler/EmpireCore/commit/0957f15ed3580334f88d3019504b8dfcd11d8ad6))

- Add service layer with auto-registration ([#2](https://github.com/eschnitzler/EmpireCore/pull/2),
  [`0957f15`](https://github.com/eschnitzler/EmpireCore/commit/0957f15ed3580334f88d3019504b8dfcd11d8ad6))

- **protocol**: Add Pydantic models for GGE protocol commands
  ([#2](https://github.com/eschnitzler/EmpireCore/pull/2),
  [`0957f15`](https://github.com/eschnitzler/EmpireCore/commit/0957f15ed3580334f88d3019504b8dfcd11d8ad6))

### Performance Improvements

- Optimize packet dispatch for high message volume
  ([#2](https://github.com/eschnitzler/EmpireCore/pull/2),
  [`0957f15`](https://github.com/eschnitzler/EmpireCore/commit/0957f15ed3580334f88d3019504b8dfcd11d8ad6))


## v0.2.1 (2026-01-04)

### Bug Fixes

- Ensure publish job gets latest version after semantic-release bump
  ([`272e3c3`](https://github.com/eschnitzler/EmpireCore/commit/272e3c3f38694da164af65b39d30f75a7dc582b0))

- Exclude _archive from pytest collection
  ([`2ba8b8c`](https://github.com/eschnitzler/EmpireCore/commit/2ba8b8cce5f51f8939831c2eb393c3ce56a19528))

- Require env vars for credentials in examples
  ([`cf005e3`](https://github.com/eschnitzler/EmpireCore/commit/cf005e34c179455abce766130cfcb50f5ecea8c2))

- Resolve CI failures by archiving old async code and fixing type errors
  ([`a514161`](https://github.com/eschnitzler/EmpireCore/commit/a51416187e9b59b87eead37f2a988d5b6fb369b9))

### Code Style

- Auto-fix ruff lint errors
  ([`3483e3e`](https://github.com/eschnitzler/EmpireCore/commit/3483e3e56e514ecb047ab8c1560658568c9fa7c7))

### Refactoring

- Replace async architecture with sync + threading
  ([`67315c6`](https://github.com/eschnitzler/EmpireCore/commit/67315c6699d580305cafe8cc5e165039ccb3cc4b))


## v0.2.0 (2025-12-31)

### Features

- Add send_support and get_bookmarks actions for troop birding
  ([`5a14466`](https://github.com/eschnitzler/EmpireCore/commit/5a1446660d5d112aec7c1866f15a514551907451))


## v0.1.0 (2025-12-29)

- Initial Release
