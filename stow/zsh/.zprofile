# Login shell setup (runs before .zshrc).

eval "$(/opt/homebrew/bin/brew shellenv zsh)"

# mise shims for non-interactive/login contexts (IDEs, scripts).
# Interactive shells switch to full `mise activate` in .zshrc.
command -v mise >/dev/null && eval "$(mise activate zsh --shims)"

[[ -f "$HOME/.zprofile.local" ]] && source "$HOME/.zprofile.local"
