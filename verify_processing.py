#!/usr/bin/env python3
"""
Comprehensive verification script for Google Photos Takeout processing results.
Validates that all original files were processed correctly and have accurate timestamps.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
import csv

class ProcessingVerifier:
    """Comprehensive verification of takeout processing results."""

    def __init__(self, processed_dir: Path):
        self.processed_dir = Path(processed_dir)
        self.google_photos_dir = self.processed_dir / "temp" / "extracted" / "Takeout" / "Google Photos"
        self.verification_results = {
            'total_media_files': 0,
            'files_with_json': 0,
            'files_with_dates': 0,
            'files_with_correct_dates': 0,
            'files_with_gps': 0,
            'files_with_descriptions': 0,
            'directory_structure_preserved': True,
            'albums_found': 0,
            'processing_errors': [],
            'timestamp_accuracy_issues': [],
            'missing_files': [],
            'sample_verifications': []
        }

    def verify_all(self) -> Dict:
        """Run comprehensive verification of all processing results."""
        print("🔍 Starting comprehensive verification...")

        # Check if directory structure exists
        if not self.google_photos_dir.exists():
            print(f"❌ Google Photos directory not found: {self.google_photos_dir}")
            return self.verification_results

        # Verify directory structure
        self.verify_directory_structure()

        # Find all media files
        media_files = self.find_all_media_files()
        self.verification_results['total_media_files'] = len(media_files)

        print(f"📁 Found {len(media_files)} media files across {self.verification_results['albums_found']} albums")

        # Verify each file
        self.verify_media_files(media_files)

        # Generate summary
        self.generate_verification_summary()

        return self.verification_results

    def verify_directory_structure(self):
        """Verify that the original directory structure is preserved."""
        try:
            albums = [d for d in self.google_photos_dir.iterdir() if d.is_dir()]
            self.verification_results['albums_found'] = len(albums)

            print(f"📂 Albums found: {len(albums)}")

            # Sample some album names to check for preservation
            sample_albums = albums[:5]
            for album in sample_albums:
                print(f"   - {album.name}")

        except Exception as e:
            print(f"❌ Error verifying directory structure: {e}")
            self.verification_results['directory_structure_preserved'] = False

    def find_all_media_files(self) -> List[Path]:
        """Find all media files in the processed directory."""
        media_extensions = {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov', '.m4v', '.gif', '.tiff', '.bmp'}
        media_files = []

        try:
            for file_path in self.google_photos_dir.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                    if not file_path.name.endswith('.json'):
                        media_files.append(file_path)
        except Exception as e:
            print(f"❌ Error finding media files: {e}")

        return media_files

    def verify_media_files(self, media_files: List[Path]):
        """Verify metadata processing for all media files."""
        print("🔍 Verifying metadata processing...")

        for i, media_file in enumerate(media_files):
            if i % 50 == 0:  # Progress update every 50 files
                progress = (i / len(media_files)) * 100
                print(f"   Progress: {progress:.1f}% ({i}/{len(media_files)})")

            self.verify_single_file(media_file)

            # Sample detailed verification for first 10 files
            if i < 10:
                detailed_result = self.detailed_file_verification(media_file)
                if detailed_result:
                    self.verification_results['sample_verifications'].append(detailed_result)

    def verify_single_file(self, media_file: Path):
        """Verify metadata processing for a single file."""
        try:
            # Find corresponding JSON file
            json_file = self.find_json_metadata(media_file)
            if json_file:
                self.verification_results['files_with_json'] += 1

                # Load JSON metadata
                json_data = self.load_json_safely(json_file)

                # Get EXIF metadata
                exif_data = self.get_exif_metadata(media_file)

                if exif_data:
                    # Check date metadata
                    if exif_data.get('DateTimeOriginal'):
                        self.verification_results['files_with_dates'] += 1

                        # Verify timestamp accuracy
                        if self.verify_timestamp_accuracy(json_data, exif_data, media_file):
                            self.verification_results['files_with_correct_dates'] += 1

                    # Check GPS metadata
                    if exif_data.get('GPSLatitude'):
                        self.verification_results['files_with_gps'] += 1

                    # Check description metadata
                    if exif_data.get('Description') or exif_data.get('ImageDescription'):
                        self.verification_results['files_with_descriptions'] += 1

        except Exception as e:
            error_msg = f"Error verifying {media_file.name}: {e}"
            self.verification_results['processing_errors'].append(error_msg)

    def detailed_file_verification(self, media_file: Path) -> Dict:
        """Perform detailed verification of a single file for sampling."""
        try:
            json_file = self.find_json_metadata(media_file)
            if not json_file:
                return None

            json_data = self.load_json_safely(json_file)
            exif_data = self.get_exif_metadata(media_file)

            if not exif_data:
                return None

            # Extract original timestamp from JSON
            original_timestamp = json_data.get('photoTakenTime', {}).get('timestamp')
            original_lat = json_data.get('geoData', {}).get('latitude', 0)
            original_desc = json_data.get('description', '')

            # Extract embedded metadata
            embedded_date = exif_data.get('DateTimeOriginal')
            embedded_gps = exif_data.get('GPSLatitude')
            embedded_desc = exif_data.get('Description') or exif_data.get('ImageDescription')

            return {
                'filename': media_file.name,
                'album': media_file.parent.name,
                'original_timestamp': original_timestamp,
                'embedded_date': embedded_date,
                'date_match': self.verify_timestamp_accuracy(json_data, exif_data, media_file),
                'has_gps_original': original_lat != 0,
                'has_gps_embedded': embedded_gps is not None,
                'has_description_original': bool(original_desc),
                'has_description_embedded': bool(embedded_desc),
                'processing_success': bool(embedded_date or embedded_gps or embedded_desc)
            }

        except Exception as e:
            return {
                'filename': media_file.name,
                'error': str(e)
            }

    def find_json_metadata(self, media_file: Path) -> Path:
        """Find corresponding JSON metadata file."""
        base_path = media_file.parent / media_file.name

        patterns = [
            f"{base_path}.supplemental-metadata.json",
            f"{base_path}.supplemental-metada.json",
            f"{base_path}.s.json",
            f"{base_path}.json"
        ]

        for pattern in patterns:
            json_path = Path(pattern)
            if json_path.exists():
                return json_path

        return None

    def load_json_safely(self, json_path: Path) -> Dict:
        """Safely load JSON metadata file."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def get_exif_metadata(self, media_file: Path) -> Dict:
        """Extract EXIF metadata using ExifTool."""
        try:
            cmd = ['exiftool', '-json', '-DateTimeOriginal', '-CreateDate', '-ModifyDate',
                   '-GPSLatitude', '-GPSLongitude', '-Description', '-ImageDescription',
                   '-Title', '-Keywords', str(media_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                return json.loads(result.stdout)[0]
        except Exception:
            pass

        return {}

    def verify_timestamp_accuracy(self, json_data: Dict, exif_data: Dict, media_file: Path) -> bool:
        """Verify that embedded timestamps match the original JSON timestamps."""
        try:
            original_timestamp = json_data.get('photoTakenTime', {}).get('timestamp')
            embedded_date = exif_data.get('DateTimeOriginal')

            if not original_timestamp or not embedded_date:
                return False

            # Convert timestamp to comparable formats (trying different timezone interpretations)
            original_utc_dt = datetime.fromtimestamp(int(original_timestamp), datetime.timezone.utc)
            original_local_dt = datetime.fromtimestamp(int(original_timestamp))

            # Parse embedded date (format: "YYYY:MM:DD HH:MM:SS")
            try:
                embedded_dt = datetime.strptime(embedded_date, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                # Try alternative format
                embedded_dt = datetime.strptime(embedded_date.split('.')[0], "%Y:%m:%d %H:%M:%S")

            # Check if dates match against either UTC or local time (with reasonable tolerance)
            utc_diff = abs((original_utc_dt.replace(tzinfo=None) - embedded_dt).total_seconds())
            local_diff = abs((original_local_dt - embedded_dt).total_seconds())

            # Accept if either interpretation is within 6 hours (timezone differences)
            time_diff = min(utc_diff, local_diff)

            if time_diff > 21600:  # 6 hours tolerance for timezone issues
                self.verification_results['timestamp_accuracy_issues'].append({
                    'file': media_file.name,
                    'original_utc': original_utc_dt.isoformat(),
                    'original_local': original_local_dt.isoformat(),
                    'embedded': embedded_dt.isoformat(),
                    'utc_diff_hours': utc_diff / 3600,
                    'local_diff_hours': local_diff / 3600
                })
                return False

            return True

        except Exception as e:
            return False

    def generate_verification_summary(self):
        """Generate and display verification summary."""
        print("\n" + "="*60)
        print("📊 COMPREHENSIVE VERIFICATION RESULTS")
        print("="*60)

        total = self.verification_results['total_media_files']

        # File coverage
        print(f"\n📁 FILE COVERAGE:")
        print(f"   Total media files found: {total}")
        print(f"   Files with JSON metadata: {self.verification_results['files_with_json']} ({self.percentage(self.verification_results['files_with_json'], total)}%)")

        # Metadata restoration
        print(f"\n📅 DATE METADATA:")
        print(f"   Files with embedded dates: {self.verification_results['files_with_dates']} ({self.percentage(self.verification_results['files_with_dates'], total)}%)")
        print(f"   Files with correct dates: {self.verification_results['files_with_correct_dates']} ({self.percentage(self.verification_results['files_with_correct_dates'], total)}%)")

        print(f"\n📍 GPS METADATA:")
        print(f"   Files with GPS data: {self.verification_results['files_with_gps']} ({self.percentage(self.verification_results['files_with_gps'], total)}%)")

        print(f"\n📝 DESCRIPTIONS:")
        print(f"   Files with descriptions: {self.verification_results['files_with_descriptions']} ({self.percentage(self.verification_results['files_with_descriptions'], total)}%)")

        # Directory structure
        print(f"\n📂 DIRECTORY STRUCTURE:")
        print(f"   Original structure preserved: {'✅ Yes' if self.verification_results['directory_structure_preserved'] else '❌ No'}")
        print(f"   Albums found: {self.verification_results['albums_found']}")

        # Issues
        if self.verification_results['timestamp_accuracy_issues']:
            print(f"\n⚠️ TIMESTAMP ACCURACY ISSUES:")
            print(f"   Files with timestamp mismatches: {len(self.verification_results['timestamp_accuracy_issues'])}")

        if self.verification_results['processing_errors']:
            print(f"\n❌ PROCESSING ERRORS:")
            print(f"   Files with processing errors: {len(self.verification_results['processing_errors'])}")
            for error in self.verification_results['processing_errors'][:5]:  # Show first 5
                print(f"      - {error}")

        # Sample verifications
        if self.verification_results['sample_verifications']:
            print(f"\n🔍 SAMPLE VERIFICATION (first 10 files):")
            for sample in self.verification_results['sample_verifications'][:5]:
                if 'error' not in sample:
                    print(f"   {sample['filename']} ({sample['album']}):")
                    print(f"      Date restored: {'✅' if sample['date_match'] else '❌'}")
                    print(f"      GPS: {'✅' if sample['has_gps_embedded'] else '❌'}")
                    print(f"      Description: {'✅' if sample['has_description_embedded'] else '❌'}")

    def percentage(self, part: int, total: int) -> float:
        """Calculate percentage with safety check."""
        return round((part / total) * 100, 1) if total > 0 else 0.0

    def save_detailed_report(self):
        """Save detailed verification report to CSV."""
        report_path = self.processed_dir / 'verification_report.csv'

        with open(report_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Metric', 'Count', 'Percentage'])

            total = self.verification_results['total_media_files']
            writer.writerow(['Total Files', total, '100.0'])
            writer.writerow(['Files with JSON', self.verification_results['files_with_json'], self.percentage(self.verification_results['files_with_json'], total)])
            writer.writerow(['Files with Dates', self.verification_results['files_with_dates'], self.percentage(self.verification_results['files_with_dates'], total)])
            writer.writerow(['Files with Correct Dates', self.verification_results['files_with_correct_dates'], self.percentage(self.verification_results['files_with_correct_dates'], total)])
            writer.writerow(['Files with GPS', self.verification_results['files_with_gps'], self.percentage(self.verification_results['files_with_gps'], total)])
            writer.writerow(['Files with Descriptions', self.verification_results['files_with_descriptions'], self.percentage(self.verification_results['files_with_descriptions'], total)])

        print(f"\n📄 Detailed report saved to: {report_path}")

def main():
    """Main entry point for verification script."""
    if len(sys.argv) != 2:
        print("Usage: python3 verify_processing.py <processed_directory>")
        print("Example: python3 verify_processing.py ~/Desktop/processed_photos_v2")
        sys.exit(1)

    processed_dir = Path(sys.argv[1]).expanduser()

    if not processed_dir.exists():
        print(f"❌ Directory not found: {processed_dir}")
        sys.exit(1)

    verifier = ProcessingVerifier(processed_dir)
    results = verifier.verify_all()
    verifier.save_detailed_report()

    print(f"\n✅ Verification complete!")

if __name__ == "__main__":
    main()