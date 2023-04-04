"""
The parser module defines the template of a Parser Class.
"""

# from abc import ABC, abstractmethod

import os
from pathlib import Path
from enum import Enum
from typing import Callable, Optional, Union, List
from dateutil import parser

from .utils import DateProcessor, DateFrequency, FTPUtil


class BaseParser:
    """Docstring"""

    def __init__(
        self,
        datatype: Union[Enum, str],
        root: str,
        fn_creator: Callable,
        fl_creator: Optional[Callable] = None,
        date_freq: DateFrequency = DateFrequency.DAILY,
    ):
        self.datatype = datatype
        self.root = Path(root).as_posix()
        self.fn_creator = fn_creator
        self.fl_creator = fl_creator
        self.date_freq = date_freq

    def download_file(
        self, date_str: str, local_folder: Union[Path, str], ftp: FTPUtil
    ) -> Path:
        """
        Download the parsed file to a local subfolder (according to the parser datatype).
        OBS: Download file always force the download. Otherwise, use the `get_file` function
        """

        # Download the file directly
        downloaded_file = ftp.download_ftp_file(
            remote_file=self.remote_target(date_str=date_str),
            local_folder=self.local_path(local_folder=local_folder),
        )

        return downloaded_file

    def filename(self, date_str: str) -> str:
        """Return just the filename given a date string"""
        # get the datetime
        date = parser.parse(date_str)

        return self.fn_creator(date)

    @property
    def subfolder(self) -> str:
        """Return the subfolder to place files based on the datatype"""
        if isinstance(self.datatype, Enum):
            return self.datatype.name
        else:
            return self.datatype

    def local_path(self, local_folder: Union[Path, str]) -> Path:
        """Create the local path based on the data type"""

        # create the local path (raises exception if local_folder does not exists)
        local_path = Path(local_folder) / self.subfolder

        local_path.mkdir(parents=False, exist_ok=True)
        return local_path

    def local_target(self, date_str: str, local_folder: Union[Path, str]) -> Path:
        """
        Local target is the full path of the local file, given a date_str
        """
        return self.local_path(local_folder) / self.filename(date_str)

    def remote_path(self, date_str: str) -> str:
        """Return just the base path given a date string"""
        # get the datetime
        date = parser.parse(date_str)

        if self.fl_creator:
            return os.path.join(self.root, self.fl_creator(date))
        else:
            return self.root

    def remote_target(self, date_str: str) -> str:
        """Target is composed by root / folder / filename"""
        return os.path.join(self.remote_path(date_str), self.filename(date_str))

    def dates_range(self, start_date: str, end_date: str) -> List[str]:
        """Return the dates range within the specified period"""
        return DateProcessor.dates_range(
            start_date=start_date, end_date=end_date, date_freq=self.date_freq
        )
