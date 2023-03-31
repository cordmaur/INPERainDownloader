"""
Module with specialized classes to understand the INPE FTP Structure
The idea is to have several classes that implement the following interface:
remote_file_path(date: str)

"""
import os

# from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime

import matplotlib.colors as colors

import xarray as xr

from .utils import DateProcessor
from .parser import BaseParser, DateFrequency


class INPETypes(Enum):
    """Data types available from INPE"""

    DAILY_RAIN = "prec"
    MONTHLY_ACCUM_YEARLY = "pacum"
    DAILY_AVERAGE = "pmed"
    MONTHLY_ACUM = "precacum"


class INPE:
    """Create the structure, given a root path (remote or local) and date/time of the file"""

    FTPurl = "ftp.cptec.inpe.br"
    DailyMERGEroot = "/modelos/tempo/MERGE/GPM/DAILY"

    # Define the colors and positions of the color stops
    cmap_colors = [(1.0, 1.0, 1.0), (1, 1, 1.0), (0.5, 0.5, 1.0), (1.0, 0.4, 0.6)]
    positions = [0.0, 0.1, 0.7, 1.0]

    # Create the colormap using LinearSegmentedColormap
    cmap = colors.LinearSegmentedColormap.from_list(
        "my_colormap", list(zip(positions, cmap_colors))
    )

    def __init__(self, root_path: str) -> None:
        self.root = os.path.normpath(root_path)

    @staticmethod
    def MERGE_structure(date: datetime) -> str:  # pylint: disable=invalid-name
        """Given a date that can be parsed by dateutil, create the structure of the MERGE files"""
        year = str(date.year)
        month = str(date.month).zfill(2)
        return "/".join([year, month])

    @staticmethod
    def MERGE_filename(date: datetime) -> str:  # pylint: disable=invalid-name
        """Create the filename of the MERGE file, given a specific date"""
        date_str = DateProcessor.normalize_date(date)
        return f"MERGE_CPTEC_{date_str}.grib2"

    # @staticmethod
    # def parse_MERGE_filename(
    #     filename: Union[str, Path]
    # ):  # pylint: disable=invalid-name
    #     """
    #     Given filename (or full path) in the MERGE/INPE format,
    #     return a dictionary with the date
    #     """

    #     # convert to Path
    #     file = Path(filename)

    #     # get the name
    #     name = file.stem

    #     date_str = name.split("_")[-1]

    #     return {"date": parser.parse(date_str)}

    @staticmethod
    def MERGE_MAY_filename(date: datetime) -> str:  # pylint: disable=invalid-name
        """
        Monthly Accumulated Yearly:
        Create the filename of the MERGE file, given a specific date
        """
        month_year = DateProcessor.month_abrev(date) + "_" + str(date.year)
        return f"MERGE_CPTEC_acum_{month_year}.nc"

    @staticmethod
    def MERGE_daily_average_filename(
        date: datetime,
    ) -> str:  # pylint: disable=invalid-name
        """
        Daily Average
        Create the filename of the MERGE file, given a specific date
        """
        day_month = f"{date.day:02d}{DateProcessor.month_abrev(date)}"
        return f"MERGE_CPTEC_12Z{day_month}.nc"

    @staticmethod
    def MERGE_MA_filename(date: datetime):  # pylint: disable=invalid-name
        """
        Monthly Accumulated - Create the filename fot the Monthly Accumulated files from MERGE/INPE
        E.g.: MERGE_CPTEC_acum_sep.nc
        """
        month_abrev = DateProcessor.month_abrev(date)
        return f"MERGE_CPTEC_acum_{month_abrev}.nc"

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

    daily_average = BaseParser(
        datatype=INPETypes.DAILY_AVERAGE,
        root="/modelos/tempo/MERGE/GPM/CLIMATOLOGY/DAILY_AVERAGE",
        fn_creator=INPE.MERGE_daily_average_filename,
        date_freq=DateFrequency.DAILY,
    )

    monthly_accum = BaseParser(
        datatype=INPETypes.MONTHLY_ACUM,
        root="/modelos/tempo/MERGE/GPM/CLIMATOLOGY/MONTHLY_ACCUMULATED/",
        fn_creator=INPE.MERGE_MA_filename,
        date_freq=DateFrequency.MONTHLY,
    )

    parsers = [daily_rain_parser, monthly_accum_yearly, daily_average, monthly_accum]
    post_processors = {".grib2": INPE.grib2_post_proc, ".nc": INPE.nc_post_proc}
