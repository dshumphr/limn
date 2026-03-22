# limn

An AI art generation agent for the age of agents.

Generates and edits images from natural language prompts using FLUX.1 and AuraSR, displays them via framebuffer, and learns your aesthetic preferences over time.

## Setup

```bash
export FAL_KEY=your_fal_key
export ANTHROPIC_API_KEY=your_anthropic_key
```

## Usage

Point an agent (e.g. Claude) at this repo with `AGENTS.md` as context. Then just ask for art.

> "Draw a foggy harbor at dawn"
> "Make it feel more like a woodblock print"
> "Show me the last image"

## Structure

- `AGENTS.md` — agent instructions and learned user preferences
- `skills/frameit/` — image generation and editing via fal.ai
- `skills/fbi/` — framebuffer display
- `images/` — all generated outputs
