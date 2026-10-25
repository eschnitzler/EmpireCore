---
description: Alliance chat, help requests, members, applications, ranks and the treasury.
---

# Alliance

`client.alliance` covers your own alliance and looks up others.

## Founding

```python
created = client.alliance.found("New Guild", "Our description", "en")
print(created.alliance_id)
```

The normal client flow costs 100 wood, 50 stone, 50 base coins and 375 base
rubies; cost modifiers can adjust the coin and ruby prices. An active premium
account waives the ruby cost. Without `spend_rubies=True`, the premium exemption
must last beyond the request timeout. The call keeps missing-resource ruby
payment disabled. `open_join=True` is the client's default; pass `False` to
require invitations or accepted applications.

A valid success installs the created alliance and your membership together.
Refusals, transport failures, malformed replies and replies from a superseded
membership keep the newer local state.

## Settings and gifts

Settings return the alliance details echoed by the server:

```python
client.alliance.set_description("Our alliance description")
client.alliance.set_announcement("Next meeting at 19:00")
client.alliance.set_language("en")
client.alliance.rename("New Name")
```

Renaming without `spend_rubies=True` first reads fresh alliance details to verify a
free rename remains. Otherwise it requires consent to the 10,000-ruby charge.
Descriptions and announcements follow the client's text encoding and 1000-character
wire limit. Permission refusals raise `CommandError`.

`set_emblem(layout_id, color_ids)` validates the layout and colours against the
client's game data. A temporary layout must still be held. It returns the selected
crest after acknowledgment; the separate crest push updates the cached crest.

Alliance fame, buffs and crest pushes update `own_alliance`. Settings and membership
responses are scoped to the membership that sent them; later pushes keep their newer
values. The push protocol carries no alliance id, so an untagged push arriving after
new alliance details cannot independently identify its originating membership.

Gifts arrive as pushes; reading `gifts` sends nothing and excludes expired gifts:

```python
for gift in client.alliance.gifts:
    collected = client.alliance.collect_gift(gift.gift_id)
    print(collected.rewards)
```

Collection returns typed rewards and removes the gift only after a valid success.
A membership change clears the cached gift list.

## Chat

```python
client.alliance.send_chat("Hello alliance!")   # special characters are encoded for you

for entry in client.alliance.get_chat_log():
    print(f"{entry.player_name}: {entry.decoded_text}")
```

State keeps the chat history from the login data on, with every message the
server sends after it, oldest first, so reading it costs no request:

```python
for entry in client.alliance.chat:
    print(entry.sent_at, entry.player_name, entry.decoded_text)
```

Subscribe to new messages with a typed callback, and detach it again with
`client.alliance.on_chat_message.remove(on_message)`:

```python
def on_message(msg):                  # an AllianceChatMessageResponse
    print(f"[{msg.player_name}] {msg.decoded_text}")

client.alliance.on_chat_message(on_message)
```

!!! warning "Chat callbacks run on the receive thread"

    Unlike the [state callbacks](movements.md), chat callbacks are called on
    the thread that reads the socket. Keep them short: a call that waits for a
    reply raises `ReceiveThreadError` there. Hand real work to another thread.

## Help requests

`client.alliance.help_requests` is the alliance help list. The login data fills
it and the server's pushes keep it current, so reading it costs no request.

```python
client.alliance.help_all()            # help every request on the list
```

To pick requests yourself, skip the ones the client skips: those you already
helped, your own, and finished ones. A request is finished once its progress
reaches its help type's `maxHelpersCount` in the items data's
`alliancehelprequests` table (3 for most types, 5 for healing and 20 for loop
recruiting in items version 786.03):

```python
max_helpers = {1: 3, 2: 5, 3: 3, 4: 3, 5: 20, 6: 3}
my_id = client.player.local_player.id

for request in client.alliance.help_requests:
    finished = request.progress >= max_helpers.get(request.help_type, 0)
    if not (request.already_confirmed or finished or request.player_id == my_id):
        client.alliance.help_member(request)
```

