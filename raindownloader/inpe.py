"""
Module with specialized classes to understand the INPE FTP Structure
"""
import os

# from abc import ABC, abstractmethod

from dateutil import parser

from .utils import DateProcessor


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
