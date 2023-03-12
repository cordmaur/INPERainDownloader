"""
Tests for the INPEDownloader classes
"""
import os
from unittest.mock import patch
from pathlib import Path
import pytest

from raindownloader.utils import FileType, DateProcessor
from raindownloader.inpe import INPE
from raindownloader.inpedownloader import INPEDownloader


class TestDownloader:
    """Test the INPE downloader class"""

    downloader = INPEDownloader(
        server=INPE.FTPurl,
        root=INPE.DailyMERGEroot,
        filename_fn=INPE.MERGE_filename,
        structure_fn=INPE.MERGE_structure,
    )

    @pytest.fixture(scope="session")
    def fixture_data(self):
        """Return the test data for the tests"""
        data = {
            "test_dir": "./tmp",
            "test_date": "2023-03-01",
            "end_date": "2023-03-03",
            "correct_structure": "2023/03",
            "correct_filename": "MERGE_CPTEC_20230301.grib2",
            "NonExistentFTP": "nonexistent.example.com",
            "DownloadTestFile": "gera_Normais.ksh",
        }
        return data

    def test_init(self):
        """Test the initialization of the class"""

        # create a downloader

        assert isinstance(self.downloader, INPEDownloader)

    def test_grib2tiff(self):
        """docstring"""
        pass

    def test_is_downloaded(self):
        """docstring"""
        pass

    def test_compare_files(self):
        """docstring"""
        pass

    def test_remote_file_path(self, fixture_data):
        """Test if remote file path is being created correctly"""

        # create a target to the remote file
        rfp = self.downloader.remote_file_path(date_str=fixture_data["test_date"])

        # use test data to reproduce the same target
        correct_rfp = os.path.join(
            INPE.DailyMERGEroot,
            fixture_data["correct_structure"],
            fixture_data["correct_filename"],
        )

        assert rfp == correct_rfp

    def test_local_file_path(self, fixture_data):
        """Test if local file path is being created correctly"""

        # test with both possible extensions
        for ext in FileType:

            filepath = self.downloader.local_file_path(
                date_str=fixture_data["test_date"],
                local_folder=fixture_data["test_dir"],
                file_type=ext,
            )
            assert filepath.exists()
            assert filepath.suffix == ext.value

    def test_download_file(self, fixture_data):
        """Test the download file method with a mock to avoid actual download"""

        # first test... by passing the default dir, the files already exists and mock
        # should not be called
        for ext in FileType:
            with patch("raindownloader.utils.FTPUtil.download_ftp_file") as ftp_mock:
                downloaded_file = self.downloader.download_file(
                    date_str=fixture_data["test_date"],
                    local_folder=fixture_data["test_dir"],
                    file_type=ext,
                    force=False,
                )

                assert downloaded_file == self.downloader.local_file_path(
                    date_str=fixture_data["test_date"],
                    local_folder=fixture_data["test_dir"],
                    file_type=ext,
                )

                # the important thing here is to ckec if it has been called
                assert not ftp_mock.called
                assert isinstance(downloaded_file, Path)
                assert downloaded_file.suffix == ext.value

        # now, we will call forcing the download, both download and grib2tiff must be called
        with patch(
            "raindownloader.inpedownloader.INPEDownloader.grib2tif"
        ) as grib2tif_mock, patch(
            "raindownloader.utils.FTPUtil.download_ftp_file"
        ) as ftp_mock:
            downloaded_file = self.downloader.download_file(
                date_str=fixture_data["test_date"],
                local_folder=fixture_data["test_dir"],
                file_type=FileType.GEOTIFF,
                force=True,
            )

            # assert both mocks have been called
            # assert self.downloader.ftp.download_ftp_file.called
            assert isinstance(downloaded_file, Path)
            assert ftp_mock.called
            assert grib2tif_mock.called

    def test_download_files(self, fixture_data):
        """
        Test the download_files function, mocking the ftp request
        """

        # to test this function we are going to pass a known number of dates to be downloaded
        # one of the dates will not be existent, so it will have to skip correctly

        def download_mock_logic(*args, **kwargs):
            return self.downloader.local_file_path(
                date_str=kwargs["date_str"], local_folder=fixture_data["test_dir"]
            )

        with patch(
            "raindownloader.inpedownloader.INPEDownloader.download_file",
            wraps=download_mock_logic,
        ):

            dates = DateProcessor.dates_range(
                start_date=fixture_data["test_date"], end_date=fixture_data["end_date"]
            )

            files = self.downloader.download_files(
                dates=dates, local_folder=fixture_data["test_dir"]
            )

            assert len(files) == len(dates)
            for file in files:
                assert isinstance(file, Path)

    def test_download_range(self, fixture_data):
        """
        Test just the overall logic of download_range method, without actually
        downloading the files.
        """
        pass
