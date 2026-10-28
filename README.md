# Thorium Browser Folder Recolor

Recolor the bright yellow bookmark folder icons in **Thorium** (and other Chromium-based browsers) to a calmer, muted blue - with a single command that survives browser updates.

Instead of hard-coding resource IDs, the script scans `chrome_100_percent.pak` and `chrome_200_percent.pak`, detects small, mostly-yellow PNG icons by color, and shifts their hue. After an update, just run it again.

## Features

- **Update-proof:** detection is color-based, not tied to resource IDs that change between versions.
- **Safe:** original files are backed up once as `*.pak.orig`; one command restores them.
- **Previewable:** `--list` shows what would change, `--export` saves before/after PNGs.
- **Tunable:** adjust target hue, paleness, brightness and detection thresholds from the command line.
- **Handles both** 100% and 200% DPI resource files and `.pak` formats v4 and v5.
- Pure Python; the only dependencies are Pillow and NumPy.

## Requirements

- Python 3.8+
- `pip install pillow numpy`

## Quick start

1. **Close Thorium completely** (check the tray and Task Manager for background processes).
2. Find the folder that contains `chrome_100_percent.pak` (see [Typical locations](#typical-locations)).
3. Preview, then apply:

```bash
# See which icons will be changed (nothing is modified)
python recolor_folders.py --list "C:\Users\YOU\AppData\Local\Thorium\Application\156.0.8078.28"

# Optional: save before/after images to ./preview
python recolor_folders.py --export preview "C:\Users\YOU\AppData\Local\Thorium\Application\156.0.8078.28"

# Apply
python recolor_folders.py "C:\Users\YOU\AppData\Local\Thorium\Application\156.0.8078.28"
```

4. Start Thorium.

You can also pass a parent folder (e.g. `...\Thorium\Application`); the script picks the newest subfolder containing the `.pak` files.

To undo:

```bash
python recolor_folders.py --restore "C:\Users\YOU\AppData\Local\Thorium\Application\156.0.8078.28"
```

> If Thorium is installed under `Program Files` (or `/opt` on Linux), run the terminal as administrator / with `sudo`.

## After updating the browser

An update ships fresh, unmodified `.pak` files (usually in a new version folder). Simply run the apply command again. Backups are created per folder, so each version keeps its own `*.pak.orig`.

## Typical locations

| OS      | Path (may vary by install)                                                       |
|---------|----------------------------------------------------------------------------------|
| Windows | `%LOCALAPPDATA%\Thorium\Application\<version>\`                                  |
| Linux   | `/opt/chromium.org/thorium/`                                                     |
| macOS   | `/Applications/Thorium.app/Contents/Frameworks/Thorium Framework.framework/...`  |

Only Windows has been tested by the author; if the folder differs on your system, search for `chrome_100_percent.pak`.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--list` | – | Only list matching icons; change nothing |
| `--export DIR` | – | Save before/after PNG previews to `DIR`; change nothing |
| `--restore` | – | Restore the original `.pak` files from `*.orig` backups |
| `--only ID [ID ...]` | – | Process only these resource IDs |
| `--skip ID [ID ...]` | – | Skip these resource IDs |
| `--target-hue` | `212` | Resulting hue in degrees (blue ≈ 210, cyan ≈ 190) |
| `--sat-scale` | `0.55` | Saturation multiplier; lower = paler / greyer |
| `--val-scale` | `0.95` | Brightness multiplier |
| `--hue-min` / `--hue-max` | `35` / `65` | Hue range (degrees) treated as "yellow" |
| `--min-sat` | `0.35` | Minimum saturation for a pixel to count as yellow |
| `--min-share` | `0.6` | Minimum fraction of yellow pixels for an image to qualify |
| `--max-size` / `--min-size` | `40` / `12` | Image side limits in px (covers 16 px and 32 px folders) |

Example - a greyer, cooler blue:

```bash
python recolor_folders.py --target-hue 200 --sat-scale 0.4 "C:\...\Thorium\Application\156.0.8078.28"
```

## How it works

1. Parses the `.pak` header, resource table and alias table (v4 / v5).
2. For every resource starting with the PNG signature and within the size limits, converts pixels to HSV.
3. If at least `--min-share` of the visible pixels fall into the yellow hue range, the image is considered a folder-like icon.
4. Yellow pixels get the new hue and scaled saturation/brightness; alpha and non-yellow pixels (outlines, shadows) are untouched.
5. The `.pak` is rewritten with updated offsets. Resources that aren't matched are copied byte-for-byte.

## Troubleshooting

- **Other yellow icons were also recolored.** Run `--list` / `--export` first, then exclude their IDs with `--skip`, or restrict the run with `--only`. Raising `--min-share` or lowering `--max-size` also helps.
- **Nothing found / folders are still yellow.** Newer Chromium versions render some icons from vector data compiled into the browser binary, which `.pak` files can't change. The bookmark manager page (`chrome://bookmarks`) uses SVGs from `resources.pak`, which this tool does not touch.
- **Icons didn't change.** Make sure Thorium was fully closed during the run and restarted afterwards, and that you pointed the script at the correct version folder.
- **Permission denied.** Run the terminal as administrator / with `sudo`.
- **Thorium shows the old icon style.** Check whether it was launched with `--disable-thorium-icons`, which switches to different resources.

## Disclaimer

This tool modifies files inside your browser installation. It keeps backups and is easy to revert, but use it at your own risk. Not affiliated with the Thorium project or Google.

## Credits
The code was written using web version of Claude Sonnet 5.5 😁.

## License

[MIT](LICENSE)
