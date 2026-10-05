# Manually Installed Applications

Things intentionally **not** managed by the Brewfile, plus one-off setup that
can't be automated. `bootstrap.sh` prints the `###` headings below as a checklist.

Corporate MDM-managed software (Company Portal, security agents, Microsoft 365, VPN)
is out of scope — the company's MDM installs and maintains it.

## Post-install Setup (apps installed by Brewfile)

### App Store sign-in
Reason: `mas` entries (Amphetamine, Xcode) need an App Store login before `brew bundle`.

### Xcode
Setup: Launch once, then `sudo xcodebuild -license accept` and `xcodebuild -runFirstLaunch`.

### Sublime Text — Package Control
Setup: Open Sublime Text → Tools → Install Package Control. It will auto-install the
packages listed in `stow/sublime-text/.../Package Control.sublime-settings` on next launch.
Add future packages there (not via the command palette alone) so they're tracked.

### VS Code — Settings Sync
Setup: Sign in to Settings Sync (Code → Settings Sync → Turn On) with your GitHub account.
Extensions, settings and keybindings sync automatically. No files to stow.

### Licences

Setup: Alfred Powerpack, BetterDisplay Pro, Shottr, IntelliJ IDEA, Sublime Text / Merge.

### macOS permissions
Setup: Grant Accessibility / Screen Recording as prompted for Alfred, BetterDisplay,
Shottr, Maccy, Ice, Stats. Re-grant after migrating an app to a Homebrew cask.

### Login items
Setup: Enable "Launch at login" in Alfred, Maccy, Ice, Stats, Amphetamine, BetterDisplay.

### Local config files
Setup: Create `~/.gitconfig.local` (`[user] email = ...`) and `~/.zshrc.local` (work env vars, secrets).

### Colima
Setup: `colima start --cpu 4 --memory 8` (or `brew services start colima` to start at login).

### Atuin (optional sync)
Setup: `atuin register` / `atuin login` to sync history across machines; `atuin import auto` to import existing zsh history.
