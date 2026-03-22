#!/usr/bin/env python3
"""
Theme Consolidation Tool for Historical Documents

After batch processing, this script:
1. Extracts all themes from processed markdown files
2. Uses Claude to identify and consolidate similar/duplicate themes
3. Creates a master theme taxonomy
4. Optionally updates all documents with standardized themes

This solves the problem of theme inconsistency across large batches.
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import Counter
import re
from anthropic import Anthropic


class ThemeConsolidator:
    """Consolidate and standardize themes across processed documents"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize the consolidator
        
        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
    
    def extract_themes_from_markdown(self, md_file: Path) -> Tuple[List[str], Dict]:
        """
        Extract themes from a markdown file's YAML frontmatter
        
        Args:
            md_file: Path to markdown file
            
        Returns:
            Tuple of (themes_list, full_metadata_dict)
        """
        content = md_file.read_text(encoding='utf-8')
        
        # Extract YAML frontmatter
        yaml_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not yaml_match:
            return [], {}
        
        try:
            metadata = yaml.safe_load(yaml_match.group(1))
            themes = metadata.get('themes', [])
            
            # Clean wiki-link format if present
            cleaned_themes = []
            for theme in themes:
                # Remove [[brackets]]
                theme_clean = re.sub(r'\[\[(.*?)\]\]', r'\1', theme)
                cleaned_themes.append(theme_clean)
            
            return cleaned_themes, metadata
        except yaml.YAMLError:
            return [], {}
    
    def collect_all_themes(self, input_dir: Path) -> Dict[str, List[Path]]:
        """
        Collect all themes from all markdown files
        
        Args:
            input_dir: Directory containing processed markdown files
            
        Returns:
            Dictionary mapping themes to list of files containing them
        """
        theme_files = {}
        
        for md_file in input_dir.glob("*.md"):
            themes, _ = self.extract_themes_from_markdown(md_file)
            
            for theme in themes:
                if theme not in theme_files:
                    theme_files[theme] = []
                theme_files[theme].append(md_file)
        
        return theme_files
    
    def consolidate_themes(self, themes: List[str]) -> Dict[str, List[str]]:
        """
        Use Claude to consolidate similar themes
        
        Args:
            themes: List of all unique themes
            
        Returns:
            Dictionary mapping canonical theme to list of variants
        """
        if len(themes) <= 1:
            return {themes[0]: [themes[0]]} if themes else {}
        
        prompt = f"""You are analyzing themes extracted from historical documents about Western American history, federal land policy, and the Sagebrush Rebellion.

Here are all the themes that were identified across {len(themes)} documents:

{chr(10).join(f"- {theme}" for theme in sorted(themes))}

Your task: Consolidate these themes by:
1. Identifying themes that refer to the same concept but use different wording
2. Choosing the most precise, historically accurate canonical term for each concept
3. Grouping variant terms under their canonical form

Output ONLY valid YAML in this format:

```yaml
theme_groups:
  - canonical: "federal grazing policy"
    variants:
      - "grazing policy"
      - "grazing regulations"
      - "federal grazing"
  - canonical: "public lands management"
    variants:
      - "public lands"
      - "public domain"
      - "federal lands"
```

Rules:
- Only group themes that CLEARLY refer to the same concept
- If unsure, keep themes separate
- Use the most specific, accurate term as canonical
- Include the canonical term in its own variants list
- Be conservative - don't over-consolidate distinct concepts
"""
        
        print("  Asking Claude to consolidate themes...")
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        # Parse YAML response
        yaml_match = re.search(r'```yaml\n(.*?)\n```', response_text, re.DOTALL)
        if not yaml_match:
            print("  ⚠ Warning: Could not parse consolidation response")
            # Return each theme as its own group
            return {theme: [theme] for theme in themes}
        
        try:
            consolidation = yaml.safe_load(yaml_match.group(1))
            theme_groups = consolidation.get('theme_groups', [])
            
            # Convert to dictionary format
            result = {}
            for group in theme_groups:
                canonical = group['canonical']
                variants = group['variants']
                result[canonical] = variants
            
            # Add any themes that weren't consolidated
            consolidated_variants = set()
            for variants in result.values():
                consolidated_variants.update(variants)
            
            for theme in themes:
                if theme not in consolidated_variants:
                    result[theme] = [theme]
            
            return result
            
        except yaml.YAMLError as e:
            print(f"  ⚠ Warning: YAML parsing error: {e}")
            return {theme: [theme] for theme in themes}
    
    def create_theme_mapping(self, theme_groups: Dict[str, List[str]]) -> Dict[str, str]:
        """
        Create a mapping from variant themes to canonical themes
        
        Args:
            theme_groups: Dictionary of canonical -> variants
            
        Returns:
            Dictionary mapping each variant to its canonical form
        """
        mapping = {}
        for canonical, variants in theme_groups.items():
            for variant in variants:
                mapping[variant] = canonical
        return mapping
    
    def update_markdown_file(
        self, 
        md_file: Path, 
        theme_mapping: Dict[str, str],
        backup: bool = True
    ) -> None:
        """
        Update a markdown file with consolidated themes
        
        Args:
            md_file: Path to markdown file
            theme_mapping: Dictionary mapping variant to canonical themes
            backup: Whether to create a backup file
        """
        content = md_file.read_text(encoding='utf-8')
        
        # Extract YAML frontmatter
        yaml_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not yaml_match:
            print(f"  ⚠ No YAML frontmatter in {md_file.name}")
            return
        
        try:
            metadata = yaml.safe_load(yaml_match.group(1))
            original_themes = metadata.get('themes', [])
            
            # Map to canonical themes
            canonical_themes = set()
            for theme in original_themes:
                # Remove wiki-link brackets
                theme_clean = re.sub(r'\[\[(.*?)\]\]', r'\1', theme)
                
                # Map to canonical
                canonical = theme_mapping.get(theme_clean, theme_clean)
                canonical_themes.add(canonical)
            
            # Update metadata
            metadata['themes'] = sorted([f"[[{theme}]]" for theme in canonical_themes])
            metadata['themes_consolidated'] = True
            
            # Preserve original themes for reference
            if 'original_themes' not in metadata:
                metadata['original_themes'] = original_themes
            
            # Rebuild frontmatter
            new_frontmatter = yaml.dump(metadata, allow_unicode=True, sort_keys=False)
            
            # Replace frontmatter
            new_content = re.sub(
                r'^---\n.*?\n---',
                f'---\n{new_frontmatter}---',
                content,
                count=1,
                flags=re.DOTALL
            )
            
            # Backup if requested
            if backup:
                backup_file = md_file.with_suffix('.md.bak')
                md_file.rename(backup_file)
            
            # Write updated file
            md_file.write_text(new_content, encoding='utf-8')
            
        except yaml.YAMLError as e:
            print(f"  ✗ Error updating {md_file.name}: {e}")
    
    def generate_theme_report(
        self,
        theme_files: Dict[str, List[Path]],
        theme_groups: Dict[str, List[str]],
        output_file: Path
    ) -> None:
        """
        Generate a markdown report of theme analysis
        
        Args:
            theme_files: Mapping of themes to files
            theme_groups: Consolidated theme groups
            output_file: Where to save the report
        """
        lines = [
            "# Theme Analysis Report\n",
            f"Generated: {Path.cwd()}\n",
            f"Total unique themes (before consolidation): {len(theme_files)}\n",
            f"Consolidated theme groups: {len(theme_groups)}\n",
            "\n## Consolidated Themes\n"
        ]
        
        # Sort by frequency
        theme_freq = {
            canonical: sum(len(theme_files.get(variant, [])) for variant in variants)
            for canonical, variants in theme_groups.items()
        }
        
        sorted_themes = sorted(
            theme_groups.items(),
            key=lambda x: theme_freq[x[0]],
            reverse=True
        )
        
        for canonical, variants in sorted_themes:
            count = theme_freq[canonical]
            lines.append(f"\n### {canonical}\n")
            lines.append(f"**Appears in:** {count} documents\n")
            
            if len(variants) > 1:
                lines.append(f"**Variants consolidated:**\n")
                for variant in sorted(variants):
                    if variant != canonical:
                        variant_count = len(theme_files.get(variant, []))
                        lines.append(f"- {variant} ({variant_count} docs)\n")
        
        output_file.write_text(''.join(lines), encoding='utf-8')


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description="Consolidate themes across batch-processed historical documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ./transcriptions --report theme_analysis.md
  %(prog)s -i ./transcriptions --apply --backup
  %(prog)s -i ./notes --report themes.md --apply --no-backup

