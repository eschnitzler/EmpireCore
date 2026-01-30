# CHANGELOG

<!-- version list -->

## v0.20.0 (2026-01-30)

### Bug Fixes

- Include kingdom_id in castle selection to support outer kingdoms
  ([`3c049b7`](https://github.com/eschnitzler/EmpireCore/commit/3c049b7a27ad59fd435087cde2e12cbe63b5ae41))

- Propagate error_code from Packet to response models
  ([`82c7e1b`](https://github.com/eschnitzler/EmpireCore/commit/82c7e1bf9a75ae8e6b909a3210cfe3e72ff87e2d))

### Features

- Add inventory service and parsing logic
  ([`0d69142`](https://github.com/eschnitzler/EmpireCore/commit/0d69142f61bddbbc09f5eb5b97376eb7bf88ce2c))

- Add VIP time tracking and fix is_premium to check active VIP
  ([`ed8ee85`](https://github.com/eschnitzler/EmpireCore/commit/ed8ee854d972f1565bb7704f8681d554368c4f61))

- Complete SCEItem enum with full inventory mapping
  ([`f7b8b2f`](https://github.com/eschnitzler/EmpireCore/commit/f7b8b2fd78868192f024d300693b45abe7044bc2))

- Implement global inventory (sce) tracking and enums
  ([`f2aea73`](https://github.com/eschnitzler/EmpireCore/commit/f2aea73b3669fe56891f51515938d96c4ec5376f))

### Refactoring

- Remove dcl inventory parsing, rely on global sce state
  ([`42a6aa4`](https://github.com/eschnitzler/EmpireCore/commit/42a6aa4ccb22ac5ea9bf944ae512dfc3859fc8cd))


## v0.19.2 (2026-01-27)

### Bug Fixes

- Network stability, map scanning retries, and protocol model updates
  ([`32e7bff`](https://github.com/eschnitzler/EmpireCore/commit/32e7bff338e5a175c1255b44ca557ed5bf59a37a))

### Chores

- Remove references to other implementations
  ([`225424f`](https://github.com/eschnitzler/EmpireCore/commit/225424fe26136a81a50f4f7e9b8d9fdb73d9d2d2))

- Remove temporary documentation files
  ([`0f04a18`](https://github.com/eschnitzler/EmpireCore/commit/0f04a187359deac0271901421ad2a0250869f9a1))


## v0.19.1 (2026-01-23)

### Bug Fixes

- Reduce keepalive interval to 30s to prevent disconnects
  ([`9b99ec1`](https://github.com/eschnitzler/EmpireCore/commit/9b99ec18b23283a4d52e2b923b2623557b57be29))


## v0.19.0 (2026-01-23)

### Features

- Add get_player_details_bulk for fast player lookup
  ([`cac62dd`](https://github.com/eschnitzler/EmpireCore/commit/cac62dd0f6f628381a2551083092a7a942359029))


## v0.18.0 (2026-01-23)

### Bug Fixes

- Align send_support fields with pygge patterns (add KID, rename LID)
  ([`cc1a57f`](https://github.com/eschnitzler/EmpireCore/commit/cc1a57f6fc1e0d51483aa0d7cabb995d369e5c66))

- Export AllianceBookmark in models init
  ([`b9cdbfe`](https://github.com/eschnitzler/EmpireCore/commit/b9cdbfe69381f9f9ef5e40a0a68dcb994406bbff))

- Update login sequence to match pygge (remove vck, add roundTrip, update CONM)
  ([`be1e0af`](https://github.com/eschnitzler/EmpireCore/commit/be1e0af697299c41d36005ef75c2fbdc9a83be53))

- Use custom TimeoutError in Connection to allow catching in Client
  ([`f3c37a6`](https://github.com/eschnitzler/EmpireCore/commit/f3c37a6c975d6139f227a28ce56be240a6c7699d))

### Features

- Add AllianceBookmark models and service method
  ([`b9cdbfe`](https://github.com/eschnitzler/EmpireCore/commit/b9cdbfe69381f9f9ef5e40a0a68dcb994406bbff))

- Add Birding capabilities (Army, Lords, Alliance Search)
  ([`0cbcac9`](https://github.com/eschnitzler/EmpireCore/commit/0cbcac92c2d013741cb374afa46fde2eb6278683))

- Enhance send_support with full protocol parameters from pygge
  ([`cc1a57f`](https://github.com/eschnitzler/EmpireCore/commit/cc1a57f6fc1e0d51483aa0d7cabb995d369e5c66))


## v0.17.1 (2026-01-11)

### Bug Fixes

- Change library logging from INFO to DEBUG
  ([`b31a461`](https://github.com/eschnitzler/EmpireCore/commit/b31a461d07f782f92a278f12107560deb3a06aef))


## v0.17.0 (2026-01-11)

### Features

- Add alliance search (hgh command)
  ([`9629811`](https://github.com/eschnitzler/EmpireCore/commit/9629811bf3a334d872dfafb83f045e3b9ed5967f))


## v0.16.0 (2026-01-11)

### Bug Fixes

- Revert version for semantic-release
  ([`8e8e35f`](https://github.com/eschnitzler/EmpireCore/commit/8e8e35fa9e947d66d633c834f28b410d7fa2b70d))

- Rewrite scan_kingdom with sequential request/response
  ([`37fc924`](https://github.com/eschnitzler/EmpireCore/commit/37fc924709b48a26ab8fce7fef624d619d76c291))

- Wait for gbd packet after login to populate player state
  ([`3057b5e`](https://github.com/eschnitzler/EmpireCore/commit/3057b5ee6fa9b0315ab4d4fa76ed832691d65e25))

### Features

- Add Kingdom enum and alliance tracking support
  ([`0b6a4d4`](https://github.com/eschnitzler/EmpireCore/commit/0b6a4d49484df1f8072e7d2b1f202386ac712ac3))

- Add scan_kingdom with BFS wave expansion
  ([`d14af84`](https://github.com/eschnitzler/EmpireCore/commit/d14af846b739cd99497f7840f06ca165ceda90a6))


## v0.15.0 (2026-01-11)

### Features

- Expose raw commander data in movements
  ([`f461d49`](https://github.com/eschnitzler/EmpireCore/commit/f461d49790b9477a033c04bc89cf295c1464795a))


## v0.14.0 (2026-01-10)

### Features

- Dispatch on_incoming_attack callback for movement updates
  ([`db39eda`](https://github.com/eschnitzler/EmpireCore/commit/db39eda257edda791d94b6102b098ab9544f7765))


## v0.13.0 (2026-01-10)

### Features

- Add activity_tier property to AllianceMember for tiered offline status
  ([`cd67fae`](https://github.com/eschnitzler/EmpireCore/commit/cd67fae55bfa78bc81fc7b92a7202975b3fb071b))

### Breaking Changes

- _online property replaced with _activity_tier


## v0.11.0 (2026-01-08)

### Features

- Add no_cache option to get_member() for fresh data
  ([`ba26735`](https://github.com/eschnitzler/EmpireCore/commit/ba2673566585be33bc9134e6c526d9752704c6e5))


## v0.10.1 (2026-01-08)

### Refactoring

- Rename get_my_* to get_local_* for consistency
  ([`75caebd`](https://github.com/eschnitzler/EmpireCore/commit/75caebdceeb62578ff97af013600d9959df72107))


## v0.10.0 (2026-01-08)

### Features

- Add convenience methods for local player's alliance data
  ([`0de1e9a`](https://github.com/eschnitzler/EmpireCore/commit/0de1e9a25bbeb104ce1cbd4d6290c647ea297b46))


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
