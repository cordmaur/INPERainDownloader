"""
Module with specialized classes to understand the INPE FTP Structure
"""
import ftplib
import os
from pathlib import Path
from typing import Union, List

# from abc import ABC, abstractmethod
from datetime import timedelta, datetime

import xarray as xr
import rasterio as rio

from .utils import DateProcessor, FTPUtil, OSUtil, FileType
from .inpe import INPE


class INPEDownloader:
    """Business logic to download files from INPE structure"""

    def __init__(
        self,
        server: str,
        root: str,
        filename_fn=INPE.MERGE_filename,
        structure_fn=INPE.MERGE_structure,
    ) -> None:

        self.ftp = FTPUtil(server)
        self.root = os.path.normpath(root)
        self.filename_fn = filename_fn
        self.structure_fn = structure_fn

    @staticmethod
    def grib2tif(grib_file: Union[str, Path]) -> Path:
        """Converts a GRIB2 file to GeoTiff and set correct CRS and Longitude"""
        grib = xr.open_dataset(grib_file)

        # tosdo: write the correct function for longitude
        grib = grib.assign_coords(longitude=grib.longitude - 360)
        grib = grib.rio.write_crs(rio.CRS.from_epsg(4326))

        # save the precipitation raster
        filename = Path(grib_file).with_suffix(FileType.GEOTIFF.value)

        grib["prec"].rio.to_raster(filename)

        return filename

    def is_downloaded(self, date_str: str, local_folder: Union[str, Path]) -> bool:
        """Compare remote and local files and return if they are equal"""
        # create a string pointing to the remote file and get its info
        remote_file = self.remote_file_path(date_str)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        # create the local_file path always pointing to the .GRIB!!!!
        local_file = self.local_file_path(
            date_str, local_folder, file_type=FileType.GRIB
        )
        local_info = OSUtil.get_local_file_info(local_file)

        # first, check the names
        if os.path.basename(remote_file) != os.path.basename(local_file):
            return False

        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)
        local_info = OSUtil.get_local_file_info(local_file)

        return (remote_info["size"] == local_info["size"]) and (
            remote_info["datetime"] == local_info["datetime"]
        )

    def compare_files(self, date_str: str, local_folder: Union[str, Path]) -> None:
        """Compare remote and local files visually"""
        remote_file = self.remote_file_path(date_str)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        local_file = self.local_file_path(date_str, local_folder)
        local_info = OSUtil.get_local_file_info(local_file)
        print(remote_info)
        print(local_info)

    def remote_file_path(self, date_str: str) -> str:
        """Create the remote file path given a date"""
        filename = self.filename_fn(date_str)
        folder = self.structure_fn(date_str)

        return "/".join([self.root, folder, filename])

    def local_file_path(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        file_type: FileType = FileType.GRIB,
    ) -> Path:
        """
        Create the path for the local file, depending on the folder and file type.
        It uses the filename function to derive the final filename.
        """
        filename = Path(self.filename_fn(date_str))

        filename = filename.with_suffix(file_type.value)

        return Path(local_folder) / filename

    def files_range(self, start_date_str: str, end_date_str: str) -> List[str]:
        """Docstring"""
        dates = DateProcessor.dates_range(
            start_date=start_date_str, end_date=end_date_str
        )
        return [self.remote_file_path(date) for date in dates]

    def download_file(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        file_type: FileType = FileType.GRIB,
        force: bool = False,
    ) -> Path:
        """
        Download a file from the FTP server to the a local folder. The filename and ftp location
        folder filename will be obtained from the functions filename_fn and structure_fn
        respectively.
        The result will be the local path for the file. If file already exists, it will not be
        downloaded again, unless it has been updated on the server.
        """
        # get the file locations
        remote_file = self.remote_file_path(date_str)
        local_file = self.local_file_path(date_str, local_folder, file_type=file_type)

        # check if file exists
        downloaded_file = None
        if local_file.exists() and not force:
            # check if they are the same
            if self.is_downloaded(date_str, local_file.parent):
                print(
                    f"file {local_file.with_suffix(FileType.GRIB.value)} already exists."
                )
            else:
                print(f"Local file {local_file} is outdated. Downloading it.")
                downloaded_file = self.ftp.download_ftp_file(
                    remote_file, local_file.parent
                )
        else:
            downloaded_file = self.ftp.download_ftp_file(remote_file, local_file.parent)

        # next step is to convert it to GeoTiff if necessary
        # if geotiff is demanded we convert in following situations:
        # new.grib was downloaded or local_file (.tif) is inexistent.
        if file_type == FileType.GEOTIFF and (
            (downloaded_file is not None) or (not local_file.exists())
        ):
            INPEDownloader.grib2tif(local_file.with_suffix(FileType.GRIB.value))

        return local_file

    def download_files(
        self,
        dates: List[str],
        local_folder: Union[str, Path],
        file_type: FileType = FileType.GRIB,
        force: bool = False,
    ) -> List[Path]:
        """
        Download files from a list of dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """
        files = []
        for date in dates:
            try:
                files.append(
                    self.download_file(
                        date_str=date,
                        local_folder=local_folder,
                        file_type=file_type,
                        force=force,
                    )
                )

            except Exception as error:  # pylint:disable=broad-except
                files.append(f"Error {date}:  {error}")

        return files

    def download_range(
        self,
        start_date: str,
        end_date: str,
        local_folder: Union[str, Path],
        file_type: FileType = FileType.GRIB,
        force: bool = False,
    ) -> List[Path]:
        """
        Download a range of files from start to end dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """

        dates = DateProcessor.dates_range(start_date, end_date)
        return self.download_files(
            dates=dates, local_folder=local_folder, file_type=file_type, force=force
        )

    def download_recent(
        self, local_folder: Union[str, Path], num: int = 1
    ) -> List[Path]:
        """
        Download the recent x files, where x is the number of files to download.
        """
        now = datetime.now()

        # testing what happens if today's not present yet
        now = now + timedelta(days=1)

        first_str = DateProcessor.normalize_date(now - timedelta(days=num - 1))
        now_str = DateProcessor.normalize_date(now)

        return self.download_range(
            start_date=first_str, end_date=now_str, local_folder=local_folder
        )

    def remote_file_exists(self, date_str: str) -> bool:
        """Docstring"""

        remote_path = self.remote_file_path(date_str)
        try:
            self.ftp.ftp.size(remote_path)

        except ftplib.error_perm as error:
            if str(error).startswith("550"):
                print("File does not exists")
            else:
                print(f"Error checking file existence: {error}")
            return False

        return True
