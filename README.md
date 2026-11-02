# FrugalBar for Linux

AI subscription usage and API balances in a native Linux Mint Cinnamon window and tray. This is the secondary Linux version of [FrugalBar](https://github.com/seankoji-com/frugalbar), using the selected Mint Ledger design and the original provider logos from that repository.

Initial release preparation is in progress. The Homebrew formula is not published yet.

## Run from source on Mint

Python 3.10 or newer and GTK 3 are required. Mint 22.x is the intended target; Cinnamon on X11 supports the tray path. Other desktops and Wayland can use the normal window when a compatible tray host is unavailable.

```sh
sudo apt install python3 python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-xapp-1.0 libsecret-tools librsvg2-common
python3 -m frugalbar_linux
```

Run the command inside the cloned repository, in your desktop session, without sudo. The app uses your system GTK theme, including Mint-Y light or dark. The tray's Open / hide usage action restores the same window; closing the window leaves monitoring active when a tray host is detected. Otherwise closing exits. Quit FrugalBar stops the process.

```sh
python3 -m frugalbar_linux --demo             # Illustrative data, no credential or network reads
python3 -m frugalbar_linux --demo --json      # Headless demo output
python3 -m frugalbar_linux --json --discover  # One real read using local CLI sessions
```

## Homebrew distribution

The intended command after the release and tap PR are published is:

```sh
brew install seankoji-com/tap/frugalbar-linux
frugalbar-linux
frugalbar-linux --install-desktop
```

The separate formula uses the existing `seankoji-com/homebrew-tap`, installs GTK, Python bindings and the Secret Service helper, and leaves the macOS `frugalbar` formula alone. It must run inside the desktop session. It is not a systemd or `brew services` daemon. Settings can opt into login startup; the application menu installer and startup setting write only this user's desktop entries.

The app first uses an available Cinnamon XApp tray. With a Homebrew Python that cannot load the system XApp typelib, it uses GTK's classic X11 tray icon. That fallback exposes the reading in its tooltip and menu rather than a panel text label. If no tray host exists, `--hidden` opens a normal window instead of leaving an invisible application.

## Configure providers

Open Settings to save a key or OAuth access token in your desktop login keyring using Secret Service. The keyring may ask to unlock. FrugalBar stores no credential in `settings.json`. Saving a blank field does nothing; Remove saved key clears that provider's entry. Environment variables take precedence over saved keys. Removing a key does not remove credentials held by another CLI.

Local CLI discovery is off by default. Enable it to read existing Claude Code, Codex, OpenCode, GitHub/Copilot, Grok, Kiro, Command Code and Cline login files. These reads never refresh or overwrite a CLI session. Expired sessions must be renewed through their owning CLI. File locations honour the supported CLI/XDG overrides and Kiro's SQLite database opens read-only.

| Row | Environment credential alternative | Reading |
| --- | --- | --- |
| Claude Code | `CLAUDE_CODE_OAUTH_TOKEN`, `FRUGALBAR_CLAUDE_TOKEN` | Published 5H and weekly usage |
| Codex | `FRUGALBAR_CODEX_TOKEN`; optional `FRUGALBAR_CODEX_ACCOUNT_ID` | Published windows and separate API credits |
| Antigravity Gemini, Argon, Claude | `FRUGALBAR_GOOGLE_ACCESS_TOKEN` | Project-scoped pools from Google's quota summary |
| OpenCode Go | `OPENCODE_GO_API_KEY` | Rolling, weekly, monthly usage and blocking |
| GitHub Copilot | `GH_TOKEN`, `GITHUB_TOKEN` | Independent premium and chat monthly allowances |
| Grok | `FRUGALBAR_GROK_TOKEN` | Published plan credit usage |
| Kiro | `FRUGALBAR_KIRO_TOKEN` and `FRUGALBAR_KIRO_PROFILE_ARN` | Monthly credit allowance |
| DevPass | `LLMGATEWAY_API_KEY`, `DEVPASS_API_KEY` | Monthly plan credits |
| Command Code | `COMMAND_CODE_API_KEY`, `COMMANDCODE_API_KEY` | Published 5H and weekly limits |
| ClinePass | `CLINE_API_KEY`, `CLINEPASS_API_KEY` | Published 5H, weekly, monthly limits |
| Muse | `FRUGALBAR_MUSE_TOKEN` | Published subscription windows |
| OpenRouter | `OPENROUTER_API_KEY` | Account credit balance or key cap remaining |
| DeepSeek | `DEEPSEEK_API_KEY` | Balances in each published currency |
| GitHub REST / GraphQL | `GH_TOKEN`, `GITHUB_TOKEN` | Request/point allowances, excluded from subscription tray selection |

Gemini's keyring credential is shared with its other Antigravity pools unless a separate pool token is saved. Google access tokens are read-only; this app has no OAuth refresh/login flow. Kiro needs its profile ARN as well as the token, discovered from its CLI or supplied with the environment variable. Codex's account header can likewise come from its login or environment. Muse's macOS Keychain login cannot be discovered on Linux; save its access token explicitly.

## Reading the ledger

Percentages mean usage, while the tray label means remaining capacity. Missing vendor windows show a dash with no empty bar. Each window retains its own reset. A passed reset says it is awaiting another reading, rather than claiming the quota is restored. The pace tick appears only when the period length and reset are known. Text and symbols identify problems as well as colour.

A failed read retains the last observation for the same credential and marks it stale, with its original time. Changed or removed credentials discard that observation. Stale and spent windows do not become the tray's remaining-capacity reading; critical pressure still controls the icon. Unavailable providers never become healthy. Published balances sit in a separate table and never become quotas. Balance changes use readings collected during this process; a single reading says Collecting readings.

Automatic reads have a 120-second per-row floor. Explicit Refresh has an independent 30-second floor. Vendor `Retry-After` holds back automatic reads; explicit refresh can probe after its own floor. Claude 403 and 429 responses are throttles, with the upstream five-minute fallback when no positive instruction is available. Cooldowns are in memory and reset when the app restarts. Credentials are only sent to fixed vendor HTTPS endpoints; redirects never forward them. Error text omits response bodies, tokens and raw transport exceptions.

## Scope of this secondary version

This release has no Android/watch publication, Drive sync, CLI Proxy fallback, browser billing sessions or grants, history database, events, notifications or token-activity charts. It does not port Grok on-demand spend, Kiro bonus/overage bars, Command Code's monthly plan mapping or organisation selector, or OpenRouter's lifetime-spend fallback. OpenCode uses one configured workspace. The token-based reads above are implemented, but vendor compatibility must be verified against the user's own accounts; fixture tests do not prove live access.

## Verification and artwork provenance

```sh
python3 -m unittest discover -v
sh scripts/check-linux.sh
```

The second command additionally requires Xvfb, xauth and dbus-x11. It runs the actual GTK app with isolated demo data and records screenshots under ignored `.artifacts/screenshots/`, exercises window restore and Settings, and never makes a vendor request. There is no previous Linux UI for before screenshots, and a mobile viewport is not applicable to this desktop application. A Linux container proves GTK behaviour there, not live Cinnamon tray hosting or account access. CI has a ten-minute execution limit.

Provider artwork is extracted from FrugalBar's `VendorAvatarView.swift` and `VendorAssetData.swift` at revision `3a058ce5f9298d90d57459b039b745d40224af3d`. `assets/provenance.json` records every imported file's SHA-256 and source. `scripts/import-logos.py /path/to/frugalbar` reproduces the extraction. No initial-letter substitutes are used. The MIT licence and original copyright are retained; vendor trademarks remain their owners'. The tray glyph is generated separately by `scripts/create-tray-assets.py`.
