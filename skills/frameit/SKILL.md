# frameit skill

Generates or edits images via fal.ai (FLUX.1 schnell + AuraSR) and saves outputs to `images/`.

## Usage

```bash
python skills/frameit/frameit.py "<improved_prompt>" [options]
```

### Options

| Flag | Description |
|------|-------------|
| `--mode gen` | Text-to-image generation (default) |
| `--mode edit` | Image-to-image edit |
| `--edit <path>` | Path to the small image to edit (edit mode only; omit to auto-use the most recent) |
| `--original-prompt "<text>"` | The raw user prompt before improvement (stored in JSON) |
| `--save-dir <path>` | Output directory (default: `images/`) |

### Environment

- `FAL_KEY` — fal.ai API key (required)

## Outputs

Every invocation saves three files to `images/`:

| File | Description |
|------|-------------|
| `YYYYMMDD_HHMMSS.png` | Small generated/edited image |
| `YYYYMMDD_HHMMSS_upscaled.png` | 4× AuraSR upscaled version |
| `YYYYMMDD_HHMMSS.json` | Metadata: original prompt, improved prompt, mode, file paths |

File names sort identically alphabetically and chronologically.

## Examples

### Generate

```bash
python skills/frameit/frameit.py \
  "A towering medieval castle rises from a fog-shrouded cliff above a restless grey sea, its battlements lit by amber dusk light, painted in the style of Caspar David Friedrich." \
  --mode gen \
  --original-prompt "castle"
```

### Edit (auto-selects most recent small image)

```bash
python skills/frameit/frameit.py \
  "Same scene but heavy snowfall, the castle walls encrusted with ice, a lone torch flickering at the gate." \
  --mode edit \
  --original-prompt "make it snowy"
```

### Edit (explicit image path)

```bash
python skills/frameit/frameit.py \
  "Transform the scene to golden hour, warm light flooding the valley below." \
  --mode edit \
  --edit images/20260320_141023.png \
  --original-prompt "golden hour version"
```

## Important Rules

- **Never pass an `_upscaled.png` file to `--edit`.** Always use the small version.
- Always pass `--original-prompt` with the user's raw input so the JSON record is complete.
- The improved prompt passed as the positional argument is what gets sent to the model.
