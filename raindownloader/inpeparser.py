"""
Module with specialized classes to understand the INPE FTP Structure
The idea is to have several classes that implement the following interface:
remote_file_path(date: str)

"""
import os

# from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union
from enum import Enum, auto

from dateutil import parser
import xarray as xr


from .utils import DateProcessor
from .parser import BaseParser, DateFrequency


class INPETypes(Enum):
    """Data types available from INPE"""

    DAILY_RAIN = auto()
    MONTHLY_ACCUM_YEARLY = auto()


class INPE:
    """Create the structure, given a root path (remote or local) and date/time of the file"""

    FTPurl = "ftp.cptec.inpe.br"
    DailyMERGEroot = "/modelos/tempo/MERGE/GPM/DAILY"

    def __init__(self, root_path: str) -> None:
        self.root = os.path.normpath(root_path)

    @staticmethod
    def MERGE_structure(date_str: str) -> str:  # pylint: disable=invalid-name
        """Given a date that can be parsed by dateutil, create the structure of the MERGE files"""
        date = parser.parse(date_str)
        year = str(date.year)
        month = str(date.month).zfill(2)
        return "/".join([year, month])

    @staticmethod
    def MERGE_filename(date_str: str) -> str:  # pylint: disable=invalid-name
        """Create the filename of the MERGE file, given a specific date"""
        date = DateProcessor.normalize_date(date_str)
        filename = f"MERGE_CPTEC_{date}.grib2"
        return filename

    @staticmethod
    def parse_MERGE_filename(
        filename: Union[str, Path]
    ):  # pylint: disable=invalid-name
        """
        Given filename (or full path) in the MERGE/INPE format,
        return a dictionary with the date
        """

        # convert to Path
        file = Path(filename)

        # get the name
        name = file.stem

        date_str = name.split("_")[-1]

        return {"date": parser.parse(date_str)}

    @staticmethod
    def MERGE_MAY_filename(date_str: str) -> str:  # pylint: disable=invalid-name
        """
        Monthly Accumulated Yearly:
        Create the filename of the MERGE file, given a specific date
        """
        # get the datetime
        date = parser.parse(date_str)

        base_name = "MERGE_CPTEC_acum_"
        suffix = ".nc"
        month_year = DateProcessor.month_abrev(date) + "_" + str(date.year)
        return base_name + month_year + suffix

    @staticmethod
    def grib2_post_proc(dset: xr.Dataset) -> xr.Dataset:
        """Adjust the longitude in INPE's grib2 files and sets the CRS"""

        dset = dset.assign_coords({"longitude": dset.longitude - 360})
        dset = dset.rio.write_crs("epsg:4326")
        return dset

    @staticmethod
    def nc_post_proc(dset: xr.Dataset) -> xr.Dataset:
        """Adjust variable names in the netCDF files and set"""

        dset = dset.rename_dims({"lon": "longitude", "lat": "latitude"})
        dset = dset.rename_vars({"lon": "longitude", "lat": "latitude"})
        dset = dset.rio.write_crs("epsg:4326")

        return dset


class INPEParsers:
    """Just a structure to store the parsers for the INPE FTP"""

    daily_rain_parser = BaseParser(
        datatype=INPETypes.DAILY_RAIN,
        root="/modelos/tempo/MERGE/GPM/DAILY/",
        fn_creator=INPE.MERGE_filename,
        fl_creator=INPE.MERGE_structure,
    )

    monthly_accum_yearly = BaseParser(
        datatype=INPETypes.MONTHLY_ACCUM_YEARLY,
        root="modelos/tempo/MERGE/GPM/CLIMATOLOGY/MONTHLY_ACCUMULATED_YEARLY/",
        fn_creator=INPE.MERGE_MAY_filename,
        date_freq=DateFrequency.MONTHLY,
    )

    parsers = [daily_rain_parser, monthly_accum_yearly]
    post_processors = {".grib2": INPE.grib2_post_proc, ".nc": INPE.nc_post_proc}
