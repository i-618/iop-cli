# iop

**I**'m **O**utta **P**atience.

Run a named sequence of shell commands with variables, in the current
directory. You type the value that changed; `iop` runs the rest.

Every time you finish a change, you retype the same five-command
dance — pull, status, add, commit, push — and the only thing that ever
changes is the commit message. `iop` turns that into one line:

    iop push "fixed the parser"

No more forgetting `git add -A` before commit, no more pushing before
pulling, no more retyping a sequence you've typed a thousand times. You
type the one thing that changed; `iop` runs the rest — in the same
directory, with real git output on screen the whole time. And it's not
just a shortcut: your commit message can contain a semicolon, quotes,
anything — it's still one argument to `git commit -m`, never a second
command that happens to execute. Safe by construction, not by
convention.

## Install

    pip install iop-cli

## Quick start

The first time you run `iop`, it creates `~/.iop/recipes.toml` with a few
starter recipes. The main one:

```toml
[push]
desc  = "pull, stage everything, commit, push"
vars  = ["msg"]
steps = [
  "git pull",
  "git status",
  "git add -A",
  { run = "git commit -m {msg}", ok_fail = true },
  "git push",
]
```

It also seeds `whoami <name> <email>` (`git config --global user.name`
and `user.email` — the two things git asks for on a brand-new machine),
`undo` (take back the last commit, keep the changes), `serve <port>`
(`python -m http.server`), and `docker <tag>` (build an image, then run
it). Bare `iop` lists whatever is in the file; edit it with `iop -e`.

Then:

    iop push "fixed the parser"

Omit the value and `iop` prompts for it:

    iop push
    msg: fixed the parser

## Commands

    iop <recipe> [values...]      run it
    iop                           list recipes
    iop -l, --list                same, explicit
    iop -n, --dry-run <recipe>    print resolved argv per step, execute nothing
    iop --where                   print the path to recipes.toml
    iop -e, --edit                open recipes.toml in $EDITOR (seeds a starter recipe on first use)
    iop --version

## How it's safe

A value is substituted into an already-tokenized argument -- never
re-split, never handed to a shell -- so `iop push "fix; rm -rf /"` commits
a message containing a semicolon; it cannot run a second command. Recipes
that genuinely need shell features (pipes, `||`) opt in per-step with
`shell = true`, which trades away that guarantee for that one step.

## Requirements

Python 3.8 or newer. No runtime dependencies on Python 3.11+.