`on_help_update(callback)` calls you after each change to the list. Ask for
help yourself with `request_build_help`, `request_repair_help`,
`request_recruit_help` and `request_heal_help`.

## Members and other alliances

```python
members = client.alliance.get_local_members()
online = client.alliance.get_local_online_members()

for result in client.alliance.search_alliances("PACT"):
    info = client.alliance.get_alliance_info(result.alliance_id)
```

`get_members(alliance_id)` and `get_online_members(alliance_id)` do the same
for any alliance, and `client.alliance.local_alliance_id` is your own alliance's
id, or `None` outside one. Outside an alliance the two `get_local_*` calls raise
`NotInAllianceError` without sending anything, so "no alliance" is never
mistaken for an alliance without members. `search_alliances` returns an empty
list when nothing matches.

A member's protection times count from when the reply was read (`received_at`,
in `time.monotonic()` seconds): `revenge_protection_end` and
`beginner_protection_end` stay fixed, and
`remaining_revenge_protection_seconds()` counts down; `has_bird` and
`has_beginner_protection` turn False once the time runs out. To store or show
an end, `revenge_protection_end_utc()` and `beginner_protection_end_utc()` give
it as a UTC `datetime` (or `None`), counted from the wall-clock time stamped at
the same read (`received_at_wall`), so they do not move between calls. A player
from `client.player.get_player_info` has the same on its `owner`.

`client.alliance.own_alliance` is your alliance's details as the login data
and the replies since left them (a chat message marks its sender online), or
`None` outside one, without a request.

## Applications, ranks and the treasury

```python
from empire_core.alliance import AllianceDonation, AllianceRank

for application in client.alliance.get_applications().applications:
    client.alliance.answer_application(application.player_id, accept=True)

client.alliance.set_rank(player_id, AllianceRank.SERGEANT)
client.alliance.donate(castle_id, AllianceDonation(wood=1000))
client.alliance.donate(castle_id, AllianceDonation(rubies=50), spend_rubies=True)
```

Also on the service: `invite`, `kick_member`, `leave`, `change_diplomacy`,
`refuse_diplomacy`, `set_auto_war` and `send_newsletter`.

All of these, and `get_chronicle`, are about your own
alliance, which the client only offers inside one. Outside an alliance they raise
`NotInAllianceError` without sending anything, and so does a server answer of
`ALLI_NOT_FOUND` (your alliance id was stale). `set_rank` returns `None` for
`NO_CHANGE`, the rank the member already has; `kick_member`, `set_rank` and
`refuse_diplomacy` otherwise return the alliance the reply carries.
`get_subscriber_count` is sent outside an alliance too, as the client sends it.

## The chronicle

