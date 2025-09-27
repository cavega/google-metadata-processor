#!/usr/bin/env python3
"""
Comprehensive unit tests for Google Photos Takeout metadata processor.

Tests all enhanced metadata processing strategies including:
- Filename pattern recognition (IMG, PANO, EFFECTS, VID formats)
- EXIF timestamp preservation
- Album directory date inference
- JSON metadata matching (direct and cross-album)
- Complete processing pipeline integration

Author: Generated for robust regression testing
Requirements: Python 3.8+, pytest, mock
"""

import unittest
import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the processor class
from takeout_processor import GoogleTakeoutProcessor


class TestGoogleTakeoutProcessor(unittest.TestCase):
    """Base test class with common setup and utility methods."""

    def setUp(self):
        """Set up test environment with temporary directories and mock data."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.output_dir = self.temp_dir / "output"
        self.input_dir = self.temp_dir / "input"
        self.google_photos_dir = self.input_dir / "Takeout" / "Google Photos"

        # Create directory structure
        self.output_dir.mkdir(parents=True)
        self.google_photos_dir.mkdir(parents=True)

        # Mock ExifTool validation for testing
        with patch('takeout_processor.GoogleTakeoutProcessor.validate_environment'):
            # Create processor instance with dry_run=True for testing
            self.processor = GoogleTakeoutProcessor(
                input_source=self.input_dir,
                output_dir=self.output_dir,
                dry_run=True
            )

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.temp_dir)

    def create_test_album(self, album_name: str) -> Path:
        """Create a test album directory."""
        album_path = self.google_photos_dir / album_name
        album_path.mkdir(parents=True, exist_ok=True)
        return album_path

    def create_test_photo(self, album_path: Path, filename: str, content: str = "test_photo") -> Path:
        """Create a test photo file."""
        photo_path = album_path / filename
        photo_path.write_text(content)
        return photo_path

    def create_test_json(self, album_path: Path, filename: str, metadata: dict) -> Path:
        """Create a test JSON metadata file."""
        json_path = album_path / filename
        with open(json_path, 'w') as f:
            json.dump(metadata, f)
        return json_path

    def create_sample_google_metadata(self, timestamp: str = "1693584000", latitude: float = 37.7749, longitude: float = -122.4194) -> dict:
        """Create sample Google Photos JSON metadata."""
        return {
            "title": "Test Photo",
            "description": "Test description",
            "photoTakenTime": {
                "timestamp": timestamp,
                "formatted": "Sep 1, 2023, 12:00:00 PM UTC"
            },
            "geoData": {
                "latitude": latitude,
                "longitude": longitude,
                "altitude": 10.0,
                "latitudeSpan": 0.0,
                "longitudeSpan": 0.0
            },
            "tags": ["vacation", "family"]
        }


class TestFilenamePatternRecognition(TestGoogleTakeoutProcessor):
    """Test filename pattern recognition strategies."""

    def test_can_extract_filename_metadata_standard_formats(self):
        """Test recognition of standard Google Photos filename patterns."""
        test_cases = [
            ("IMG_20210619_125530.jpg", True),      # Standard IMG format
            ("20210619_125530.jpg", True),          # Date without IMG prefix
            ("PANO_20210619_125530.jpg", True),     # Panorama format
            ("IMG_20210619_125530-EFFECTS.jpg", True),  # Effects format
            ("VID_20210619_125530.mp4", True),      # Video format
            ("2021-06-19 12-55-30.jpeg", True),     # Alternative timestamp format
            ("2021-06-19.jpg", True),               # Date only format
        ]

        album = self.create_test_album("Test Album")

        for filename, expected in test_cases:
            with self.subTest(filename=filename):
                photo = self.create_test_photo(album, filename)
                result = self.processor._can_extract_filename_metadata(photo)
                self.assertEqual(result, expected, f"Failed for {filename}")

    def test_can_extract_filename_metadata_non_matching(self):
        """Test that non-matching filename patterns return False."""
        non_matching_cases = [
            "Picture 001.jpg",        # Generic picture name
            "IMG_001.jpg",           # No date pattern
            "photo.jpg",             # Generic name
            "DVC00001.JPG",          # Camera model without date
            "screenshot.png",        # Screenshot
            "untitled.jpeg",         # Generic untitled
        ]

        album = self.create_test_album("Test Album")

        for filename in non_matching_cases:
            with self.subTest(filename=filename):
                photo = self.create_test_photo(album, filename)
                result = self.processor._can_extract_filename_metadata(photo)
                self.assertFalse(result, f"Should not match {filename}")

    def test_extract_filename_metadata_processing(self):
        """Test actual metadata extraction from filenames."""
        test_cases = [
            {
                "filename": "IMG_20210619_125530.jpg",
                "expected_date": "2021:06:19 12:55:30"
            },
            {
                "filename": "PANO_20180917_143000.jpg",
                "expected_date": "2018:09:17 14:30:00"
            },
            {
                "filename": "2021-06-19.jpg",
                "expected_date": "2021:06:19 12:00:00"
            }
        ]

        album = self.create_test_album("Test Album")

        for case in test_cases:
            with self.subTest(filename=case["filename"]):
                photo = self.create_test_photo(album, case["filename"])

                # Mock ExifTool call to verify correct date extraction
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stderr = ""

                    # Test that the function would call ExifTool with correct date
                    result = self.processor.extract_filename_metadata(photo, photo)

                    if mock_run.called:
                        call_args = mock_run.call_args[0][0]
                        # Check that the ExifTool command contains the expected date
                        date_arg = next((arg for arg in call_args if case["expected_date"] in arg), None)
                        self.assertIsNotNone(date_arg, f"Expected date {case['expected_date']} not found in ExifTool call")


class TestEXIFPreservationStrategy(TestGoogleTakeoutProcessor):
    """Test EXIF timestamp preservation strategy."""

    def test_has_existing_exif_timestamp_detection(self):
        """Test detection of files with existing EXIF timestamps."""
        album = self.create_test_album("Photos from 2003")
        photo = self.create_test_photo(album, "IMG_0001.JPG")

        # Test dry-run mode simulation
        result = self.processor._has_existing_exif_timestamp(photo)
        self.assertTrue(result, "Should detect EXIF for Photos from XXXX albums")

        # Test with DVC camera file
        dvc_photo = self.create_test_photo(album, "DVC00001.JPG")
        result = self.processor._has_existing_exif_timestamp(dvc_photo)
        self.assertTrue(result, "Should detect EXIF for DVC camera files")

        # Test with generic filename in modern album
        modern_album = self.create_test_album("Recent Photos")
        modern_photo = self.create_test_photo(modern_album, "screenshot.png")
        result = self.processor._has_existing_exif_timestamp(modern_photo)
        self.assertFalse(result, "Should not assume EXIF for modern generic files")

    def test_preserve_exif_timestamp_success(self):
        """Test successful EXIF timestamp preservation."""
        album = self.create_test_album("Test Album")
        photo = self.create_test_photo(album, "old_photo.jpg")

        # This should always return True as it just preserves existing data
        result = self.processor.preserve_exif_timestamp(photo, photo)
        self.assertTrue(result, "EXIF preservation should always succeed")


class TestAlbumDateInference(TestGoogleTakeoutProcessor):
    """Test album directory date inference strategy."""

    def test_can_infer_album_date_patterns(self):
        """Test recognition of album names with inferable dates."""
        test_cases = [
            ("Photos from 2003", True),
            ("Photos from 2015", True),
            ("2013 Xmas", True),
            ("2018 Vacation", True),
            ("Random Album", False),
            ("Untitled", False),
            ("Garden of the Gods", False),
        ]

        for album_name, expected in test_cases:
            with self.subTest(album_name=album_name):
                album = self.create_test_album(album_name)
                photo = self.create_test_photo(album, "test.jpg")

                result = self.processor._can_infer_album_date(photo)
                self.assertEqual(result, expected, f"Failed for album: {album_name}")

    def test_apply_album_date_inference(self):
        """Test album date inference application."""
        album = self.create_test_album("Photos from 2003")
        photo = self.create_test_photo(album, "test.jpg")

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ""

            result = self.processor.apply_album_date_inference(photo, photo)

            if mock_run.called:
                call_args = mock_run.call_args[0][0]
                # Verify that 2003 date is being applied
                date_arg = next((arg for arg in call_args if "2003:01:01" in arg), None)
                self.assertIsNotNone(date_arg, "Expected 2003 date not found in ExifTool call")


class TestJSONMetadataMatching(TestGoogleTakeoutProcessor):
    """Test JSON metadata matching strategies."""

    def test_find_json_metadata_direct_patterns(self):
        """Test direct JSON metadata file matching."""
        album = self.create_test_album("Test Album")
        photo = self.create_test_photo(album, "IMG_001.jpg")

        # Test standard supplemental metadata pattern
        json_data = self.create_sample_google_metadata()
        json_file = self.create_test_json(album, "IMG_001.jpg.supplemental-metadata.json", json_data)

        result = self.processor.find_json_metadata(photo)
        self.assertEqual(result, json_file, "Should find direct JSON match")

    def test_find_json_metadata_edited_photos(self):
        """Test JSON matching for edited photos."""
        album = self.create_test_album("Test Album")

        # Create original photo JSON
        json_data = self.create_sample_google_metadata()
        original_json = self.create_test_json(album, "IMG_001.jpg.supplemental-metadata.json", json_data)

        # Create edited photo (should inherit JSON from original)
        edited_photo = self.create_test_photo(album, "IMG_001-edited.jpg")

        result = self.processor.find_json_metadata(edited_photo)
        self.assertEqual(result, original_json, "Edited photo should inherit original's JSON")

    def test_enhanced_metadata_strategy_selection(self):
        """Test the enhanced metadata strategy selection logic."""
        # Test direct JSON matching
        album = self.create_test_album("Test Album")
        photo = self.create_test_photo(album, "IMG_001.jpg")
        json_data = self.create_sample_google_metadata()
        json_file = self.create_test_json(album, "IMG_001.jpg.supplemental-metadata.json", json_data)

        json_path, strategy = self.processor.find_json_metadata_enhanced(photo)
        self.assertEqual(strategy, "direct", "Should use direct strategy for files with JSON")
        self.assertEqual(json_path, json_file)

        # Test filename strategy
        filename_photo = self.create_test_photo(album, "IMG_20210619_125530.jpg")
        json_path, strategy = self.processor.find_json_metadata_enhanced(filename_photo)
        self.assertEqual(strategy, "filename", "Should use filename strategy for dateable filenames")

        # Test EXIF preservation strategy
        old_album = self.create_test_album("Photos from 2003")
        old_photo = self.create_test_photo(old_album, "IMG_0001.JPG")
        json_path, strategy = self.processor.find_json_metadata_enhanced(old_photo)
        self.assertEqual(strategy, "exif_preservation", "Should use EXIF preservation for old photos")

        # Test album date inference
        dated_album = self.create_test_album("2018 Summer")
        generic_photo = self.create_test_photo(dated_album, "picture.jpg")
        json_path, strategy = self.processor.find_json_metadata_enhanced(generic_photo)
        self.assertEqual(strategy, "album_date_inference", "Should use album date inference")


class TestProcessingPipelineIntegration(TestGoogleTakeoutProcessor):
    """Test complete processing pipeline integration."""

    def test_metadata_indexing(self):
        """Test metadata indexing for enhanced processing."""
        # Create test albums with JSON files
        album1 = self.create_test_album("Album 1")
        album2 = self.create_test_album("Album 2")

        # Create JSON files with timestamps
        json_data1 = self.create_sample_google_metadata("1693584000")
        json_data2 = self.create_sample_google_metadata("1693670400")

        self.create_test_json(album1, "photo1.jpg.supplemental-metadata.json", json_data1)
        self.create_test_json(album2, "photo2.jpg.supplemental-metadata.json", json_data2)

        # Create album metadata
        album_metadata = {
            "title": "Test Album",
            "date": {"timestamp": "1693584000"}
        }
        self.create_test_json(album1, "metadata.json", album_metadata)

        # Test indexing
        google_photos_dirs = [self.google_photos_dir]
        self.processor.index_metadata_for_enhanced_processing(google_photos_dirs)

        self.assertTrue(self.processor.metadata_indexed, "Should mark metadata as indexed")
        self.assertEqual(len(self.processor.json_metadata_cache), 2, "Should index 2 JSON files")
        self.assertEqual(len(self.processor.album_metadata_cache), 1, "Should index 1 album metadata")

    def test_statistics_tracking(self):
        """Test that statistics are properly tracked."""
        # Initialize stats should have all strategy counters
        expected_stats = [
            'json_matched', 'cross_album_matched', 'album_metadata_applied',
            'filename_metadata_extracted', 'exif_preserved', 'album_date_inferred'
        ]

        for stat in expected_stats:
            self.assertIn(stat, self.processor.stats, f"Missing stat: {stat}")
            self.assertEqual(self.processor.stats[stat], 0, f"Stat {stat} should start at 0")

    def test_enhanced_batch_processing_simulation(self):
        """Test enhanced batch processing in dry-run mode."""
        # Create test files with different strategies
        album = self.create_test_album("Mixed Album")

        # Direct JSON file
        photo1 = self.create_test_photo(album, "photo1.jpg")
        json_data = self.create_sample_google_metadata()
        self.create_test_json(album, "photo1.jpg.supplemental-metadata.json", json_data)

        # Filename extractable
        photo2 = self.create_test_photo(album, "IMG_20210619_125530.jpg")

        # EXIF preservation candidate
        old_album = self.create_test_album("Photos from 2003")
        photo3 = self.create_test_photo(old_album, "IMG_0001.JPG")

        batch = [photo1, photo2, photo3]

        # Test batch processing
        success, unmapped, processed = self.processor._process_batch_with_enhanced_metadata(batch, 1)

        self.assertEqual(success, 3, "Should process all 3 files successfully")
        self.assertEqual(len(unmapped), 0, "Should have no unmapped files")
        self.assertEqual(len(processed), 3, "Should have 3 processed files")


class TestEdgeCasesAndRegressions(TestGoogleTakeoutProcessor):
    """Test edge cases and prevent regressions."""

    def test_unicode_album_names(self):
        """Test handling of album names with Unicode characters."""
        unicode_album = self.create_test_album("Matías & Chago's 2017 Birthday")
        photo = self.create_test_photo(unicode_album, "IMG_20170101_120000.jpg")

        # Should still be able to extract filename metadata
        result = self.processor._can_extract_filename_metadata(photo)
        self.assertTrue(result, "Should handle Unicode album names")

    def test_empty_json_files(self):
        """Test handling of empty or malformed JSON files."""
        album = self.create_test_album("Test Album")
        photo = self.create_test_photo(album, "test.jpg")

        # Create empty JSON file
        empty_json = album / "test.jpg.supplemental-metadata.json"
        empty_json.write_text("")

        # Should handle gracefully
        result = self.processor._load_json_safely(empty_json)
        self.assertEqual(result, {}, "Should return empty dict for invalid JSON")

    def test_very_long_filenames(self):
        """Test handling of very long filenames."""
        album = self.create_test_album("Test Album")
        long_filename = "a" * 200 + "_20210619_125530.jpg"
        photo = self.create_test_photo(album, long_filename)

        result = self.processor._can_extract_filename_metadata(photo)
        self.assertTrue(result, "Should handle long filenames with date patterns")

    def test_case_sensitivity(self):
        """Test case sensitivity in filename patterns."""
        album = self.create_test_album("Test Album")

        case_variants = [
            "IMG_20210619_125530.jpg",  # Standard
            "IMG_20210619_125530.JPG",  # Uppercase extension
            "img_20210619_125530.jpg",  # Lowercase prefix (should not match)
        ]

        for filename in case_variants:
            with self.subTest(filename=filename):
                photo = self.create_test_photo(album, filename)
                result = self.processor._can_extract_filename_metadata(photo)

                if filename.startswith("IMG_"):
                    self.assertTrue(result, f"Should match {filename}")
                else:
                    self.assertFalse(result, f"Should not match lowercase {filename}")


class TestReportGeneration(TestGoogleTakeoutProcessor):
    """Test report generation and statistics."""

    def test_enhanced_report_structure(self):
        """Test that enhanced reports include all strategy statistics."""
        # Simulate some processing statistics
        self.processor.stats.update({
            'total_files': 100,
            'processed_files': 95,
            'json_matched': 40,
            'cross_album_matched': 5,
            'album_metadata_applied': 10,
            'filename_metadata_extracted': 25,
            'exif_preserved': 10,
            'album_date_inferred': 5,
            'date_restored': 90,
            'gps_restored': 30
        })

        report = self.processor.generate_report()

        # Check required report fields
        self.assertIn('processing_stats', report)
        self.assertIn('metadata_strategies', report)
        self.assertIn('strategy_breakdown', report)
        self.assertIn('enhanced_metadata_total', report)

        # Check strategy breakdown calculations
        expected_total = 40 + 5 + 10 + 25 + 10 + 5  # Sum of all strategies
        self.assertEqual(report['enhanced_metadata_total'], expected_total)

        # Check percentage calculations
        strategy_breakdown = report['strategy_breakdown']
        self.assertIn('direct_json', strategy_breakdown)
        self.assertIn('exif_preserved', strategy_breakdown)
        self.assertIn('album_date_inferred', strategy_breakdown)


if __name__ == '__main__':
    # Configure test runner
    unittest.main(verbosity=2)