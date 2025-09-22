#!/usr/bin/env python3
"""
Comprehensive file mapping analysis for Google Photos Takeout.
Analyzes the relationship between media files and JSON metadata files.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
import csv

class TakeoutMappingAnalyzer:
    """Analyzes file-to-metadata mappings in Google Photos Takeout."""

    def __init__(self, takeout_dir: Path):
        self.takeout_dir = Path(takeout_dir)
        self.google_photos_dir = self.takeout_dir / "Google Photos"

        self.analysis_results = {
            'total_media_files': 0,
            'total_json_files': 0,
            'direct_matches': 0,
            'edited_photos': 0,
            'edited_with_original_json': 0,
            'photos_without_json': 0,
            'json_without_photos': 0,
            'album_metadata_files': 0,
            'mapping_patterns': defaultdict(int),
            'file_details': [],
            'unmapped_files': [],
            'mapping_analysis': {}
        }

    def analyze_all_mappings(self) -> Dict:
        """Run comprehensive mapping analysis."""
        print("🔍 Starting comprehensive file mapping analysis...")

        if not self.google_photos_dir.exists():
            print(f"❌ Google Photos directory not found: {self.google_photos_dir}")
            return self.analysis_results

        # Find all files
        media_files = self.find_all_media_files()
        json_files = self.find_all_json_files()

        self.analysis_results['total_media_files'] = len(media_files)
        self.analysis_results['total_json_files'] = len(json_files)

        print(f"📁 Found {len(media_files)} media files")
        print(f"📄 Found {len(json_files)} JSON files")

        # Analyze mappings
        self.analyze_file_mappings(media_files, json_files)

        # Generate detailed analysis
        self.generate_mapping_analysis()

        return self.analysis_results

    def find_all_media_files(self) -> List[Path]:
        """Find all media files in the Google Photos directory."""
        media_extensions = {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov', '.m4v', '.gif', '.tiff', '.bmp'}
        media_files = []

        for file_path in self.google_photos_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                media_files.append(file_path)

        return sorted(media_files)

    def find_all_json_files(self) -> List[Path]:
        """Find all JSON metadata files."""
        json_files = []

        for file_path in self.google_photos_dir.rglob('*.json'):
            if file_path.is_file():
                json_files.append(file_path)

        return sorted(json_files)

    def analyze_file_mappings(self, media_files: List[Path], json_files: List[Path]):
        """Analyze the mapping between media files and JSON files."""
        print("🔍 Analyzing file mappings...")

        # Create sets for efficient lookup
        json_set = set(json_files)
        media_set = set(media_files)

        for media_file in media_files:
            file_analysis = self.analyze_single_file_mapping(media_file, json_set)
            self.analysis_results['file_details'].append(file_analysis)

            # Update counters
            if file_analysis['is_edited']:
                self.analysis_results['edited_photos'] += 1
                if file_analysis['has_json']:
                    self.analysis_results['edited_with_original_json'] += 1

            if file_analysis['has_direct_json']:
                self.analysis_results['direct_matches'] += 1
            elif not file_analysis['has_json']:
                self.analysis_results['photos_without_json'] += 1
                self.analysis_results['unmapped_files'].append(str(media_file))

            # Track mapping patterns
            pattern = file_analysis['mapping_pattern']
            self.analysis_results['mapping_patterns'][pattern] += 1

        # Analyze JSON files that don't have corresponding media files
        self.analyze_orphaned_json_files(json_files, media_set)

    def analyze_single_file_mapping(self, media_file: Path, json_set: Set[Path]) -> Dict:
        """Analyze mapping for a single media file."""
        result = {
            'filename': media_file.name,
            'album': media_file.parent.name,
            'full_path': str(media_file),
            'is_edited': '-edited' in media_file.name,
            'has_direct_json': False,
            'has_json': False,
            'json_file': None,
            'mapping_pattern': 'no_json',
            'metadata_source': None
        }

        # Check for direct JSON match
        direct_json = self.find_json_for_media_file(media_file)
        if direct_json and direct_json in json_set:
            result['has_direct_json'] = True
            result['has_json'] = True
            result['json_file'] = str(direct_json)
            result['mapping_pattern'] = 'direct_match'
            result['metadata_source'] = 'direct'
            return result

        # Check if it's an edited photo and can inherit from original
        if result['is_edited']:
            original_name = media_file.name.replace('-edited', '')
            original_file = media_file.parent / original_name
            original_json = self.find_json_for_media_file(original_file)

            if original_json and original_json in json_set:
                result['has_json'] = True
                result['json_file'] = str(original_json)
                result['mapping_pattern'] = 'edited_inherits_from_original'
                result['metadata_source'] = 'inherited'
                return result

        # Check for alternative JSON naming patterns
        alternative_json = self.find_alternative_json_patterns(media_file)
        if alternative_json:
            for alt_json in alternative_json:
                if alt_json in json_set:
                    result['has_json'] = True
                    result['json_file'] = str(alt_json)
                    result['mapping_pattern'] = 'alternative_pattern'
                    result['metadata_source'] = 'alternative'
                    return result

        return result

    def find_json_for_media_file(self, media_file: Path) -> Path:
        """Find the expected JSON file for a media file."""
        base_path = media_file.parent / media_file.name

        # Standard Google naming patterns
        patterns = [
            f"{base_path}.supplemental-metadata.json",
            f"{base_path}.supplemental-metada.json",  # Google's typo
            f"{base_path}.s.json",
            f"{base_path}.json"
        ]

        for pattern in patterns:
            json_path = Path(pattern)
            if json_path.exists():
                return json_path

        return None

    def find_alternative_json_patterns(self, media_file: Path) -> List[Path]:
        """Find alternative JSON patterns that might match."""
        alternatives = []

        # Try without extension
        base_name = media_file.stem
        base_dir = media_file.parent

        # Look for JSON files with similar names
        for json_file in base_dir.glob("*.json"):
            if json_file.name.startswith(base_name):
                alternatives.append(json_file)

        return alternatives

    def analyze_orphaned_json_files(self, json_files: List[Path], media_set: Set[Path]):
        """Analyze JSON files that don't have corresponding media files."""
        for json_file in json_files:
            # Skip album metadata files
            if json_file.name == 'metadata.json':
                self.analysis_results['album_metadata_files'] += 1
                continue

            # Try to find corresponding media file
            if not self.find_media_for_json(json_file, media_set):
                self.analysis_results['json_without_photos'] += 1

    def find_media_for_json(self, json_file: Path, media_set: Set[Path]) -> bool:
        """Check if a JSON file has a corresponding media file."""
        # Extract base name from JSON file
        json_name = json_file.name

        # Remove JSON suffixes
        suffixes_to_remove = [
            '.supplemental-metadata.json',
            '.supplemental-metada.json',
            '.s.json',
            '.json'
        ]

        base_name = json_name
        for suffix in suffixes_to_remove:
            if json_name.endswith(suffix):
                base_name = json_name[:-len(suffix)]
                break

        # Look for corresponding media file
        media_file = json_file.parent / base_name
        return media_file in media_set

    def generate_mapping_analysis(self):
        """Generate comprehensive mapping analysis."""
        print("\n" + "="*60)
        print("📊 FILE MAPPING ANALYSIS")
        print("="*60)

        total_media = self.analysis_results['total_media_files']
        total_json = self.analysis_results['total_json_files']

        print(f"\n📁 FILE COUNTS:")
        print(f"   Total media files: {total_media}")
        print(f"   Total JSON files: {total_json}")
        print(f"   Album metadata files: {self.analysis_results['album_metadata_files']}")

        print(f"\n🔗 MAPPING RESULTS:")
        print(f"   Direct JSON matches: {self.analysis_results['direct_matches']} ({self.percentage(self.analysis_results['direct_matches'], total_media)}%)")
        print(f"   Edited photos: {self.analysis_results['edited_photos']}")
        print(f"   Edited with original JSON: {self.analysis_results['edited_with_original_json']}")
        print(f"   Photos without JSON: {self.analysis_results['photos_without_json']} ({self.percentage(self.analysis_results['photos_without_json'], total_media)}%)")
        print(f"   JSON without photos: {self.analysis_results['json_without_photos']}")

        print(f"\n📋 MAPPING PATTERNS:")
        for pattern, count in self.analysis_results['mapping_patterns'].items():
            print(f"   {pattern}: {count} ({self.percentage(count, total_media)}%)")

        # Calculate potential 100% coverage
        direct_coverage = self.analysis_results['direct_matches']
        edited_coverage = self.analysis_results['edited_with_original_json']
        total_potential = direct_coverage + edited_coverage

        print(f"\n🎯 COVERAGE ANALYSIS:")
        print(f"   Current direct coverage: {self.percentage(direct_coverage, total_media)}%")
        print(f"   Potential with inheritance: {self.percentage(total_potential, total_media)}%")
        print(f"   Files that would remain unmapped: {total_media - total_potential}")

        # Store summary for return
        self.analysis_results['mapping_analysis'] = {
            'current_coverage_percent': self.percentage(direct_coverage, total_media),
            'potential_coverage_percent': self.percentage(total_potential, total_media),
            'unmappable_files': total_media - total_potential
        }

    def percentage(self, part: int, total: int) -> float:
        """Calculate percentage with safety check."""
        return round((part / total) * 100, 1) if total > 0 else 0.0

    def save_detailed_report(self, output_dir: Path):
        """Save detailed mapping report to CSV."""
        report_path = output_dir / 'file_mapping_analysis.csv'

        with open(report_path, 'w', newline='') as csvfile:
            fieldnames = ['filename', 'album', 'is_edited', 'has_direct_json', 'has_json',
                         'mapping_pattern', 'metadata_source', 'json_file']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for file_detail in self.analysis_results['file_details']:
                # Remove full_path for cleaner CSV
                csv_row = {k: v for k, v in file_detail.items() if k != 'full_path'}
                writer.writerow(csv_row)

        print(f"\n📄 Detailed mapping report saved to: {report_path}")

        # Also save unmapped files list
        unmapped_path = output_dir / 'unmapped_files.txt'
        with open(unmapped_path, 'w') as f:
            for unmapped_file in self.analysis_results['unmapped_files']:
                f.write(f"{unmapped_file}\n")

        print(f"📄 Unmapped files list saved to: {unmapped_path}")

    def print_sample_mappings(self, num_samples: int = 10):
        """Print sample mappings for verification."""
        print(f"\n🔍 SAMPLE MAPPINGS (first {num_samples}):")

        for i, detail in enumerate(self.analysis_results['file_details'][:num_samples]):
            status = "✅" if detail['has_json'] else "❌"
            edited = " (EDITED)" if detail['is_edited'] else ""
            print(f"   {status} {detail['filename']}{edited}")
            if detail['has_json']:
                print(f"      → {Path(detail['json_file']).name} ({detail['metadata_source']})")
            print()


def main():
    """Main entry point for mapping analysis."""
    if len(sys.argv) != 2:
        print("Usage: python3 analyze_file_mapping.py <google_photos_directory>")
        print("Example: python3 analyze_file_mapping.py ~/Desktop/processed_photos_final/temp/extracted/Takeout")
        sys.exit(1)

    takeout_dir = Path(sys.argv[1]).expanduser()

    if not takeout_dir.exists():
        print(f"❌ Directory not found: {takeout_dir}")
        sys.exit(1)

    analyzer = TakeoutMappingAnalyzer(takeout_dir)
    results = analyzer.analyze_all_mappings()

    # Save reports
    output_dir = takeout_dir.parent.parent.parent  # Go back to main output directory
    analyzer.save_detailed_report(output_dir)

    # Print sample mappings
    analyzer.print_sample_mappings()

    print(f"\n✅ Mapping analysis complete!")
    print(f"📊 Potential coverage with fixes: {results['mapping_analysis']['potential_coverage_percent']}%")

if __name__ == "__main__":
    main()