# dotfiles-wl

Declarative, Git-managed setup for an Apple Silicon Mac.

| Layer | Tool | Lives in |
|---|---|---|
| CLI tools, GUI apps | Homebrew + `brew bundle` | `Brewfile` |
| Active config files | GNU Stow (symlinks into this repo) | `stow/<package>/` |
| Runtime versions (Node, Python, Java) | mise | `stow/mise/.config/mise/config.toml` |
| Project dependencies | uv / pnpm / Maven & Gradle wrappers | each project |
| App Store apps, licences, one-off setup | humans | `manual-apps.md` |

## Rebuild a machine

```sh
xcode-select --install                     # 1. Command Line Tools (wait for it to finish)
git clone <repo-url> ~/dotfiles-wl         # 2. git ships with the CLT
~/dotfiles-wl/bootstrap.sh                 # 3. Homebrew, brew bundle, stow, mise install
```

Then work through the checklist printed at the end (from `manual-apps.md`),
including installing the Mac App Store apps by hand.

`bootstrap.sh` is idempotent — re-run it whenever the Brewfile or stow packages change.
Existing files that would block Stow are moved to `~/.dotfiles-backup/<timestamp>/`.

## Day to day

Config files in `$HOME` are symlinks into this repo, so editing `~/.zshrc`
edits `stow/zsh/.zshrc` directly. Just commit.

**Homebrew** (`HOMEBREW_BUNDLE_FILE` is set in `.zshrc`, so `--file` is optional):

```sh
brew bundle add jq                  # add a CLI tool and install it
brew bundle add --cask bruno        # add a GUI app and install it
brew bundle check                   # is the machine missing anything?
brew bundle cleanup                 # preview what's installed but not declared
brew bundle cleanup --force         # ...remove it (review the preview first!)
```

The Brewfile is the desired state, not a lockfile. Only list top-level packages
you actually want — never transitive dependencies. To compare against the machine:

```sh
brew leaves; brew list --cask
brew bundle dump --file=/tmp/Brewfile.current --force   # then merge by hand
```

**Runtimes** — mise owns Node/Python/Java; don't list them in the Brewfile.
Homebrew may still install `node` as a dependency of a formula (e.g. `pi-coding-agent`);
that's fine — mise's version comes first on `PATH` in interactive shells.

```sh
mise use -g node@24                 # change a global version (edits the tracked config)
mise use java@temurin-17            # pin a version for the current project (mise.toml)
mise ls --current
```

**Adding a new stow package**, e.g. for lazygit:

```sh
mkdir -p stow/lazygit/.config/lazygit
mv ~/.config/lazygit/config.yml stow/lazygit/.config/lazygit/
# add "lazygit" to STOW_PACKAGES in bootstrap.sh, then:
./bootstrap.sh
```

## Local, untracked overrides

Tracked config stays generic. Machine- or work-specific values go in:

| File | Loaded by | Use for |
|---|---|---|
| `~/.gitconfig.local` | `[include]` in `.gitconfig` | `user.email`, signing keys, work `includeIf` |
| `~/.zshrc.local` | end of `.zshrc` | work env vars, tokens, proxies |
| `~/.zprofile.local` | end of `.zprofile` | login-shell-only overrides |

## Migrating manually installed apps to Homebrew

`bootstrap.sh` does this automatically: for each Brewfile cask that isn't
installed but whose `.app` already exists in `/Applications`, it runs
`brew install --cask --adopt <cask>`. Quit the apps first.

If adoption fails because the versions differ, quit the app and replace it:

```sh
brew install --cask --force <cask>
```

Never use `brew uninstall --zap` here — it deletes preferences and support data.
macOS may ask you to re-grant Accessibility / Screen Recording afterwards.

## Decisions

- **Colima over OrbStack** — this is a corporate machine; OrbStack needs a paid
  licence for commercial use. Don't install both.
- **mise only** — no SDKMAN/nvm/pyenv unless a tool specifically requires one.
- **No `mas` entries** — `mas install` needs admin rights, which Privilege Management
  blocks on this machine, so App Store apps live in `manual-apps.md` instead.
- **Claude Code** uses Anthropic's native installer (self-updating), run by `bootstrap.sh`.
