# CHANGELOG

<!-- version list -->

## v0.41.0 (2026-09-30)

### Bug Fixes

- **alliance**: Read the alliance chat log from CM as the client does
  ([#235](https://github.com/eschnitzler/EmpireCore/pull/235),
  [`c28e42e`](https://github.com/eschnitzler/EmpireCore/commit/c28e42ef087ce772cf8e3b9ef864ba6562acd0c9))

- **army**: Read RUT arrays and odd gcu values as the client does, and keep bup off the hospital
  ([#218](https://github.com/eschnitzler/EmpireCore/pull/218),
  [`c665907`](https://github.com/eschnitzler/EmpireCore/commit/c665907d0fda08acbb30cfee3a70a403dd7957c3))

- **army**: Send army and hospital commands as the client's command objects do
  ([#218](https://github.com/eschnitzler/EmpireCore/pull/218),
  [`c665907`](https://github.com/eschnitzler/EmpireCore/commit/c665907d0fda08acbb30cfee3a70a403dd7957c3))

- **attack**: Keep cra owner records by the client's truthiness of OID
  ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- **attack**: Require the commander on CreateAttackRequest
  ([#220](https://github.com/eschnitzler/EmpireCore/pull/220),
  [`c4d5791`](https://github.com/eschnitzler/EmpireCore/commit/c4d5791e3ad94336d467962f28381e79bafbcca5))

- **castle**: Keep a listed castle without a name, and leave out quietly the rows that name no
  castle ([#230](https://github.com/eschnitzler/EmpireCore/pull/230),
  [`fbc8b75`](https://github.com/eschnitzler/EmpireCore/commit/fbc8b75e51547062730cc75bfb2db76c90f3de2a))

- **castle,movements**: Send arc in the client's order and encoding, and gam with no castle
  ([#215](https://github.com/eschnitzler/EmpireCore/pull/215),
  [`aae83e4`](https://github.com/eschnitzler/EmpireCore/commit/aae83e414e44efca3f1d2c2ee2a6a9185ebef6c6))

- **enums**: Drop enum members the client does not define
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- **enums**: Make the enums match the client's constants
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- **gamedata**: A league row without an event id matches no event
  ([#228](https://github.com/eschnitzler/EmpireCore/pull/228),
  [`a755b53`](https://github.com/eschnitzler/EmpireCore/commit/a755b53df62f48ce50ccd6acc9fe8ed827df4497))

- **gamedata**: Give falsy values the client's default, and read the new tables with parseInt
  ([#219](https://github.com/eschnitzler/EmpireCore/pull/219),
  [`79957ed`](https://github.com/eschnitzler/EmpireCore/commit/79957ed0ad310f9b15dc6daeec5817ac4dad9490))

- **gamedata**: Keep a cached level of 0 instead of reading it as missing
  ([#224](https://github.com/eschnitzler/EmpireCore/pull/224),
  [`825b77f`](https://github.com/eschnitzler/EmpireCore/commit/825b77fb57d5b0904447560b1d5a079193c8bc77))

- **gamedata**: Load the default game data once, and back off after a failed load
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Load the id enums lazily, and guard the generator against the cache file
  ([#224](https://github.com/eschnitzler/EmpireCore/pull/224),
  [`825b77f`](https://github.com/eschnitzler/EmpireCore/commit/825b77fb57d5b0904447560b1d5a079193c8bc77))

- **gamedata**: Name researches and construction items by group and level, and report name changes
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Quote generated strings the way ruff format does
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Raise a remembered load failure without its old traceback, and open the ids PR when
  the branch is already pushed ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Read unit and tool rows with the client's keys, types and defaults
  ([#219](https://github.com/eschnitzler/EmpireCore/pull/219),
  [`79957ed`](https://github.com/eschnitzler/EmpireCore/commit/79957ed0ad310f9b15dc6daeec5817ac4dad9490))

- **models**: Build rst and csm as the client does
  ([#230](https://github.com/eschnitzler/EmpireCore/pull/230),
  [`fbc8b75`](https://github.com/eschnitzler/EmpireCore/commit/fbc8b75e51547062730cc75bfb2db76c90f3de2a))

- **models**: Read each castle list row by its area type's layout
  ([#230](https://github.com/eschnitzler/EmpireCore/pull/230),
  [`fbc8b75`](https://github.com/eschnitzler/EmpireCore/commit/fbc8b75e51547062730cc75bfb2db76c90f3de2a))

- **protocol**: Read an int too large for a JS number as none, and say where the row readers are
  more lenient than the client ([#235](https://github.com/eschnitzler/EmpireCore/pull/235),
  [`c28e42e`](https://github.com/eschnitzler/EmpireCore/commit/c28e42ef087ce772cf8e3b9ef864ba6562acd0c9))

- **protocol**: Read the refer-a-friend flag through parseInt, and warn only on unreadable rows
  ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- **ranking**: Take the highscore list types from the client, and call LID the league type id
  ([#228](https://github.com/eschnitzler/EmpireCore/pull/228),
  [`a755b53`](https://github.com/eschnitzler/EmpireCore/commit/a755b53df62f48ce50ccd6acc9fe8ed827df4497))

- **spy**: Check a caught report's position too, and take the payment options by keyword
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **spy**: Pay for a spy mission only when asked
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **spy**: Read the csm reply's movement from A as the client does
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **spy**: Wait for this mission's own report, and name the paid options as the other senders do
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **spy,defense**: Fix what a live run of the stack found
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **types**: Key the camp offset and landmark level tables by their enums
  ([#225](https://github.com/eschnitzler/EmpireCore/pull/225),
  [`47deee9`](https://github.com/eschnitzler/EmpireCore/commit/47deee9d5d89056303159825041639de8737d3ef))

### Build System

- **release**: List every breaking change in the changelog and release notes
  ([#232](https://github.com/eschnitzler/EmpireCore/pull/232),
  [`510c220`](https://github.com/eschnitzler/EmpireCore/commit/510c2200a92584660a75b8415aaf21a69865be98))

### Documentation

- Describe the research names and the name-change list
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- Keep client references out of Flank's summary and spy_type's description
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- Name where every runtime id input comes from, and require the attack commander
  ([#220](https://github.com/eschnitzler/EmpireCore/pull/220),
  [`c4d5791`](https://github.com/eschnitzler/EmpireCore/commit/c4d5791e3ad94336d467962f28381e79bafbcca5))

- **gamedata**: Say which columns the id enum members keep, and that GameData keeps the raw rows of
  the id tables ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Show GameData.record in the GameData docstring and the README imports
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **models**: Describe where each request's runtime ids come from
  ([#220](https://github.com/eschnitzler/EmpireCore/pull/220),
  [`c4d5791`](https://github.com/eschnitzler/EmpireCore/commit/c4d5791e3ad94336d467962f28381e79bafbcca5))

- **models**: Keep field descriptions to what each field is
  ([#225](https://github.com/eschnitzler/EmpireCore/pull/225),
  [`47deee9`](https://github.com/eschnitzler/EmpireCore/commit/47deee9d5d89056303159825041639de8737d3ef))

- **models**: Say where castle resources come from, and point building ids at BuildResponse
  ([#225](https://github.com/eschnitzler/EmpireCore/pull/225),
  [`47deee9`](https://github.com/eschnitzler/EmpireCore/commit/47deee9d5d89056303159825041639de8737d3ef))

- **ranking**: Say llsp's LID is the event's league, or -1
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **ranking,alliance**: Say llsp pages event leaderboards and that the server answers acl
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **services**: Name the call that returns each runtime id a method takes
  ([#220](https://github.com/eschnitzler/EmpireCore/pull/220),
  [`c4d5791`](https://github.com/eschnitzler/EmpireCore/commit/c4d5791e3ad94336d467962f28381e79bafbcca5))

### Features

- **defense**: Read your own castle's defense with dfc, and name sdi for support
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **enums**: Add Flank.REINFORCEMENT_SUMMARY and cite the client's constants
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- **enums**: Type attack, spy, castle and map inputs with the client's constants
  ([#216](https://github.com/eschnitzler/EmpireCore/pull/216),
  [`675b87f`](https://github.com/eschnitzler/EmpireCore/commit/675b87ffa5c274a1945339094ddc2713892658da))

- **enums**: Type finite inputs with the client's constants
  ([#216](https://github.com/eschnitzler/EmpireCore/pull/216),
  [`675b87f`](https://github.com/eschnitzler/EmpireCore/commit/675b87ffa5c274a1945339094ddc2713892658da))

- **gamedata**: Carry each id's fixed data and link it to the loaded game data
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Generate enums for buildings, researches, construction items, events and more
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Generate id enums from the items data
  ([#224](https://github.com/eschnitzler/EmpireCore/pull/224),
  [`825b77f`](https://github.com/eschnitzler/EmpireCore/commit/825b77fb57d5b0904447560b1d5a079193c8bc77))

- **gamedata**: Give the id enums their rows' fixed data, and look full records up on GameData
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **gamedata**: Look up game-data rows by their unique keys
  ([#217](https://github.com/eschnitzler/EmpireCore/pull/217),
  [`90fe2d3`](https://github.com/eschnitzler/EmpireCore/commit/90fe2d37bf0341566cb812412c735a8c5c748419))

### Refactoring

- Consolidate duplicated helpers ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- Import models from their area packages and move the enums up
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Merge the commander services into commanders.service
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Move models and services into per-area packages (renames only)
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Move the owner records from movements to map.models.owners
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Name currency 1 and 2 coins and rubies
  ([#227](https://github.com/eschnitzler/EmpireCore/pull/227),
  [`e1a20f3`](https://github.com/eschnitzler/EmpireCore/commit/e1a20f386c2648537f3e65507bae44799a3c3c32))

- Organise the library by game area ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Split the alliance models into info, help and search
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Split the army models into units, production and hospital
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Split the attack models by command group, waves to army, spy commands to spy
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Split the castle models into castles, details and actions
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Split the equipment models out of the commander roster
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Split the map models into items and areas
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Take Kingdom, not Kingdom | int, and build the touched models to spec
  ([#230](https://github.com/eschnitzler/EmpireCore/pull/230),
  [`fbc8b75`](https://github.com/eschnitzler/EmpireCore/commit/fbc8b75e51547062730cc75bfb2db76c90f3de2a))

- **alliance**: Drop the chat helpers that duplicate AllianceService
  ([#234](https://github.com/eschnitzler/EmpireCore/pull/234),
  [`8f0bd0a`](https://github.com/eschnitzler/EmpireCore/commit/8f0bd0ac51a4901cd9a6923742a5115c7f7a2ee4))

- **castle**: Type the jca and arc kingdom and area type inputs, and describe jca
  ([#216](https://github.com/eschnitzler/EmpireCore/pull/216),
  [`675b87f`](https://github.com/eschnitzler/EmpireCore/commit/675b87ffa5c274a1945339094ddc2713892658da))

- **client**: Reach the area helpers through their services
  ([#234](https://github.com/eschnitzler/EmpireCore/pull/234),
  [`8f0bd0a`](https://github.com/eschnitzler/EmpireCore/commit/8f0bd0ac51a4901cd9a6923742a5115c7f7a2ee4))

- **combat**: Name effect types with CombatEffectType
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- **enums**: Keep every enum in the utils.enums package
  ([#222](https://github.com/eschnitzler/EmpireCore/pull/222),
  [`af04c1d`](https://github.com/eschnitzler/EmpireCore/commit/af04c1d3ed9a6de4636fb7b66eca84b3605d062d))

- **enums**: One enum per id space, with WearerType as the client has it
  ([#216](https://github.com/eschnitzler/EmpireCore/pull/216),
  [`675b87f`](https://github.com/eschnitzler/EmpireCore/commit/675b87ffa5c274a1945339094ddc2713892658da))

- **enums**: Spell members as the client does where only the spelling differed
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- **gamedata**: Drop the implicit game data behind the id enums, and look records up on GameData
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- **map**: Type the client the map scanner uses
  ([#234](https://github.com/eschnitzler/EmpireCore/pull/234),
  [`8f0bd0a`](https://github.com/eschnitzler/EmpireCore/commit/8f0bd0ac51a4901cd9a6923742a5115c7f7a2ee4))

- **models**: Compare with enums instead of raw ids and labels
  ([#223](https://github.com/eschnitzler/EmpireCore/pull/223),
  [`37bb461`](https://github.com/eschnitzler/EmpireCore/commit/37bb4618266ca770b93e97c682353a1eb1ff2fd0))

- **models**: Drop the hand-written location type names
  ([#230](https://github.com/eschnitzler/EmpireCore/pull/230),
  [`fbc8b75`](https://github.com/eschnitzler/EmpireCore/commit/fbc8b75e51547062730cc75bfb2db76c90f3de2a))

- **models**: Share the gcu model, type the army replies with it, and drop ProductionListType
  ([#218](https://github.com/eschnitzler/EmpireCore/pull/218),
  [`c665907`](https://github.com/eschnitzler/EmpireCore/commit/c665907d0fda08acbb30cfee3a70a403dd7957c3))

- **models**: Skip unreadable rows and blocks with one set of helpers
  ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- **movements**: Move the tracked Movement into the movements area
  ([#234](https://github.com/eschnitzler/EmpireCore/pull/234),
  [`8f0bd0a`](https://github.com/eschnitzler/EmpireCore/commit/8f0bd0ac51a4901cd9a6923742a5115c7f7a2ee4))

- **protocol**: Encode and decode text only as the client does
  ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- **protocol**: Keep the client's JavaScript conversions in one module
  ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- **services**: Look an own castle up in the state in one place
  ([#226](https://github.com/eschnitzler/EmpireCore/pull/226),
  [`7db5537`](https://github.com/eschnitzler/EmpireCore/commit/7db5537e3bf3881c370474bd072e034704d593ad))

- **types**: Take Kingdom, not Kingdom | int
  ([#230](https://github.com/eschnitzler/EmpireCore/pull/230),
  [`fbc8b75`](https://github.com/eschnitzler/EmpireCore/commit/fbc8b75e51547062730cc75bfb2db76c90f3de2a))

### Testing

- Enforce the area layering, and point the docs at the new layout
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- Forget the default game data after every test
  ([#231](https://github.com/eschnitzler/EmpireCore/pull/231),
  [`266e006`](https://github.com/eschnitzler/EmpireCore/commit/266e00655f28518eec18741a70032aa855854755))

- Mirror the area packages in the test tree
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- **attack**: Give the cra enum test its commander so it can fail
  ([#220](https://github.com/eschnitzler/EmpireCore/pull/220),
  [`c4d5791`](https://github.com/eschnitzler/EmpireCore/commit/c4d5791e3ad94336d467962f28381e79bafbcca5))

- **gamedata**: Keep CombatEffectType's ids within the generated EffectType
  ([#224](https://github.com/eschnitzler/EmpireCore/pull/224),
  [`825b77f`](https://github.com/eschnitzler/EmpireCore/commit/825b77fb57d5b0904447560b1d5a079193c8bc77))

- **gamedata**: Read row models out of generic annotations on Python 3.10
  ([#217](https://github.com/eschnitzler/EmpireCore/pull/217),
  [`90fe2d3`](https://github.com/eschnitzler/EmpireCore/commit/90fe2d37bf0341566cb812412c735a8c5c748419))

- **map**: Watch the map areas logger that reports skipped area rows
  ([#233](https://github.com/eschnitzler/EmpireCore/pull/233),
  [`0c4ad8f`](https://github.com/eschnitzler/EmpireCore/commit/0c4ad8f0451131e033015055b7d8f050fb4e1d9f))

- **spy**: Make the owner record's level, might, achievement points and crest colours up
  ([#236](https://github.com/eschnitzler/EmpireCore/pull/236),
  [`a76006b`](https://github.com/eschnitzler/EmpireCore/commit/a76006bf12e0b2d78b70ce986a871e9f9ec73bdc))

- **state**: Name the no-gcu test after coins and rubies
  ([#227](https://github.com/eschnitzler/EmpireCore/pull/227),
  [`e1a20f3`](https://github.com/eschnitzler/EmpireCore/commit/e1a20f386c2648537f3e65507bae44799a3c3c32))

### Breaking Changes

- Deep module paths moved. Import from empire_core, empire_core.protocol.models or the area packages
  instead. Removed paths, with where their contents live after this series:

- Renamed public names: AutoSkipCooldownType.C2 -> AutoSkipCooldownType.RUBIES;
  UnitStats.healing_cost_c1 -> healing_cost_coins; UnitStats.healing_cost_c2 -> healing_cost_rubies;
  AttackSlotDef.cost_c2 -> cost_rubies; FillOptions.allow_c1_cost -> allow_coin_cost;
  FillOptions.allow_c2_cost -> allow_ruby_cost; CurrencyTotals.gold -> coins; Player.gold -> coins;
  PlayerSnapshot.gold -> coins (sqlite column player_snapshots.gold -> coins);
  AllianceMemberInfo.given_c1 -> given_coins; AllianceMemberInfo.given_c2 -> given_rubies;
  AllianceStorage.coins1 -> coins, coins2 -> rubies, food -> oil, gold -> glass, coins -> coal;
  GGEError.NOT_ENOUGH_CURRENCY1 -> NOT_ENOUGH_COINS; GGEError.NOT_ENOUGH_CURRENCY2 ->
  NOT_ENOUGH_RUBIES; GGEError.ALLI_NOT_ENOUGH_C1 -> ALLI_NOT_ENOUGH_COINS;
  GGEError.ALLI_NOT_ENOUGH_C2 -> ALLI_NOT_ENOUGH_RUBIES; GGEError.WRONG_AMOUNT_OF_BOUGHT_C2 ->
  WRONG_AMOUNT_OF_BOUGHT_RUBIES; GGEError.C2_CONFIRMATION_REQUIRED -> RUBY_CONFIRMATION_REQUIRED

- **alliance**: ChatLogEntry is removed; AllianceChatLogResponse.chat_log and
  AllianceService.get_chat_log now hold ChatMessageData, which has no timestamp field (use
  age_seconds). chat_log reads the "CM" key, not "CL". ChatMessageData's PID, PN and MT are no
  longer required: missing ones read as 0 and "".

- **army**: Army request fields and service signatures follow the client. Renamed:
  DeleteUnitsRequest/Response -> DismissUnitsRequest/Response, DeleteWoundedRequest/Response ->
  DismissWoundedRequest/Response, GetProductionQueueRequest/Response ->
  GetProductionListRequest/Response, ProductionQueueItem -> ProductionSlot (plus
  CurrentProductionSlot and HospitalSlot), DoubleProductionRequest/Response ->
  DoubleProductionSlotRequest/Response, ArmyService.delete_units -> dismiss_units,
  get_production_queue -> get_production_list, skip_heal_time -> skip_heal. New: ProductionListId,
  SlotType, DismissManyWoundedRequest, WoundedUnits, AddedUnit, ProductionList, BUY_UNIT_PACKAGE_SK,
  ArmyService.dismiss_wounded_units. produce_units, get_production_list, cancel_production and
  double_production_slot take a ProductionListId (and slot type and position) instead of building
  and queue ids; unit methods take wod_id/amount; cancel_heal and skip_heal take a slot position;
  heal_all takes ruby_cost and returns bool instead of an invented healed count. The old reply
  fields (QID, CT, RS, UH, Q) are gone.

- **attack**: CreateAttackRequest.commander_id (LID) has no default.

- **castle**: RenameCastleRequest.kingdom_id takes Kingdom | int and castle_type MapItemType | int.

- **castle,movements**: GetMovementsRequest has no castle_id. RenameCastleRequest sends its keys in
  the client's order and encodes the name.

- **client**: The game-area helpers are no longer EmpireClient methods. Old -> new:

- **combat**: The effect type constants ATTACK_BONUS_UNIT_TYPE, UNLOCK_ABILITY_EFFECT_TYPE
  (combat.bonuses), TOOL_DEFENSE_BONUS_TYPE, DEFENDER_WALL_BONUS_TYPE, DEFENDER_GATE_BONUS_TYPE,
  DEFENDER_MOAT_BONUS_TYPE, DEFENSE_BONUS_TYPE, DEFENSE_BOOST_YARD_TYPE, DEFENSE_BOOST_FRONT_TYPE,
  DEFENSE_BOOST_FLANK_TYPE (combat.defense), MELEE_DEFENSE_MALUS_TYPE and RANGE_DEFENSE_MALUS_TYPE
  (combat.tools, also exported from empire_core.combat) are gone; use the CombatEffectType members
  of the same ids.

- **defense**: DefenseService.get_castle_defense is renamed get_support_defense_info.

- **enums**: MapItemType.METRO, ABG_RESOURCE_TOWER and ABG_TOWER, AttackType.KINGS_TOWER_CONQUER and
  CombatEffectType.REINFORCEMENT_BONUS and REINFORCEMENT_BOOST are renamed as above.

- **enums**: MapItemType.ROBBER_BARON, EXTERNAL_KINGDOM, KHAN_CAMP and KHAN_TENT are gone; use
  DUNGEON, KINGDOM_CASTLE and ALLIANCE_NOMAD_CAMP. MovementType.UNKNOWN is gone, and
  Movement.movement_type_enum returns MovementType | None.

- **enums**: MapObjectType and KingdomType are removed (use MapItemType and Kingdom), as are the
  MapObjectType is_player/is_npc/is_event/is_resource groupings and its UNKNOWN member;
  Movement.target_type_enum returns MapItemType | None. ISLAND_KINGDOM_ID is removed (use
  Kingdom.STORM). WearerType.ALL is removed in favour of WearerType.UNDEFINED (-1), and
  Equipment.wearer_type defaults to -1 instead of 0.

- **enums**: Send_attack's attack_type and loot_priority, and get_attack_info's area_type, are now
  enums; CreateAttackRequest's ATT, LP and ASCT and SendSpyRequest's ST reject values the client
  does not define, and kingdom inputs are typed Kingdom | int.

- **enums**: The enums are no longer importable from their old modules:

- **gamedata**: UnitStats.level defaults to -1 instead of 0, so a row without a level no longer
  matches unit(type, 0) or tool(type, 0); pass level=-1 for those. ToolStats.category defaults to
  "0" instead of "". ToolStats.tool_category is lowercased ("basic", not "Basic").
  UnitStats.loot_value and the ToolStats raw_*_bonus fields are int, not float.
  UnitStats.might_value, ToolStats.delete_after_battle and ToolStats.is_consumed_in_battle are
  removed. ToolStats.allowed_targets is typed tuple[tuple[int | None, int | None], ...].

- **models**: CurrencyTotals is imported from protocol.models.base (still re-exported from
  protocol.models); the army replies' currencies are CurrencyTotals instead of dicts;
  ProductionListType is removed, use ProductionListId.

- **models**: Gcl entries in a block whose KID is not a Kingdom are dropped from GetCastlesResponse
  and state.castles. PlayerCastle.from_list raises ValueError (ValidationError for a field of the
  wrong type) on a short row, an area type a castle list does not hold or bad field types, where it
  used to return an object; its location_id and name are None for a faction capital, which has no
  CastleInfo. PlayerCastle.capturer_id, CastleInfo.occupier_id and get_location_captures now include
  main and kingdom castles, and count occupier 0. CastleInfo and PlayerCastle level fields are int |
  None (None for landmarks) and castle rows' levels are floored as the client does.
  RenameCastleRequest.castle_type no longer takes an int outside MapItemType.

- **models**: LOCATION_TYPES, get_location_type_name, PlayerCastle.castle_type_name and
  LocationCapture.location_type_name are removed; use MapItemType(...).name. castle_type and
  location_type are MapItemType, and CastleInfo.occupier_id of a castle or kingdom castle is read
  from its row instead of always being -1.

- **models**: RelocateCastleRequest takes PX and PY only (castle_id, kingdom_id and the X/Y aliases
  are gone), SendSpyRequest.sd is renamed slowdown, and csm is sent in the client's key order.

- **models**: RelocateCastleRequest.kingdom_id is typed Kingdom | int and defaults to Kingdom.GREEN.

- **movements**: Empire_core.state.world_models is now empire_core.movements.tracked, and its logger
  is empire_core.movements.tracked. empire_core.Movement and empire_core.MovementResources are
  unchanged.

- **protocol**: Client_int, ClientInt, parse_int and ParseInt are no longer in
  empire_core.protocol.models.base. Import them from empire_core.protocol.js; client_int is now
  js_int and parse_int is js_parse_int_or_zero.

- **protocol**: Encode_chat_text and decode_chat_text are removed from empire_core,
  empire_core.protocol.models and its base and chat modules. Use encode_json_text and
  decode_json_text from empire_core (or empire_core.protocol.text). smartfox_json_text and
  parse_chat_json_message are no longer in empire_core.protocol.models.base.

- **ranking**: RankingType members renamed: ACHIEVEMENTS -> PLAYER_ACHIEVEMENT_POINTS, PLAYER_MIGHT
  -> PLAYER_MIGHT_POINTS, LEGEND_LEVEL -> PLAYER_LEGEND, ALLIANCE_MIGHT -> ALLIANCE_MIGHT_POINTS,
  DOMINION_POINTS -> ALLIANCE_LANDMARKS, CARGO_POINTS -> ALLIANCE_AQUA_POINTS. Removed, as the
  client has no such list at those values: FOREIGN_INVASION=71 (use ALIEN_INVASION,
  ALLIANCE_ALIEN_INVASION_PLAYER or ALLIANCE_ALIEN_INVASION_ALLIANCE), BLOODCROWS=72 (use
  ALLIANCE_RED_ALIEN_INVASION_PLAYER or ALLIANCE_RED_ALIEN_INVASION_ALLIANCE), SAMURAI=80 (use
  SAMURAI_PLAYER or SAMURAI_ALLIANCE), NOMAD=85 (use NOMADINVASION, ALLIANCE_NOMADINVASION_PLAYER or
  ALLIANCE_NOMADINVASION_ALLIANCE), OUTER_REALMS=63 (63 is KINGDOMS_LEAGUE_SEASON), BERIMOND=113,
  SHAPESHIFTER=60 and HORIZON=134. RankingCategory is removed. list_id -> league_type_id on
  GetHighscoreRequest, GetHighscoreResponse, GetRankingListRequest, GetRankingListResponse and
  SearchAllianceRequest, and on RankingService.get_highscore/get_ranking_list. GetHighscoreRequest
  and GetRankingListRequest default it to -1 and always send it; GetHighscoreResponse.league_type_id
  is -1 rather than None when missing. GetRankingListRequest requires max_results (M) and defaults
  rank to 1; get_ranking_list takes max_results as its third argument. LeagueBracketDef.league_id ->
  league_type_id. The list type (LT) of GetHighscoreRequest, GetRankingListRequest,
  SearchAllianceRequest and RankingService.get_highscore/get_ranking_list takes a RankingType
  instead of an int.

- **spy**: Execute_instant_spy no longer pays with feathers by default; pass feathers=True for the
  old behaviour.

- **spy**: SendSpyResponse no longer has the arrival_time field; movement_id is a property that is
  None when the reply has no movement, and the movement is spy_movement.

- **spy**: The invalid_sne_format and sne_timeout_or_error_* reasons are gone: unreadable or
  unrelated sne messages are skipped, and a wait that ends without the report gives sne_timeout (or
  report_target_mismatch when only reports for another position came, disconnected when the
  connection dropped).

- **types**: Kingdom parameters and fields are typed Kingdom. An int naming one of the six kingdoms
  still validates, but any other id is now a ValidationError (ValueError from fill_attack),
  GetMapAreaResponse with an unknown KID fails validation, camp_kingdom_id returns Kingdom | None,
  and GetDefenseRequest.kingdom_id defaults to None instead of -1.


## v0.40.0 (2026-09-29)

### Bug Fixes

- **alliance**: Decode ain text exactly as parseChatJSONMessage does
  ([#204](https://github.com/eschnitzler/EmpireCore/pull/204),
  [`b08d0a7`](https://github.com/eschnitzler/EmpireCore/commit/b08d0a7afe31078119ec3fe8ecaebe1056c366de))

- **alliance**: Drop the duplicate SRFU/HRFU fields and read ain text as the client does
  ([#204](https://github.com/eschnitzler/EmpireCore/pull/204),
  [`b08d0a7`](https://github.com/eschnitzler/EmpireCore/commit/b08d0a7afe31078119ec3fe8ecaebe1056c366de))

- **alliance**: Read the parseInt fields of ain as parseInt does
  ([#204](https://github.com/eschnitzler/EmpireCore/pull/204),
  [`b08d0a7`](https://github.com/eschnitzler/EmpireCore/commit/b08d0a7afe31078119ec3fe8ecaebe1056c366de))

- **attack**: Fill from the pre-calculation's army, and join the castle before gui
  ([#211](https://github.com/eschnitzler/EmpireCore/pull/211),
  [`c990e47`](https://github.com/eschnitzler/EmpireCore/commit/c990e47cfddd11f9f101cad7d5af925c2605a3cc))

- **attack**: Fill from the stronghold units too, and refuse to read an unjoined castle
  ([#211](https://github.com/eschnitzler/EmpireCore/pull/211),
  [`c990e47`](https://github.com/eschnitzler/EmpireCore/commit/c990e47cfddd11f9f101cad7d5af925c2605a3cc))

- **combat**: Add the bonuses of the gems slotted in a commander's equipment
  ([#205](https://github.com/eschnitzler/EmpireCore/pull/205),
  [`64d43fe`](https://github.com/eschnitzler/EmpireCore/commit/64d43fe9346b2a649a26f60d3a1035484610179a))

- **combat**: Count a commander's alien equipment bonuses
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **combat**: Count alien equipment gems and add bonuses in the client's order
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **combat**: Count worn items in the client's slot order, one per slot
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **combat**: Read the value, not the wod id, of effect types 47, 51, 168 and 214
  ([#205](https://github.com/eschnitzler/EmpireCore/pull/205),
  [`64d43fe`](https://github.com/eschnitzler/EmpireCore/commit/64d43fe9346b2a649a26f60d3a1035484610179a))

- **combat**: Resolve commander equipment bonuses and gems as the client does
  ([#205](https://github.com/eschnitzler/EmpireCore/pull/205),
  [`64d43fe`](https://github.com/eschnitzler/EmpireCore/commit/64d43fe9346b2a649a26f60d3a1035484610179a))

- **combat**: Resolve equipment bonus ids through the equipment effect table
  ([#205](https://github.com/eschnitzler/EmpireCore/pull/205),
  [`64d43fe`](https://github.com/eschnitzler/EmpireCore/commit/64d43fe9346b2a649a26f60d3a1035484610179a))

- **commanders**: Keep an item whose set id or rarity is odd
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **gamedata**: Read equipment effect rows with the client's defaults, and describe them
  ([#205](https://github.com/eschnitzler/EmpireCore/pull/205),
  [`64d43fe`](https://github.com/eschnitzler/EmpireCore/commit/64d43fe9346b2a649a26f60d3a1035484610179a))

- **skills**: Keep RS fractions as parse_SKL does, and describe the id list rule
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

- **skills**: Read generals and skills as the client does, and add the general commands
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

- **skills**: Read null skill lists as no skills, and document the general commands
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

- **skills**: Read the general's flags, old xp and fixed level as the client does
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

### Documentation

- **alliance**: Describe every AllianceInfo field and read AID as parseInt does
  ([#204](https://github.com/eschnitzler/EmpireCore/pull/204),
  [`b08d0a7`](https://github.com/eschnitzler/EmpireCore/commit/b08d0a7afe31078119ec3fe8ecaebe1056c366de))

- **commanders**: Describe every equipment and commander field and cite the gli classes
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **skills**: Describe every general and skill field and cite the gie and skl classes
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

### Features

- **commanders**: Add the arl command to rename a commander or castellan
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **commanders**: Keep the hero alien string, add UNIQUE_TEMPORARY and has_set
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **commanders**: Read LICID, AIE/TAE/GEM and a castellan's movement availability
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **commanders**: Read LICID, alien equipment and hero fields, and rename commanders
  ([#206](https://github.com/eschnitzler/EmpireCore/pull/206),
  [`6d3742e`](https://github.com/eschnitzler/EmpireCore/commit/6d3742e6c7bf6fae17cf95a5fe57ffeb17df7909))

- **equipment**: Read the equipment inventory and equip or unequip items
  ([#208](https://github.com/eschnitzler/EmpireCore/pull/208),
  [`4de96af`](https://github.com/eschnitzler/EmpireCore/commit/4de96af7b76ae576907e9d76a1240a5d81f070ee))

- **skills**: Add the commands that change generals
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

- **skills**: Read the reset counter and the sceat skills being activated
  ([#207](https://github.com/eschnitzler/EmpireCore/pull/207),
  [`398eec2`](https://github.com/eschnitzler/EmpireCore/commit/398eec279abc198ae28aeca64da6b852ef7d4305))

### Refactoring

- **army**: Read gui as parse_GUI does ([#211](https://github.com/eschnitzler/EmpireCore/pull/211),
  [`c990e47`](https://github.com/eschnitzler/EmpireCore/commit/c990e47cfddd11f9f101cad7d5af925c2605a3cc))

### Breaking Changes

- **alliance**: AllianceInfo.spend_resources_food_upgrade and help_resources_food_upgrade are
  removed; use soft_relic_forge_uses and hard_relic_forge_uses. description and announcement are
  decoded, and an empty announcement reads as " ".

- **army**: GetUnitsResponse.inventory is renamed units and, with in_production, stronghold and
  hospital, holds {wod_id: amount} instead of [wod_id, amount] lists; the units (U) and tools (T)
  fields are removed.

- **attack**: GetUnitsRequest has no castle_id and sends {}; army.get_units and get_units_response
  join the given castle before reading it.

- **combat**: Commander_bonuses takes the GameData as its first argument:
  commander_bonuses(game_data, commander, area_effects=...).

- **skills**: General.fixed_level is -1 for L: 0 (was 0), and General.star_level is derived from L
  when ST is missing or 0 and L is a multiple of 10 (was 0).


## v0.39.0 (2026-09-25)

### Bug Fixes

- **alliance**: Name the ain settings and owner record points as the client reads them
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **army**: Send_support no longer uses the premium commander or feathers by default
  ([#195](https://github.com/eschnitzler/EmpireCore/pull/195),
  [`d4f6890`](https://github.com/eschnitzler/EmpireCore/commit/d4f6890fa988ce7bdf73508cead07e3549d5d08a))

- **attack**: BPC is the premium commander on attacks too, and supports need a commander
  ([#195](https://github.com/eschnitzler/EmpireCore/pull/195),
  [`d4f6890`](https://github.com/eschnitzler/EmpireCore/commit/d4f6890fa988ce7bdf73508cead07e3549d5d08a))

- **attack**: Keep the currency, owner and attack-in-progress data of a cra reply
  ([#192](https://github.com/eschnitzler/EmpireCore/pull/192),
  [`b8e7f20`](https://github.com/eschnitzler/EmpireCore/commit/b8e7f20ad086fa47e20c439ea54d06df11ec6390))

- **attack**: Keep the pre-calculation when the tile scan fails, drop treasure dungeons
  ([#191](https://github.com/eschnitzler/EmpireCore/pull/191),
  [`5bc2157`](https://github.com/eschnitzler/EmpireCore/commit/5bc2157f74570833fb0cf2a8fdc410363289727b))

- **attack**: Leave spied amounts of 0 or less out, as the client does
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **attack**: Model msd and sdc as the dungeon cooldown skips they are
  ([#193](https://github.com/eschnitzler/EmpireCore/pull/193),
  [`ea54062`](https://github.com/eschnitzler/EmpireCore/commit/ea540625abb4faa7f3a23cdf437be80af017a279))

- **attack**: No defender legend skills without a spy report
  ([#190](https://github.com/eschnitzler/EmpireCore/pull/190),
  [`9eed1b5`](https://github.com/eschnitzler/EmpireCore/commit/9eed1b5f7f16d5920535abf56cd7c51070e6b242))

- **attack**: Parse a dungeon skip's reply row as a map area
  ([#193](https://github.com/eschnitzler/EmpireCore/pull/193),
  [`ea54062`](https://github.com/eschnitzler/EmpireCore/commit/ea540625abb4faa7f3a23cdf437be80af017a279))

- **attack**: Raise ATTACK_IN_PROGRESS with its details, and name FC send_anyway
  ([#192](https://github.com/eschnitzler/EmpireCore/pull/192),
  [`b8e7f20`](https://github.com/eschnitzler/EmpireCore/commit/b8e7f20ad086fa47e20c439ea54d06df11ec6390))

- **attack**: Read attack presets in the client's shape and allow saving them
  ([#194](https://github.com/eschnitzler/EmpireCore/pull/194),
  [`99d0cca`](https://github.com/eschnitzler/EmpireCore/commit/99d0cca9a1a3c9dcd4710e7820a85b3411e1b5de))

- **attack**: Read the spy report age and the castellan from aci like the client
  ([#190](https://github.com/eschnitzler/EmpireCore/pull/190),
  [`9eed1b5`](https://github.com/eschnitzler/EmpireCore/commit/9eed1b5f7f16d5920535abf56cd7c51070e6b242))

- **attack**: Send adi's keys in the client's order
  ([#191](https://github.com/eschnitzler/EmpireCore/pull/191),
  [`5bc2157`](https://github.com/eschnitzler/EmpireCore/commit/5bc2157f74570833fb0cf2a8fdc410363289727b))

- **attack**: Send attack waves and support in the client's shape
  ([#195](https://github.com/eschnitzler/EmpireCore/pull/195),
  [`d4f6890`](https://github.com/eschnitzler/EmpireCore/commit/d4f6890fa988ce7bdf73508cead07e3549d5d08a))

- **attack**: Take the defender's legend skills from the pre-calculation
  ([#201](https://github.com/eschnitzler/EmpireCore/pull/201),
  [`26a10a1`](https://github.com/eschnitzler/EmpireCore/commit/26a10a1527e7bb2552d2217db67a330977e620a1))

- **castle**: Log gcl kingdom entries that cannot be read
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **combat**: Add legend skills, support tools and extra waves to the attacker
  ([#199](https://github.com/eschnitzler/EmpireCore/pull/199),
  [`0fc7649`](https://github.com/eschnitzler/EmpireCore/commit/0fc7649c755f3a3c13b1b0afd0418181883d81a5))

- **combat**: Apply the client's three legendary-fight rules
  ([#197](https://github.com/eschnitzler/EmpireCore/pull/197),
  [`de689d8`](https://github.com/eschnitzler/EmpireCore/commit/de689d85e2b38996f6db7cf3f6c62ce1a94add64))

- **combat**: Count defense tools and defender legend skills in a spied defense
  ([#201](https://github.com/eschnitzler/EmpireCore/pull/201),
  [`26a10a1`](https://github.com/eschnitzler/EmpireCore/commit/26a10a1527e7bb2552d2217db67a330977e620a1))

- **combat**: Faction camp owners, conquer control, and the owner's legend level from aci
  ([#197](https://github.com/eschnitzler/EmpireCore/pull/197),
  [`de689d8`](https://github.com/eschnitzler/EmpireCore/commit/de689d85e2b38996f6db7cf3f6c62ce1a94add64))

- **combat**: Merge the flank bonus sources before truncating
  ([#198](https://github.com/eschnitzler/EmpireCore/pull/198),
  [`68aa0b4`](https://github.com/eschnitzler/EmpireCore/commit/68aa0b406fe9a2355c1db019189ff1cac868b3b2))

- **combat**: Refuse raid-boss tools when their boss is not active
  ([#200](https://github.com/eschnitzler/EmpireCore/pull/200),
  [`17dd902`](https://github.com/eschnitzler/EmpireCore/commit/17dd902e8b09027f4ce74b4f1ae2030f1a38d7e3))

- **defense**: Import Any for the dfc castellan validators
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **defense**: Keep a dfc reply whose castellan cannot be read
  ([#196](https://github.com/eschnitzler/EmpireCore/pull/196),
  [`43b768c`](https://github.com/eschnitzler/EmpireCore/commit/43b768c203f9a57ee56fd89099b45071370a31d2))

- **defense**: Send the castle defense commands in the client's shape
  ([#196](https://github.com/eschnitzler/EmpireCore/pull/196),
  [`43b768c`](https://github.com/eschnitzler/EmpireCore/commit/43b768c203f9a57ee56fd89099b45071370a31d2))

- **defense**: Type the dfc castellan and unit inventory
  ([#196](https://github.com/eschnitzler/EmpireCore/pull/196),
  [`43b768c`](https://github.com/eschnitzler/EmpireCore/commit/43b768c203f9a57ee56fd89099b45071370a31d2))

- **map**: Read structure levels only from rows that carry them
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **models**: Keep owner records, map rows and leaderboards as lenient as the client
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **models**: Read commanders, owner records, cra and sne as leniently as the client
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **player**: Fold gdi's landmark lists into its castles, and find a wsp player at X/Y
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **ranking**: Read llsp rows as leniently as the client
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

### Documentation

- **messages**: Describe bsd as the spy report it is
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

### Features

- **attack**: Pre-calculate each kind of target with the command the client uses
  ([#191](https://github.com/eschnitzler/EmpireCore/pull/191),
  [`5bc2157`](https://github.com/eschnitzler/EmpireCore/commit/5bc2157f74570833fb0cf2a8fdc410363289727b))

- **commanders**: Model a relic item's type, might and gem
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

### Refactoring

- **alliance**: Type the member info, diplomacy, landmark, bookmark and search lists
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **attack**: Type the gaa, gui and gli blocks of a pre-calculation reply
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **attack**: Type the movement, owners and currencies of a cra reply
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **attack**: Type the spied castellan of a pre-calculation reply
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **attack**: Type the spy positions and area effects of a pre-calculation reply
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **commanders**: Type the effects, equipment and item bonuses of a commander
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **defense**: Type the spy positions, castellan, gui and gli of an sdi reply
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **gamedata**: Keep a tool's effects as the string the client splits
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **map**: Parse a map area's rows into items at parse time
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **messages**: Type the sne messages and the bsd spy report
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **models**: Type the crest, faction and castle lists of owner records
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **models**: Type the wire data models hold as raw dicts and lists
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **movements**: Type the area rows and the commander of a movement
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **player**: Type the gcl block of gdi and the gaa block of wsp
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **ranking**: Type the llsp leaderboard entries
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

- **skills**: Type a general's selected abilities
  ([#203](https://github.com/eschnitzler/EmpireCore/pull/203),
  [`cceab23`](https://github.com/eschnitzler/EmpireCore/commit/cceab230500fb68a81ad76566d8ef69d5ddaa59d))

### Testing

- **attack**: Give the stubbed pre-calculation its owner records
  ([#201](https://github.com/eschnitzler/EmpireCore/pull/201),
  [`26a10a1`](https://github.com/eschnitzler/EmpireCore/commit/26a10a1527e7bb2552d2217db67a330977e620a1))

### Breaking Changes

- **alliance**: AllianceInfo.castle_count, total_castles, homepage, invite_only,
  ignore_applications, kick_applications, abbreviation, friendly_raids, support_priority,
  auto_accept, alliance_war, member_limit, attack_protection, message_filter and invite_friends are
  renamed to fame_points, highest_fame_points, can_be_invited_to_hard_pact, is_searching_members,
  is_accepting_members, is_king_alliance, announcement, free_renames, can_be_invited_to_soft_pact,
  application_count, auto_war, external_member_level, aqua_points, is_able_to_forge and
  is_forge_inventory_full; required_trust is removed. PlayerProfileBase h_field, castle_count,
  total_castles and avatar_points are renamed to honor, glory_points, highest_glory_points and
  achievement_points.

- **alliance**: AllianceInfo.member_info is list[AllianceMemberInfo]; alliance_diplomacy is
  list[AllianceDiplomacyStatus]; alliance_contracts, alliance_truces, alliance_kingdoms,
  alliance_monuments and alliance_landmarks are renamed to capitals, metropolises, kings_towers,
  monuments and laboratories (list[MapAreaItem]). AllianceBookmark.object_info and positions are
  replaced by owner, a MapObject. SearchAllianceResponse.raw_results is replaced by results;
  AllianceSearchResult.from_list and might are removed, and it gains rank, score and fame_points. A
  non-list AMI or L now reads as empty instead of failing validation, and a missing search name is
  "" instead of "Unknown".

- **army**: Send_support's boost_with_coins is use_premium_commander (default False), feathers is a
  bool (default False) and commander_id defaults to 0. SendSupportRequest.boost_with_coins is
  use_premium_commander, and LID, BPC and PTT default to 0.

- **attack**: AttackInfoResponse.raw_defending_castellan and raw_defending_castellan_fallback are
  replaced by spied_castellan and spied_castellan_fallback, which hold Commander models.

- **attack**: AttackInfoResponse.raw_map_area, raw_inventory and raw_commanders are replaced by
  target_area, unit_inventory and commander_roster, and owner_records() returns MapObject records
  instead of dicts.

- **attack**: AttackInfoResponse.raw_spy_army is renamed spy_data, and raw_attacker_effects is
  replaced by attacker_effects, a list of CommanderEffect models.

- **attack**: CreateAttackResponse.attack_movement is a MovementWrapper instead of a dict,
  currencies a CurrencyTotals or None instead of a dict, and owners a list of MovementOwner models.
  CreateAttackRequest's and send_attack's collector_booster take a list of [currency_id, amount]
  pairs.

- **attack**: Fill_wave and fill_waves return waves whose containers are padded with [-1, 0] for
  every empty or locked slot. SendSupportRequest no longer has kingdom_id and
  CastleService.send_support no longer takes it.

- **attack**: GetAttackInfoResponse.defending_castellan_id is now spy_age_seconds.
  raw_defending_castellan now holds abe and the B entry moved to raw_defending_castellan_fallback.
  spy_army() and defending_castellan() return None when S is empty. target_row() no longer unwraps a
  nested row list.

- **attack**: GetPresetsRequest takes no castle_id. AttackPreset now has index, name and raw_army
  with an army() decoder instead of preset_id, name, units and tools. GetPresetsResponse.presets
  reads the S key.

- **attack**: GetTargetInfoRequest, GetTargetInfoResponse and TargetInfo are removed; use
  GetDungeonAttackInfoRequest and GetDungeonAttackInfoResponse. get_attack_info returns an
  AttackInfoResponse and takes timeout as a keyword after area_type and conquer. fill_attack on a
  target of unknown area type now scans the tile before the pre-calculation.

- **attack**: Send_attack raises AttackInProgressError on ATTACK_IN_PROGRESS instead of returning
  False. CreateAttackRequest.fast_cast is send_anyway.

- **attack**: Send_attack's boost_with_coins and CreateAttackRequest.boost_with_coins are
  use_premium_commander. send_support takes commander_id right after units, with no default, and
  SendSupportRequest.commander_id is required.

- **attack**: SkipAttackCooldownRequest/Response are now MinuteSkipDungeonRequest/Response and
  SkipDefenseCooldownRequest/Response are now SkipDungeonCooldownRequest/Response. The requests take
  the dungeon's coordinates, kingdom and treasure-map ids instead of castle_id, and the replies
  expose area_row instead of rubies_spent.

- **combat**: EffectDef.raid_boss_id is replaced by raw_raid_boss_ids and the raid_boss_ids
  property. can_use_tool_on_target now takes the game data as a third argument.

- **combat**: Fill_waves and fill_attack no longer take sceat_skill_ids.

- **combat**: Is_legendary_fight is removed; use LegendaryFight.evaluate. Without owner_id,
  fill_waves grants no legend skills except an alien camp's, whose owner id follows from its area
  type.

- **commanders**: LeaderBase.raw_equipment and the equipment() method are replaced by the equipment
  field, a list of Equipment. LeaderBase.effects and area_effects hold CommanderEffect models
  instead of raw rows. Equipment.bonuses holds EquipmentBonus models, and a relic item's bonuses
  move to Equipment.relic_bonuses as RelicBonus models.

- **defense**: GetDefenseRequest and the ChangeKeep/Wall/MoatDefenseRequest models take the castle's
  coordinates and area id instead of castle_id, and the change requests take slot lists instead of
  units and tools, with ChangeWallDefenseRequest taking one WallSectionSetup per section.
  GetDefenseResponse has the dfc fields instead of keep/wall/moat/courtyard. DefenseConfiguration is
  removed, and ChangeKeep/Wall/MoatDefenseResponse are replaced by KeepDefense, WallDefense and
  MoatDefense.

- **defense**: GetSupportDefenseResponse.castellan_info (dict) is replaced by castellan (Castellan),
  unit_inventory is a UnitInventory instead of a dict, and commanders_info (dict) is replaced by
  commander_roster (CommanderRoster). defense_positions holds pairs already read through int().

- **gamedata**: ToolStats.effects is renamed to raw_effects and is a str instead of Any.

- **map**: GetMapAreaResponse.raw_items is removed; items is now a field holding the parsed rows,
  and unparseable rows are logged when the reply is parsed rather than when items is read.

- **map**: MapAreaItem's structure levels are 0 for kings towers, monuments, laboratories, villages
  and isles, and a capital's or metropolis's keep, wall and gate levels are no longer floored at 1.

- **messages**: SystemNotificationEvent.messages is list[MessageInfo] instead of raw lists.
  BattleSpyDataResponse.battle_data and SpyResult.battle_data are renamed to defending_castellan and
  are Castellan | None instead of a dict. BattleSpyDataResponse.spy_data and SpyResult.spy_data are
  list[list[list[int]]].

- **models**: MemberEmblem and MemberCastle are removed. AllianceMember.emblem,
  PlayerOwnerInfo.emblem and MapObject.emblem are OwnerCrest (icon_style is now is_set,
  symbol_color1/2 are symbol1_color/symbol2_color). PlayerProfileBase.castle_positions and
  village_positions are list[OwnerCastlePosition] and the castles property is removed.
  MapObject.faction is OwnerFaction and MapObject.alliance_emblem is AllianceEmblem instead of
  dicts.

- **movements**: Movement.target_area and Movement.source_area are MovementArea | None instead of
  the raw list (the row is at .row). Movement.commander_equipment is list[Equipment] and
  Movement.commander_effects is list[CommanderEffect] instead of raw lists.
  MovementUnitInfo.commander is Commander | None instead of a dict.

- **player**: A gcl row wrapped in an extra list is no longer unwrapped and is skipped, as the
  client would not read it. SearchPlayerResponse gains x and y, and get_player picks the owner of
  the area at X/Y rather than the first owner record.

- **player**: GetPlayerInfoResponse.raw_castle_list is replaced by castle_list (GetCastlesResponse)
  and get_castles returns list[CastleInfo] instead of list[PlayerCastle] (castle_name, kingdom_id,
  castle_id and occupier_id instead of name, kingdom, location_id and capturer_id). Like the gcl
  command it drops rows of ten fields or fewer, and a capture's kingdom is the list's KID.
  SearchPlayerResponse.raw_gaa is replaced by area, SearchPlayerResult is removed and get_player
  returns MapObject | None. PlayerCastle, LOCATION_TYPES and get_location_type_name are no longer
  importable from models.player; import them from models.castle or models.

- **ranking**: GetRankingListResponse.raw_list is replaced by scores, a list[LeaderboardScore].

- **skills**: General.raw_abilities is replaced by selected_abilities, a list[SelectedAbility];
  ability_ids no longer includes -1 or bare ids.


## v0.38.0 (2026-09-25)

### Bug Fixes

- **state**: Alliance alerts only for players, and the township counts as yours
  ([#184](https://github.com/eschnitzler/EmpireCore/pull/184),
  [`ec52eb7`](https://github.com/eschnitzler/EmpireCore/commit/ec52eb72f0790f20888a074d6dd0ea29e3235755))

- **state**: An unreadable LVL or XP keeps the previous value
  ([#188](https://github.com/eschnitzler/EmpireCore/pull/188),
  [`6a0a193`](https://github.com/eschnitzler/EmpireCore/commit/6a0a193d1e788ea7fa8792d111857f75852b5574))

- **state**: Apply player pushes after login, plus honor and protection
  ([#187](https://github.com/eschnitzler/EmpireCore/pull/187),
  [`3ff527f`](https://github.com/eschnitzler/EmpireCore/commit/3ff527f5b7b58bae52951320943ddfeb018ba6b0))

- **state**: Call the sce entries special currencies, not inventory
  ([#189](https://github.com/eschnitzler/EmpireCore/pull/189),
  [`c391575`](https://github.com/eschnitzler/EmpireCore/commit/c391575c9fa624f07d3d50e2fda489bdb5e5c835))

- **state**: Compute legend level and level XP bounds like the client
  ([#188](https://github.com/eschnitzler/EmpireCore/pull/188),
  [`6a0a193`](https://github.com/eschnitzler/EmpireCore/commit/6a0a193d1e788ea7fa8792d111857f75852b5574))

- **state**: Copy beginner_protection in snapshots, skip unreadable pushes
  ([#187](https://github.com/eschnitzler/EmpireCore/pull/187),
  [`3ff527f`](https://github.com/eschnitzler/EmpireCore/commit/3ff527f5b7b58bae52951320943ddfeb018ba6b0))

- **state**: Drop the deprecated inventory names
  ([#189](https://github.com/eschnitzler/EmpireCore/pull/189),
  [`c391575`](https://github.com/eschnitzler/EmpireCore/commit/c391575c9fa624f07d3d50e2fda489bdb5e5c835))

- **state**: Keep movement owner records and alert like the client
  ([#184](https://github.com/eschnitzler/EmpireCore/pull/184),
  [`ec52eb7`](https://github.com/eschnitzler/EmpireCore/commit/ec52eb72f0790f20888a074d6dd0ea29e3235755))

- **state**: Read area ids and names at the area type's own positions
  ([#183](https://github.com/eschnitzler/EmpireCore/pull/183),
  [`470da9a`](https://github.com/eschnitzler/EmpireCore/commit/470da9a26c9967e7766828578e9165b824441e7f))

- **state**: Read every movement wrapper block the client reads
  ([#182](https://github.com/eschnitzler/EmpireCore/pull/182),
  [`c007a99`](https://github.com/eschnitzler/EmpireCore/commit/c007a991f117f5202e57cbd58c312470750d36ef))

- **state**: Store the movements you send from the send replies
  ([#186](https://github.com/eschnitzler/EmpireCore/pull/186),
  [`794e132`](https://github.com/eschnitzler/EmpireCore/commit/794e13299fc61d74080f21b8c460132c20a44e42))

- **state**: The deprecated Player.inventory can be assigned again
  ([#189](https://github.com/eschnitzler/EmpireCore/pull/189),
  [`c391575`](https://github.com/eschnitzler/EmpireCore/commit/c391575c9fa624f07d3d50e2fda489bdb5e5c835))

### Breaking Changes

- **state**: MovementResources.ash is aquamarine. Movement.resources is filled from market goods or
  travel loot, never from GS.

- **state**: On_incoming_attack no longer fires before the local player is known, nor for attacks
  whose target is outside your alliance.

- **state**: Player.inventory, Player(inventory=...) and GameState.get_inventory() are gone. Use
  Player.special_currencies and GameState.get_special_currencies().

- **state**: Player.LVL, XP, LL, XPFCL and XPTNL are replaced by level, xp, legendary_level,
  xp_for_current_level and xp_to_next_level, which are now fields (they were read-only properties).

- **state**: Player.model_dump() now uses the key special_currencies; there is no inventory key any
  more. Player(inventory=...) and the inventory property still work, with a DeprecationWarning.


## v0.37.0 (2026-09-25)

### Bug Fixes

- **protocol**: Model gam as wrappers around a movement record
  ([#177](https://github.com/eschnitzler/EmpireCore/pull/177),
  [`14deeb9`](https://github.com/eschnitzler/EmpireCore/commit/14deeb9d3c7ab74d0e46e44a81bcfa469163cd4e))

- **protocol**: Type every gam block from the client's parsers
  ([#177](https://github.com/eschnitzler/EmpireCore/pull/177),
  [`14deeb9`](https://github.com/eschnitzler/EmpireCore/commit/14deeb9d3c7ab74d0e46e44a81bcfa469163cd4e))

- **state**: Fill castles from the whole dcl entry, with the client's names
  ([#179](https://github.com/eschnitzler/EmpireCore/pull/179),
  [`65ae161`](https://github.com/eschnitzler/EmpireCore/commit/65ae1618388d63a7815ed2dec3e42272bf50eab1))

- **state**: Read the alliance search flag and fame from gal
  ([#178](https://github.com/eschnitzler/EmpireCore/pull/178),
  [`8fd8861`](https://github.com/eschnitzler/EmpireCore/commit/8fd886172ba16ad3223b1566666da236fc10b85e))

### Code Style

- **protocol**: Drop comments that restate the field descriptions
  ([#177](https://github.com/eschnitzler/EmpireCore/pull/177),
  [`14deeb9`](https://github.com/eschnitzler/EmpireCore/commit/14deeb9d3c7ab74d0e46e44a81bcfa469163cd4e))

- **state**: Drop a comment that restates the validator
  ([#178](https://github.com/eschnitzler/EmpireCore/pull/178),
  [`8fd8861`](https://github.com/eschnitzler/EmpireCore/commit/8fd886172ba16ad3223b1566666da236fc10b85e))

- **state**: Shorten a fixture comment ([#179](https://github.com/eschnitzler/EmpireCore/pull/179),
  [`65ae161`](https://github.com/eschnitzler/EmpireCore/commit/65ae1618388d63a7815ed2dec3e42272bf50eab1))

### Refactoring

- Point docs, comments and time patches at the modules that moved
  ([#181](https://github.com/eschnitzler/EmpireCore/pull/181),
  [`f4a2f53`](https://github.com/eschnitzler/EmpireCore/commit/f4a2f5385fb2f4f994dd40ef72b0db55a97fd43e))

- Split GameState and the gam models by area
  ([#181](https://github.com/eschnitzler/EmpireCore/pull/181),
  [`f4a2f53`](https://github.com/eschnitzler/EmpireCore/commit/f4a2f5385fb2f4f994dd40ef72b0db55a97fd43e))

- **protocol**: Call the UM lord a commander
  ([#177](https://github.com/eschnitzler/EmpireCore/pull/177),
  [`14deeb9`](https://github.com/eschnitzler/EmpireCore/commit/14deeb9d3c7ab74d0e46e44a81bcfa469163cd4e))

- **protocol**: Move the gam models out of map.py
  ([#181](https://github.com/eschnitzler/EmpireCore/pull/181),
  [`f4a2f53`](https://github.com/eschnitzler/EmpireCore/commit/f4a2f5385fb2f4f994dd40ef72b0db55a97fd43e))

- **state**: Split GameState into per-area mixins
  ([#181](https://github.com/eschnitzler/EmpireCore/pull/181),
  [`f4a2f53`](https://github.com/eschnitzler/EmpireCore/commit/f4a2f5385fb2f4f994dd40ef72b0db55a97fd43e))

### Testing

- Split the state and gam model tests by area
  ([#181](https://github.com/eschnitzler/EmpireCore/pull/181),
  [`f4a2f53`](https://github.com/eschnitzler/EmpireCore/commit/f4a2f5385fb2f4f994dd40ef72b0db55a97fd43e))

- **protocol**: Type the gam fixture for mypy
  ([#177](https://github.com/eschnitzler/EmpireCore/pull/177),
  [`14deeb9`](https://github.com/eschnitzler/EmpireCore/commit/14deeb9d3c7ab74d0e46e44a81bcfa469163cd4e))

### Breaking Changes

- **protocol**: Protocol.models.map.Movement is removed. GetMovementsResponse.movements holds
  MovementWrapper entries; the record is .movement, with the fields of the state Movement.

- **state**: Alliance.abbreviation is removed; is_searching is the flag SA really holds. The AID, N,
  SA and R attributes are replaced by id, name, is_searching and rank.

- **state**: Castle.max_castellans, has_workshop, has_dwelling, has_harbour and next_day_population
  are replaced by market_carriages, has_siege_workshop, has_defense_workshop, has_hospital and
  neutral_deco_points; defence and stronghold_units are new. Resources.ash is aquamarine. The OID,
  N, KID, X, Y, P, NDP, MC, B, WS, DW and H attributes are gone: use id, name, kingdom_id, x, y and
  the properties above.


## v0.36.0 (2026-09-24)

### Bug Fixes

- **state**: Arrive by time, route abr/asr/mcm/mfc, mrm is a removal
  ([#161](https://github.com/eschnitzler/EmpireCore/pull/161),
  [`8673d4c`](https://github.com/eschnitzler/EmpireCore/commit/8673d4cbd0d923082cb447244e82e0d2b7a08945))

- **state**: Movement types and direction from the game client
  ([#160](https://github.com/eschnitzler/EmpireCore/pull/160),
  [`424a5ea`](https://github.com/eschnitzler/EmpireCore/commit/424a5eac351b748a3b03fb32788e05a2f339185c))

- **state**: Number movement types the way the game client does
  ([#160](https://github.com/eschnitzler/EmpireCore/pull/160),
  [`424a5ea`](https://github.com/eschnitzler/EmpireCore/commit/424a5eac351b748a3b03fb32788e05a2f339185c))

- **state**: Tell incoming from outgoing by owner, returns by D
  ([#160](https://github.com/eschnitzler/EmpireCore/pull/160),
  [`424a5ea`](https://github.com/eschnitzler/EmpireCore/commit/424a5eac351b748a3b03fb32788e05a2f339185c))

- **state**: Time-based arrival, abr/asr/mcm/mfc, mrm as removal
  ([#161](https://github.com/eschnitzler/EmpireCore/pull/161),
  [`8673d4c`](https://github.com/eschnitzler/EmpireCore/commit/8673d4cbd0d923082cb447244e82e0d2b7a08945))

### Documentation

- **state**: A return home arrives as a new TRAVEL movement
  ([#160](https://github.com/eschnitzler/EmpireCore/pull/160),
  [`424a5ea`](https://github.com/eschnitzler/EmpireCore/commit/424a5eac351b748a3b03fb32788e05a2f339185c))

- **state**: Say which movements alert and that returns arrive too
  ([#161](https://github.com/eschnitzler/EmpireCore/pull/161),
  [`8673d4c`](https://github.com/eschnitzler/EmpireCore/commit/8673d4cbd0d923082cb447244e82e0d2b7a08945))

### Refactoring

- **state**: Snake_case Movement fields aliased to their wire keys
  ([#161](https://github.com/eschnitzler/EmpireCore/pull/161),
  [`8673d4c`](https://github.com/eschnitzler/EmpireCore/commit/8673d4cbd0d923082cb447244e82e0d2b7a08945))

### Breaking Changes

- **state**: Every MovementType member except SPY changed number or name. SUPPORT is DEFENCE,
  TRANSPORT is MARKET, and RAID, SETTLE, CAMP, TRADE, ATTACK_CAMP, RAID_CAMP and RETURN are removed.

- **state**: Is_incoming and is_outgoing need the local player id and no longer read D. is_returning
  is D == 1. get_outgoing_movements() lists your armies heading out, not armies on their way home.
  is_transport is a market transport only; troops moved between your own castles are is_travel.

- **state**: Movement no longer has the MID, T, PT, TT, D, TID, KID, SID, OID and HBW attributes.
  Use movement_id, movement_type, progress_time, total_time, direction, target_id, kingdom_id,
  source_id, owner_id and horse_booster_id, which keep their names and meanings.

- **state**: On_movement_arrived is time-based and can fire from a query; STALE_MOVEMENT_GRACE is
  gone. on_movement_recalled no longer fires on mrm: use on_movement_removed for removals.


## v0.35.3 (2026-09-24)

### Bug Fixes

- **map**: Tidy owner records and cover them with a live-shaped test
  ([`64e2095`](https://github.com/eschnitzler/EmpireCore/commit/64e20954de217d06af7ccce75368c006f6e10e8a))


## v0.35.2 (2026-09-24)

### Bug Fixes

- **castle**: Look up a castle's type and kingdom when renaming it
  ([`04fd1f3`](https://github.com/eschnitzler/EmpireCore/commit/04fd1f330615d2ff562aafdd24d5928f247af45b))


## v0.35.1 (2026-09-23)

### Bug Fixes

- **ranking**: Retain response and entry metadata
  ([`d2338e9`](https://github.com/eschnitzler/EmpireCore/commit/d2338e91c3be787d3d09d406bb40acc2aac72dc4))

### Documentation

- Add contact details to the README
  ([`58abfb8`](https://github.com/eschnitzler/EmpireCore/commit/58abfb88d292d83bf34aa0eb81884e21b8e6be1e))


## v0.35.0 (2026-09-22)

### Bug Fixes

- **castle**: Read gcl and dcl in the shape the server sends
  ([`3210f47`](https://github.com/eschnitzler/EmpireCore/commit/3210f476a1ea764ebc709abc2ce9bce25618bf12))

- **map**: A row's owner is its player id for every owned type
  ([`4033349`](https://github.com/eschnitzler/EmpireCore/commit/403334901f4b8857c483fdc2981d3e1559d32fba))

- **map**: An unclaimed outpost has no owner
  ([`4010955`](https://github.com/eschnitzler/EmpireCore/commit/4010955c67eea797bb7c7dec1c58fa9d8f3fd8dd))

- **map**: Only rows that carry an owner report one
  ([`e35edee`](https://github.com/eschnitzler/EmpireCore/commit/e35edee2c62472be09fe30967b156cd0c5434930))

### Features

- **castle**: Model every gcl and dcl field the game client reads
  ([`ace984b`](https://github.com/eschnitzler/EmpireCore/commit/ace984bd7d6e3aa7b53450b9a34ecdd7ac2c69fb))

- **castle**: Typed storage and production from dcl, kingdom from the list
  ([`df2d0fb`](https://github.com/eschnitzler/EmpireCore/commit/df2d0fbb4959665ec7398d410d157d4592fdd175))

### Refactoring

- **castle**: Alias each positional gcl row field to its index
  ([`a4d20b8`](https://github.com/eschnitzler/EmpireCore/commit/a4d20b8fea03901e06f7768e59138bf9bdef51ac))

- **castle**: Alias every gpa per-resource key
  ([`bddfea7`](https://github.com/eschnitzler/EmpireCore/commit/bddfea7cb7782e7df7126ff08c591cbe0b2a0bc2))

- **castle**: One aliased field per dcl wire key, derived rates as properties
  ([`ea7a8b5`](https://github.com/eschnitzler/EmpireCore/commit/ea7a8b52f57c3ba0ce2ef1eafd6bd83fedeb6b6c))

### Testing

- **castle**: Narrow the optional castle before reading its units
  ([`8d79e0c`](https://github.com/eschnitzler/EmpireCore/commit/8d79e0c9950289f81017d2df5c3d1afcee59114b))

### Breaking Changes

- **castle**: CastleInfo lost level and gained owner_id. DetailedCastleInfo lost buildings,
  population and max_population; items is now units. BuildingInfo is gone. GetDetailedCastleRequest
  no longer takes a castle id. GetCastlesResponse and GetDetailedCastleResponse carry player_id and
  a castles list.

- **map**: MapAreaItem.owner_id is the player id for type-1 and type-12 rows too. Use the new
  location_id for the castle id.


## v0.34.0 (2026-09-09)

### Bug Fixes

- **attack**: Buff the courtyard's units too
  ([`3219224`](https://github.com/eschnitzler/EmpireCore/commit/3219224a423a8c5d3c45c90b8d66ed08e218acf0))

- **attack**: Fall back to the map when the pre-calculation is refused
  ([`f6f1f01`](https://github.com/eschnitzler/EmpireCore/commit/f6f1f01ac0017ce131b5edd3c1c12c783d90f1b3))

- **attack**: Return to the attacking castle after scanning
  ([`cff2d70`](https://github.com/eschnitzler/EmpireCore/commit/cff2d7015510f1686394b31912d24d13d1a7412f))

- **attack**: Say which of three things left a target with no level
  ([`9399a4b`](https://github.com/eschnitzler/EmpireCore/commit/9399a4ba58f069fdc39672a8cef1b5ad2c69b9a0))

- **attack**: The commander's own equipment widens the flanks
  ([`16b8e70`](https://github.com/eschnitzler/EmpireCore/commit/16b8e7002a43932df90797eb2931da3cad8703ca))

- **combat**: A daimyo township is not a camp
  ([`a8a27e8`](https://github.com/eschnitzler/EmpireCore/commit/a8a27e8ab2f298a8ac59d5d5e131b63c72dd77bc))

- **combat**: A row too short to name its camp is not a camp
  ([`678986f`](https://github.com/eschnitzler/EmpireCore/commit/678986f192bea2afae5a2ba89a870e9d662b661c))

- **combat**: A unit with an empty attack column stays at zero
  ([`d749e95`](https://github.com/eschnitzler/EmpireCore/commit/d749e95d1dff0ff3361304378313838acf4f21c4))

- **combat**: Act on the review's confirmed findings
  ([`bc5bbf2`](https://github.com/eschnitzler/EmpireCore/commit/bc5bbf29de66a0aa2b40644f43e87414b62938c2))

- **combat**: Apply every condition an effect carries
  ([`4af43b3`](https://github.com/eschnitzler/EmpireCore/commit/4af43b3548831ac13a38fffc173e8bd576084e31))

- **combat**: Budget a tool per wave, not per flank
  ([`8d811a5`](https://github.com/eschnitzler/EmpireCore/commit/8d811a5e751c85d0358442e9740cbcd1a5459b30))

- **combat**: Feed a tool's effect malus back into the reductions
  ([`2e11329`](https://github.com/eschnitzler/EmpireCore/commit/2e11329d1c7776e435f75eb050a8ed53b9b3689f))

- **combat**: Gate legend skills on a legendary fight, and drop the invented cap
  ([`4fd20f5`](https://github.com/eschnitzler/EmpireCore/commit/4fd20f51a36b5dee60e55af6ae10ee8b7b248559))

- **combat**: Only the middle flank meets the gate
  ([`11215d4`](https://github.com/eschnitzler/EmpireCore/commit/11215d4fa2c39412efff57d07941231130ea702f))

- **combat**: Read a keyed effect's value, not its key
  ([`b8667d9`](https://github.com/eschnitzler/EmpireCore/commit/b8667d925e0f56bb8b24f2e123e6c292aaf757b1))

- **combat**: Scale the flanks and the middle by their own bonuses
  ([`9161e9b`](https://github.com/eschnitzler/EmpireCore/commit/9161e9b7271a300e16f2775c3a4054f367fa5364))

- **combat**: Size a wave by the level its target defends at
  ([`bdf48b6`](https://github.com/eschnitzler/EmpireCore/commit/bdf48b6c3cb0c5c0ddfa481b90599b2b45c37552))

- **combat**: Size a wave from the general's unit limits
  ([`9eba05c`](https://github.com/eschnitzler/EmpireCore/commit/9eba05cba9ebd949bc07a19f58f45d0852f580ba))

- **combat**: Size a wave from the target owner's level
  ([`2cb8674`](https://github.com/eschnitzler/EmpireCore/commit/2cb8674bb614dee1de4902e343bf12859421b5fe))

- **combat**: Tool bonuses are fractions, and each placed tool feeds back
  ([`ccd7023`](https://github.com/eschnitzler/EmpireCore/commit/ccd7023100b481266237a3f4706dede871d95ac2))

- **gamedata**: Do not reuse a cache written against older tables
  ([`5046412`](https://github.com/eschnitzler/EmpireCore/commit/504641241db7ad63afe63e6f05091be5e3a01e6f))

- **map**: Read an NPC camp's own fields instead of guessing them
  ([`2e786a8`](https://github.com/eschnitzler/EmpireCore/commit/2e786a8c2bbde25c88bf904d03c264ff089ad1ec))

- **protocol**: Stop treating any payload key E as an error code
  ([`b5ada61`](https://github.com/eschnitzler/EmpireCore/commit/b5ada61965ad4db09be872dd046056726f06f691))

### Chores

- Keep local review notes out of the repo
  ([`63b75a2`](https://github.com/eschnitzler/EmpireCore/commit/63b75a223965c5ec75ad1c9b4d8045d2c4f7c03a))

### Code Style

- Use American spelling throughout
  ([`70112db`](https://github.com/eschnitzler/EmpireCore/commit/70112dbc3e42b6a4f107a3a0ccb7e1f08126ad52))

### Documentation

- Add a fill-waves example
  ([`99deb7b`](https://github.com/eschnitzler/EmpireCore/commit/99deb7bd36d58549c501b39c063ccf30e0cb0112))

- The example and README only need a target now
  ([`649ea60`](https://github.com/eschnitzler/EmpireCore/commit/649ea604a027675227837126ca06e4ed2694ae48))

- **combat**: Catalogue every effect that can change a wave
  ([`5dcf736`](https://github.com/eschnitzler/EmpireCore/commit/5dcf736766f306b1614d5a30aa7d598100db10a7))

- **combat**: Close the relic map encoding question
  ([`0b41e99`](https://github.com/eschnitzler/EmpireCore/commit/0b41e99ee005829312d5db527a3a181dc1d6fff4))

- **combat**: Record which level drives which quantity
  ([`ea42a90`](https://github.com/eschnitzler/EmpireCore/commit/ea42a90a83a97efc44f323eaa93fb4e9b2f94699))

- **combat**: Say why the unit buff checks no conditions
  ([`8d52109`](https://github.com/eschnitzler/EmpireCore/commit/8d521098305516f2a00f202b9b7b081477c3bf90))

- **combat**: State which way the tool discard quirk was decided
  ([`8dfa4e4`](https://github.com/eschnitzler/EmpireCore/commit/8dfa4e487d4aebc1364ce6cef053453952a7d5f0))

### Features

- **attack**: Build a complete attack in one call, and let tools into the pool
  ([`9614a0a`](https://github.com/eschnitzler/EmpireCore/commit/9614a0ab37929deed27ef375cde65c93864ab3bb))

- **attack**: Count the Hall of Legends skills in flank sizing
  ([`8ea1045`](https://github.com/eschnitzler/EmpireCore/commit/8ea1045bbd79e9ca2a67050038107dcc03bf2ee2))

- **attack**: Derive a camp's level from its victory count
  ([`5398d94`](https://github.com/eschnitzler/EmpireCore/commit/5398d9410f824370e8ac899c2bde1642172a891e))

- **attack**: Fill waves from a castle's inventory
  ([`f6995a8`](https://github.com/eschnitzler/EmpireCore/commit/f6995a8e97a97f263f0aca7d3e1cc2e61bce1652))

- **attack**: Fill waves on samurai and daimyo targets
  ([`51d1cf1`](https://github.com/eschnitzler/EmpireCore/commit/51d1cf1d4ab2823a54829cf23e8c597fa9819f6f))

- **attack**: Read a spied castle's defenders per flank
  ([`d65d5f8`](https://github.com/eschnitzler/EmpireCore/commit/d65d5f810ccb7016eb1823b0483830f5666cc157))

- **attack**: Read the area type off the target row
  ([`fbcfd5e`](https://github.com/eschnitzler/EmpireCore/commit/fbcfd5e7926884f536e7cb4ea49feb7780eda549))

- **attack**: Read the attack pre-calculation
  ([`21cbda7`](https://github.com/eschnitzler/EmpireCore/commit/21cbda700f538b130cecc9deb3626ca061e46d83))

- **attack**: Read the defending castellan's effects
  ([`69c251b`](https://github.com/eschnitzler/EmpireCore/commit/69c251b3147cf1a35a294da95cc6b0dae0c3de27))

- **attack**: Read the generals and skills that size a wave
  ([`ac3f8f9`](https://github.com/eschnitzler/EmpireCore/commit/ac3f8f91fd362c6e39303c78079d7665702eeca1))

- **combat**: Buff unit attack values from active global effects
  ([`17086b7`](https://github.com/eschnitzler/EmpireCore/commit/17086b765f1499075085621ee820b4dd0d73cc2b))

- **combat**: Count a tool's effects, not just its columns
  ([`999a182`](https://github.com/eschnitzler/EmpireCore/commit/999a1829605b75c9201038e13cfbc2eba3383cd3))

- **combat**: Fill a wave's units the way the client's auto-fill does
  ([`651a07b`](https://github.com/eschnitzler/EmpireCore/commit/651a07b61a206cc43f2de960a75615fe2ff455fd))

- **combat**: Fill tools and the courtyard wave into an attack
  ([`bb2b16e`](https://github.com/eschnitzler/EmpireCore/commit/bb2b16e428e6be6f34ac8cf7cde5a14afb642db0))

- **combat**: Gate tools by target, and send every yard slot
  ([`f6cbef3`](https://github.com/eschnitzler/EmpireCore/commit/f6cbef361fdbd596c063b1c01971bf9f2791efa8))

- **combat**: Give camps their walls, and fix a scaling round-trip
  ([`8cc4387`](https://github.com/eschnitzler/EmpireCore/commit/8cc4387682e146dab351a804c7ea27fbde79697d))

- **combat**: Pick tools with the client's five strategies
  ([`11c2efa`](https://github.com/eschnitzler/EmpireCore/commit/11c2efa2f9490eb97f856b6552f96ef36a21b621))

- **combat**: Place tools in a flank's slots
  ([`cbbb547`](https://github.com/eschnitzler/EmpireCore/commit/cbbb54741fc4eba0b41615cab87014b4388debd6))

- **combat**: Port the flank attack and defence maths
  ([`8615432`](https://github.com/eschnitzler/EmpireCore/commit/861543222bb03e711b7294eb6c4d88619a5e966e))

- **combat**: Read fortification from the event camp tables
  ([`fbf61c3`](https://github.com/eschnitzler/EmpireCore/commit/fbf61c38e2af9f055b41263f9d97a7653d61249a))

- **combat**: Resolve commander bonuses, in the right id space
  ([`15c366c`](https://github.com/eschnitzler/EmpireCore/commit/15c366c92909bc67a83b2540d30a7e690ca43f79))

- **combat**: Resolve the bonus sources that are not equipment
  ([`3ec7163`](https://github.com/eschnitzler/EmpireCore/commit/3ec71633bf0f85350ef12657154c62770439eb13))

- **combat**: Score units with the commander's attack multipliers
  ([`75c21a8`](https://github.com/eschnitzler/EmpireCore/commit/75c21a8dca64e26e99291fe903dcb7d566318698))

- **combat**: Size a wave from the level instead of asking the caller
  ([`644cf54`](https://github.com/eschnitzler/EmpireCore/commit/644cf5415735ead48eb4336c16ade17e2ea7b5ed))

- **combat**: Size the courtyard wave
  ([`8439bd4`](https://github.com/eschnitzler/EmpireCore/commit/8439bd46fcf7cd1bda82b643c572b892ca9930e5))

- **combat**: Take the live strength of a global effect, and its level bracket
  ([`d7dc1ff`](https://github.com/eschnitzler/EmpireCore/commit/d7dc1ff186793c329d4940df51e15751d333df23))

- **commanders**: Parse the general assigned to a commander
  ([`3dcafdf`](https://github.com/eschnitzler/EmpireCore/commit/3dcafdf405ca714e5eb4ed5b79ab35cc9cf133d2))

- **gamedata**: Load unit and tool stats from the items payload
  ([`fe794d6`](https://github.com/eschnitzler/EmpireCore/commit/fe794d65c87c300130e7ead4c25884635a85a5d9))

- **gamedata**: Parse the combat and camp-defence tables
  ([`cbc32d9`](https://github.com/eschnitzler/EmpireCore/commit/cbc32d932996dd506e0847f47de9d945a9475644))

- **map**: Read the structures that defend a location
  ([`6574428`](https://github.com/eschnitzler/EmpireCore/commit/6574428aea5be360225bbe2f930efe79e8abe783))

### Refactoring

- **attack**: Give fill_attack a target, not the target's data
  ([`0b4849b`](https://github.com/eschnitzler/EmpireCore/commit/0b4849b05bc8d1effd0c8228ac0f03c3abe77066))

- **attack**: Read the inventory once for both passes
  ([`1a0a23a`](https://github.com/eschnitzler/EmpireCore/commit/1a0a23ad67b79009ec69043847135993cb218b5a))

- **attack**: Simplify the fill path
  ([`275662b`](https://github.com/eschnitzler/EmpireCore/commit/275662b3e19ecdc614af4cfa3e64edb9fc6e0bfa))

### Testing

- Type-check clean under the CI configuration
  ([`7ece9a0`](https://github.com/eschnitzler/EmpireCore/commit/7ece9a03ecd944d4c136acb61cfa9a45474703ae))

- **attack**: Pin the castellan to the defence it builds
  ([`aff6982`](https://github.com/eschnitzler/EmpireCore/commit/aff6982b8cee7acc36688ab124f9d6b3125d6049))

- **attack**: Pin the courtyard wave to the RW field
  ([`37028ac`](https://github.com/eschnitzler/EmpireCore/commit/37028accaba3a67c4523954f20050c54c8ce438d))

- **attack**: Stop the courtyard assertion passing on an empty wave
  ([`b50f942`](https://github.com/eschnitzler/EmpireCore/commit/b50f9420786839fcebe4c71824a850ec91376db4))

- **combat**: Assert a roleless unit yields no stack value
  ([`1eec625`](https://github.com/eschnitzler/EmpireCore/commit/1eec6255446f7539768853b13911e2dc55430630))

- **combat**: Assert the solver's invariants over random inputs
  ([`e352008`](https://github.com/eschnitzler/EmpireCore/commit/e352008c7e99c050a997c1d95b37b2a0959108b2))

- **combat**: Pin that an out-reduced defence needs no tool
  ([`033eb9c`](https://github.com/eschnitzler/EmpireCore/commit/033eb9ca7347e4354772a9afc09fad24ad172999))


## v0.33.0 (2026-08-25)

### Bug Fixes

- **army**: Read the unit inventory the shape a live server sends
  ([`8839447`](https://github.com/eschnitzler/EmpireCore/commit/883944750f78909859adea994d07218b30e71150))

- **attack**: Require a commander instead of defaulting LID to 0
  ([`748b277`](https://github.com/eschnitzler/EmpireCore/commit/748b277ec111159057c661307ef75ca31eb9bb44))

- **commanders**: Parse the equipment graphic field as an int
  ([`116d373`](https://github.com/eschnitzler/EmpireCore/commit/116d373e2f3cc989cc2ebf2356a13c56cb8e4c7e))

- **commanders,attack**: Stop accessors raising on drifted payloads
  ([`45bc153`](https://github.com/eschnitzler/EmpireCore/commit/45bc153ecd80e199e40bfad001dc74af1ebf56e7))

- **map**: Correct the map item type table and report the ruin flag
  ([`c3993eb`](https://github.com/eschnitzler/EmpireCore/commit/c3993eb903e39f036dbbb1b53b7faff7e0856d49))

### Documentation

- **protocol**: Re-extract the client bundle and correct the cra fields
  ([`0fc26df`](https://github.com/eschnitzler/EmpireCore/commit/0fc26df7564fb0b0d771dbea73261ea0b2e6a1ab))

- **protocol**: Record the client's map object types
  ([`3ad804d`](https://github.com/eschnitzler/EmpireCore/commit/3ad804d0b02d19d06d11b5f39d0867047051db30))

- **readme**: Document the commander and attack APIs with an example
  ([`59bd5bb`](https://github.com/eschnitzler/EmpireCore/commit/59bd5bbb0d8d37b8380e4b5136ba8ecbc6d9154e))

### Features

- **attack**: Confirm cra against a live server and parse its response
  ([`86a3a57`](https://github.com/eschnitzler/EmpireCore/commit/86a3a572eb4e4b3e09cd8217d16a507dd4e35af4))

- **attack**: Send attacks with waves and a chosen commander
  ([`00bad10`](https://github.com/eschnitzler/EmpireCore/commit/00bad104d6326b97449845f97f6a1660f1cc9215))

- **commanders**: Rename lords to commanders and parse the full entry
  ([`97f41fa`](https://github.com/eschnitzler/EmpireCore/commit/97f41fade9b3b9769dc2b7d2165e151a231fc455))

### Breaking Changes

- **attack**: AttackService.send_attack now takes commander_id as a required argument, positioned
  after waves, and empire_core.services.attack.NO_COMMANDER is removed.

- **commanders**: Client.lords is now client.commanders, LordsService is CommandersService,
  get_lords() is get_commanders(), the Lord model is Commander with lord_id renamed to commander_id,
  and the lord_id keyword of CastleService.send_support is now commander_id.


## v0.32.1 (2026-08-19)

### Bug Fixes

- **spy**: Trade accuracy for risk instead of refusing the mission
  ([`ac7b892`](https://github.com/eschnitzler/EmpireCore/commit/ac7b89265352657cce68bb49af0e47a01c452a97))

### Code Style

- **tests**: Apply ruff format to the spy report fixtures
  ([`c732d1d`](https://github.com/eschnitzler/EmpireCore/commit/c732d1d7a1f95e53316d4e09b38fe2f58fecfc29))


## v0.32.0 (2026-08-18)

### Features

- **spy**: Forward a spy report to other players
  ([`d3ef597`](https://github.com/eschnitzler/EmpireCore/commit/d3ef5977b6d030ba812b431d9709c7210f28a864))

- **spy**: Parse the spied castle's fortifications
  ([`c81be4c`](https://github.com/eschnitzler/EmpireCore/commit/c81be4cec5fb24a8ee5598fd88fc3b0b4e2ffae8))

- **spy**: Split a spy report's army by the position it holds
  ([`0532dfb`](https://github.com/eschnitzler/EmpireCore/commit/0532dfbdab4fde9aee9be3746b08cec5b6ab3549))

### Testing

- **spy**: Narrow SpyPlan before reading it
  ([`7431b5e`](https://github.com/eschnitzler/EmpireCore/commit/7431b5e1529e65a482f5f32105cb35926194af6c))


## v0.31.0 (2026-08-18)

### Bug Fixes

- **network**: Drop a session the server has stopped answering
  ([`8d8cce1`](https://github.com/eschnitzler/EmpireCore/commit/8d8cce1e5724d918de898f5998ba0f00a5b49e8b))

- **protocol**: Wait for jaa when selecting a castle
  ([`3d563d3`](https://github.com/eschnitzler/EmpireCore/commit/3d563d37c226fbd5505dea47d715ba3c4b1655f3))

- **spy**: Read the mission outcome instead of assuming it succeeded
  ([`2a9df22`](https://github.com/eschnitzler/EmpireCore/commit/2a9df2209837fb797bf745a59ad30af0df32fcfd))

### Features

- **spy**: Size a mission from the game's own risk formula
  ([`26528c9`](https://github.com/eschnitzler/EmpireCore/commit/26528c9ae53af1ad89bfeb745b2c92f206ab3b95))

### Refactoring

- **spy**: Treat max risk as a send gate, not a target
  ([`e10cbd3`](https://github.com/eschnitzler/EmpireCore/commit/e10cbd384ca68ed976ad3ef3d3b98e32eb1118af))


## v0.30.3 (2026-08-12)

### Bug Fixes

- **client**: Pass include_unowned_types through the scan_chunks facade
  ([`6e73d04`](https://github.com/eschnitzler/EmpireCore/commit/6e73d040c3ba1761430833ac5f2b839957549a99))


## v0.30.2 (2026-08-12)

### Bug Fixes

- **scanner**: Pass include_unowned_types through scan_chunks
  ([`1ded741`](https://github.com/eschnitzler/EmpireCore/commit/1ded74111fc41188b6a9a2d1e2037f699c856c43))


## v0.30.1 (2026-08-11)

### Bug Fixes

- **scanner**: Stop reporting normal short map entries as schema drift
  ([`2523fae`](https://github.com/eschnitzler/EmpireCore/commit/2523fae83561e890951d7a16eddf520b2c0d7494))


## v0.30.0 (2026-08-11)

### Bug Fixes

- **accounts**: Stop logging plaintext passwords for invalid entries
  ([`7909709`](https://github.com/eschnitzler/EmpireCore/commit/79097099bac6cf6384c49fa650b6a9038582a61c))

- **accounts,pool**: Credential hygiene and honest failure reporting
  ([`4746562`](https://github.com/eschnitzler/EmpireCore/commit/47465629ea9705c6c82219b7a9e1832fd76c2973))

- **client**: Guard handler registry, type the scan API, pace bulk requests
  ([`b028fee`](https://github.com/eschnitzler/EmpireCore/commit/b028fee3ccb7e4c674893a760936f18929a017c5))

- **config,pool**: Per-install id, immutable default config, scoped leases
  ([`a6ae59f`](https://github.com/eschnitzler/EmpireCore/commit/a6ae59fef072aae1aa94cbc89824fc3690cca67c))

- **connection**: Apply state updates before waking request waiters
  ([`5e52a4e`](https://github.com/eschnitzler/EmpireCore/commit/5e52a4e687b660c828669e4259b0dbc83718e977))

- **connection**: Redact credentials from frame logs and serialize lifecycle
  ([`fdcac48`](https://github.com/eschnitzler/EmpireCore/commit/fdcac48fda36b60b2949c91251bd4c1f888e2f9f))

- **connection,client**: Survive malformed frames and report typed errors
  ([`c2d1e95`](https://github.com/eschnitzler/EmpireCore/commit/c2d1e957ff94200e63d88b80f6f80564e806014e))

- **protocol**: Correct moving-flag parsing and bound hostile frames
  ([`a6b2c19`](https://github.com/eschnitzler/EmpireCore/commit/a6b2c198e5e9cce6f9c763eccefc0edc01781a9d))

- **protocol**: Log every degradation path and stop accessors raising raw pydantic
  ([`4b93996`](https://github.com/eschnitzler/EmpireCore/commit/4b939960770e939766a25cb0a63645231ae025b1))

- **protocol**: Make packet parsing total and guard alliance arrays
  ([`bbe3ec3`](https://github.com/eschnitzler/EmpireCore/commit/bbe3ec3b5fde5189ca02ad6f2794f254e24a7cde))

- **protocol**: Stop drifted payloads crashing documented accessors
  ([`51b08ec`](https://github.com/eschnitzler/EmpireCore/commit/51b08ecfa5179ce03387ba1606b2145e6b80e38b))

- **release**: Keep uv.lock in step with the released version
  ([`80f7e2c`](https://github.com/eschnitzler/EmpireCore/commit/80f7e2cecb99c0c7c9b529857ac4834f6e20b6c7))

- **scanner**: Report server errors and abandoned chunks as failures
  ([`1f92e45`](https://github.com/eschnitzler/EmpireCore/commit/1f92e45b2ffdd3de943be6dfe129e60b900caad5))

- **scanner**: Surface dropped map entries instead of debug-logging them
  ([`005c7e0`](https://github.com/eschnitzler/EmpireCore/commit/005c7e0b5a65ebf9c6334296f236758ed1d6f4e6))

- **services**: Typed errors for drifted payloads and a chat unsubscribe
  ([`47fc2f3`](https://github.com/eschnitzler/EmpireCore/commit/47fc2f33d9c4bc4bf0742d096270bfb359edd55d))

- **state**: Atomic player and castle merges, locked callback registration
  ([`f8e4989`](https://github.com/eschnitzler/EmpireCore/commit/f8e4989f6ebad8a29126ba707e26d3f5bfe0ecff))

- **state**: Locked player snapshots and honest movement lifecycle
  ([`dded0a5`](https://github.com/eschnitzler/EmpireCore/commit/dded0a58697bfcfafe57702f8c6fa7a239e0a3ad))

- **state**: Thread-safe movement reads and atomic castle updates
  ([`f6487a0`](https://github.com/eschnitzler/EmpireCore/commit/f6487a05686a87c54de139a4901c376a3ba52e0b))

- **utils**: Stop reporting CDN failures as empty results
  ([`51f512a`](https://github.com/eschnitzler/EmpireCore/commit/51f512a574339ad31c54e85812431c27e2c69f0b))

### Chores

- Refresh uv.lock after the version bump
  ([`cb7c67c`](https://github.com/eschnitzler/EmpireCore/commit/cb7c67c9fa85d61b15bd96064196b2311e744c2a))

### Documentation

- **contributing**: Stop teaching the failure modes this review had to fix
  ([`00fad2e`](https://github.com/eschnitzler/EmpireCore/commit/00fad2ed1c4c19eaac08da3e9f698b0642e320d3))

- **readme**: Document the state, pool and error APIs, and tidy the rest
  ([`269143d`](https://github.com/eschnitzler/EmpireCore/commit/269143df3608ecbcff1f723dfe6272e3cf3b9914))

- **state**: Document the snapshot accessors and freshness rules
  ([`6826cde`](https://github.com/eschnitzler/EmpireCore/commit/6826cde48e437fb3feab67fcb872992cd9f16d23))

### Features

- **api**: Export the pool and troop helpers, fix the docs that trap users
  ([`82c8a23`](https://github.com/eschnitzler/EmpireCore/commit/82c8a2394e7297aeb66e04fbb0289ecc27dc18fa))

- **api**: Re-export the de-facto public surface from the package root
  ([`c1d76f5`](https://github.com/eschnitzler/EmpireCore/commit/c1d76f5e9a65195db96e642ebf9f4a163e23c5c5))

- **packaging**: Ship py.typed and make storage deps optional
  ([`0afae77`](https://github.com/eschnitzler/EmpireCore/commit/0afae7724ddf395f821237292e2baf18353eb7db))

- **state**: Pass movements to arrival callbacks and expose freshness
  ([`41b2c68`](https://github.com/eschnitzler/EmpireCore/commit/41b2c685dddaaf7a3072c9d314657cec1670b65c))

### Testing

- Cover the services layer, login handshake and drifted payloads
  ([`ad10342`](https://github.com/eschnitzler/EmpireCore/commit/ad103420e072b49ed52d51bbb0f4e5ed72abb756))

- Keep the type checker happy about deliberately malformed fixtures
  ([`5b7c618`](https://github.com/eschnitzler/EmpireCore/commit/5b7c618f2e9576804122b581936c7b3ece26b577))

### Breaking Changes

- **accounts,pool**: Lease() raising instead of returning None, and .env no longer being read at
  import.

- **connection,client**: Connect() raises NetworkError instead of leaking websocket-client/socket
  exceptions, and send(wait=True)/request() raise PacketError instead of pydantic ValidationError.

- **packaging**: Sqlmodel and aiosqlite moved to the optional [storage] extra; importing
  empire_core.storage without it raises an ImportError.

- **protocol**: Get_moving_flags() keys results by player id (was castle id) and only includes
  castles that are actually relocating.

- **utils**: Get_active_events() and get_troop_ids() raise NetworkError on CDN failure instead of
  returning an empty list/set.


## v0.29.0 (2026-08-11)

### Features

- Add include_unowned option to scan_kingdom
  ([`15cdb2e`](https://github.com/eschnitzler/EmpireCore/commit/15cdb2ed0feebabac39079d5f3f5cf37656b84f9))


## v0.28.0 (2026-07-07)

### Bug Fixes

- Harden protocol model registry and parsing robustness
  ([`cb5f64c`](https://github.com/eschnitzler/EmpireCore/commit/cb5f64c2b998d0f5502397d548ed9c8b6bb4a3da))

- Remove committed credentials, declare requests dep, gate releases on tests
  ([`924f8a2`](https://github.com/eschnitzler/EmpireCore/commit/924f8a234594744fdbc40e0906c7f15effe4a63f))

- Satisfy mypy in test files and Account.alias default
  ([`d22947b`](https://github.com/eschnitzler/EmpireCore/commit/d22947b57e2f9ab8cf2e251df764feb69499487e))

- State manager thread-safety and movement lifecycle
  ([`d968681`](https://github.com/eschnitzler/EmpireCore/commit/d968681d7b692fc2dd077741e76d353f0b81132d))

- Typed error propagation and race-free request/response correlation
  ([`0c1440a`](https://github.com/eschnitzler/EmpireCore/commit/0c1440a5197c1e218df86ec577b1610568710094))

### Code Style

- Apply ruff-format to map scanner tests
  ([`2aa01bb`](https://github.com/eschnitzler/EmpireCore/commit/2aa01bb04331473a5737dcaf1a26c1c5969423a5))

### Documentation

- Align README and design docs with the shipped implementation
  ([`db96fb9`](https://github.com/eschnitzler/EmpireCore/commit/db96fb9675ab0385c841e7a03765f5be78b71e18))

- Document map scanning, chunk pacing, and cheap re-scans in README
  ([`01b3b88`](https://github.com/eschnitzler/EmpireCore/commit/01b3b885bbaacd51b50b79a812374926dccf6d0a))

### Features

- Add scan_chunks + content_chunks for cheap targeted re-scans
  ([`a490634`](https://github.com/eschnitzler/EmpireCore/commit/a490634d4fd22c2002d18874623bed5f19b2a71e))

- Pace kingdom-scan requests with a configurable chunk_delay
  ([`449ed1d`](https://github.com/eschnitzler/EmpireCore/commit/449ed1da06be92367902d5219c48b04a50b12023))

### Refactoring

- Collapse service boilerplate onto typed request/execute helpers
  ([`898d193`](https://github.com/eschnitzler/EmpireCore/commit/898d193710992751d21e382482cb3abce1be9418))

- Drop unused config constants
  ([`df12625`](https://github.com/eschnitzler/EmpireCore/commit/df12625687a6e7ce05d35d26db1cf8011cebb878))

- Hoist unnecessary inline imports to module scope
  ([`e22c0e1`](https://github.com/eschnitzler/EmpireCore/commit/e22c0e1bbe1fdfc858ff42ef1526a17dbe1d9024))

- Prune dead modules, fix pool/accounts lifecycle, add test suite
  ([`843d835`](https://github.com/eschnitzler/EmpireCore/commit/843d8354915ed804423a6568ba9eb9c7984dd9ca))

### Breaking Changes

- Client.send(wait=True) and query methods now raise typed exceptions instead of returning None on
  failure.


## v0.27.0 (2026-05-29)

### Chores

- Update GitHub Actions to Node.js 24-compatible versions
  ([`daf11af`](https://github.com/eschnitzler/EmpireCore/commit/daf11af438df10cb40942a79ae7bdfadb1625dc2))

### Features

- Expand gdi model with full O fields and typed castle parsing
  ([`d8ecd75`](https://github.com/eschnitzler/EmpireCore/commit/d8ecd75553aea62ccf48e2a170badf395763052e))


## v0.26.0 (2026-05-26)

### Bug Fixes

- Apply ruff formatting and remove unused import in events integration
  ([`87b0c08`](https://github.com/eschnitzler/EmpireCore/commit/87b0c088e7f2e747cadb9fc89e62072acbb9abea))

### Features

- Add GameEvent dataclass and get_active_events CDN resolver
  ([`5fccf23`](https://github.com/eschnitzler/EmpireCore/commit/5fccf23827ed848909785b728c29e580aab80a32))

- Add get_active_events to EmpireClient and export GameEvent
  ([`bf8183f`](https://github.com/eschnitzler/EmpireCore/commit/bf8183f35433b3769b365082269f18e76c60dd2a))

### Refactoring

- Use direct import for GameEvent, drop TYPE_CHECKING guard
  ([`d80b064`](https://github.com/eschnitzler/EmpireCore/commit/d80b064bb188c723c3829dd07aeb40faca439d3e))

### Testing

- Add smoke tests to fix CI test collection failure
  ([`c439f01`](https://github.com/eschnitzler/EmpireCore/commit/c439f01d8e53afae95a274894e05e3c3982b0bcb))


## v0.25.7 (2026-05-08)

### Bug Fixes

- Remove irrelevant tests
  ([`700ad19`](https://github.com/eschnitzler/EmpireCore/commit/700ad19b0668b7674f6da1f06e42c53ad7adf0ad))


## v0.25.6 (2026-05-07)

### Bug Fixes

- Prevent socket disconnects via dual-layer sliding window rate limiter
  ([`6c4218e`](https://github.com/eschnitzler/EmpireCore/commit/6c4218e1537614c04befcb4d8314a79962404b20))

### Chores

- Remove inline imports and unused files
  ([`efebab6`](https://github.com/eschnitzler/EmpireCore/commit/efebab645b9083390b415c65969a683bcb1a2b3f))


## v0.25.5 (2026-05-07)

### Bug Fixes

- Improve map scanner resilience and fix waiter race condition
  ([`f843e77`](https://github.com/eschnitzler/EmpireCore/commit/f843e770fa8eeef7b649939c5e395a38e352a1bb))


## v0.25.4 (2026-05-07)

### Bug Fixes

- Serialize WebSocket sends with a threading.Lock
  ([`3f22a8c`](https://github.com/eschnitzler/EmpireCore/commit/3f22a8c8e4b082371b8ee563b8edaa56ffd02272))


## v0.25.3 (2026-04-26)

### Bug Fixes

- Remove duplicate Army class from world_models
  ([`6085bf7`](https://github.com/eschnitzler/EmpireCore/commit/6085bf70f9ab8ac89d9af8a7f85c265c5deea07d))

### Chores

- Delete stale TODO.md
  ([`103c2b8`](https://github.com/eschnitzler/EmpireCore/commit/103c2b8ef78dbe80a06a1341e6d679cb032e5982))

- Remove archive directories with dead code
  ([`c6416f4`](https://github.com/eschnitzler/EmpireCore/commit/c6416f4b72c917cf009b065c48610be443a21e5e))

### Documentation

- Remove outdated pygge comparison files
  ([`e9dd4dd`](https://github.com/eschnitzler/EmpireCore/commit/e9dd4dd92ecff8568952ee2b484e19b73138163b))

### Refactoring

- Improve EmpireClient type safety and fix alliance chat encoding
  ([`c88957d`](https://github.com/eschnitzler/EmpireCore/commit/c88957d42f1b1a9f2e007076fbde0bdab95843f8))

- Modernize typing imports to built-in syntax
  ([`5c8d5cc`](https://github.com/eschnitzler/EmpireCore/commit/5c8d5cc8a6703e37039529e39faf4b2e6a2f3396))

- Remove unnecessary TYPE_CHECKING guards in services
  ([`6a98545`](https://github.com/eschnitzler/EmpireCore/commit/6a98545f9b1bc0e87d9f3bfea1be4354068f0f0b))


## v0.25.2 (2026-04-26)

### Bug Fixes

- Correct GetTargetInfoRequest payload for adi command
  ([#22](https://github.com/eschnitzler/EmpireCore/pull/22),
  [`02f9b88`](https://github.com/eschnitzler/EmpireCore/commit/02f9b885ce8104709ac9a8d8f0e145017d9a5de3))


## v0.25.1 (2026-04-06)

### Bug Fixes

- Include username in disconnect and login failure logs
  ([#21](https://github.com/eschnitzler/EmpireCore/pull/21),
  [`214aa34`](https://github.com/eschnitzler/EmpireCore/commit/214aa34b6cefc0538a454ec038e3a70328794a6d))

### Performance Improvements

- Clear arrived movement IDs on each gam update to prevent unbounded growth
  ([#21](https://github.com/eschnitzler/EmpireCore/pull/21),
  [`214aa34`](https://github.com/eschnitzler/EmpireCore/commit/214aa34b6cefc0538a454ec038e3a70328794a6d))


## v0.25.0 (2026-03-23)

### Bug Fixes

- Pass XT packet error code to payload before parsing
  ([`18acccc`](https://github.com/eschnitzler/EmpireCore/commit/18acccc7a983e55d54ef431cf5c1f1b0ee1e9e7a))

- Race condition in wait_for dropping packets
  ([`297ddb8`](https://github.com/eschnitzler/EmpireCore/commit/297ddb886d374936c460342e6722d741ce2a9040))

- Rename global_rank to is_in_ruins for R flag in AllianceMember
  ([`7777116`](https://github.com/eschnitzler/EmpireCore/commit/7777116e2ae84ba6245c01a181273f845fcab5b0))

### Features

- Upgrade map scanner to return player objects and fix property indices
  ([`6a06bdf`](https://github.com/eschnitzler/EmpireCore/commit/6a06bdf986c526624efd9e4e174822db44028739))


## v0.24.2 (2026-03-22)

### Bug Fixes

- Include target info in bsd response
  ([`d6840af`](https://github.com/eschnitzler/EmpireCore/commit/d6840afc41a99a835b54f9b05b3496b06502480e))

- MapItemType.EXTERNAL_KINGDOM for other kingdoms main castles
  ([`20c165c`](https://github.com/eschnitzler/EmpireCore/commit/20c165c7f539bfdff8deeac8dfaac8cd510645e9))


## v0.24.1 (2026-03-22)

### Bug Fixes

- Exclude non-error commands from server error logging
  ([`9682453`](https://github.com/eschnitzler/EmpireCore/commit/9682453eb14f6ddb0bfde7c5c8a7110d8bc321cf))


## v0.24.0 (2026-03-20)

### Bug Fixes

- Remove TYPE_CHECKING from alliance.py
  ([`50de2aa`](https://github.com/eschnitzler/EmpireCore/commit/50de2aa6b5495ed2924a3dee594429be7c9808f3))

### Features

- Add spy protocol models and service
  ([`1d7aa19`](https://github.com/eschnitzler/EmpireCore/commit/1d7aa19dfdeb54240e69a03537037cec83a1d236))


## v0.23.1 (2026-03-15)

### Chores

- Delete _archive/ dead code directory
  ([`2e250bf`](https://github.com/eschnitzler/EmpireCore/commit/2e250bf5f910fd33939a967df57432fe4cf24c53))

### Refactoring

- Extract scan_kingdom into MapScanner class (#1, #6, #10, #12)
  ([`50c7db6`](https://github.com/eschnitzler/EmpireCore/commit/50c7db6d26cb691420bf70f6d271b4e567ce8bde))

- State/manager.py — dispatch dict, split _handle_gbd, merge atv/ata, multi-listener callbacks (#2,
  #3, #8, #9)
  ([`dd6e920`](https://github.com/eschnitzler/EmpireCore/commit/dd6e920c3bc16a31d50ed9466b066377ae996b0e))

- Typed returns, queue-based bulk fetch, remove duplicate encoding (#4, #5, #7)
  ([`7a776ab`](https://github.com/eschnitzler/EmpireCore/commit/7a776abd6e332404d6592b4faaccc867919b4a29))


## v0.23.0 (2026-03-08)

### Bug Fixes

- Handle offset=1 entry format in RankingEntry parser
  ([`3990cba`](https://github.com/eschnitzler/EmpireCore/commit/3990cba4b9b0b1381be342a2a24229646aec5b16))

- Support dict format in RankingEntry for llsp/llsw responses
  ([`d73ce87`](https://github.com/eschnitzler/EmpireCore/commit/d73ce876171dba9df4aced73f6e182aa62f62181))

### Features

- Add unranked classmethod to RankingEntry
  ([`6ac4563`](https://github.com/eschnitzler/EmpireCore/commit/6ac4563b23b15a14d8031c9b651bcd3c0c097782))

- Track active event IDs from sei packet and fix timezone-aware bird expiry
  ([`2ce9ffd`](https://github.com/eschnitzler/EmpireCore/commit/2ce9ffd4137cf93c026a4ceacb842ca52c6184fb))


## v0.22.1 (2026-02-17)

### Bug Fixes

- Return timezone-aware UTC datetime from bird_end_time property
  ([`1564b15`](https://github.com/eschnitzler/EmpireCore/commit/1564b15a8340f24ae6dc71f74dd986aff2073ffa))


## v0.22.0 (2026-02-08)

### Bug Fixes

- Handle target_type in movement parsing and update dependencies
  ([`a496836`](https://github.com/eschnitzler/EmpireCore/commit/a496836a06c13a20ca870f83c95fe510042f11d0))

- Improve network error logging and connection stability
  ([`4e2c0b4`](https://github.com/eschnitzler/EmpireCore/commit/4e2c0b44e8ebe4605e5c57c829ccd7b5ddc2f53d))

### Features

- Add player search request and response models
  ([`9f80313`](https://github.com/eschnitzler/EmpireCore/commit/9f80313c99340728caf3a8414ac210f2ea298b86))

- Add ranking and highscore protocol models
  ([`b987d11`](https://github.com/eschnitzler/EmpireCore/commit/b987d111f57a85321575dfebe11f8d4504b24a9f))

- Implement player search in EmpireClient
  ([`916e131`](https://github.com/eschnitzler/EmpireCore/commit/916e131ef3ace6b7eb100f0799d5b88da3ff1b96))

- Implement ranking service
  ([`a55eb99`](https://github.com/eschnitzler/EmpireCore/commit/a55eb992df81ef3337310e1261fdd6376269ccab))


## v0.21.0 (2026-02-01)

### Features

- Add GGEError enum with all protocol error codes
  ([`f5034cc`](https://github.com/eschnitzler/EmpireCore/commit/f5034cc9c4f71cf3ffde479299d306d93266160d))


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


## v0.12.0 (2026-01-10)

### Bug Fixes

- Use AMI array for online status instead of H field
  ([`623fc10`](https://github.com/eschnitzler/EmpireCore/commit/623fc10fa05fe4fded7824cc276e4b4c27744c9d))

### Breaking Changes

- The H field was incorrectly assumed to be 'hours since online'. It's actually 'honor' points.
  Online status now correctly comes from the AMI array (index 4), where 0 = online and non-zero =
  offline.


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


## v0.4.3 (2026-01-04)

### Bug Fixes

- Route all packets through GameState for callbacks
  ([`88ada1b`](https://github.com/eschnitzler/EmpireCore/commit/88ada1bf4998e4c044657a22f08e2e24b816045e))

### Chores

- Bump version to 0.4.3
  ([`4dd9202`](https://github.com/eschnitzler/EmpireCore/commit/4dd92028d375776f3aca1975e7f04d7bee4306fd))


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
