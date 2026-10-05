#!/usr/bin/env bash
# Idempotent machine bootstrap — safe to re-run at any time.
# Order matters: Xcode CLT -> Homebrew -> brew bundle -> stow -> mise install.
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOW_DIR="$DOTFILES_DIR/stow"
STOW_PACKAGES=(zsh git ghostty mise sublime-text)
BACKUP_DIR="$HOME/.dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# Bring manually installed apps under Homebrew without touching their prefs.
adopt_existing_casks() {
  local installed cask app
  installed="$(brew list --cask -1 2>/dev/null || true)"
  while IFS= read -r cask; do
    grep -qx "$cask" <<<"$installed" && continue
    app="$(brew info --cask "$cask" |
      awk '/^==> Artifacts/ {f=1; next} /^==>/ {f=0} f && / \(App\)$/ {sub(/ \(App\)$/, ""); print; exit}')"
    [[ -n "$app" && -d "/Applications/$app" ]] || continue
    info "Adopting existing /Applications/$app as cask '$cask'"
    brew install --cask --adopt "$cask" ||
      warn "Could not adopt $cask (version differs?). Quit the app, then: brew install --cask --force $cask"
  done < <(brew bundle list --cask --file="$DOTFILES_DIR/Brewfile")
}

# Move real files that would block Stow into a timestamped backup dir.
backup_stow_conflicts() {
  local pkg src target
  for pkg in "${STOW_PACKAGES[@]}"; do
    while IFS= read -r -d '' src; do
      target="$HOME/${src#"$STOW_DIR/$pkg/"}"
      [[ -e "$target" || -L "$target" ]] || continue
      [[ "$(realpath "$target" 2>/dev/null)" == "$(realpath "$src")" ]] && continue
      mkdir -p "$BACKUP_DIR/$(dirname "${target#"$HOME/"}")"
      mv "$target" "$BACKUP_DIR/${target#"$HOME/"}"
      warn "Backed up existing $target -> $BACKUP_DIR"
    done < <(find "$STOW_DIR/$pkg" \( -type f -o -type l \) ! -name .DS_Store -print0)
  done
}

[[ "$(uname -s)" == Darwin ]] || die "This script is for macOS."

# 1. Xcode Command Line Tools
if ! xcode-select -p >/dev/null 2>&1; then
  info "Installing Xcode Command Line Tools"
  xcode-select --install || true
  die "Re-run bootstrap.sh after the Command Line Tools installer finishes."
fi

# 2. Homebrew
if [[ ! -x /opt/homebrew/bin/brew ]]; then
  info "Installing Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
eval "$(/opt/homebrew/bin/brew shellenv)"

# 3. Homebrew packages and apps
adopt_existing_casks
info "Running brew bundle"
brew bundle --file="$DOTFILES_DIR/Brewfile" ||
  warn "Some Brewfile entries failed (running apps? version mismatch?). Fix and re-run."

command -v stow >/dev/null || die "stow is missing; brew bundle must succeed for it first."
command -v mise >/dev/null || die "mise is missing; brew bundle must succeed for it first."

# 4. Oh My Zsh (sourced by the tracked .zshrc)
if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
  info "Installing Oh My Zsh"
  git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
fi

# 5. Activate dotfiles
info "Stowing: ${STOW_PACKAGES[*]}"
backup_stow_conflicts
stow --dir="$STOW_DIR" --target="$HOME" --no-folding --restow "${STOW_PACKAGES[@]}"

# 6. Runtimes declared in ~/.config/mise/config.toml
info "Installing mise runtimes"
(cd "$HOME" && mise install && mise ls --current)

# 7. Azure CLI extensions
if command -v az >/dev/null; then
  if ! az extension show --name azure-devops >/dev/null 2>&1; then
    info "Installing Azure CLI extension: azure-devops"
    az extension add --name azure-devops
  fi
fi

# 8. Claude Code (native installer, self-updating)
if ! command -v claude >/dev/null && [[ ! -x "$HOME/.local/bin/claude" ]]; then
  info "Installing Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash
fi

# 8. Azure DevOps MCP server (configs are app-managed, so patch rather than stow)
AZURE_DEVOPS_ORG="silksong"
CLAUDE_BIN="$(command -v claude || echo "$HOME/.local/bin/claude")"

# Claude Code: user scope = available in every project. Checked from the repo dir
# so a local-scope entry for some other directory doesn't count.
if [[ -x "$CLAUDE_BIN" ]] &&
  ! (cd "$DOTFILES_DIR" && "$CLAUDE_BIN" mcp get azure-devops >/dev/null 2>&1); then
  info "Registering Azure DevOps MCP in Claude Code"
  "$CLAUDE_BIN" mcp add --scope user azure-devops -- npx -y @azure-devops/mcp "$AZURE_DEVOPS_ORG"
fi

# Claude Desktop: merge only mcpServers.ado, keeping the app's own preferences.
CLAUDE_DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [[ ! -f "$CLAUDE_DESKTOP_CFG" ]]; then
  warn "Claude Desktop hasn't been launched yet; re-run bootstrap.sh to register its MCP server."
elif ! jq -e '.mcpServers.ado' "$CLAUDE_DESKTOP_CFG" >/dev/null 2>&1; then
  info "Registering Azure DevOps MCP in Claude Desktop (restart Claude to load it)"
  tmp="$(mktemp)"
  jq --arg org "$AZURE_DEVOPS_ORG" \
    '.mcpServers.ado = {command: "npx", args: ["-y", "@azure-devops/mcp", $org]}' \
    "$CLAUDE_DESKTOP_CFG" >"$tmp" && mv "$tmp" "$CLAUDE_DESKTOP_CFG"
fi

# 9. Checks and remaining manual work
git config --global --includes user.email >/dev/null ||
  warn "git user.email not set. Add it to ~/.gitconfig.local:  [user] email = you@example.com"

info "Done. Remaining manual setup ($DOTFILES_DIR/manual-apps.md):"
grep '^### ' "$DOTFILES_DIR/manual-apps.md" | sed 's/^### /  - /'
