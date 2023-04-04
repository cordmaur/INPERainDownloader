"""
Module with specialized classes to understand the INPE FTP Structure
The idea is to have several classes that implement the following interface:
remote_file_path(date: str)

"""
import os

# from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Union

from datetime import datetime

import matplotlib.colors as colors

import xarray as xr

from .parser import BaseParser
from .utils import DateProcessor, DateFrequency, FTPUtil, GISUtil


class INPETypes(Enum):
    """Data types available from INPE"""

    DAILY_RAIN = "prec"
    MONTHLY_ACCUM_YEARLY = "pacum"
    DAILY_AVERAGE = "pmed"
    MONTHLY_ACCUM = "precacum"
    MONTHLY_ACCUM_MANUAL = "monthacum"


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

    @staticmethod
    def MERGE_MAY_filename(date: datetime) -> str:  # pylint: disable=invalid-name
        """
        Monthly Accumulated Yearly:
        Create the filename of the MERGE file, given a specific date
        """
        month_year = DateProcessor.month_abrev(date) + "_" + str(date.year)
        return f"MERGE_CPTEC_acum_{month_year}.nc"

    @staticmethod
    def MERGE_daily_average_filename(  # pylint: disable=invalid-name
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
        """Adjust variable names in the netCDF files and set CRS"""
        if "lon" in dset.dims:
            dset = dset.rename_dims({"lon": "longitude", "lat": "latitude"})
            dset = dset.rename_vars({"lon": "longitude", "lat": "latitude"})

        dset = dset.rio.write_crs("epsg:4326")

        return dset


class MonthAccumParser(BaseParser):
    """Docstring"""

    def __init__(
        self,
        datatype: Union[Enum, str],
        root: str,
        fn_creator: Callable,
        daily_parser: BaseParser,
        fl_creator: Optional[Callable] = None,
        date_freq: DateFrequency = DateFrequency.DAILY,
        ftp: Optional[FTPUtil] = None,
        avoid_update: bool = True,
    ):
        super().__init__(
            datatype=datatype,
            root=root,
            fn_creator=fn_creator,
            fl_creator=fl_creator,
            date_freq=date_freq,
            ftp=ftp,
            avoid_update=avoid_update,
        )

        self.daily_parser = daily_parser

    def download_file(self, date_str: str, local_folder: Union[str, Path]):
        """Actually this function performs as accum_monthly_rain"""
        # raise NotImplementedError(
        #     f"download_file not implemented for parser {self.datatype}"

        # accumulate the daily rain
        return self.accum_monthly_rain(
            date_str=date_str, local_folder=local_folder, force_download=True
        )

    def accum_monthly_rain(
        self, date_str: str, local_folder: Union[str, Path], force_download: bool
    ) -> Path:
        """Docstring"""

        # create a cube with the daily rain in the given month
        start_date, end_date = DateProcessor.start_end_dates(date=date_str)
        daily_files = self.daily_parser.get_range(
            start_date=start_date,
            end_date=end_date,
            local_folder=local_folder,
            force_download=force_download,
        )

        dset = GISUtil.create_cube(files=daily_files, dim_key="time")
        cube = INPE.grib2_post_proc(dset)
        accum = cube[INPETypes.DAILY_RAIN.value].sum(dim="time")
        accum = accum.rename(INPETypes.MONTHLY_ACCUM_MANUAL.value)

        # save the file to disk
        target_file = self.local_target(date_str=date_str, local_folder=local_folder)
        accum.to_dataset().to_netcdf(target_file)

        return target_file

        # return self.daily_parser.get_file(date_str=date_str, local_folder=local_folder)

    def get_file(
        self,
        date_str: str,
        local_folder: Union[str, Path],
        force_download: bool = False,
    ) -> Path:
        """
        Get a specific file. If it is not available locally, download it just in time.
        If it is available locally and avoid_update is not True, check if the file has
        changed in the server
        """

        local_target = self.local_target(date_str=date_str, local_folder=local_folder)
        if force_download or not local_target.exists():
            return self.accum_monthly_rain(
                date_str=date_str,
                local_folder=local_folder,
                force_download=force_download,
            )

        else:

            return local_target


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
        datatype=INPETypes.MONTHLY_ACCUM,
        root="/modelos/tempo/MERGE/GPM/CLIMATOLOGY/MONTHLY_ACCUMULATED/",
        fn_creator=INPE.MERGE_MA_filename,
        date_freq=DateFrequency.MONTHLY,
    )

    month_accum_manual = MonthAccumParser(
        datatype=INPETypes.MONTHLY_ACCUM_MANUAL,
        root="",
        fn_creator=INPE.MERGE_MAY_filename,
        date_freq=DateFrequency.MONTHLY,
        daily_parser=daily_rain_parser,
    )

    parsers = [
        daily_rain_parser,
        monthly_accum_yearly,
        daily_average,
        monthly_accum,
        month_accum_manual,
    ]
    post_processors = {".grib2": INPE.grib2_post_proc, ".nc": INPE.nc_post_proc}
