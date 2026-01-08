# CHANGELOG

<!-- version list -->

## v0.9.0 (2026-01-08)

### Features

- Add alliance info command (ain) with member online status
  ([`fcc9977`](https://github.com/eschnitzler/EmpireCore/commit/fcc9977580d05144cd8ff8e4a818a3a8f8caf710))


## v0.8.0 (2026-01-06)

### Features

- Add on_movement_arrived callback and change recall/arrived to pass MID only
  ([`6e8084d`](https://github.com/eschnitzler/EmpireCore/commit/6e8084dc949596a3813004179476635c6e4086c2))


## v0.7.3 (2026-01-06)

### Bug Fixes

- Don't remove movements in gam handler, wait for arrival/recall packets
  ([`0b5d49f`](https://github.com/eschnitzler/EmpireCore/commit/0b5d49f5ba2cc52860544fe2e463475046dca88a))


## v0.7.2 (2026-01-06)

### Bug Fixes

- Use mrm packet for recall detection, not maa
  ([`6c8c461`](https://github.com/eschnitzler/EmpireCore/commit/6c8c46101bb65fe995725b17da1b99568087f951))


## v0.7.1 (2026-01-06)

### Bug Fixes

- Detect recalls via maa packet instead of gam comparison
  ([`82ed870`](https://github.com/eschnitzler/EmpireCore/commit/82ed8708b6aae0134e4c65ef2d62d4d1fea93e3e))


## v0.7.0 (2026-01-06)

### Features

- Add estimated_size field to Movement for non-visible armies
  ([`23fed4d`](https://github.com/eschnitzler/EmpireCore/commit/23fed4d0a10c33bcb1ab1244327dba767f3d1647))


## v0.6.6 (2026-01-06)

### Bug Fixes

- Handle GS as int and SA as int in gam/gal packets
  ([`51855ae`](https://github.com/eschnitzler/EmpireCore/commit/51855ae13f34bc8390e45f96889a73df4e9a2ca3))


## v0.6.5 (2026-01-06)

### Bug Fixes

- Coerce SA field to string in Alliance model
  ([`b6b23aa`](https://github.com/eschnitzler/EmpireCore/commit/b6b23aa459ff2e0d0fb223a3dba5e4c5eb8a5b80))

### Chores

- Add info-level logging for SDI debugging
  ([`faf9564`](https://github.com/eschnitzler/EmpireCore/commit/faf95645810ef7be1d7673439e60669da00b18e3))


## v0.6.4 (2026-01-06)

### Bug Fixes

- Handle lli packet for alliance info + add debug logging
  ([`7cdb545`](https://github.com/eschnitzler/EmpireCore/commit/7cdb545bfbf870a92c162c62ebe899481f1ef339))


## v0.6.3 (2026-01-06)

### Bug Fixes

- Dispatch callbacks in thread pool to avoid blocking receive loop
  ([`a30562f`](https://github.com/eschnitzler/EmpireCore/commit/a30562f172d409bae74ba1cd645bbfa780bfa9d7))


## v0.6.2 (2026-01-06)

### Bug Fixes

- Get_max_defense returns yard_limit only (includes support capacity)
  ([`22c9fdc`](https://github.com/eschnitzler/EmpireCore/commit/22c9fdc7788cf920b6cbab63355e43331a1ba774))


## v0.6.1 (2026-01-06)

### Bug Fixes

- Correct castle coordinate parsing from lli response
  ([`db057d1`](https://github.com/eschnitzler/EmpireCore/commit/db057d10cbfd4a5692c5731b8963945c4245bbe6))


## v0.6.0 (2026-01-05)

### Features

- Add defense capacity limits (yard_limit, wall_limit) to SDI response
  ([`ec886df`](https://github.com/eschnitzler/EmpireCore/commit/ec886dfbfd588a90dd4b9f82b653acfc38c05a47))


## v0.5.0 (2026-01-05)

### Features

- Add SDI (Support Defense Info) command for querying alliance castle defense
  ([`abcc58d`](https://github.com/eschnitzler/EmpireCore/commit/abcc58d4855849991bbb923e98d9525216be487b))


## v0.4.5 (2026-01-05)

### Bug Fixes

- Extract GA units from wrapper level, not inside UM
  ([`d645968`](https://github.com/eschnitzler/EmpireCore/commit/d6459687b1e1c43cc5c49156ec6ed06d914ca107))


## v0.4.4 (2026-01-05)

### Bug Fixes

- Parse GA (Garrison Army) units from movement wrapper
  ([`83ff404`](https://github.com/eschnitzler/EmpireCore/commit/83ff40424ad583c324d8790616cac5e81de25eb4))

### Chores

- Bump version to 0.4.4
  ([`6f14f68`](https://github.com/eschnitzler/EmpireCore/commit/6f14f6867546550751cdad4df0073df3176d253b))


## v0.4.2 (2026-01-05)

### Bug Fixes

- Include T=0 as attack movement type
  ([`1b4b219`](https://github.com/eschnitzler/EmpireCore/commit/1b4b219add109c7500a6124cbf9b7c828ea2ddce))


## v0.4.1 (2026-01-05)

### Bug Fixes

- Trigger attack callback for all attacks, not just incoming
  ([`0592812`](https://github.com/eschnitzler/EmpireCore/commit/0592812aecd74fff39ddc37e152dc9fe60c39c68))


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
