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
from typing import Union, List, Optional
from enum import Enum

# from abc import ABC, abstractmethod
from datetime import timedelta, datetime

from dateutil import parser
import pytz

import xarray as xr


class FileType(Enum):
    """Specifies the file types for downloading"""

    GRIB = ".grib2"
    GEOTIFF = ".tif"


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
        remote_tz_str: str = "GMT",
        local_tz_str: str = "Brazil/East",
        alt_server: Optional[str] = None,
    ) -> Path:
        """Download an ftp file preserving filename and timestamps"""

        # to start, check if the timezones are valid
        remote_tz = pytz.timezone(remote_tz_str)
        local_tz = pytz.timezone(local_tz_str)

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
        local_time = remote_tz.localize(remote_time).astimezone(local_tz)

        timestamp = local_time.timestamp()
        os.utime(local_path, (timestamp, timestamp))

        return local_path

    def get_ftp_file_info(
        self,
        remote_file: str,
        remote_tz_str: str = "GMT",
        local_tz_str: str = "Brazil/East",
        alt_server: Optional[str] = None,
    ) -> dict:
        """Get modification time and size of a specific file in the FTP server"""
        # to start, check if the timezones are valid
        remote_tz = pytz.timezone(remote_tz_str)
        local_tz = pytz.timezone(local_tz_str)

        # get a valid connection
        ftp = self.get_connection(alt_server=alt_server)

        remote_time_str = ftp.sendcmd("MDTM " + remote_file)
        remote_time = parser.parse(remote_time_str[4:])

        # correct the timestamp
        local_time = remote_tz.localize(remote_time).astimezone(local_tz)
        size = ftp.size(remote_file)

        return {"datetime": local_time, "size": size}

    def __repr__(self) -> str:
        output = f"FTP {'' if self.is_connected else 'Not '}connected to server {self.ftp.host}"
        return output


class GISUtil:
    """Helper class for basic GIS operations"""

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
    def get_local_file_info(
        file_path: Union[str, Path], local_tz_str="Brazil/East"
    ) -> dict:
        """Get the size and modification time of a local file"""

        # create the local timezone object
        local_tz = pytz.timezone(local_tz_str)

        # get the status of the file
        stat = Path(file_path).stat()

        # parse the date correctly
        local_dt = local_tz.localize(datetime.fromtimestamp(stat.st_mtime))

        return {"datetime": local_dt, "size": stat.st_size}


class DateProcessor:
    """Docstring"""

    @staticmethod
    def normalize_date(date: Union[str, datetime]) -> str:
        """
        Parse the date string in any format accepted by dateutil and delivers a date
        in the following format: "YYYYMMDD"
        """
        if not isinstance(date, datetime):
            date = parser.parse(date)

        return date.strftime("%Y%m%d")

    @staticmethod
    def pretty_date(date: Union[str, datetime]) -> str:
        """Return the date in a pretty printable format dd/mm/yyyy"""
        if not isinstance(date, datetime):
            date = parser.parse(date)

        return date.strftime("%d-%m-%Y")

    @staticmethod
    def dates_range(start_date: str, end_date: str) -> List[str]:
        """Spawn a dates list in normalized format in the desired range"""

        initial_date = parser.parse(start_date)
        final_date = parser.parse(end_date)

        dates = []
        while initial_date <= final_date:
            dates.append(initial_date.strftime("%Y%m%d"))
            initial_date += timedelta(days=1)

        return dates
