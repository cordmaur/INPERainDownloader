# download 1 arquivo por data/dia/etc.
# download um range de datas
# download última chuva
# download ulitmos X dias

import ftplib
import os
from pathlib import Path
from typing import Union, List, Optional

# from abc import ABC, abstractmethod
from datetime import timedelta, datetime

from dateutil import parser
import pytz


class FTPUtil:
    """FTP helper class to download file preserving timestamp and get file info, among others"""

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
        s = f"FTP {'' if self.is_connected else 'Not '}connected to server {self.ftp.host}"
        return s


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
    def dates_range(start_date: str, end_date: str) -> List[str]:
        """Spawn a dates list in normalized format in the desired range"""

        initial_date = parser.parse(start_date)
        final_date = parser.parse(end_date)

        dates = []
        while initial_date <= final_date:
            dates.append(initial_date.strftime("%Y%m%d"))
            initial_date += timedelta(days=1)

        return dates


class INPE:
    """Create the structure, given a root path (remote or local) and date/time of the file"""

    def __init__(self, root_path: str) -> None:
        self.root = os.path.normpath(root_path)

    @staticmethod
    def MERGE_structure(date_str: str) -> str:  # pylint: disable=invalid-name
        """Docstring"""
        date = parser.parse(date_str)
        year = str(date.year)
        month = str(date.month).zfill(2)
        return "/".join([year, month])

    @staticmethod
    def MERGE_filename(date_str: str) -> str:  # pylint: disable=invalid-name
        """Docstring"""
        date = DateProcessor.normalize_date(date_str)
        filename = f"MERGE_CPTEC_{date}.grib2"
        return filename


class INPEDownloader:
    """Docstring"""

    def __init__(
        self,
        server: str,
        root: str,
        filename_fn=INPE.MERGE_filename,
        structure_fn=INPE.MERGE_structure,
    ) -> None:

        self.ftp = FTPUtil(server)
        self.root = os.path.normpath(root)
        self.filename_fn = filename_fn
        self.structure_fn = structure_fn

    def files_equal(self, date_str: str, local_folder: Union[str, Path]) -> bool:
        """Compare remote and local files and return if they are equal"""
        remote_file = self.remote_file_path(date_str)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        local_file = self.local_file_path(date_str, local_folder)
        local_info = OSUtil.get_local_file_info(local_file)

        # first, check the names
        if os.path.basename(remote_file) != os.path.basename(local_file):
            return False

        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)
        local_info = OSUtil.get_local_file_info(local_file)

        return (remote_info["size"] == local_info["size"]) and (
            remote_info["datetime"] == local_info["datetime"]
        )

    def compare_files(self, date_str: str, local_folder: Union[str, Path]) -> None:
        """Compare remote and local files visually"""
        remote_file = self.remote_file_path(date_str)
        remote_info = self.ftp.get_ftp_file_info(remote_file=remote_file)

        local_file = self.local_file_path(date_str, local_folder)
        local_info = OSUtil.get_local_file_info(local_file)
        print(remote_info)
        print(local_info)

    def remote_file_path(self, date_str: str) -> str:
        """Docstring"""
        filename = self.filename_fn(date_str)
        folder = self.structure_fn(date_str)

        return "/".join([self.root, folder, filename])

    def local_file_path(self, date_str: str, local_folder: Union[str, Path]) -> Path:
        """Docstring"""
        filename = self.filename_fn(date_str)
        return Path(local_folder) / filename

    def files_range(self, start_date_str: str, end_date_str: str) -> List[str]:
        """Docstring"""
        dates = DateProcessor.dates_range(
            start_date=start_date_str, end_date=end_date_str
        )
        return [self.remote_file_path(date) for date in dates]

    def download_file(self, date_str: str, local_folder: Union[str, Path]) -> Path:
        """
        Download a file from the FTP server to the a local folder. The filename and ftp location
        folder filename will be obtained from the functions filename_fn and structure_fn
        respectively.

        The return will be the local path for the file. If file already exists, it will not be
        downloaded again, unless it has been updated on the server.
        """
        # get the file locations
        remote_file = self.remote_file_path(date_str)
        local_file = self.local_file_path(date_str, local_folder)

        # check if file exists
        if local_file.exists():
            # check if they are the same
            if self.files_equal(date_str, local_file.parent):
                print(f"file {local_file} already exists.")
            else:
                print(f"Local file {local_file} is outdated. Downloading it.")
                self.ftp.download_ftp_file(remote_file, local_file.parent)
        else:
            self.ftp.download_ftp_file(remote_file, local_file.parent)

        return local_file

    def download_files(
        self, dates: List[str], local_folder: Union[str, Path]
    ) -> List[Path]:
        """
        Download files from a list of dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """
        files = []
        for date in dates:
            try:
                files.append(
                    self.download_file(date_str=date, local_folder=local_folder)
                )

            except Exception as error:  # pylint:disable=broad-except
                files.append(f"Error {date}:  {error}")

        return files

    def download_range(
        self, start_date: str, end_date: str, local_folder: Union[str, Path]
    ) -> List[Path]:
        """
        Download a range of files from start to end dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """

        dates = DateProcessor.dates_range(start_date, end_date)
        return self.download_files(dates=dates, local_folder=local_folder)

    def download_recent(
        self, local_folder: Union[str, Path], num: int = 1
    ) -> List[Path]:
        """
        Download the recent x files, where x is the number of files to download.
        """
        now = datetime.now()

        # testing what happens if today's not present yet
        now = now + timedelta(days=1)

        first_str = DateProcessor.normalize_date(now - timedelta(days=num - 1))
        now_str = DateProcessor.normalize_date(now)

        return self.download_range(
            start_date=first_str, end_date=now_str, local_folder=local_folder
        )

    def remote_file_exists(self, date_str: str) -> bool:
        """Docstring"""

        remote_path = self.remote_file_path(date_str)
        try:
            self.ftp.ftp.size(remote_path)

        except ftplib.error_perm as error:
            if str(error).startswith("550"):
                print("File does not exists")
            else:
                print(f"Error checking file existence: {error}")
            return False

        return True
