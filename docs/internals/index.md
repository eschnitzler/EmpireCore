---
description: How EmpireCore talks to the game server, and the design notes behind it.
---

# Internals

These pages are for contributors, and for anyone who wants to know what happens
under a service call.

<div class="grid cards" markdown>

-   :material-handshake-outline:{ .lg .middle } **[Login and requests](login-and-requests.md)**

    ---

    The login handshake, how a reply finds its request, and the package
    layers, drawn.

-   :material-layers-triple-outline:{ .lg .middle } **[Architecture](../design/architecture.md)**

    ---

    The network, protocol, state and client layers and what each owns.

-   :material-lan:{ .lg .middle } **[Protocol](../design/protocol.md)**

    ---

    The SmartFox handshake and the `%xt%` message format, as the game client
    sends them.

-   :material-database-cog-outline:{ .lg .middle } **[State management](../design/state_management.md)**

    ---

    Thread safety, passive updates, object identity and the movement
    lifecycle.

</div>

## The game client is the source of truth

Every model and request is written against the game's own HTML5 client. A
model's docstring ends with a `Client:` line naming the client class, and the
line of the client bundle it was read from. Where the library is more lenient
than the client, its docstring says so. The command ids the library uses are
checked against a snapshot of the client's command tables, and a weekly
workflow compares that snapshot with the live client.

[Contributing](../contributing.md) explains how to add a command and the
conventions every model follows.
