"""
Module with specialized classes to understand the INPE FTP Structure
The idea is to have several classes that implement the following interface:
remote_file_path(date: str)

"""
import os

# from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional, Union

from datetime import datetime
from dateutil import parser
from dateutil.relativedelta import relativedelta

import matplotlib.colors as colors

import xarray as xr

from .parser import BaseParser
from .utils import DateProcessor, DateFrequency, FTPUtil, GISUtil


class INPETypes(Enum):
    """Data types available from INPE"""

    DAILY_RAIN = {"id": auto(), "var": "prec"}
    MONTHLY_ACCUM_YEARLY = {"id": auto(), "var": "pacum"}
    DAILY_AVERAGE = {"id": auto(), "var": "pmed"}
    MONTHLY_ACCUM = {"id": auto(), "var": "precacum"}
    MONTHLY_ACCUM_MANUAL = {"id": auto(), "var": "monthacum"}
    YEARLY_ACCUM = {"id": auto(), "var": "pacum"}


class INPE:
    """Create the structure, given a root path (remote or local) and date/time of the file"""

    # DailyMERGEroot = "/modelos/tempo/MERGE/GPM/DAILY"

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
    def MERGE_DA_filename(date: datetime) -> str:  # pylint: disable=invalid-name
        """
        Daily Average
        Create the filename of the MERGE file, given a specific date
        """
        day_month = f"{date.day:02d}{DateProcessor.month_abrev(date)}"
        return f"MERGE_CPTEC_12Z{day_month}.nc"

    @staticmethod
    def MERGE_MA_filename(date: datetime) -> str:  # pylint: disable=invalid-name
        """
        Monthly Accumulated - Create the filename fot the Monthly Accumulated files from MERGE/INPE
        E.g.: MERGE_CPTEC_acum_sep.nc
        """
        month_abrev = DateProcessor.month_abrev(date)
        return f"MERGE_CPTEC_acum_{month_abrev}.nc"

    @staticmethod
    def MERGE_YA_filename(date: datetime) -> str:  # pylint: disable=invalid-name
        """
        Yearly Accumulated - Create the filename fot the Yearly Accumulated files from MERGE/INPE
            E.g.: MERGE_CPTEC_acum_2003.nc
        """
        return f"MERGE_CPTEC_acum_{date.year}.nc"

    @staticmethod
    def yearly_post_proc(dset: xr.Dataset, date_str, **kwargs) -> xr.Dataset:
        """Adjust the time for the dataset"""
        date = DateProcessor.parse_date(date_str)

        # fix month and day as 1
        date = date + relativedelta(day=1, month=1)

        return dset.assign_coords({"time": [date]})

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

    def download_file(self, date: Union[str, datetime], local_folder: Union[str, Path]):
        """Actually this function performs as accum_monthly_rain"""
        # accumulate the daily rain
        return self.accum_monthly_rain(
            date=date, local_folder=local_folder, force_download=True
        )

    def accum_monthly_rain(
        self,
        date: Union[str, datetime],
        local_folder: Union[str, Path],
        force_download: bool,
    ) -> Path:
        """Docstring"""

        # create a cube with the daily rain in the given month
        start_date, end_date = DateProcessor.start_end_dates(date=date)

        # here, we will check for the current month
        now = datetime.now()
        today = datetime(now.year, now.month, now.day)

        if DateProcessor.parse_date(end_date) >= today:
            # if the end date is future, it meansn we are trying to get the current month
            # in this case, let's start going backwards to see the last available file in the FTP
            for day in range(today.day, 0, -1):
                end_date = today + relativedelta(day=day)
                remote_file = self.daily_parser.remote_target(
                    DateProcessor.normalize_date(end_date)
                )

                # if the file exists, then we have our end date
                if self.ftp.file_exists(remote_file):
                    break

                # otherwise, raise exception if we reached the first day
                if day == 1:
                    raise Exception(f"No avilable file to calculate month {date}")

        end_date = DateProcessor.normalize_date(end_date)

        daily_files = self.daily_parser.get_range(
            start_date=start_date,
            end_date=end_date,
            local_folder=local_folder,
            force_download=force_download,
        )

        dset = GISUtil.create_cube(files=daily_files, dim_key="time")
        cube = INPE.grib2_post_proc(dset)

        # get the reference datetime
        ref_time = cube.time[0].values

        accum = cube[INPETypes.DAILY_RAIN.value["var"]].sum(dim="time")
        accum = accum.rename(INPETypes.MONTHLY_ACCUM_MANUAL.value["var"])

        # once the reduction is being done in the time dimension, create a new dimension for time
        accum = accum.assign_coords({"time": ref_time}).expand_dims(dim="time")

        # save the file to disk
        target_file = self.local_target(date=date, local_folder=local_folder)
        accum.to_dataset().to_netcdf(target_file)

        return target_file

    def get_file(
        self,
        date: Union[str, datetime],
        local_folder: Union[str, Path],
        force_download: bool = False,
    ) -> Path:
        """
        Get a specific file. If it is not available locally, download it just in time.
        If it is available locally and avoid_update is not True, check if the file has
        changed in the server
        """

        local_target = self.local_target(date=date, local_folder=local_folder)

        # we will force the accum_monthly rain if the month is the current month
        date = DateProcessor.parse_date(date) + relativedelta(day=1)

        now = datetime.now() + relativedelta(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # check if we are in the same month... if that's the case, force the parsers to check if the files
        # were updated in the server
        if now == date or force_download or not local_target.exists():
            # store the old avoid update status
            avoid_update = self.daily_parser.avoid_update
            self.daily_parser.avoid_update = True  # False

            file = self.accum_monthly_rain(
                date=date,
                local_folder=local_folder,
                force_download=force_download,
            )

            # retrieve the avoid_update status
            self.daily_parser.avoid_update = avoid_update

            return file

        else:
            return local_target


class INPEParsers:
    """Just a structure to store the parsers for the INPE FTP"""

    FTPurl = "ftp.cptec.inpe.br"

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
        fn_creator=INPE.MERGE_DA_filename,
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

    year_accum = BaseParser(
        datatype=INPETypes.YEARLY_ACCUM,
        root="/modelos/tempo/MERGE/GPM/CLIMATOLOGY/YEAR_ACCUMULATED",
        fn_creator=INPE.MERGE_YA_filename,
        date_freq=DateFrequency.YEARLY,
        post_proc=INPE.yearly_post_proc,
    )

    parsers = [
        daily_rain_parser,
        monthly_accum_yearly,
        daily_average,
        monthly_accum,
        month_accum_manual,
        year_accum,
    ]

    post_processors = {".grib2": INPE.grib2_post_proc, ".nc": INPE.nc_post_proc}
