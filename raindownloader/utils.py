"""
Module with several utils used in raindownloader INPEraindownloader package
"""
# download 1 arquivo por data/dia/etc.
# download um range de datas
# download última chuva
# download ulitmos X dias

import ftplib
import os
from pathlib import Path
from typing import Union, List, Optional, Tuple
from enum import Enum, auto

# from abc import ABC, abstractmethod
import datetime
import calendar

from dateutil import parser
from dateutil.relativedelta import relativedelta

import xarray as xr


class DateFrequency(Enum):
    """Specifies date frequency for the products"""

    DAILY = auto()
    MONTHLY = auto()


class FileType(Enum):
    """Specifies the file types for downloading"""

    GRIB = ".grib2"
    GEOTIFF = ".tif"
    NETCDF = ".nc"


class FTPUtil:
    """FTP helper class to download file preserving timestamp and to get file info, among others"""

    def __init__(self, server: str) -> None:
        self.ftp = FTPUtil.open_connection(server)

    @staticmethod
    def open_connection(server: str) -> ftplib.FTP:
        """Open an ftp connection and return an FTP instance"""
        ftp = ftplib.FTP(server)
        ftp.login()
        ftp.sendcmd("TYPE I")

        return ftp

    @property
    def is_connected(self) -> bool:
        """Check if the connection is open"""

        try:
            # test if the ftp is still responding
            self.ftp.pwd()
            return True

        except Exception:  # pylint:disable=broad-except
            # otherwise, return False
            return False

    def get_connection(self, alt_server: Optional[str] = None) -> ftplib.FTP:
        """
        Return a connection. If current connection is closed, connect again.
        If an alternative server is provided, return the alternative server.
        """
        if alt_server is not None:
            return FTPUtil.open_connection(alt_server)

        if not self.is_connected:
            self.ftp = FTPUtil.open_connection(self.ftp.host)

        return self.ftp

    def download_ftp_file(
        self,
        remote_file: str,
        local_folder: Union[str, Path],
        # remote_tz_str: str = "GMT",
        # local_tz_str: str = "Brazil/East",
        alt_server: Optional[str] = None,
    ) -> Path:
        """Download an ftp file preserving filename and timestamps"""

        # to start, check if the timezones are valid
        # remote_tz = pytz.timezone(remote_tz_str)
        # local_tz = pytz.timezone(local_tz_str)

        # get a valid connection
        ftp = self.get_connection(alt_server=alt_server)

        # get the filename and set the target path
        filename = os.path.basename(remote_file)
        local_path = Path(local_folder) / filename

        # Retrieve the file from the ftp
        with open(local_path, "wb") as local_file:
            ftp.retrbinary("RETR " + remote_file, local_file.write)

        # once downloaded, retrieve the remote time, correct the timezone and save it
        remote_time_str = ftp.sendcmd("MDTM " + remote_file)
        remote_time = parser.parse(remote_time_str[4:])

        # correct the timestamp
        # local_time = remote_tz.localize(remote_time).astimezone(local_tz)

        # timestamp = local_time.timestamp()
        timestamp = remote_time.timestamp()
        os.utime(local_path, (timestamp, timestamp))

        return local_path

    def get_ftp_file_info(
        self,
        remote_file: str,
        alt_server: Optional[str] = None,
    ) -> dict:
        """Get modification time and size of a specific file in the FTP server"""

        # get a valid connection
        ftp = self.get_connection(alt_server=alt_server)

        remote_time_str = ftp.sendcmd("MDTM " + remote_file)
        remote_time = parser.parse(remote_time_str[4:])

        # correct the timestamp
        size = ftp.size(remote_file)

        return {"datetime": remote_time, "size": size}

    def __repr__(self) -> str:
        output = f"FTP {'' if self.is_connected else 'Not '}connected to server {self.ftp.host}"
        return output

    def file_exists(self, remote_file: str) -> bool:
        """Docstring"""

        try:
            self.ftp.size(remote_file)

        except ftplib.error_perm as error:
            if str(error).startswith("550"):
                print("File does not exists")
            else:
                print(f"Error checking file existence: {error}")
            return False

        return True

    def file_changed(self, remote_file: str, file_info: dict) -> bool:
        """
        Check if the remote file has changed based in the size and datetime values
        within file_info dict
        """

        remote_info = self.get_ftp_file_info(remote_file=remote_file)

        return (remote_info["size"] == file_info["size"]) and (
            remote_info["datetime"] == file_info["datetime"]
        )


