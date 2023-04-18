"""
Module with several utils used in raindownloader INPEraindownloader package
"""
import ftplib
import os
from pathlib import Path
from typing import Union, List, Optional, Tuple
from enum import Enum

# from abc import ABC, abstractmethod
import datetime
import calendar

from dateutil import parser
from dateutil.relativedelta import relativedelta

import rasterio as rio
import xarray as xr
import rioxarray as xrio


class DateFrequency(Enum):
    """Specifies date frequency for the products"""

    DAILY = {"days": 1}
    MONTHLY = {"months": 1}
    YEARLY = {"years": 1}


class DateProcessor:
    """Docstring"""

    @staticmethod
    def parse_date(date: Union[str, datetime.datetime]) -> datetime.datetime:
        """Return a date in datetime format, regardless the input [str | datetime]"""
        return date if isinstance(date, datetime.datetime) else parser.parse(date)

    @staticmethod
    def normalize_date(date: Union[str, datetime.datetime]) -> str:
        """
        Parse the date string in any format accepted by dateutil and delivers a date
        in the following format: "YYYYMMDD"
        """
        date = DateProcessor.parse_date(date)

        return date.strftime("%Y%m%d")

    @staticmethod
    def pretty_date(date: Union[str, datetime.datetime]) -> str:
        """Return the date in a pretty printable format dd/mm/yyyy"""
        date = DateProcessor.parse_date(date)

        return date.strftime("%d-%m-%Y")

    @staticmethod
    def dates_range(
        start_date: Union[str, datetime.datetime],
        end_date: Union[str, datetime.datetime],
        date_freq: DateFrequency,
    ) -> List[str]:
        """Spawn a dates list in normalized format in the desired range"""

        current_date = DateProcessor.parse_date(start_date)
        final_date = DateProcessor.parse_date(end_date)

        # create the step to be applied to the current date
        step = relativedelta(**date_freq.value)

        # looop through the dates
        dates = []
        while current_date <= final_date:
            dates.append(DateProcessor.normalize_date(current_date))
            current_date += step

        return dates

    @staticmethod
    def month_abrev(date: Union[str, datetime.datetime]) -> str:
        """Return the month as a three-character string"""
        date = DateProcessor.parse_date(date)

        return date.strftime("%b").lower()

    @staticmethod
    def start_end_dates(date: Union[str, datetime.datetime]) -> Tuple[str, str]:
        """Return the first date and last date in a specific month"""
        date = DateProcessor.parse_date(date)

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
        date = DateProcessor.parse_date(date)

        start_date = date - relativedelta(months=lookback - 1)

        start_date_str = f"{start_date.year}-{start_date.month}"
        end_date_str = f"{date.year}-{date.month}"

        return (start_date_str, end_date_str)

    @staticmethod
    def create_monthly_periods(
        start_date: Union[str, datetime.datetime],
        end_date: Union[str, datetime.datetime],
        month_step: int,
    ) -> List[tuple]:
        """Create monthly periods given a step (e.g, quaterly=3, semestraly=6, yearly=12)"""
        current_date = DateProcessor.parse_date(start_date)
        final_date = DateProcessor.parse_date(end_date)

        periods = []
        while current_date <= final_date:
            start_period = current_date
            end_period = start_period + relativedelta(months=month_step - 1)

            # if the end date for the period is inside the final date, add this period
            if end_period <= final_date:
                periods.append((start_period, end_period))

            # otherwise, quit the loop
            else:
                break

            current_date += relativedelta(months=month_step)

        return periods


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
        alt_server: Optional[str] = None,
    ) -> Path:
        """Download an ftp file preserving filename and timestamps"""

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
        dim_key: Optional[str] = "time",
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


class OSUtil:
    """Helper class for OS related functions"""

    @staticmethod
    def get_local_file_info(file_path: Union[str, Path]) -> dict:
        """Get the size and modification time of a local file"""

        # get the status of the file
        stat = Path(file_path).stat()

        local_dt = datetime.datetime.fromtimestamp(stat.st_mtime)

        return {"datetime": local_dt, "size": stat.st_size}