Workflow:
  1. Extract all themes from processed markdown files
  2. Use Claude to identify similar/duplicate themes
  3. Create consolidated theme taxonomy
  4. Optionally update files with standardized themes
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        type=Path,
        required=True,
        help='Directory containing processed markdown files'
    )
    
    parser.add_argument(
        '--report',
        type=Path,
        default='theme_consolidation_report.md',
        help='Output file for theme analysis report (default: theme_consolidation_report.md)'
    )
    
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Apply consolidated themes to markdown files'
    )
    
    parser.add_argument(
        '--backup/--no-backup',
        dest='backup',
        default=True,
        help='Create backup files before updating (default: yes)'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        help='Anthropic API key (or set ANTHROPIC_API_KEY environment variable)'
    )
    
    parser.add_argument(
        '--model',
        type=str,
        default='claude-sonnet-4-5-20250929',
        help='Claude model to use (default: claude-sonnet-4-5-20250929)'
    )
    
    args = parser.parse_args()
    
    # Get API key
    import os
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        parser.error("API key required via --api-key or ANTHROPIC_API_KEY environment variable")
    
    # Validate input directory
    if not args.input.exists():
        parser.error(f"Input directory does not exist: {args.input}")
    
    print("=" * 60)
    print("Theme Consolidation Tool")
    print("=" * 60)
    print()
    
    # Initialize consolidator
    consolidator = ThemeConsolidator(api_key, args.model)
    
    # Step 1: Collect all themes
    print("Step 1: Collecting themes from all documents...")
    theme_files = consolidator.collect_all_themes(args.input)
    
    unique_themes = list(theme_files.keys())
    print(f"  ✓ Found {len(unique_themes)} unique themes")
    print(f"  ✓ Across {len(list(args.input.glob('*.md')))} documents")
    print()
    
    # Show most common themes
    theme_counts = Counter({theme: len(files) for theme, files in theme_files.items()})
    print("  Most common themes:")
    for theme, count in theme_counts.most_common(10):
        print(f"    - {theme} ({count} docs)")
    print()
    
    # Step 2: Consolidate themes
    print("Step 2: Consolidating similar themes...")
    theme_groups = consolidator.consolidate_themes(unique_themes)
    
    consolidated_count = len(theme_groups)
    reduction = len(unique_themes) - consolidated_count
    
    print(f"  ✓ Consolidated into {consolidated_count} theme groups")
    if reduction > 0:
        print(f"  ✓ Reduced theme count by {reduction} ({reduction/len(unique_themes)*100:.1f}%)")
    print()
    
    # Show consolidations
    print("  Consolidation examples:")
    for canonical, variants in list(theme_groups.items())[:5]:
        if len(variants) > 1:
            print(f"    {canonical}:")
            for variant in variants:
                if variant != canonical:
                    print(f"      ← {variant}")
    print()
    
    # Step 3: Generate report
    print("Step 3: Generating theme analysis report...")
    consolidator.generate_theme_report(theme_files, theme_groups, args.report)
    print(f"  ✓ Report saved to: {args.report}")
    print()
    
    # Step 4: Apply to files (optional)
    if args.apply:
        print("Step 4: Applying consolidated themes to markdown files...")
        
        if args.backup:
            print("  (Creating backup files with .bak extension)")
        
        theme_mapping = consolidator.create_theme_mapping(theme_groups)
        
        md_files = list(args.input.glob("*.md"))
        for i, md_file in enumerate(md_files, 1):
            consolidator.update_markdown_file(md_file, theme_mapping, args.backup)
            if i % 10 == 0:
                print(f"  Processed {i}/{len(md_files)} files...")
        
        print(f"  ✓ Updated {len(md_files)} files")
        print()
    else:
        print("Step 4: Skipping file updates (use --apply to update files)")
        print("  Run with --apply to update markdown files with consolidated themes")
        print()
    
    print("=" * 60)
    print("✓ Theme consolidation complete!")
    print("=" * 60)
    print()
    print(f"Review the report: {args.report}")
    if args.apply:
        print(f"Markdown files updated in: {args.input}")
        if args.backup:
            print("Backup files saved with .bak extension")


if __name__ == "__main__":
    main()