class GISUtil:
    """Helper class for basic GIS operations"""

    @staticmethod
    def create_cube(
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

    @staticmethod
    def profile_from_xarray(array: xr.DataArray, driver: Optional[str] = "GTiff"):
        """Create a rasterio profile given an rioxarray"""
        profile = dict(
            driver=driver,
            width=array.rio.width,
            height=array.rio.height,
            count=array.rio.count,
            dtype=array.dtype,
            crs=array.rio.crs,
            transform=array.rio.transform(),
            nodata=array.rio.nodata,
        )

        return profile


class OSUtil:
    """Helper class for OS related functions"""

    @staticmethod
    def get_local_file_info(file_path: Union[str, Path]) -> dict:
        """Get the size and modification time of a local file"""

        # get the status of the file
        stat = Path(file_path).stat()

        local_dt = datetime.datetime.fromtimestamp(stat.st_mtime)

        return {"datetime": local_dt, "size": stat.st_size}


class DateProcessor:
    """Docstring"""

    @staticmethod
    def normalize_date(date: Union[str, datetime.datetime]) -> str:
        """
        Parse the date string in any format accepted by dateutil and delivers a date
        in the following format: "YYYYMMDD"
        """
        if not isinstance(date, datetime.datetime):
            date = parser.parse(date)

        return date.strftime("%Y%m%d")

    @staticmethod
    def as_datetime(date: Union[str, datetime.datetime]) -> datetime.datetime:
        """
        Return the date as datetime
        """
        if not isinstance(date, datetime.datetime):
            date = parser.parse(date)

        return date

    @staticmethod
    def pretty_date(date: Union[str, datetime.datetime]) -> str:
        """Return the date in a pretty printable format dd/mm/yyyy"""
        if not isinstance(date, datetime.datetime):
            date = parser.parse(date)

        return date.strftime("%d-%m-%Y")

    @staticmethod
    def dates_range(
        start_date: str, end_date: str, date_freq: DateFrequency
    ) -> List[str]:
        """Spawn a dates list in normalized format in the desired range"""

        current_date = parser.parse(start_date)
        final_date = parser.parse(end_date)

        dates = []

        if date_freq == DateFrequency.DAILY:
            while current_date <= final_date:
                dates.append(current_date.strftime("%Y%m%d"))
                current_date += datetime.timedelta(days=1)

        elif date_freq == DateFrequency.MONTHLY:
            # set the first day of the month
            current_date = datetime.datetime(current_date.year, current_date.month, 1)
            while current_date <= final_date:
                dates.append(DateProcessor.normalize_date(current_date))
                days = calendar.monthrange(current_date.year, current_date.month)[1]
                current_date += datetime.timedelta(days=days)

        return dates

    @staticmethod
    def month_abrev(date: Union[str, datetime.datetime]) -> str:
        """Return the month as a three-character string"""
        if not isinstance(date, datetime.datetime):
            date = parser.parse(date)

        return date.strftime("%b").lower()

    @staticmethod
    def start_end_dates(date: Union[str, datetime.datetime]) -> Tuple[str, str]:
        """Return the first date and last date in a specific month"""
        if not isinstance(date, datetime.datetime):
            date = parser.parse(date)

        # get the number of days
        _, days = calendar.monthrange(date.year, date.month)
        first_day = datetime.datetime(date.year, date.month, 1)
        last_day = first_day + datetime.timedelta(days=days - 1)
        return DateProcessor.normalize_date(first_day), DateProcessor.normalize_date(
            last_day
        )

    @staticmethod
    def last_n_months(
        date: Union[str, datetime.datetime], lookback: int = 6
    ) -> Tuple[str, str]:
        """
        Return start and end month considering the month of the given date and
        looking back n months
        """

        if not isinstance(date, datetime.datetime):
            date = parser.parse(date)

        start_date = date - relativedelta(months=lookback - 1)

        start_date_str = f"{start_date.year}-{start_date.month}"
        end_date_str = f"{date.year}-{date.month}"

        return (start_date_str, end_date_str)
