"""
Module with specialized classes to understand the INPE FTP Structure
"""
import ftplib
import os
from pathlib import Path
from enum import Enum
from typing import Union, List, Optional

# from abc import ABC, abstractmethod
from datetime import timedelta, datetime

import xarray as xr
import rioxarray as xrio
import rasterio as rio

from .utils import DateProcessor, FTPUtil, OSUtil, FileType
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

        self.ftp = FTPUtil(server)
        self.parsers = parsers

        # Avoid checking for updates in the server everytime a file is requested
        self.avoid_update = avoid_update

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
    def data_types(self):
        """Return the data types available in the parsers"""
        return [parse.type for parse in self.parsers]

    def is_downloaded(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        check_for_update=False,
    ) -> bool:
        """Compare remote and local files and return if they are equal"""
        # create a string pointing to the remote file and get its info
        remote_file = self.remote_file_path(date_str, datatype=datatype)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        # create the local_file path always pointing to the .GRIB!!!!
        local_file = self.local_file_path(
            date_str,
            local_folder,
            datatype=datatype,  # file_type=FileType.GRIB
        )

        # if the file does not exist, exit with false
        if not local_file.exists():
            return False

        if check_for_update:
            local_info = OSUtil.get_local_file_info(local_file)

            # first, check the names
            if os.path.basename(remote_file) != os.path.basename(local_file):
                return False

            remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)
            local_info = OSUtil.get_local_file_info(local_file)

            return (remote_info["size"] == local_info["size"]) and (
                remote_info["datetime"] == local_info["datetime"]
            )

        return True

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
            if parser.type == datatype:
                return parser

        raise ValueError(f"Parser not found for data type {datatype}")

    def remote_file_path(self, date_str: str, datatype: Union[Enum, str]) -> str:
        """Create the remote file path given a date"""
        # filename = self.filename_fn(date_str)
        # folder = self.structure_fn(date_str)

        # return "/".join([self.root, folder, filename])
        parser = self.get_parser(datatype=datatype)

        return parser.target(date_str=date_str)

    def remote_file_exists(self, date_str: str, datatype: Union[Enum, str]) -> bool:
        """Docstring"""

        remote_path = self.remote_file_path(date_str, datatype=datatype)
        try:
            self.ftp.ftp.size(remote_path)

        except ftplib.error_perm as error:
            if str(error).startswith("550"):
                print("File does not exists")
            else:
                print(f"Error checking file existence: {error}")
            return False

        return True

    def local_file_path(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        # file_type: FileType = FileType.GRIB,
    ) -> Path:
        """
        Create the path for the local file, depending on the folder and file type.
        It uses the filename function to derive the final filename.
        """
        parser = self.get_parser(datatype=datatype)
        filename = Path(parser.filename(date_str))

        # if file_type is not None:
        #     filename = filename.with_suffix(file_type.value)

        return Path(local_folder) / filename

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
        file_type: Optional[FileType] = None,
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
        remote_file = self.remote_file_path(date_str, datatype=datatype)
        local_file = self.local_file_path(
            date_str, local_folder, datatype=datatype  # , file_type=file_type
        )

        # check if file exists
        downloaded_file = None
        if local_file.exists() and not force:
            # check if they are the same
            if self.avoid_update or self.is_downloaded(
                date_str, local_file.parent, datatype=datatype
            ):
                pass
                # print(
                #     f"file {local_file.with_suffix(FileType.GRIB.value)} already exists."
                # )
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
            Downloader.grib2tif(local_file.with_suffix(FileType.GRIB.value))

        return local_file

    def download_files(
        self,
        dates: List[str],
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        file_type: FileType = FileType.GRIB,
        force: bool = False,
    ) -> List[Path]:
        """
        Download files from a list of dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """

        # before downloading the files, check if the local folder exists
        if not Path(local_folder).exists():
            raise FileNotFoundError(f"Folder not found: {local_folder}")

        files = []
        for date in dates:
            # try:
            files.append(
                self.download_file(
                    date_str=date,
                    local_folder=local_folder,
                    datatype=datatype,
                    file_type=file_type,
                    force=force,
                )
            )

            # except Exception as error:  # pylint:disable=broad-except
            #     files.append(f"Error {date}:  {error}")

        return files

    def download_range(
        self,
        start_date: str,
        end_date: str,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        file_type: FileType = FileType.GRIB,
        force: bool = False,
    ) -> List[Path]:
        """
        Download a range of files from start to end dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """

        dates = self.get_parser(datatype).dates_range(start_date, end_date)
        return self.download_files(
            dates=dates,
            local_folder=local_folder,
            file_type=file_type,
            force=force,
            datatype=datatype,
        )

    def download_recent(
        self,
        local_folder: Union[str, Path],
        datatype: Union[Enum, str],
        num: int = 1,
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
            start_date=first_str,
            end_date=now_str,
            local_folder=local_folder,
            datatype=datatype,
        )

    def open_file(self, file: Union[Path, str]) -> xr.Dataset:
        """Open a file and apply the post processing, if existent"""
        dset = xr.open_dataset(file)

        file_format = Path(file).suffix
        if file_format in self.post_processors:
            dset = self.post_processors[file_format](dset)

        return dset

    @staticmethod
    def _create_cube(
        files: List,
        # name_parser: Optional[Callable] = None,
        dim_key: Optional[str] = "time",
        # squeeze_dims: Optional[Union[List[str], str]] = None,
    ) -> xr.Dataset:
        """
        Stack the images in the list as one XARRAY Dataset cube.
        """

        # first, check if name parser and dimension key are setted correctly
        # if (name_parser is None) ^ (dim_key is None):
        #     raise ValueError("If name parser or dim key is set, both must be setted.")

        # set the stacked dimension name
        dim = "time" if dim_key is None else dim_key

        # create a cube with the files
        data_arrays = [
            xr.open_dataset(file).astype("float32")
            for file in files
            if Path(file).exists()
        ]

        cube = xr.concat(data_arrays, dim=dim)

        return cube

    def create_cube(self, files: list, dim_key: Optional[str] = "time") -> xr.Dataset:
        """Create a cube from the list of files and apply the post_processor of the downloader"""

        cube = Downloader._create_cube(files=files, dim_key=dim_key)

        file_format = Path(files[0]).suffix
        if file_format in self.post_processors:
            cube = self.post_processors[file_format](cube)

        return cube
