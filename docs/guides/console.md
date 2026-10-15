---
description: An interactive Python console on a live client, beside every socket frame it sends and receives.
---

# Console

`empire-console` is a full-screen Python REPL with a logged-in `client` ready to use. You type
code on the left; every frame the connection sends and receives scrolls by on the right.

```bash
pip install 'empire-core[console]'

export GGE_USERNAME=your_user
export GGE_PASSWORD=your_pass      # or leave it out to be asked
empire-console                     # or: python -m empire_core.console
```

`--no-login` starts without connecting, which is enough to explore the API with completion.
`--log-level INFO` shows the library's log in the output pane.

## Writing code

`client` and `empire_core` are already in scope. Completion comes from jedi on the live objects,
so `client.castle.` lists the castle service's methods, and the line above the input shows the
signature of the call the cursor is in.

```python
>>> castles = client.castle.get_all()
>>> [c.castle_name for c in castles]
```

Enter runs the input once it is a complete statement; a block (`for`, `def`, `with`) runs on an
empty line, as in the Python REPL. Esc then Enter runs whatever is typed. Code runs on a worker
thread, so the frame pane keeps moving while a request waits for its reply. One input runs at a
time. History is kept in `~/.empire_console_history`.

## Reading frames

Each frame is one line: time, direction (`↑` sent, `↓` received), command, error code, size and
the start of the payload. Press F2 to move focus to the frame list, then Up and Down to select a
frame; its payload appears below as indented JSON. End goes back to following the newest frame.

| Command | Does |
|---------|------|
| `:filter gbd gam` | Show only these commands; `:filter` alone shows all |
| `:pause` | Freeze the view; frames are still recorded and appear on the next `:pause` |
| `:clear` | Forget every recorded frame |
| `:quit` | Close the client and exit (also Ctrl-D, or `exit()` in code) |

Passwords and login tokens never reach the pane: login frames show only their size, and
credential fields in other frames are masked. The same frames are open to your own code through
`client.connection.add_frame_listener`.
