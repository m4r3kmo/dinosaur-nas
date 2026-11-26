import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from media_import import (
    build_destination,
    normalize_movie_title,
    normalize_series_title,
)


class MediaImportTests(unittest.TestCase):

    def test_release_title(self):
        self.assertEqual(
            normalize_series_title(
                "The.Lord.of.the.Rings.The.Rings.of.Power."
                "S03E04.CZ-EN dabing.2160p.WEB-DL.DV.HDR.H.265-"
            ),
            "The Lord of the Rings The Rings of Power",
        )

    def test_short_release_title(self):
        self.assertEqual(
            normalize_series_title(
                "The Rings of Power S03E06 4K"
            ),
            "The Rings of Power",
        )

    def test_clean_title(self):
        self.assertEqual(
            normalize_series_title(
                "The Rings of Power (2022)"
            ),
            "The Rings of Power (2022)",
        )

    def test_series_destination(self):
        self.assertEqual(
            build_destination(
                filename="episode.mkv",
                library="series",
                title="The Rings of Power S03E06 4K",
                season=3,
                episode=6,
            ),
            "series/The Rings of Power/Season 03/"
            "The Rings of Power S03E06.mkv",
        )

    def test_movie_destination(self):
        self.assertEqual(
            build_destination(
                filename="movie.mkv",
                library="movies",
                title="The Mask (1994)",
            ),
            "movies/The Mask (1994)/The Mask (1994).mkv",
        )

    def test_download_destination(self):
        self.assertIsNone(
            build_destination(
                filename="video.mkv",
                library="downloads",
            )
        )

    def test_movie_release_titles(self):
        cases = [
            (
                "Mumie - The Mummy (1999) UHD 4K HDR10 H265",
                "Mumie - The Mummy (1999)",
            ),
            (
                "Odyssea - The Odyssey (2026)(CZEN)",
                "Odyssea - The Odyssey (2026)",
            ),
            (
                "The.Matrix.1999.2160p.BluRay.x265",
                "The Matrix 1999",
            ),
        ]

        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    normalize_movie_title(source),
                    expected,
                )

    def test_movie_title_preserved(self):
        for title in (
            "1917",
            "Blade Runner 2049",
            "Mortal Kombat II",
            "The Mask (1994)",
            "Mr. Nobody (2009)",
        ):
            with self.subTest(title=title):
                self.assertEqual(
                    normalize_movie_title(title),
                    title,
                )

    def test_normalized_movie_destination(self):
        self.assertEqual(
            build_destination(
                filename="movie.mkv",
                library="movies",
                title="The Mummy (1999) UHD 4K HDR10",
            ),
            "movies/The Mummy (1999)/The Mummy (1999).mkv",
        )

    def test_unsafe_title(self):
        with self.assertRaises(ValueError):
            normalize_series_title("../unsafe")


    def test_existing_series_matching(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            title = "The Lord of the Rings - The Rings of Power (2022)"
            (root / title).mkdir()

            self.assertEqual(
                build_destination(
                    filename="episode.mkv",
                    library="series",
                    title="The.Lord.of.the.Rings.The.Rings.of.Power.S03E07",
                    season=3,
                    episode=7,
                    series_root=root,
                ),
                f"series/{title}/Season 03/{title} S03E07.mkv",
            )

    def test_different_series_year(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Example Show (2022)").mkdir()

            self.assertEqual(
                build_destination(
                    filename="episode.mkv",
                    library="series",
                    title="Example Show (2024)",
                    season=1,
                    episode=1,
                    series_root=root,
                ),
                "series/Example Show (2024)/Season 01/"
                "Example Show (2024) S01E01.mkv",
            )

    def test_ambiguous_series_matching(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)

            for year in (2022, 2024):
                (root / f"Example Show ({year})").mkdir()

            with self.assertRaisesRegex(ValueError, "Multiple"):
                build_destination(
                    filename="episode.mkv",
                    library="series",
                    title="Example Show",
                    season=1,
                    episode=1,
                    series_root=root,
                )


if __name__ == "__main__":
    unittest.main()
