# OpenEvidence Converter

Convert OpenEvidence web clipper markdown output to clean, vault-compliant Obsidian markdown with proper citations, images, and YAML frontmatter.

## Features

- **Vault-compliant YAML frontmatter** — Three-tier standard with proper metadata
- **H1 document title** — Clean title extraction from content or filename
- **Normalized heading levels** — Proportional mapping starting at H2
- **Obsidian footnote citations** — Converts `Journal + N\[X-Y\]` to `[^N]` format
- **Local image references** — `<span class="rightimg">` format with download manifest
- **Clean reference section** — PMID/DOI links, tracking parameters removed
- **No boilerplate** — Strips OpenEvidence UI elements

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/openevidence-converter.git
cd openevidence-converter

# No dependencies required - uses Python 3 standard library only
python3 --version  # Requires Python 3.8+
```

## Usage

### Command Line

```bash
python3 openevidence_converter.py "INPUT_FILE.md" "OUTPUT_FILE.md"
```

**Options:**
- `--download-images` — (Future) Download images to local media folder

### Example

```bash
python3 openevidence_converter.py \
  "Sympathetic Nervous System (Original).md" \
  "Sympathetic Nervous System Activation in Heart Failure.md"
```

**Output:**
```
✓ Converted: Sympathetic Nervous System (Original).md
✓ Output: Sympathetic Nervous System Activation in Heart Failure.md

Images to download (2):
  - https://storage.googleapis.com/nejm-multimedia/...
    → Sympathetic-Nervous-System-2026-01-29-1.png
```

## Conversion Pipeline

```
Phase 1: Remove Preamble
├── Strip YAML (preserve for later)
├── Remove "Finished researching" and prior content
└── Skip redundant H3 title

Phase 2: Transform Inline Citations
├── Journal + N\[X-Y\] → [^X] [^Y]
├── Remove favicon images
└── Normalize citation spacing

Phase 3: Transform Images
├── Convert to <span class="rightimg"> format
├── Generate local filenames
└── Create download manifest

Phase 4: Format References
├── Parse reference entries
├── Extract author/title/journal/year
├── Add PMID links where available
└── Clean tracking parameters from URLs

Phase 5: Cleanup
├── Normalize heading levels (H4→H2, H5→H3)
├── Italicize table references
├── Remove artifacts
└── Normalize whitespace

Phase 6: Generate Output
├── Create vault-compliant YAML frontmatter
├── Add H1 document title
└── Write final output
```

## Output Format

### YAML Frontmatter

```yaml
---
created: 2026-01-29
modified: 2026-01-29
document-type: article
status: draft
area: medicine
topics:
  - heart failure
  - neurohormonal activation
tags:
  - medicine
  - cardiology/heart-failure
source: https://www.openevidence.com/ask/...
summary: "OpenEvidence article on..."
---
```

### Image Format

Images are converted to:
```html
<span class="rightimg">
<a href="#" tabindex="0">
<img src="Document-Title-2026-01-29-1.png" >
</a>
Figure 1. Caption text. Ref: Article Title. Journal. Date URL
</span>
```

### Citation Format

Input (OpenEvidence):
```markdown
sympathetic nervous system activation plays a crucial roleNEJM + 3\[7-9\]
```

Output (Obsidian):
```markdown
sympathetic nervous system activation plays a crucial role [^7] [^8] [^9]
```

## Full Production Workflow

For production-quality output, follow this complete workflow:

```bash
# 1. Run Python converter (99.5% of work)
python3 openevidence_converter.py "Original.md" "Converted.md"

# 2. Download images to media/ folder
mkdir -p media/
curl -o "media/image-1.png" "https://storage.googleapis.com/..."

# 3. LLM Post-Processing (heading semantics, YAML polish)
# - Fix any heading level inconsistencies
# - Improve tags and summary
# - Add appropriate aliases

# 4. Citation Sculptor (Vancouver formatting)
# See: https://github.com/YOUR_USERNAME/CitationSculptor
python3 citation_sculptor.py "Converted.md" --verbose --no-backup

# 5. Verify output
# - Spot-check references against PubMed
# - Check for "Webpage" misclassifications (Elsevier URLs)
# - Verify images render correctly in Obsidian
```

## Integration with Citation Sculptor

This converter produces references in a format that [Citation Sculptor](https://github.com/YOUR_USERNAME/CitationSculptor) can process:

**Before Citation Sculptor:**
```markdown
[^1]: Author. Title. Journal. Year. [PMID 12345678](https://pubmed.ncbi.nlm.nih.gov/12345678)
```

**After Citation Sculptor:**
```markdown
[^AuthorA-2024-12345678]: Author A, et al. Title. J Abbrev. 2024 Jan;1(1):1-10. [DOI](...). [PMID: 12345678](...)
```

## Known Limitations

1. **Heading level normalization** — OpenEvidence uses inconsistent H3/H4 for main sections. The converter normalizes proportionally, but semantic review may be needed.

2. **Image download** — Images must be downloaded manually (manifest provided). The `--download-images` flag is a future feature.

3. **Reference parsing** — Complex reference formats may not parse perfectly. Citation Sculptor handles final formatting.

4. **Elsevier URLs** — Links to `linkinghub.elsevier.com` may cause Citation Sculptor to misclassify as "webpages" instead of journal articles. Manual PMID lookup may be needed.

## Requirements

- Python 3.8+
- No external dependencies (standard library only)

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Related Projects

- [Citation Sculptor](https://github.com/YOUR_USERNAME/CitationSculptor) — Vancouver-style citation formatting with PubMed lookup
