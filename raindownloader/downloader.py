"""
Module with specialized classes to understand the INPE FTP Structure
"""

from pathlib import Path
from enum import Enum
from typing import Union, List, Optional, Callable
from datetime import datetime

import geopandas as gpd
import xarray as xr

from .utils import FTPUtil, OSUtil
from .inpeparser import INPETypes
from .parser import BaseParser


class Downloader:
    """Business logic to download files from a given structure"""

    def __init__(
        self,
        server: str,
        parsers: List[BaseParser],
        local_folder: Union[str, Path],
        avoid_update: bool = True,
        post_processors: Optional[dict] = None,
    ) -> None:
        # store initialization variables
        self.ftp = FTPUtil(server)
        self.parsers = parsers
        self.local_folder = Path(local_folder)

        # Avoid checking for updates in the server everytime a file is requested
        self.avoid_update = avoid_update

        # update the parsers with global configs
        for parser in self.parsers:
            parser.ftp = self.ftp
            parser.avoid_update = self.avoid_update
            parser.clean_local_folder(local_folder=local_folder)

        # functions to be applied to filetypes after they are loaded
        self.post_processors = {} if post_processors is None else post_processors

    @staticmethod
    def cut_cube_by_geoms(
        cube: xr.DataArray, geometries: gpd.GeoSeries
    ) -> xr.DataArray:
        """
        Calculate the cube inside the given geometries in the GeoDataFrame.
        The geometries are stored in a GeoSeries from Pandas
        """
        # first make sure we have the same CRS
        geometries = geometries.to_crs(cube.rio.crs)

        # Let's use clip to ignore data outide the geometry
        clipped = cube.rio.clip(geometries)

        return clipped

    @staticmethod
    def get_time_series(
        cube: xr.DataArray,
        shp: gpd.GeoDataFrame,
        reducer: Callable,
        keep_dim: str = "time",  # specify the dimension along with we will retrieve the TS
    ):
        """Get a time series of values within the shape, given a reducer method"""
        # clip to the desired area
        area = cube.rio.clip(shp.geometry)

        # get the dimensions to be reduced
        reduce_dims = list(cube.dims)
        reduce_dims.remove(keep_dim)

        series = reducer(area, dim=reduce_dims).to_series()

        return series

    @property
    def data_types(self) -> List[Union[Enum, str]]:
        """Return the data types available in the parsers"""
        return [parse.datatype for parse in self.parsers]

    def is_downloaded(
        self,
        date_str: str,
        # local_folder: Union[str, Path],
        datatype: Union[INPETypes, str],
    ):
        """Return if the desired file is downloaded. Dispatch to the correct parser"""
        parser = self.get_parser(datatype=datatype)
        return parser.is_downloaded(
            date=date_str,
            local_folder=self.local_folder,
        )

    def compare_files(
        self,
        date_str: str,
        datatype: Union[INPETypes, str],
    ) -> None:
        """Compare remote and local files visually"""
        remote_file = self.remote_file_path(date_str, datatype=datatype)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        local_file = self.local_file_path(date_str, datatype=datatype)
        local_info = OSUtil.get_local_file_info(local_file)
        print(remote_info)
        print(local_info)

    def get_parser(self, datatype: Union[Enum, str]) -> BaseParser:
        """Get the correct parser for the specified datatype"""
        for parser in self.parsers:
            if parser.datatype == datatype:
                return parser

        raise ValueError(f"Parser not found for data type {datatype}")

    def remote_file_path(
        self, date: Union[str, datetime], datatype: Union[Enum, str]
    ) -> str:
        """Create the remote file path given a date"""
        parser = self.get_parser(datatype=datatype)

        return parser.remote_target(date=date)

    def remote_file_exists(
        self, date: Union[str, datetime], datatype: Union[Enum, str]
    ) -> bool:
        """Check if a remote file exists"""

        remote_file = self.remote_file_path(date, datatype=datatype)
        return self.ftp.file_exists(remote_file=remote_file)

    def local_file_exists(
        self, date: Union[str, datetime], datatype: Union[Enum, str]
    ) -> bool:
        """Verify if a specific local file exists"""
        parser = self.get_parser(datatype=datatype)
        local_target = parser.local_target(date=date, local_folder=self.local_folder)

        return local_target.exists()

    def local_file_path(
        self,
        date: Union[str, datetime],
        datatype: Union[Enum, str],
    ) -> Path:
        """
        Create the path for the local file, depending on the folder and file type.
        It uses the filename function to derive the final filename.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.local_target(date=date, local_folder=self.local_folder)

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
        date: str,
        datatype: Union[Enum, str],
    ) -> Path:
        """
        Download a file from the FTP server to the a local folder. The filename and ftp location
        folder filename will be obtained from the respective parsers.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.download_file(date=date, local_folder=self.local_folder)

    def get_file(
        self,
        date: Union[str, datetime],
        datatype: Union[Enum, str],
        force_download: bool = False,
    ) -> Path:
        """
        Get a specific file. If it is not available locally, download it just in time.
        If it is available locally and avoid_update is not True, check if the file has
        changed in the server.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.get_file(
            date=date,
            local_folder=self.local_folder,
            force_download=force_download,
        )

    def get_files(
        self,
        dates: List[str],
        datatype: Union[Enum, str],
        force_download: bool = False,
    ) -> List[Path]:
        """
        Download files from a list of dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """
        parser = self.get_parser(datatype=datatype)
        return parser.get_files(
            dates=dates, local_folder=self.local_folder, force_download=force_download
        )

    def get_range(
        self,
        start_date: str,
        end_date: str,
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
            local_folder=self.local_folder,
            force_download=force_download,
        )

    def open_file(
        self,
        date_str: str,
        datatype: Union[Enum, str],
        force_download: bool = False,
        return_array: bool = True,
    ) -> Union[xr.Dataset, xr.DataArray]:
        """
        Open a file and apply the post processing, if existent.
        If return_array is True, it will try to access the corresponding variable
        from the dataset, otherwise return the dataset.
        """

        # get the file
        file = self.get_file(
            date=date_str, datatype=datatype, force_download=force_download
        )

        # open the file as is
        dset = xr.open_dataset(file)

        # apply processing based on the file suffix
        file_format = Path(file).suffix
        if file_format in self.post_processors:
            dset = self.post_processors[file_format](dset)

        # get the parser to check if there is a post processing associated with it
        parser = self.get_parser(datatype=datatype)
        if parser.post_proc is not None:
            dset = parser.post_proc(dset, date_str=date_str)

        # transform the dataset into array
        if return_array:
            if isinstance(datatype, Enum):
                return dset[datatype.value["var"]]
            else:
                return dset.to_array()
        else:
            return dset

    def _create_cube(
        self,
        dates: List,
        datatype: Union[Enum, str],
        dim_key: Optional[str] = "time",
        force_download: bool = False,
    ) -> xr.DataArray:
        """
        Stack the images in the list as one XARRAY Dataset cube.
        """

        # set the stacked dimension name
        dim = "time" if dim_key is None else dim_key

        # create a cube with the files
        data_arrays = [
            self.open_file(date, datatype, force_download).astype("float32")
            for date in dates
        ]

        cube = xr.concat(data_arrays, dim=dim)  # type: ignore

        return cube

    def create_cube(
        self,
        start_date: str,
        end_date: str,
        datatype: Union[Enum, str],
        dim_key: Optional[str] = "time",
        force_download: bool = False,
    ) -> xr.DataArray:
        """Create a cube from the range and apply the post_processor of the downloader"""

        # first, let's grab the desired dates
        dates = self.get_parser(datatype).dates_range(
            start_date=start_date, end_date=end_date
        )

        # make sure the files are downloaded
        self.get_files(dates=dates, datatype=datatype)

        # then, create the cube
        cube = self._create_cube(
            dates=dates,
            datatype=datatype,
            dim_key=dim_key,
            force_download=force_download,
        )

        return cube

    def accum_rain(
        self,
        start_date: str,
        end_date: str,
        data_type: INPETypes,
        force_download: bool = False,
    ) -> xr.DataArray:
        """Accumulate the rain in the given period"""

        # first, get the cube
        cube = self.create_cube(
            start_date=start_date,
            end_date=end_date,
            datatype=data_type,
            force_download=force_download,
        )[data_type.value["var"]]

        dset = cube.sum(dim="time")
        dset = dset.assign_coords({"time": cube.time[0].values})

        return dset

    def accum_periodically_rain(
        self, periods: List, data_type: INPETypes, force_download: bool = False
    ) -> xr.DataArray:
        """Accumulate the rain in given periods."""

        # get the arrays with the accumulated rain in each period
        rains = [
            self.accum_rain(
                start_date=start,
                end_date=end,
                data_type=data_type,
                force_download=force_download,
            )
            for start, end in periods
        ]

        cube = xr.concat(rains, dim="time")
        return cube
