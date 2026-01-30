#!/usr/bin/env python3
"""
OpenEvidence Web Clipper to Obsidian Markdown Converter

Converts markdown files from Obsidian Web Clipper (OpenEvidence) into
clean, standardized Obsidian markdown with proper footnote citations.

Usage:
    python openevidence_converter.py input.md output.md [--download-images]
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def remove_preamble(text: str) -> str:
    """
    Phase 1: Remove OpenEvidence UI boilerplate.

    Preserves YAML frontmatter and removes everything between it and the
    actual content start (detected by "Finished researching" line or fallbacks).
    """
    lines = text.split('\n')

    # Find YAML frontmatter boundaries
    yaml_start = -1
    yaml_end = -1
    for i, line in enumerate(lines):
        if line.strip() == '---':
            if yaml_start == -1:
                yaml_start = i
            else:
                yaml_end = i
                break

    if yaml_end == -1:
        # No valid YAML frontmatter found
        yaml_section = []
        search_start = 0
    else:
        yaml_section = lines[yaml_start:yaml_end + 1]
        search_start = yaml_end + 1

    # Find content start using priority methods
    content_start = None

    # PRIMARY: Find "Finished researching" line
    for i in range(search_start, len(lines)):
        if 'Finished researching' in lines[i]:
            # Content starts at next non-blank line
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    content_start = j
                    break
            break

    # FALLBACK 1: Find first H4 heading (####)
    if content_start is None:
        for i in range(search_start, len(lines)):
            if lines[i].strip().startswith('####'):
                content_start = i
                break

    # FALLBACK 2: Find first line with citation pattern
    if content_start is None:
        citation_pattern = re.compile(r'\\\[\d+')
        for i in range(search_start, len(lines)):
            if citation_pattern.search(lines[i]):
                content_start = i
                break

    if content_start is None:
        content_start = search_start

    # Check if content starts with redundant H3 title (### Title that duplicates H1)
    content_lines = lines[content_start:]
    if content_lines and content_lines[0].strip().startswith('### '):
        # Skip this redundant heading
        content_start += 1

    # Reconstruct document
    result_lines = yaml_section + lines[content_start:]
    return '\n'.join(result_lines)


def parse_reference_numbers(ref_string: str) -> list[int]:
    """
    Parse reference string like '7-9' or '7' and return list of integers.
    '7-9' → [7, 8, 9]
    '7' → [7]
    """
    ref_string = ref_string.strip()
    if '-' in ref_string:
        parts = ref_string.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            start, end = int(parts[0]), int(parts[1])
            return list(range(start, end + 1))
    if ref_string.isdigit():
        return [int(ref_string)]
    return []


def extract_all_references(bracket_string: str) -> list[int]:
    """
    Parse string like '\\[7\\]\\[11-13\\]' and return all reference numbers.
    Returns: [7, 11, 12, 13] (preserves order, no sorting)
    """
    # Find all bracket groups: \[...\] or just digits
    pattern = r'\\?\[(\d+(?:-\d+)?)\]?'
    matches = re.findall(pattern, bracket_string)

    result = []
    for match in matches:
        result.extend(parse_reference_numbers(match))
    return result


def transform_inline_citations(text: str) -> str:
    """
    Phase 2: Convert inline citations to Obsidian footnote format.

    Handles patterns like:
    - Journal + count + range: Hypertension + 2\[1-3\] → [^1] [^2] [^3]
    - Favicon + journal + refs: ![](favicon...)NEJM + 2\[7-9\] → [^7] [^8] [^9]
    """

    # Step 1: Remove all favicon images (simplifies later patterns)
    favicon_pattern = r'!\[\]\(https://www\.google\.com/s2/favicons\?domain=[^)]+\)'
    text = re.sub(favicon_pattern, '', text)

    # Step 2: Transform citation blocks with journal prefix
    # Pattern: JournalName (1-4 capitalized words) + optional count + bracket groups
    # Examples: NEJM, ACC, Lancet, Internal Medicine, Heart Failure Reviews

    # Comprehensive pattern for journal names followed by citations
    journal_citation_pattern = re.compile(
        r'([A-Z][A-Za-z]*(?:\s+[A-Za-z]+){0,5})'  # Journal name (1-6 words)
        r'(?:\s*\+\s*\d+)?'  # Optional " + N" count
        r'\s*'
        r'((?:\\\[\d+(?:-\d+)?\\\])+)',  # One or more bracket groups
        re.MULTILINE
    )

    def replace_journal_citation(match):
        bracket_groups = match.group(2)
        refs = extract_all_references(bracket_groups)
        if refs:
            # No leading space - citations attach directly to preceding text
            return ' '.join(f'[^{r}]' for r in refs)
        return match.group(0)

    text = journal_citation_pattern.sub(replace_journal_citation, text)

    # Step 3: Handle any remaining escaped bracket citations without journal prefix
    # Pattern: \[N\] or \[N-M\] standing alone
    standalone_citation = re.compile(r'((?:\\\[\d+(?:-\d+)?\\\])+)')

    def replace_standalone(match):
        refs = extract_all_references(match.group(1))
        if refs:
            return ' '.join(f'[^{r}]' for r in refs)
        return match.group(0)

    text = standalone_citation.sub(replace_standalone, text)

    # Step 4: Handle incomplete citations (missing closing bracket at end of line)
    # Pattern: \[26 without closing bracket
    incomplete_pattern = re.compile(r'\\\[(\d+)(?!\])')
    text = incomplete_pattern.sub(r'[^\1]', text)

    # Step 5: Clean up any remaining escaped brackets that look like citations
    # Convert \[N\] patterns that might have been missed
    leftover_pattern = re.compile(r'\\\[(\d+)\\\]')
    text = leftover_pattern.sub(r'[^\1]', text)

    # Step 6: Normalize spacing around footnote citations
    # Do NOT add space before [^ - keep citations tight to preceding text
    # text = re.sub(r'([a-zA-Z0-9\.\,\;\:])(\[\^)', r'\1 \2', text)

    # Ensure single space between consecutive footnotes
    text = re.sub(r'\]\s*\[\^', '] [^', text)

    # Remove double spaces
    text = re.sub(r'  +', ' ', text)

    return text


def clean_url(url: str) -> str:
    """
    Remove tracking parameters from URLs.
    """
    # Parameters to remove
    tracking_params = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'url_ver', 'rfr_id', 'rfr_dat'
    ]

    try:
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            # Remove tracking parameters
            filtered = {k: v for k, v in params.items() if k not in tracking_params}
            if filtered:
                new_query = urlencode(filtered, doseq=True)
            else:
                new_query = ''
            cleaned = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))
            return cleaned
        return url
    except Exception:
        return url


def transform_images(text: str, doc_title: str, date: str) -> tuple[str, list[dict]]:
    """
    Phase 3: Convert external images to local reference format.

    Returns transformed text and a manifest of images to download.
    """
    image_manifest = []
    image_counter = [0]  # Use list to allow modification in nested function

    # Pattern to detect image blocks:
    # ![](external URL)
    #
    # Figure/Table N. Caption text
    #
    # [Article Title](URL) Journal. Date.
    #
    # Optional license line

    image_block_pattern = re.compile(
        r'!\[\]\((https://storage\.googleapis\.com/[^)]+)\)\s*\n'  # Image URL
        r'\s*\n?'  # Optional blank line
        r'((?:Figure|Table)\s+\d+\.?\s*[^\n]+)\s*\n'  # Caption
        r'\s*\n?'
        r'\[([^\]]+)\]\(([^)]+)\)\s*([^\n]+)\s*\n'  # [Article Title](URL) Journal. Date.
        r'(?:[^\n]*(?:license|License)[^\n]*\n)?',  # Optional license line
        re.MULTILINE
    )

    def replace_image_block(match):
        image_counter[0] += 1

        image_url = match.group(1)
        caption = match.group(2).strip()
        article_title = match.group(3).strip()
        source_url = clean_url(match.group(4).strip())
        journal_date = match.group(5).strip()

        # Generate local filename
        # Clean doc_title for filename
        safe_title = re.sub(r'[^\w\s-]', '', doc_title).strip()
        safe_title = re.sub(r'\s+', ' ', safe_title)
        local_filename = f"{safe_title}-{date}-{image_counter[0]}.png"

        # Add to manifest
        image_manifest.append({
            'source_url': image_url,
            'local_filename': local_filename,
            'caption': caption
        })

        # Strip trailing periods to avoid double periods
        article_title = article_title.rstrip('.')

        # Build HTML span
        html = (
            f'<span class="rightimg">'
            f'<a href="#" tabindex="0">'
            f'<img src="{local_filename}" >'
            f'</a>'
            f'{caption} Ref: {article_title}. {journal_date} {source_url}'
            f'</span>'
        )

        return html

    text = image_block_pattern.sub(replace_image_block, text)

    return text, image_manifest


def format_reference_section(text: str) -> str:
    """
    Phase 4: Restructure reference section to footnote format.

    Converts verbose reference entries with abstracts into compact footnotes.
    """
    # Find where references section begins
    # Look for the pattern: ### (empty or references header) followed by 1.
    ref_section_pattern = re.compile(
        r'(###\s*\n+)?'  # Optional empty ### header
        r'^1\.\s*$',  # First reference marker
        re.MULTILINE
    )

    match = ref_section_pattern.search(text)
    if not match:
        return text

    ref_start = match.start()
    body_text = text[:ref_start].rstrip()
    ref_text = text[ref_start:]

    # Parse individual reference entries
    # Each entry starts with "1." on its own line
    ref_entries = re.split(r'^1\.\s*$', ref_text, flags=re.MULTILINE)

    formatted_refs = []
    ref_number = 0

    # Remove favicon pattern
    favicon_pattern = re.compile(r'!\[\]\(https://www\.google\.com/s2/favicons[^)]+\)')

    for entry in ref_entries:
        if not entry.strip():
            continue

        # Extract title and URL from the link
        # Handle URLs that may contain parentheses (e.g., S0735-1097(15)00714-7)
        # Find [Title](URL) where we properly match parentheses in URL
        link_match = re.search(r'\[([^\]]+)\]\(', entry)
        if not link_match:
            continue

        title = link_match.group(1).strip()

        # Find the URL by counting balanced parentheses
        url_start = link_match.end()
        paren_count = 1
        url_end = url_start
        for i, char in enumerate(entry[url_start:], url_start):
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count == 0:
                    url_end = i
                    break
            elif char in '\n\r' and paren_count == 1:
                # URL shouldn't span lines, use current position
                url_end = i
                break

        if url_end <= url_start:
            continue

        raw_url = entry[url_start:url_end].strip()
        url = clean_url(raw_url)

        # Only increment after confirming this is a valid reference
        ref_number += 1

        # Extract journal line (line after the link)
        # Remove favicon if present
        entry_clean = favicon_pattern.sub('', entry)

        # Find the journal/author line
        lines = entry_clean.split('\n')
        journal_line = None
        for i, line in enumerate(lines):
            # Skip lines that are links (contain ]( which indicates markdown link)
            if '](' in line:
                continue
            # Journal line typically has pattern: Journal. Year. Authors.
            # Year should be standalone (not part of a URL like jama.2020.10262)
            if re.search(r'\.\s*(19|20)\d{2}\.\s+[A-Z]', line):
                journal_line = line.strip()
                break

        if not journal_line:
            # Fallback: take line after the link (look for line containing the title)
            for i, line in enumerate(lines):
                if title in line and '[' in line:
                    if i + 1 < len(lines) and lines[i + 1].strip():
                        journal_line = lines[i + 1].strip()
                    break

        if not journal_line:
            journal_line = "Unknown Journal."

        # Remove "Guideline" suffix if present
        journal_line = re.sub(r'\.?\s*Guideline\s*$', '', journal_line)

        # Parse journal line: Journal. Year. Authors.
        # Or: Authors are sometimes at the end
        journal_parts = journal_line.split('.')

        # Try to extract: Journal, Year, Authors
        journal = ""
        year = ""
        authors = ""

        # Look for year pattern
        for i, part in enumerate(journal_parts):
            year_match = re.search(r'\b(19|20)\d{2}\b', part)
            if year_match:
                year = year_match.group(0)
                # Everything before is journal
                journal = '.'.join(journal_parts[:i]).strip()
                if not journal:
                    journal = part.split(year)[0].strip()
                # Everything after (in same part or next) is authors
                after_year = part.split(year)[1].strip() if year in part else ''
                if after_year:
                    authors = after_year.lstrip('. ')
                elif i + 1 < len(journal_parts):
                    authors = '.'.join(journal_parts[i + 1:]).strip()
                break

        if not journal:
            journal = journal_parts[0].strip() if journal_parts else "Unknown"

        # Format URL link
        # Check if PubMed
        pmid_match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url)
        if pmid_match:
            pmid = pmid_match.group(1)
            url_link = f'[PMID {pmid}]({url})'
        else:
            url_link = f'[Link]({url})'

        # Strip trailing periods from components to avoid double periods
        authors = authors.rstrip('.')
        title = title.rstrip('.')
        journal = journal.rstrip('.')

        # Build footnote line
        # Format: [^N]: Authors. Title. Journal. Year. [PMID/Link](URL)
        if authors:
            footnote = f'[^{ref_number}]: {authors}. {title}. {journal}. {year}. {url_link}'
        else:
            footnote = f'[^{ref_number}]: {title}. {journal}. {year}. {url_link}'

        formatted_refs.append(footnote)

    # Combine body and references
    if formatted_refs:
        result = body_text + '\n\n# References\n' + '\n\n'.join(formatted_refs) + '\n'
    else:
        result = body_text

    return result


def normalize_heading_levels(text: str) -> str:
    """
    Normalize heading levels so content starts at H2 (after H1 title).

    OpenEvidence content often uses inconsistent H3/H4 for main sections.
    This maps all unique heading levels proportionally starting from H2.
    """
    heading_pattern = re.compile(r'^(#{2,6})\s+(.+)$', re.MULTILINE)
    headings = heading_pattern.findall(text)

    if not headings:
        return text

    # Get unique levels sorted
    unique_levels = sorted(set(len(h[0]) for h in headings))

    # If already starting at H2, no change needed
    if unique_levels and unique_levels[0] <= 2:
        return text

    # Create mapping: existing levels → new levels starting at H2
    # This handles inconsistent source levels (e.g., H3, H4 both as main sections)
    level_map = {}
    for i, level in enumerate(unique_levels):
        # Map to H2, H3, H4, etc. based on position in hierarchy
        level_map[level] = min(2 + i, 6)  # Cap at H6

    def replace_heading(match):
        hashes = match.group(1)
        content = match.group(2)
        old_level = len(hashes)
        new_level = level_map.get(old_level, old_level)
        return '#' * new_level + ' ' + content

    text = heading_pattern.sub(replace_heading, text)
    return text


def cleanup_misc(text: str) -> str:
    """
    Phase 5: Final cleanup passes.
    """
    # Fix escaped characters in body (not in URLs)
    # Only unescape brackets that aren't part of URLs
    text = re.sub(r'\\(\[|\])', r'\1', text)

    # Fix escaped parentheses in URLs
    text = re.sub(r'S0735-1097\\?\((\d+)\\?\)', r'S0735-1097(\1)', text)

    # Normalize heading levels (H4/H5 → H2/H3)
    text = normalize_heading_levels(text)

    # Italicize table references in body (before reference section)
    ref_section = text.find('# References')
    if ref_section > 0:
        body = text[:ref_section]
        refs = text[ref_section:]

        # Italicize "Table N" references
        body = re.sub(r'(?<!\*)\bTable\s+(\d+)\b(?!\*)', r'*Table \1*', body)

        text = body + refs

    # Remove orphaned section artifacts
    text = re.sub(r'^###\s*$', '', text, flags=re.MULTILINE)

    # Normalize whitespace - max 2 consecutive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove trailing whitespace on lines
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)

    # Ensure single newline at end of file
    text = text.rstrip() + '\n'

    return text


def extract_document_info(text: str, input_path: Path = None) -> dict:
    """
    Extract document metadata from YAML frontmatter, content, or filename.

    Returns dict with: title, date, source_url, topics
    """
    info = {
        'title': 'Document',
        'date': datetime.now().strftime('%Y-%m-%d'),
        'source_url': None,
        'topics': [],
        'area': 'medicine'  # Default for OpenEvidence content
    }

    # Try to get title from H1 heading
    title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if title_match:
        info['title'] = title_match.group(1).strip()
    elif input_path:
        # Fall back to filename
        info['title'] = input_path.stem

    # Clean title - remove parenthetical suffixes like "(Original)", "(OpenEvidence)"
    info['title'] = re.sub(r'\s*\([^)]*\)\s*$', '', info['title'])

    # Try to get date from YAML
    date_match = re.search(r'modified:\s*(\d{4}-\d{2}-\d{2})', text)
    if date_match:
        info['date'] = date_match.group(1)

    # Try to extract OpenEvidence source URL
    oe_url_match = re.search(r'https://www\.openevidence\.com/ask/[a-f0-9-]+', text)
    if oe_url_match:
        info['source_url'] = oe_url_match.group(0)

    # Extract topics from H3/H4 headings (after "Finished researching")
    headings = re.findall(r'^#{3,4}\s+(.+)$', text, re.MULTILINE)
    if headings:
        # Use first few headings as topics, clean them up
        topics = []
        for h in headings[:5]:
            # Skip generic headings
            if h.lower() not in ['references', 'sources', 'bibliography']:
                topic = h.strip()
                # Convert to kebab-case for potential tag use
                topics.append(topic)
        info['topics'] = topics

    return info


def generate_yaml_frontmatter(info: dict) -> str:
    """
    Generate vault-compliant YAML frontmatter.

    Follows the three-tier YAML standard:
    - Tier 1 (mandatory): created, modified, document-type, tags, status
    - Tier 2 (context): area, topics, summary, source
    """
    today = datetime.now().strftime('%Y-%m-%d')

    # Generate tags based on area and topics
    tags = []
    if info.get('area'):
        tags.append(info['area'])

    # Add topic-based tags (convert to kebab-case)
    for topic in info.get('topics', [])[:3]:
        tag = re.sub(r'[^\w\s-]', '', topic.lower())
        tag = re.sub(r'\s+', '-', tag)
        if tag and tag not in tags:
            tags.append(f"{info.get('area', 'medicine')}/{tag}")

    # Build YAML
    yaml_lines = [
        '---',
        f'created: {today}',
        f'modified: {today}',
        'document-type: article',
        'status: draft',
    ]

    # Area
    if info.get('area'):
        yaml_lines.append(f"area: {info['area']}")

    # Topics
    if info.get('topics'):
        yaml_lines.append('topics:')
        for topic in info['topics'][:5]:
            yaml_lines.append(f'  - {topic}')

    # Tags
    yaml_lines.append('tags:')
    for tag in tags[:10]:
        yaml_lines.append(f'  - {tag}')

    # Source
    if info.get('source_url'):
        yaml_lines.append(f"source: {info['source_url']}")

    # Summary placeholder
    yaml_lines.append(f'summary: "OpenEvidence article on {info["title"]}"')

    yaml_lines.append('---')

    return '\n'.join(yaml_lines)


def convert(input_path: Path, output_path: Path, download_images: bool = False) -> dict:
    """
    Main conversion function.

    Returns a dict with conversion results and image manifest.
    """
    text = input_path.read_text(encoding='utf-8')

    # Extract document info for image naming and frontmatter
    doc_info = extract_document_info(text, input_path)
    doc_title = doc_info['title']
    doc_date = doc_info['date']

    # Phase 1: Remove preamble
    text = remove_preamble(text)

    # Phase 2: Transform inline citations
    text = transform_inline_citations(text)

    # Phase 3: Transform images
    text, image_manifest = transform_images(text, doc_title, doc_date)

    # Phase 4: Format reference section
    text = format_reference_section(text)

    # Phase 5: Cleanup
    text = cleanup_misc(text)

    # Phase 6: Generate proper YAML frontmatter and add title
    # Remove any existing minimal YAML frontmatter
    text = re.sub(r'^---\s*\n(?:.*?\n)*?---\s*\n', '', text)

    # Generate vault-compliant frontmatter
    frontmatter = generate_yaml_frontmatter(doc_info)

    # Add H1 title after frontmatter
    text = f"{frontmatter}\n# {doc_title}\n{text.lstrip()}"

    # Write output
    output_path.write_text(text, encoding='utf-8')

    return {
        'input': str(input_path),
        'output': str(output_path),
        'title': doc_title,
        'images': image_manifest,
        'image_count': len(image_manifest)
    }


def main():
    """CLI entry point."""
    if len(sys.argv) < 3:
        print("Usage: python openevidence_converter.py input.md output.md [--download-images]")
        print("\nConverts OpenEvidence web clipper markdown to clean Obsidian format.")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    download_images = '--download-images' in sys.argv

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    try:
        result = convert(input_path, output_path, download_images)

        print(f"✓ Converted: {result['input']}")
        print(f"✓ Output: {result['output']}")

        if result['images']:
            print(f"\nImages to download ({result['image_count']}):")
            for img in result['images']:
                print(f"  - {img['source_url']}")
                print(f"    → {img['local_filename']}")

    except Exception as e:
        print(f"Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
