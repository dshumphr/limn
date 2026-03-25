# fbi skill

Displays images on the Linux framebuffer using `fbi` (framebuffer imageviewer). Used to show generated art on a Raspberry Pi or any Linux system with a framebuffer device.

## Usage

```bash
echo "sudo fbi -a -noverbose -T 1 <image_path>" | sh
```

### Common Flags

| Flag | Description |
|------|-------------|
| `-a` | Autozoom — scale image to fit the screen |
| `-noverbose` | Suppress status output |
| `-T 1` | Use virtual terminal 1 |
| `-t <seconds>` | Slideshow delay in seconds (use with multiple images) |
| `--once` | Exit after showing all images (slideshow) |

## Examples

### Display the most recent upscaled image

```bash
echo "sudo fbi -a -noverbose -T 1 images/$(ls images/ | grep '_upscaled' | sort | tail -1)" | sh
```

### Display a specific image

```bash
echo "sudo fbi -a -noverbose -T 1 images/20260320_141023_upscaled.png" | sh
```

### Slideshow of all upscaled images

```bash
echo "sudo fbi -a -noverbose -T 1 -t 10 --once images/*_upscaled.png" | sh
```

## Notes

- Always prefer displaying `_upscaled.png` files for best visual quality.
- Always run with `sudo` via `echo "..." | sh` to avoid framebuffer/TTY permission issues, especially over SSH.
- To kill an active `fbi` instance: `echo "sudo pkill fbi" | sh`
- **Never use the View tool to display images.** Always use `sudo fbi` via `echo "..." | sh`. The View tool does not display on the framebuffer.