`get_chronicle` returns the entries of your alliance's chronicle, newest first.
What an entry's `action_values` hold depends on its action; `details` reads
them as the client does, typed: a `ChronicleDiplomacy` (the other alliance's
name and a `DiplomacyStatus`), a `ChronicleBuff` (an `AllianceBuffType`, and
the smithy's level for its upgrade), a `ChronicleAmount`, `ChronicleLevel`,
`ChroniclePlace`, `ChronicleTournamentPrize`, `ChronicleText`,
`ChronicleMember` or `ChronicleDaimyoContract`, or `None` where the entry
carries nothing (the entries about a player name them in `player_name`).
`describe()` writes the line the overview shows.

```python
from empire_core.alliance import ChronicleAmount, ChronicleDiplomacy

for entry in client.alliance.get_chronicle():
    print(entry.describe())             # "1,500 coins have been donated to the alliance funds"
    match entry.details:
        case ChronicleAmount(amount=amount):
            ...
        case ChronicleDiplomacy(alliance_name=name, status=status):
            ...
```

`describe()` fetches the language file on first use, as `empire_core.texts`
does, and takes `lang`. A completed daimyo contract reads its rank and level
from the game data, loaded on first use or passed as `entry.describe(data)`. On a special server
with a skin (such as `"Maya"` on Beyond the Horizon), pass `skin` for
the texts the client shows there. An entry no player made (`player_id` -1)
names an alliance instead: `named_alliance_id` and `named_alliance_name`.

## Map bookmarks

`get_bookmarks` lists your own bookmarks and your alliance's. Your own are a
friend or an enemy; the alliance ones (free attack, defend, attack order) need
the right to manage bookmarks. A name is 1 to 30 characters
(`BOOKMARK_NAME_MAX_LENGTH`) and goes out as typed.

```python
from empire_core.alliance import BookmarkType

added = client.alliance.add_bookmark(640, 655, "Farm", BookmarkType.PLAYER_FRIEND)
client.alliance.change_bookmark(640, 655, "Barn", BookmarkType.PLAYER_FRIEND)
client.alliance.delete_bookmark(added)
```

`add_bookmark` and `change_bookmark` return the bookmark the reply carries and
raise `CommandError` when the server refuses, such as `BOOKMARK_ALREADY_ADDED`,
`BOOKMARK_MAX_ENTRYS` (50 own) or `NO_SELF_TARGET`; the alliance list of 20
has `ALLIANCE_BOOKMARK_MAX_ENTRYS`.
`change_bookmark` changes only your own bookmarks, as the client does.
`delete_bookmark` deletes an own bookmark by its position and an alliance one
by its id, and raises `CommandError` when the server refuses. An alliance attack order
takes `attack_in_seconds` (an hour to just under a day) and `attacker_ids`.
Adding or deleting an alliance bookmark outside an alliance raises
`NotInAllianceError` without sending anything.

## Runnable example

```python title="examples/alliance_chat.py"
--8<-- "examples/alliance_chat.py"
```

**API:** [`AllianceService`](../reference/alliance.md#empire_core.alliance.service.AllianceService)


## Forum

`get_forum_topics()` returns a typed overview, including the total topic count
(which includes hidden topics) and visible topics sorted by last post, newest
first. `get_topic(topic_id)` opens a topic and returns its posts; opening a topic
can mark it read on the server. Request the current count with
`get_unread_topic_count()`.

```python
from empire_core.alliance import ForumRankGroup

for topic in client.alliance.get_forum_topics().topics:
    detail = client.alliance.get_topic(topic.topic_id)
    for post in detail.posts:
        print(post.author, post.text)

client.alliance.create_topic("Plans", "Meet tomorrow", [ForumRankGroup.LEADER, ForumRankGroup.GENERAL])
client.alliance.reply(topic_id, "Ready for tomorrow")
client.alliance.set_topic_visibility(topic_id, [ForumRankGroup.LEADER])
client.alliance.delete_reply(topic_id, reply_id)
client.alliance.delete_topic(topic_id)
```

Visibility uses `ForumRankGroup`, which has five groups; member ranks use
`AllianceRank`, which has ten ranks. Unknown groups and ranks in replies remain
integers. Titles and posts are trimmed, validated after the client's first text
encoding pass, then encoded again for sending. Titles allow 2–38 UTF-16 code units;
posts allow 2–2000. Server refusals raise `CommandError`; transport failures
propagate. Write methods return `None` after acceptance, except visibility changes,
which return the echoed topic when provided. All requests accept keyword-only
`timeout`.


## Applications, invitations and recruitment

```python
client.alliance.apply(alliance_id, "I would like to join")
joined = client.alliance.join_open(alliance_id)

# Invitation APIs use a message id from the mailbox, not a player id.
inviting_alliance = client.alliance.get_invitation(message_id)
joined = client.alliance.accept_invitation(message_id)
client.alliance.accept_invitation(message_id, accept=False)

recruits = client.alliance.find_recruits()
for recruit in recruits.recruits:
    owner = recruits.owner_of(recruit)
    if owner is not None:
        print(owner.name, recruit.distance)

client.alliance.set_looking_for_members(True, open_join=True)
client.alliance.set_looking_for_alliance(True)
```

`join_open` returns the joined alliance. Invitation acceptance returns the echoed
alliance, and declining normally returns `None`. Server refusals raise
`CommandError`; timeouts and disconnections propagate. All sending methods accept
keyword-only `timeout`. Existing `invite`, `get_applications`,
`answer_application` and `leave` keep their interfaces.

A successful join applies membership before alliance details. Changing alliance
identity clears details, chat and help from the former alliance. Late `ain`
updates for another alliance do not replace your own alliance. Recruitment flags
are independent: looking for members (`IS`) and allowing open joining (`IA`).
The flag replies carry no updated values; refresh alliance information to read
those flags. Player looking-for-alliance status also appears in owner records and
`AllianceMembership.looking_for_alliance` in membership protocol replies. Recruit
search returns typed rows sorted by distance with optional owner records; malformed
rows are skipped with a warning.


Membership cache changes are scoped to `join_open` and `accept_invitation`.
Unsolicited `gal` pushes remain authoritative. Raw, rejected and delayed `joa` or
`aai` replies do not update cached membership on their own. If a membership push
or session reset arrives while a service call waits, applying its reply raises
`ReplyMismatchError` and preserves the newer context. The server action may
already have succeeded; read the current membership before another action.
Invitation replies do not echo their message id, so validation checks that their
membership and alliance details name the same alliance; it cannot identify an
invitation by message id from the reply.

## Upgrades and temporary boosts

`client.alliance.upgrade(AllianceBuffType.FORGE_UPGRADE)` upgrades the alliance
smithy. The same method purchases permanent buffs and activates or prolongs
supported temporary boosts. Pass `level=2` for a customizable temporary boost;
permanent and standard boosts send the client's default level, `1`.

The method first requests fresh alliance details and resolves the cost from
`client.game_data` (or the loaded game data). Permanent upgrades cost the next
level's price; customizable boosts cost the selected level's price. An active
customizable boost can only be prolonged at its current level. Unknown costs,
levels and unmet prerequisites are rejected before sending the purchase.

Costs come from the **alliance treasury**, including its rubies. A purchase that
costs treasury rubies requires `spend_rubies=True`; personal rubies are not spent
by this command. The server enforces rank permissions and sufficient funds,
raising `CommandError` on refusal. Transport failures retain their exception type.

The returned `AllianceUpgradeResponse` contains the authoritative `storage` and
`buildings` lists. These update the alliance cache while preserving newer pushes
and rejecting replies from a previous membership.

## Joining automatically

`client.alliance.auto_join("Alliance")` asks the server to put you in an
alliance, as the game's "join alliance" button does. The reply's `membership`
is your new one when it did, applied to state; otherwise `alliances` lists
alliances to join (`language="de"` limits the list to one language). A pushed
`aja` (you were put in an alliance) and `sal` (alliances to join) are read too.

## Donation resources, aqua points and the forge

`client.alliance.get_donation_resources(castle_id)` returns what one of your
castles has to donate and your special currencies.
`client.alliance.get_member_aqua_points()` lists each member's Storm Islands
aqua points; `client.player.get_aqua_points()` asks for yours and your
alliance's, and `client.player.aqua_points` keeps the last value.
`client.player.get_storm_islands_info()` adds your rank and your alliance's
standing on the islands, kept as `client.player.storm_islands`.

`client.alliance.forge()` crafts in the alliance forge. Below legend level 1 it
needs the alliance's `is_able_to_forge`; from legend level 1 the relic forge
crafts, paid in coins, or in rubies with `pay_with_rubies=True` (which needs
`spend_rubies=True`). A crafted gem joins `client.commanders.gems`.

## Laboratories

Your alliance's laboratories are `client.alliance.own_alliance.laboratories`,
replaced by every `sll` push. Your own laboratories, with the units in them,
are `client.castle.laboratories`, and `client.castle.laboratory_reset` counts
down to the next laboratory reset.
