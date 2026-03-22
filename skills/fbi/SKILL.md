# fbi skill

Displays images on the Linux framebuffer using `fbi` (framebuffer imageviewer). Used to show generated art on a Raspberry Pi or any Linux system with a framebuffer device.

## Usage

```bash
fbi -a -noverbose -T 1 <image_path>
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
fbi -a -noverbose -T 1 images/$(ls images/ | grep '_upscaled' | sort | tail -1)
```

### Display a specific image

```bash
fbi -a -noverbose -T 1 images/20260320_141023_upscaled.png
```

### Slideshow of all upscaled images

```bash
fbi -a -noverbose -T 1 -t 10 --once images/*_upscaled.png
```

## Notes

- Always prefer displaying `_upscaled.png` files for best visual quality.
- Requires root or membership in the `video` group on most systems.
- To kill an active `fbi` instance: `sudo pkill fbi`
