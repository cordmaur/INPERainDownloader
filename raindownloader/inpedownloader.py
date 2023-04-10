"""
Module with specialized classes to understand the INPE FTP Structure
"""

from pathlib import Path
from enum import Enum
from typing import Union, List, Optional

# from abc import ABC, abstractmethod

import xarray as xr
import rioxarray as xrio
import rasterio as rio

from .utils import FTPUtil, OSUtil, FileType, GISUtil
from .inpeparser import INPETypes
from .parser import BaseParser


class Downloader:
    """Business logic to download files from a given structure"""

    def __init__(
        self,
        server: str,
        parsers: List[BaseParser],
        avoid_update: bool = True,
        post_processors: Optional[dict] = None,
    ) -> None:

        # Avoid checking for updates in the server everytime a file is requested
        self.avoid_update = avoid_update
        self.ftp = FTPUtil(server)

        self.parsers = parsers

        # update the parsers with global configs
        for parser in self.parsers:
            parser.ftp = self.ftp
            parser.avoid_update = self.avoid_update

        # functions to be applied to filetypes after they are loaded
        self.post_processors = {} if post_processors is None else post_processors

    @staticmethod
    def grib2tif(grib_file: Union[str, Path], epsg: int = 4326) -> Path:
        """
        Converts a GRIB2 file to GeoTiff and set correct CRS and Longitude
        """
        grib = xrio.open_rasterio(grib_file)  # type: ignore[no-unsized-index]

        grib = grib.rio.write_crs(rio.CRS.from_epsg(epsg))  # type: ignore[attr]

        # save the precipitation raster
        filename = Path(grib_file).with_suffix(FileType.GEOTIFF.value)

        grib[0].rio.to_raster(filename, compress="deflate")

        return filename

    @staticmethod
    def grib2tif_old(grib_file: Union[str, Path], epsg: int = 4326) -> Path:
        """
        Converts a GRIB2 file to GeoTiff and set correct CRS and Longitude
        """
        grib = xrio.open_rasterio(grib_file)  # type: ignore[no-unsized-index]

        # else:
        grib = grib.rio.write_crs(rio.CRS.from_epsg(epsg))  # type: ignore[attr]

        # save the precipitation raster
        filename = Path(grib_file).with_suffix(FileType.GEOTIFF.value)

        grib["prec"].rio.to_raster(filename, compress="deflate")

        return filename

    @property
    def data_types(self) -> List[Union[Enum, str]]:
        """Return the data types available in the parsers"""
        return [parse.datatype for parse in self.parsers]

    def is_downloaded(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[INPETypes, str],
    ):
        """Return if the desired file is downloaded. Dispatch to the correct parser"""
        parser = self.get_parser(datatype=datatype)
        return parser.is_downloaded(
            date_str=date_str,
            local_folder=local_folder,
        )

    def compare_files(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[INPETypes, str],
    ) -> None:
        """Compare remote and local files visually"""
        remote_file = self.remote_file_path(date_str, datatype=datatype)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        local_file = self.local_file_path(date_str, local_folder, datatype=datatype)
        local_info = OSUtil.get_local_file_info(local_file)
        print(remote_info)
        print(local_info)

    def get_parser(self, datatype: Union[Enum, str]) -> BaseParser:
        """Get the correct parser for the specified datatype"""
        for parser in self.parsers:
            if parser.datatype == datatype:
                return parser

        raise ValueError(f"Parser not found for data type {datatype}")

    def remote_file_path(self, date_str: str, datatype: Union[Enum, str]) -> str:
        """Create the remote file path given a date"""
        parser = self.get_parser(datatype=datatype)

        return parser.remote_target(date_str=date_str)

    def remote_file_exists(self, date_str: str, datatype: Union[Enum, str]) -> bool:
        """Check if a remote file exists"""

        remote_file = self.remote_file_path(date_str, datatype=datatype)
        return self.ftp.file_exists(remote_file=remote_file)

    def local_file_path(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
    ) -> Path:
        """
        Create the path for the local file, depending on the folder and file type.
        It uses the filename function to derive the final filename.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.local_target(date_str=date_str, local_folder=local_folder)

    def files_range(
        self, start_date_str: str, end_date_str: str, datatype: Union[INPETypes, str]
    ) -> List[str]:
        """Docstring"""
        dates = self.get_parser(datatype).dates_range(
            start_date=start_date_str, end_date=end_date_str
        )
        return [self.remote_file_path(date, datatype=datatype) for date in dates]

    def download_file(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
    ) -> Path:
        """
        Download a file from the FTP server to the a local folder. The filename and ftp location
        folder filename will be obtained from the respective parsers.
        The result will be the local path for the file. If file already exists, it will not be
        downloaded again, unless it has been updated on the server.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.download_file(date_str=date_str, local_folder=local_folder)

    def get_file(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        force_download: bool = False,
    ) -> Path:
        """
        Get a specific file. If it is not available locally, download it just in time.
        If it is available locally and avoid_update is not True, check if the file has
        changed in the server
        """
        parser = self.get_parser(datatype=datatype)
        return parser.get_file(
            date_str=date_str,
            local_folder=local_folder,
            force_download=force_download,
        )

    def get_files(
        self,
        dates: List[str],
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        force_download: bool = False,
    ) -> List[Path]:
        """
        Download files from a list of dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.get_files(
            dates=dates, local_folder=local_folder, force_download=force_download
        )

    def get_range(
        self,
        start_date: str,
        end_date: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        force_download: bool = False,
    ) -> List[Path]:
        """
        Download a range of files from start to end dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """

        parser = self.get_parser(datatype=datatype)
        return parser.get_range(
            start_date=start_date,
            end_date=end_date,
            local_folder=local_folder,
            force_download=force_download,
        )

    # def download_recent(
    #     self,
    #     local_folder: Union[str, Path],
    #     datatype: Union[Enum, str],
    #     num: int = 1,
    # ) -> List[Path]:
    #     """
    #     Download the recent x files, where x is the number of files to download.
    #     """
    #     now = datetime.now()

    #     # testing what happens if today's not present yet
    #     now = now + timedelta(days=1)

    #     first_str = DateProcessor.normalize_date(now - timedelta(days=num - 1))
    #     now_str = DateProcessor.normalize_date(now)

    #     return self.get_range(
    #         start_date=first_str,
    #         end_date=now_str,
    #         local_folder=local_folder,
    #         datatype=datatype,
    #     )

    def open_file(self, file: Union[Path, str]) -> xr.Dataset:
        """Open a file and apply the post processing, if existent"""
        dset = xr.open_dataset(file)

        file_format = Path(file).suffix
        if file_format in self.post_processors:
            dset = self.post_processors[file_format](dset)

        return dset

    def create_cube(self, files: list, dim_key: Optional[str] = "time") -> xr.Dataset:
        """Create a cube from the list of files and apply the post_processor of the downloader"""

        cube = GISUtil.create_cube(files=files, dim_key=dim_key)

        file_format = Path(files[0]).suffix
        if file_format in self.post_processors:
            cube = self.post_processors[file_format](cube)

        return cube
