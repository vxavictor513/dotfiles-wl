# Interactive shell setup. Tracked in ~/dotfiles-wl via Stow.
# Machine/work-specific settings and secrets go in ~/.zshrc.local (untracked).

# --- Oh My Zsh ---
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"
plugins=(git)
[[ -f "$ZSH/oh-my-zsh.sh" ]] && source "$ZSH/oh-my-zsh.sh"

# --- Environment ---
export PATH="$HOME/.local/bin:$PATH"
export HOMEBREW_BUNDLE_FILE="$HOME/dotfiles-wl/Brewfile"
export EDITOR="subl -w"

# --- Tool activation ---
command -v mise >/dev/null && eval "$(mise activate zsh)"

if command -v fzf >/dev/null; then
  export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
  export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
  export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'
  source <(fzf --zsh)
fi

command -v zoxide >/dev/null && eval "$(zoxide init zsh)"

# After fzf so Atuin owns Ctrl-R; Up-arrow keeps normal zsh behaviour.
command -v atuin >/dev/null && eval "$(atuin init zsh --disable-up-arrow)"

# --- Aliases ---
if command -v eza >/dev/null; then
  alias ls='eza --group-directories-first'
  alias ll='eza -l --git --group-directories-first'
  alias la='eza -la --git --group-directories-first'
  alias lt='eza --tree --level=2'
fi
alias lg='lazygit'

# --- Local overrides (keep last) ---
[[ -f "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"
export PATH="$PATH:/Applications/IntelliJ IDEA.app/Contents/MacOS"
