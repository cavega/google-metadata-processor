#!/usr/bin/env python3
"""
Google Photos Takeout to Apple Photos Migration Tool
Hybrid CLI/GUI implementation with automatic ZIP handling.

This tool processes Google Photos Takeout files and prepares them for seamless
import into Apple Photos while preserving all metadata including dates, GPS
coordinates, descriptions, and tags.

Author: Generated from comprehensive development plan
Requirements: Python 3.8+, ExifTool
Optional: tkinter for GUI interface
"""

import os
import json
import subprocess
import logging
import shutil
import zipfile
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union
import argparse
import sys
import re
from collections import defaultdict
import concurrent.futures

# GUI imports (optional)
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


class GoogleTakeoutProcessor:
    """Main processor class for Google Takeout to Apple Photos migration."""

    def __init__(self, input_source: Union[Path, List[Path]], output_dir: Path,
                 dry_run: bool = False, use_system_unzip: bool = True):
        self.input_source = input_source
        self.output_dir = Path(output_dir)
        self.dry_run = dry_run
        self.use_system_unzip = use_system_unzip
        self.temp_dir = Path(output_dir) / "temp"

        # Track processing progress for GUI updates
        self.progress_callback = None
        self.status_callback = None

        # Statistics tracking
        self.stats = {
            'total_files': 0,
            'processed_files': 0,
            'json_matched': 0,
            'date_restored': 0,
            'gps_restored': 0,
            'extensions_fixed': 0,
            'live_photos_paired': 0,
            'zip_files_extracted': 0,
            'errors': []
        }

        self.setup_logging()
        self.validate_environment()

    def setup_logging(self):
        """Configure logging for detailed operation tracking."""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(self.output_dir / 'takeout_processing.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def validate_environment(self):
        """Validate that required tools and directories exist."""
        # Check ExifTool installation
        try:
            result = subprocess.run(['exiftool', '-ver'],
                                  capture_output=True, text=True, check=True)
            self.logger.info(f"ExifTool version {result.stdout.strip()} detected")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ExifTool not found. Install with: brew install exiftool")

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def update_status(self, message: str, progress: Optional[float] = None):
        """Update status for GUI or log for CLI."""
        self.logger.info(message)
        if self.status_callback:
            self.status_callback(message)
        if self.progress_callback and progress is not None:
            self.progress_callback(progress)

    def extract_takeout_zips(self, zip_sources: List[Path]) -> Path:
        """Extract ZIP files with performance optimization and Unicode support."""
        extraction_dir = self.temp_dir / "extracted"
        extraction_dir.mkdir(parents=True, exist_ok=True)

        self.update_status(f"Extracting {len(zip_sources)} ZIP files...")

        # Check if any ZIP files might have Unicode issues by scanning first few entries
        has_unicode_issues = self._check_for_unicode_issues(zip_sources[:1])  # Check first ZIP

        if has_unicode_issues:
            self.logger.info("Detected potential Unicode filename issues, using Python zipfile extraction")
            self._extract_sequential(zip_sources, extraction_dir)
        elif self.use_system_unzip and shutil.which('unzip'):
            self._extract_with_system_unzip(zip_sources, extraction_dir)
        elif len(zip_sources) > 1:
            self._extract_parallel(zip_sources, extraction_dir)
        else:
            self._extract_sequential(zip_sources, extraction_dir)

        self.stats['zip_files_extracted'] = len(zip_sources)
        return extraction_dir

    def _check_for_unicode_issues(self, zip_files: List[Path]) -> bool:
        """Check if ZIP files contain problematic Unicode filenames."""
        for zip_file in zip_files:
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    for member in zip_ref.infolist()[:10]:  # Check first 10 files
                        # Look for common problematic patterns
                        if any(char in member.filename for char in ['í', 'á', 'é', 'ñ', '�', '&']):
                            return True
                        # Check for non-ASCII characters
                        try:
                            member.filename.encode('ascii')
                        except UnicodeEncodeError:
                            return True
            except Exception:
                # If we can't read the ZIP, assume it might have issues
                return True
        return False

    def _extract_with_system_unzip(self, zip_files: List[Path], extraction_dir: Path):
        """Use system unzip command for best performance with Unicode support."""
        for i, zip_file in enumerate(zip_files):
            self.update_status(f"Extracting {zip_file.name}...", (i / len(zip_files)) * 0.2)
            try:
                # First try with -U flag for Unicode support
                result = subprocess.run([
                    'unzip', '-U', '-q', str(zip_file), '-d', str(extraction_dir)
                ], capture_output=True, text=True)

                if result.returncode != 0:
                    # If Unicode flag fails, try without it
                    self.logger.warning(f"Unicode extraction failed for {zip_file.name}, trying fallback...")
                    result = subprocess.run([
                        'unzip', '-q', str(zip_file), '-d', str(extraction_dir)
                    ], capture_output=True, text=True)

                if result.returncode != 0:
                    # If system unzip fails completely, fall back to Python zipfile
                    self.logger.warning(f"System unzip failed for {zip_file.name}, using Python zipfile...")
                    self._extract_single_zip(zip_file, extraction_dir)

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to extract {zip_file} with system unzip: {e}")
                # Fall back to Python zipfile
                try:
                    self.logger.info(f"Falling back to Python zipfile for {zip_file.name}")
                    self._extract_single_zip(zip_file, extraction_dir)
                except Exception as e2:
                    self.logger.error(f"Python zipfile also failed for {zip_file}: {e2}")
                    self.stats['errors'].append(f"Extraction failed: {zip_file}")
            except Exception as e:
                self.logger.error(f"Unexpected error extracting {zip_file}: {e}")
                # Fall back to Python zipfile
                try:
                    self.logger.info(f"Falling back to Python zipfile for {zip_file.name}")
                    self._extract_single_zip(zip_file, extraction_dir)
                except Exception as e2:
                    self.logger.error(f"Python zipfile also failed for {zip_file}: {e2}")
                    self.stats['errors'].append(f"Extraction failed: {zip_file}")

    def _extract_parallel(self, zip_files: List[Path], extraction_dir: Path):
        """Extract multiple ZIPs in parallel."""
        max_workers = min(3, len(zip_files))  # Limit to avoid I/O saturation

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for zip_file in zip_files:
                future = executor.submit(self._extract_single_zip, zip_file, extraction_dir)
                futures.append((future, zip_file))

            for i, (future, zip_file) in enumerate(futures):
                try:
                    future.result()
                    self.update_status(f"Extracted {zip_file.name}", (i / len(futures)) * 0.2)
                except Exception as e:
                    self.logger.error(f"Failed to extract {zip_file}: {e}")
                    self.stats['errors'].append(f"Extraction failed: {zip_file}")

    def _extract_sequential(self, zip_files: List[Path], extraction_dir: Path):
        """Extract ZIPs one by one."""
        for i, zip_file in enumerate(zip_files):
            self.update_status(f"Extracting {zip_file.name}...", (i / len(zip_files)) * 0.2)
            try:
                self._extract_single_zip(zip_file, extraction_dir)
            except Exception as e:
                self.logger.error(f"Failed to extract {zip_file}: {e}")
                self.stats['errors'].append(f"Extraction failed: {zip_file}")

    def _extract_single_zip(self, zip_file: Path, extraction_dir: Path):
        """Extract a single ZIP file with Unicode filename handling."""
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                # Extract files one by one to handle problematic filenames
                for member in zip_ref.infolist():
                    try:
                        # Try to extract the file normally first
                        zip_ref.extract(member, extraction_dir)
                    except (UnicodeDecodeError, OSError) as e:
                        # Handle files with problematic names
                        self.logger.warning(f"Skipping file with problematic name: {member.filename} ({e})")
                        continue
                    except Exception as e:
                        self.logger.warning(f"Failed to extract {member.filename}: {e}")
                        continue
        except zipfile.BadZipFile as e:
            self.logger.error(f"Corrupted ZIP file {zip_file}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to extract {zip_file}: {e}")
            raise

    def find_google_photos_dirs(self, search_dir: Path) -> List[Path]:
        """Locate all 'Google Photos' directories in the structure."""
        google_photos_dirs = []
        for root, dirs, files in os.walk(search_dir):
            if 'Google Photos' in dirs:
                google_photos_dirs.append(Path(root) / 'Google Photos')
        return google_photos_dirs

    def determine_input_type(self) -> Tuple[str, Path]:
        """Determine if input is ZIP files, directory with ZIPs, or extracted directory."""
        if isinstance(self.input_source, list):
            # List of ZIP files provided
            return "zip_files", None

        input_path = Path(self.input_source)

        if input_path.is_file() and input_path.suffix.lower() == '.zip':
            # Single ZIP file
            return "zip_files", None

        if input_path.is_dir():
            # Check if it's a directory with ZIP files
            zip_files = list(input_path.glob("takeout-*.zip"))
            if zip_files:
                return "zip_directory", input_path

            # Check if it's already an extracted Takeout directory
            if (input_path / "Google Photos").exists() or self.find_google_photos_dirs(input_path):
                return "extracted_directory", input_path

        raise ValueError(f"Invalid input source: {self.input_source}. Must be ZIP file(s), directory with takeout-*.zip files, or directory containing 'Google Photos' folder.")

    def get_media_files_from_directory(self, directory: Path) -> List[Path]:
        """Get all media files from a directory structure."""
        media_extensions = {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov', '.m4v', '.gif', '.tiff', '.bmp'}
        media_files = []

        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                # Skip JSON files
                if not file_path.name.endswith('.json'):
                    media_files.append(file_path)

        return media_files

    def find_json_metadata(self, media_file: Path) -> Optional[Path]:
        """Find corresponding JSON file using various Google naming patterns with edited photo support."""
        base_path = media_file.parent / media_file.name

        # Google's JSON naming patterns (in order of preference)
        patterns = [
            f"{base_path}.supplemental-metadata.json",
            f"{base_path}.supplemental-metada.json",  # Google's typo
            f"{base_path}.s.json",
            f"{base_path}.json"
        ]

        # Try direct patterns first
        for pattern in patterns:
            json_path = Path(pattern)
            if json_path.exists():
                return json_path

        # If it's an edited photo, try to find the original's JSON
        if self._is_edited_photo(media_file):
            original_name = self._get_original_name(media_file)
            if original_name:
                original_file = media_file.parent / original_name
                original_base_path = media_file.parent / original_name

                # Try patterns for the original file
                for pattern in [
                    f"{original_base_path}.supplemental-metadata.json",
                    f"{original_base_path}.supplemental-metada.json",
                    f"{original_base_path}.s.json",
                    f"{original_base_path}.json"
                ]:
                    json_path = Path(pattern)
                    if json_path.exists():
                        return json_path

        return None

    def _is_edited_photo(self, media_file: Path) -> bool:
        """Check if this is an edited photo."""
        filename = media_file.name.lower()
        return any(pattern in filename for pattern in [
            '-edited',
            '-effects-edited',
            '_edited',
            '_1-edited'  # Handle special case like IMG_20180804_134812_1-edited.jpg
        ])

    def _get_original_name(self, edited_file: Path) -> Optional[str]:
        """Get the original filename from an edited photo name."""
        filename = edited_file.name

        # Handle various edited patterns
        patterns_to_remove = [
            '-EFFECTS-edited',  # IMG_20180917_135645-EFFECTS-edited.jpg
            '-edited',          # IMG_20180120_160121-edited.jpg
            '_1-edited',        # IMG_20180804_134812_1-edited.jpg
            '_edited'           # Alternative pattern
        ]

        for pattern in patterns_to_remove:
            if pattern in filename:
                # Remove the pattern and keep the extension
                base_name = filename.replace(pattern, '')
                return base_name

        return None

    def detect_file_type_mismatch(self, file_path: Path) -> Optional[str]:
        """Detect files with incorrect extensions using ExifTool."""
        try:
            cmd = ['exiftool', '-json', '-FileType', str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            metadata = json.loads(result.stdout)[0]

            actual_type = metadata.get('FileType', '').upper()
            extension = file_path.suffix.lower()

            # Common mismatches
            mismatches = {
                '.jpg': ['MP4', 'PNG'],
                '.png': ['JPEG'],
                '.heic': ['MOV']  # Live Photos video component
            }

            if extension in mismatches and actual_type in mismatches[extension]:
                return actual_type.lower()

        except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
            pass

        return None

    def fix_file_extensions(self, media_files: List[Path]) -> List[Path]:
        """Correct file extensions that don't match actual file types."""
        corrected_files = []

        self.update_status("Checking file extensions...")

        for i, file_path in enumerate(media_files):
            if i % 100 == 0:  # Update progress every 100 files
                self.update_status(f"Checking extensions: {i}/{len(media_files)}",
                                 0.2 + (i / len(media_files)) * 0.1)

            correct_type = self.detect_file_type_mismatch(file_path)

            if correct_type:
                new_extension = f".{correct_type}"
                new_path = file_path.with_suffix(new_extension)

                if not self.dry_run:
                    shutil.move(str(file_path), str(new_path))

                self.logger.info(f"Fixed extension: {file_path.name} -> {new_path.name}")
                self.stats['extensions_fixed'] += 1
                corrected_files.append(new_path)
            else:
                corrected_files.append(file_path)

        return corrected_files

    def identify_live_photos(self, media_files: List[Path]) -> Dict[str, Tuple[Path, Path]]:
        """Identify and pair Live Photos components."""
        live_photos = {}

        self.update_status("Identifying Live Photos...")

        for file_path in media_files:
            if file_path.suffix.lower() == '.heic':
                base_name = file_path.stem
                video_patterns = [
                    file_path.parent / f"{base_name}(1).heic",
                    file_path.parent / f"{base_name}.mov"
                ]

                for video_path in video_patterns:
                    if video_path.exists():
                        live_photos[base_name] = (file_path, video_path)
                        self.stats['live_photos_paired'] += 1
                        break

        self.logger.info(f"Found {len(live_photos)} Live Photos pairs")
        return live_photos

    def process_with_exiftool(self, media_files: List[Path], batch_size: int = 50) -> bool:
        """Process files using ExifTool with detailed tracking and error handling."""
        success_count = 0
        unmapped_files = []
        successfully_processed_files = []
        total_batches = (len(media_files) + batch_size - 1) // batch_size

        self.update_status(f"Processing {len(media_files)} files with ExifTool...")

        # Process in smaller batches to avoid command line issues
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(media_files))
            batch = media_files[start_idx:end_idx]

            progress = 0.3 + (batch_num / total_batches) * 0.4
            self.update_status(f"Processing batch {batch_num + 1}/{total_batches}", progress)

            if self.dry_run:
                self.logger.info(f"DRY RUN: Would process batch of {len(batch)} files")
                success_count += len(batch)
                # Simulate metadata tracking for dry run
                for file_path in batch:
                    json_file = self.find_json_metadata(file_path)
                    if json_file:
                        self.stats['json_matched'] += 1
                        successfully_processed_files.append(file_path)
                        # Simulate checking for metadata
                        json_data = self._load_json_safely(json_file)
                        if json_data.get('photoTakenTime', {}).get('timestamp'):
                            self.stats['date_restored'] += 1
                        if json_data.get('geoData', {}).get('latitude', 0) != 0:
                            self.stats['gps_restored'] += 1
                    else:
                        unmapped_files.append(file_path)
                continue

            # Process batch with ExifTool and collect unmapped files
            batch_success, batch_unmapped, batch_processed = self._process_batch_with_verification(batch, batch_num + 1)
            success_count += batch_success
            unmapped_files.extend(batch_unmapped)
            successfully_processed_files.extend(batch_processed)

        # Copy successfully processed files to output directory
        if successfully_processed_files and not self.dry_run:
            self._copy_processed_files_to_output(successfully_processed_files)

        # Handle unmapped files
        if unmapped_files and not self.dry_run:
            self._handle_unmapped_files(unmapped_files)

        self.stats['processed_files'] = success_count
        return success_count > 0

    def _load_json_safely(self, json_path: Path) -> Dict:
        """Safely load JSON metadata file."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load JSON {json_path}: {e}")
            return {}

    def _process_batch_with_verification(self, batch: List[Path], batch_num: int) -> Tuple[int, List[Path], List[Path]]:
        """Process a batch of files and verify metadata was actually applied."""
        batch_success = 0
        batch_unmapped = []
        batch_processed = []

        # First, try to process the entire batch
        try:
            cmd = [
                'exiftool',
                '-api', 'largefilesupport=1',
                '-overwrite_original',
                '-d', '%s',
                '-ext', 'jpg', '-ext', 'jpeg', '-ext', 'png', '-ext', 'heic',
                '-ext', 'mp4', '-ext', 'mov', '-ext', 'm4v',

                # JSON file patterns (try all variants)
                '-tagsfromfile', '%d/%F.supplemental-metadata.json',
                '-tagsfromfile', '%d/%F.supplemental-metada.json',
                '-tagsfromfile', '%d/%F.s.json',
                '-tagsfromfile', '%d/%F.json',

                # GPS metadata mapping (with proper coordinate handling)
                '-GPSLatitude<GeoDataLatitude',
                '-GPSLatitudeRef<GeoDataLatitude',
                '-GPSLongitude<GeoDataLongitude',
                '-GPSLongitudeRef<GeoDataLongitude',
                '-GPSAltitude<GeoDataAltitude',

                # Date metadata mapping (convert Unix timestamp)
                '-DateTimeOriginal<PhotoTakenTimeTimestamp',
                '-CreateDate<PhotoTakenTimeTimestamp',
                '-FileCreateDate<PhotoTakenTimeTimestamp',
                '-FileModifyDate<PhotoTakenTimeTimestamp',

                # Description and title metadata mapping (fix field names)
                '-ImageDescription<Description',
                '-Caption-Abstract<Description',
                '-Description<Description',
                '-XMP:Description<Description',

                # Keywords and tags metadata mapping
                '-Keywords<Tags',
                '-Subject<Tags',
                '-XMP:Subject<Tags',
                '-Title<Title',
                '-XMP:Title<Title',
            ] + [str(f) for f in batch]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                # Batch succeeded, now verify each file
                for file_path in batch:
                    if self._verify_file_processing(file_path):
                        batch_success += 1
                        batch_processed.append(file_path)
                    else:
                        # Check if it's unmapped (no JSON found)
                        json_file = self.find_json_metadata(file_path)
                        if not json_file:
                            batch_unmapped.append(file_path)
                self.logger.info(f"Batch {batch_num} processed successfully: {batch_success}/{len(batch)} files")
            else:
                # Batch failed, try individual processing
                self.logger.warning(f"Batch {batch_num} failed, processing files individually")
                self.logger.warning(f"ExifTool stderr: {result.stderr}")
                batch_success, batch_unmapped, batch_processed = self._process_files_individually(batch, batch_num)

        except subprocess.TimeoutExpired:
            self.logger.error(f"Batch {batch_num} timed out, processing files individually")
            batch_success, batch_unmapped, batch_processed = self._process_files_individually(batch, batch_num)
        except Exception as e:
            self.logger.error(f"Batch {batch_num} failed with error: {e}")
            batch_success, batch_unmapped, batch_processed = self._process_files_individually(batch, batch_num)

        return batch_success, batch_unmapped, batch_processed

    def _process_files_individually(self, batch: List[Path], batch_num: int) -> Tuple[int, List[Path], List[Path]]:
        """Process files individually when batch processing fails."""
        individual_success = 0
        individual_unmapped = []
        individual_processed = []

        for i, file_path in enumerate(batch):
            try:
                json_file = self.find_json_metadata(file_path)
                if not json_file:
                    self.logger.debug(f"No JSON metadata found for {file_path.name}")
                    individual_unmapped.append(file_path)
                    continue

                # Process single file
                cmd = [
                    'exiftool',
                    '-api', 'largefilesupport=1',
                    '-overwrite_original',
                    '-d', '%s',
                    f'-tagsfromfile={json_file}',

                    # GPS metadata mapping
                    '-GPSLatitude<GeoDataLatitude',
                    '-GPSLatitudeRef<GeoDataLatitude',
                    '-GPSLongitude<GeoDataLongitude',
                    '-GPSLongitudeRef<GeoDataLongitude',
                    '-GPSAltitude<GeoDataAltitude',

                    # Date metadata mapping (convert Unix timestamp)
                    '-DateTimeOriginal<PhotoTakenTimeTimestamp',
                    '-CreateDate<PhotoTakenTimeTimestamp',
                    '-FileCreateDate<PhotoTakenTimeTimestamp',
                    '-FileModifyDate<PhotoTakenTimeTimestamp',

                    # Description metadata mapping
                    '-ImageDescription<Description',
                    '-Caption-Abstract<Description',
                    '-Description<Description',
                    '-XMP:Description<Description',

                    # Keywords and tags metadata mapping
                    '-Keywords<Tags',
                    '-Subject<Tags',
                    '-XMP:Subject<Tags',
                    '-Title<Title',
                    '-XMP:Title<Title',
                    str(file_path)
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                if result.returncode == 0:
                    if self._verify_file_processing(file_path):
                        individual_success += 1
                        individual_processed.append(file_path)
                else:
                    self.logger.warning(f"Failed to process {file_path.name}: {result.stderr}")

            except Exception as e:
                self.logger.error(f"Error processing {file_path.name}: {e}")

        if individual_success > 0:
            self.logger.info(f"Individual processing for batch {batch_num}: {individual_success}/{len(batch)} files")
        else:
            error_msg = f"Batch {batch_num} completely failed: {len(batch)} files"
            self.logger.error(error_msg)
            self.stats['errors'].append(error_msg)

        return individual_success, individual_unmapped, individual_processed

    def _verify_file_processing(self, file_path: Path) -> bool:
        """Verify that metadata was actually applied to the file."""
        try:
            # Find corresponding JSON file
            json_file = self.find_json_metadata(file_path)
            if not json_file:
                return False

            self.stats['json_matched'] += 1

            # Load JSON data
            json_data = self._load_json_safely(json_file)
            if not json_data:
                return False

            # Check if the file now has embedded metadata that matches JSON
            cmd = ['exiftool', '-json', '-DateTimeOriginal', '-GPSLatitude', '-Description', str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                return False

            exif_data = json.loads(result.stdout)[0]
            metadata_restored = False

            # Check date restoration
            original_timestamp = json_data.get('photoTakenTime', {}).get('timestamp')
            if original_timestamp and exif_data.get('DateTimeOriginal'):
                self.stats['date_restored'] += 1
                metadata_restored = True

            # Check GPS restoration
            original_lat = json_data.get('geoData', {}).get('latitude', 0)
            if original_lat != 0 and exif_data.get('GPSLatitude'):
                self.stats['gps_restored'] += 1
                metadata_restored = True

            # Check description restoration
            original_desc = json_data.get('description', '')
            if original_desc and exif_data.get('Description'):
                metadata_restored = True

            return metadata_restored

        except Exception as e:
            self.logger.debug(f"Verification failed for {file_path.name}: {e}")
            return False

    def _handle_unmapped_files(self, unmapped_files: List[Path]):
        """Copy unmapped files to a separate unmapped directory preserving structure."""
        if not unmapped_files:
            return

        unmapped_dir = self.output_dir / "unmapped"
        unmapped_dir.mkdir(exist_ok=True)

        self.logger.info(f"Copying {len(unmapped_files)} unmapped files to unmapped directory...")

        for file_path in unmapped_files:
            try:
                # Preserve the relative path structure from the Google Photos directory
                google_photos_dirs = self.find_google_photos_dirs(file_path.parents[5])  # Go up to find Takeout dir
                if not google_photos_dirs:
                    # Fallback: find the closest Google Photos directory
                    current = file_path.parent
                    while current.name != "Google Photos" and current.parent != current:
                        current = current.parent
                    if current.name == "Google Photos":
                        google_photos_dir = current
                    else:
                        google_photos_dir = file_path.parents[1]  # Default fallback
                else:
                    google_photos_dir = google_photos_dirs[0]

                # Calculate relative path from Google Photos directory
                rel_path = file_path.relative_to(google_photos_dir)
                dest_path = unmapped_dir / rel_path

                # Create destination directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy the file
                shutil.copy2(file_path, dest_path)
                self.logger.debug(f"Copied unmapped file: {file_path.name} -> {rel_path}")

            except Exception as e:
                self.logger.warning(f"Failed to copy unmapped file {file_path.name}: {e}")

        self.logger.info(f"✅ Unmapped files copied to: {unmapped_dir}")

    def _copy_processed_files_to_output(self, processed_files: List[Path]):
        """Copy successfully processed files to the main output directory preserving structure."""
        if not processed_files:
            return

        self.logger.info(f"Copying {len(processed_files)} successfully processed files to output directory...")

        progress_counter = 0
        for file_path in processed_files:
            try:
                # Preserve the relative path structure from the Google Photos directory
                google_photos_dirs = self.find_google_photos_dirs(file_path.parents[5])  # Go up to find Takeout dir
                if not google_photos_dirs:
                    # Fallback: find the closest Google Photos directory
                    current = file_path.parent
                    while current.name != "Google Photos" and current.parent != current:
                        current = current.parent
                    if current.name == "Google Photos":
                        google_photos_dir = current
                    else:
                        google_photos_dir = file_path.parents[1]  # Default fallback
                else:
                    google_photos_dir = google_photos_dirs[0]

                # Calculate relative path from Google Photos directory
                rel_path = file_path.relative_to(google_photos_dir)
                dest_path = self.output_dir / rel_path

                # Create destination directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy the file with metadata preserved
                shutil.copy2(file_path, dest_path)
                self.logger.debug(f"Copied processed file: {file_path.name} -> {rel_path}")

                # Update progress every 50 files
                progress_counter += 1
                if progress_counter % 50 == 0:
                    progress = 0.7 + (progress_counter / len(processed_files)) * 0.2
                    self.update_status(f"Copying processed files: {progress_counter}/{len(processed_files)}", progress)

            except Exception as e:
                self.logger.warning(f"Failed to copy processed file {file_path.name}: {e}")

        self.logger.info(f"✅ Successfully processed files copied to: {self.output_dir}")

    def generate_report(self) -> Dict:
        """Generate final processing report."""
        report = {
            'processing_stats': self.stats,
            'summary': f"Processed {self.stats['processed_files']} of {self.stats['total_files']} files",
            'success_rate': f"{(self.stats['processed_files'] / max(1, self.stats['total_files'])) * 100:.1f}%"
        }

        # Save detailed report
        report_path = self.output_dir / 'processing_report.json'
        if not self.dry_run:
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)

        return report

    def import_to_photos_app(self):
        """Import processed photos to macOS Photos app."""
        if sys.platform != 'darwin':
            self.logger.warning("Photos app import only available on macOS")
            return False

        try:
            applescript = f'''
            tell application "Photos"
                import from POSIX file "{self.output_dir}" skip check duplicates false
            end tell
            '''
            subprocess.run(['osascript', '-e', applescript], check=True)
            self.logger.info("Successfully imported to Photos app")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to import to Photos app: {e}")
            return False

    def process(self) -> bool:
        """Main processing pipeline."""
        self.update_status("Starting Google Takeout processing...")

        try:
            # Phase 1: Determine input type and prepare working directory
            input_type, working_dir = self.determine_input_type()

            if input_type == "zip_files":
                # Extract ZIP files
                zip_files = self.input_source if isinstance(self.input_source, list) else [self.input_source]
                working_dir = self.extract_takeout_zips([Path(f) for f in zip_files])
            elif input_type == "zip_directory":
                # Find and extract all ZIP files in directory
                zip_files = list(working_dir.glob("takeout-*.zip"))
                working_dir = self.extract_takeout_zips(zip_files)
            # else: input_type == "extracted_directory", use working_dir as-is

            # Phase 2: Discover media files
            self.update_status("Scanning for media files...", 0.2)
            google_photos_dirs = self.find_google_photos_dirs(working_dir)

            if not google_photos_dirs:
                raise ValueError("No 'Google Photos' directories found")

            all_media_files = []
            for photos_dir in google_photos_dirs:
                media_files = self.get_media_files_from_directory(photos_dir)
                all_media_files.extend(media_files)

            self.stats['total_files'] = len(all_media_files)
            self.update_status(f"Found {len(all_media_files)} media files", 0.25)

            # Phase 3: Fix file extensions
            corrected_files = self.fix_file_extensions(all_media_files)

            # Phase 4: Identify Live Photos
            live_photos = self.identify_live_photos(corrected_files)

            # Phase 5: Process metadata with ExifTool
            self.process_with_exiftool(corrected_files)

            # Phase 6: Generate final report
            self.update_status("Generating report...", 0.9)
            report = self.generate_report()

            self.update_status(f"Processing complete: {report['summary']}", 1.0)
            return True

        except Exception as e:
            error_msg = f"Processing failed: {e}"
            self.logger.error(error_msg)
            self.update_status(error_msg)
            return False


class TakeoutProcessorGUI:
    """GUI interface for the Google Takeout processor."""

    def __init__(self):
        if not GUI_AVAILABLE:
            raise RuntimeError("GUI not available. tkinter is required for GUI mode.")

        self.root = tk.Tk()
        self.root.title("Google Photos Takeout to Apple Photos")
        self.root.geometry("700x500")
        self.root.resizable(True, True)

        # Variables
        self.zip_files = []
        self.output_dir = None
        self.processor = None

        # Options
        self.dry_run_var = tk.BooleanVar()
        self.import_to_photos_var = tk.BooleanVar(value=True)
        self.use_system_unzip_var = tk.BooleanVar(value=True)

        self.create_widgets()
        self.center_window()

    def center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")

    def create_widgets(self):
        """Create the GUI interface."""
        # Main frame
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)

        # Title
        title = tk.Label(main_frame, text="Google Photos Takeout Processor",
                        font=("Arial", 18, "bold"), fg="#007AFF")
        title.pack(pady=(0, 20))

        # Subtitle
        subtitle = tk.Label(main_frame,
                           text="Convert Google Takeout files for Apple Photos with metadata preservation",
                           font=("Arial", 10), fg="gray")
        subtitle.pack(pady=(0, 30))

        # Input selection frame
        input_frame = tk.LabelFrame(main_frame, text="Select Input Files", font=("Arial", 12, "bold"))
        input_frame.pack(fill="x", pady=(0, 20))

        # ZIP file selection
        zip_frame = tk.Frame(input_frame)
        zip_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(zip_frame, text="Takeout ZIP files:", font=("Arial", 10)).pack(anchor="w")

        zip_button_frame = tk.Frame(zip_frame)
        zip_button_frame.pack(fill="x", pady=(5, 0))

        tk.Button(zip_button_frame, text="Select ZIP Files",
                 command=self.select_zip_files,
                 bg="#34C759", fg="white", font=("Arial", 10)).pack(side="left")

        tk.Label(zip_button_frame, text=" or ", font=("Arial", 10)).pack(side="left", padx=5)

        tk.Button(zip_button_frame, text="Select Folder with ZIPs",
                 command=self.select_zip_folder,
                 bg="#FF9500", fg="white", font=("Arial", 10)).pack(side="left")

        self.zip_label = tk.Label(zip_frame, text="No files selected",
                                 fg="gray", font=("Arial", 9))
        self.zip_label.pack(anchor="w", pady=(5, 0))

        # Output directory selection
        output_frame = tk.LabelFrame(main_frame, text="Select Output Location", font=("Arial", 12, "bold"))
        output_frame.pack(fill="x", pady=(0, 20))

        output_inner = tk.Frame(output_frame)
        output_inner.pack(fill="x", padx=10, pady=10)

        tk.Label(output_inner, text="Processed photos will be saved to:", font=("Arial", 10)).pack(anchor="w")

        output_button_frame = tk.Frame(output_inner)
        output_button_frame.pack(fill="x", pady=(5, 0))

        tk.Button(output_button_frame, text="Select Output Folder",
                 command=self.select_output_dir,
                 bg="#007AFF", fg="white", font=("Arial", 10)).pack(side="left")

        self.output_label = tk.Label(output_inner, text="No folder selected",
                                    fg="gray", font=("Arial", 9))
        self.output_label.pack(anchor="w", pady=(5, 0))

        # Options frame
        options_frame = tk.LabelFrame(main_frame, text="Processing Options", font=("Arial", 12, "bold"))
        options_frame.pack(fill="x", pady=(0, 20))

        options_inner = tk.Frame(options_frame)
        options_inner.pack(fill="x", padx=10, pady=10)

        tk.Checkbutton(options_inner, text="Dry run (preview changes without modifying files)",
                      variable=self.dry_run_var, font=("Arial", 10)).pack(anchor="w", pady=2)

        tk.Checkbutton(options_inner, text="Import to Photos app when complete (macOS only)",
                      variable=self.import_to_photos_var, font=("Arial", 10)).pack(anchor="w", pady=2)

        tk.Checkbutton(options_inner, text="Use system unzip for better performance",
                      variable=self.use_system_unzip_var, font=("Arial", 10)).pack(anchor="w", pady=2)

        # Process button
        self.process_button = tk.Button(main_frame, text="Process Photos",
                                       command=self.start_processing,
                                       bg="#007AFF", fg="white",
                                       font=("Arial", 14, "bold"),
                                       state="disabled", height=2)
        self.process_button.pack(pady=20, fill="x")

        # Progress frame
        progress_frame = tk.Frame(main_frame)
        progress_frame.pack(fill="x", pady=(0, 10))

        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill="x")

        # Status label
        self.status_label = tk.Label(main_frame, text="Ready to process",
                                    fg="green", font=("Arial", 10))
        self.status_label.pack()

    def select_zip_files(self):
        """Select individual ZIP files."""
        files = filedialog.askopenfilenames(
            title="Select Google Takeout ZIP files",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )

        if files:
            self.zip_files = list(files)
            self.zip_label.config(text=f"{len(files)} ZIP files selected", fg="black")
            self.check_ready_to_process()

    def select_zip_folder(self):
        """Select folder containing ZIP files."""
        directory = filedialog.askdirectory(title="Select folder containing Takeout ZIP files")

        if directory:
            zip_files = list(Path(directory).glob("takeout-*.zip"))
            if zip_files:
                self.zip_files = directory  # Store directory path
                self.zip_label.config(text=f"Folder with {len(zip_files)} ZIP files selected", fg="black")
                self.check_ready_to_process()
            else:
                messagebox.showwarning("No ZIP Files",
                    "No takeout ZIP files found in the selected folder.\n"
                    "Please select a folder containing files named 'takeout-*.zip'")

    def select_output_dir(self):
        """Select output directory."""
        directory = filedialog.askdirectory(title="Select output directory for processed photos")

        if directory:
            self.output_dir = directory
            # Truncate long paths for display
            display_path = directory
            if len(display_path) > 50:
                display_path = "..." + display_path[-47:]
            self.output_label.config(text=display_path, fg="black")
            self.check_ready_to_process()

    def check_ready_to_process(self):
        """Enable process button when inputs are ready."""
        if self.zip_files and self.output_dir:
            self.process_button.config(state="normal")

    def update_progress(self, progress: float):
        """Update progress bar (0.0 to 1.0)."""
        self.progress['value'] = progress * 100
        self.root.update_idletasks()

    def update_status(self, message: str):
        """Update status label."""
        self.status_label.config(text=message)
        self.root.update_idletasks()

    def start_processing(self):
        """Start processing in a separate thread."""
        # Disable UI during processing
        self.process_button.config(state="disabled", text="Processing...")
        self.progress['value'] = 0
        self.update_status("Initializing...")

        # Start processing in background thread
        thread = threading.Thread(target=self.process_photos, daemon=True)
        thread.start()

    def process_photos(self):
        """Process photos in background thread."""
        try:
            # Create processor with callbacks
            self.processor = GoogleTakeoutProcessor(
                input_source=self.zip_files,
                output_dir=Path(self.output_dir),
                dry_run=self.dry_run_var.get(),
                use_system_unzip=self.use_system_unzip_var.get()
            )

            # Set up callbacks for GUI updates
            self.processor.progress_callback = self.update_progress
            self.processor.status_callback = self.update_status

            # Process the files
            success = self.processor.process()

            # Update UI on completion
            self.root.after(0, self.processing_complete, success)

        except Exception as e:
            self.root.after(0, self.processing_error, str(e))

    def processing_complete(self, success: bool):
        """Handle processing completion."""
        self.progress['value'] = 100
        self.process_button.config(state="normal", text="Process Photos")

        if success:
            stats = self.processor.stats
            message = (f"✅ Processing Complete!\n\n"
                      f"📁 Files processed: {stats['processed_files']}/{stats['total_files']}\n"
                      f"📅 Dates restored: {stats['date_restored']}\n"
                      f"📍 GPS data restored: {stats['gps_restored']}\n"
                      f"🔧 Extensions fixed: {stats['extensions_fixed']}\n"
                      f"📸 Live Photos paired: {stats['live_photos_paired']}")

            if stats['errors']:
                message += f"\n⚠️ Errors: {len(stats['errors'])}"

            self.update_status("Processing complete! ✅")

            # Show completion dialog with options
            result = messagebox.askyesno("Processing Complete",
                message + "\n\nWould you like to import the photos to the Photos app now?")

            if result and self.import_to_photos_var.get():
                self.update_status("Importing to Photos app...")
                if self.processor.import_to_photos_app():
                    messagebox.showinfo("Import Complete", "Photos successfully imported to Photos app!")
                else:
                    messagebox.showwarning("Import Failed", "Failed to import to Photos app. You can manually import from the output folder.")

        else:
            error_count = len(self.processor.stats['errors']) if self.processor else 0
            self.update_status(f"Processing failed - {error_count} errors")
            messagebox.showerror("Processing Failed",
                "Processing encountered errors. Check the log file for details.")

    def processing_error(self, error_message: str):
        """Handle processing errors."""
        self.progress['value'] = 0
        self.process_button.config(state="normal", text="Process Photos")
        self.update_status("Error occurred")
        messagebox.showerror("Error", f"Processing failed:\n\n{error_message}")

    def run(self):
        """Start the GUI application."""
        self.root.mainloop()


def create_cli_parser():
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Google Photos Takeout to Apple Photos processor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # GUI mode (default)
  python takeout_processor.py

  # Process individual ZIP files
  python takeout_processor.py --zip-files takeout-001.zip takeout-002.zip --output ~/Pictures/processed

  # Process folder containing ZIP files
  python takeout_processor.py --zip-dir ~/Downloads --output ~/Pictures/processed

  # Process already extracted directory
  python takeout_processor.py --extracted-dir ~/Downloads/Takeout --output ~/Pictures/processed

  # Dry run to preview changes
  python takeout_processor.py --zip-dir ~/Downloads --output ~/Pictures/processed --dry-run

  # Full process with Photos import
  python takeout_processor.py --zip-dir ~/Downloads --output ~/Pictures/processed --import-to-photos
        """
    )

    # Input source options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('--zip-files', nargs='+', metavar='FILE',
                           help='Individual ZIP files to process')
    input_group.add_argument('--zip-dir', metavar='DIR',
                           help='Directory containing takeout ZIP files')
    input_group.add_argument('--extracted-dir', metavar='DIR',
                           help='Already extracted takeout directory')

    # Output directory
    parser.add_argument('--output', '-o', required=False, metavar='DIR',
                       help='Output directory for processed files')

    # Processing options
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying files')
    parser.add_argument('--import-to-photos', action='store_true',
                       help='Import to Photos app after processing (macOS only)')
    parser.add_argument('--no-system-unzip', action='store_true',
                       help='Don\'t use system unzip command (use Python zipfile for Unicode support)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    # GUI options
    parser.add_argument('--gui', action='store_true',
                       help='Force GUI mode (default if no arguments)')
    parser.add_argument('--no-gui', action='store_true',
                       help='Force CLI mode even with no arguments')

    return parser


def main():
    """Main entry point for the application."""
    parser = create_cli_parser()

    # If no arguments provided, try to launch GUI
    if len(sys.argv) == 1:
        if GUI_AVAILABLE:
            app = TakeoutProcessorGUI()
            app.run()
            return
        else:
            print("GUI not available. Use command line mode:")
            parser.print_help()
            sys.exit(1)

    args = parser.parse_args()

    # Handle GUI/CLI mode selection
    if args.gui and not GUI_AVAILABLE:
        print("GUI mode requested but tkinter not available.")
        sys.exit(1)

    if args.gui or (not args.no_gui and not any([args.zip_files, args.zip_dir, args.extracted_dir])):
        if GUI_AVAILABLE:
            app = TakeoutProcessorGUI()
            app.run()
            return
        else:
            print("GUI not available. Using CLI mode.")

    # CLI mode - validate arguments
    if not args.output:
        print("Error: --output directory is required in CLI mode")
        parser.print_help()
        sys.exit(1)

    if not any([args.zip_files, args.zip_dir, args.extracted_dir]):
        print("Error: Must specify input source (--zip-files, --zip-dir, or --extracted-dir)")
        parser.print_help()
        sys.exit(1)

    # Set up logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine input source
    if args.zip_files:
        input_source = args.zip_files
    elif args.zip_dir:
        input_source = args.zip_dir
    else:  # args.extracted_dir
        input_source = args.extracted_dir

    # Create and run processor
    try:
        processor = GoogleTakeoutProcessor(
            input_source=input_source,
            output_dir=Path(args.output),
            dry_run=args.dry_run,
            use_system_unzip=not args.no_system_unzip
        )

        print("Starting Google Photos Takeout processing...")
        success = processor.process()

        if success:
            print(f"\n✅ Processing completed successfully!")
            print(f"📊 Report: {processor.generate_report()['summary']}")

            if args.import_to_photos:
                print("🍎 Importing to Photos app...")
                if processor.import_to_photos_app():
                    print("✅ Successfully imported to Photos app!")
                else:
                    print("❌ Failed to import to Photos app")
        else:
            print("❌ Processing failed. Check the log file for details.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()