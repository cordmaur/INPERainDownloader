"""This module has the functions for the Command Line Interface"""

import argparse
from configparser import ConfigParser
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import geopandas as gpd
import xarray as xr

from raindownloader.inpeparser import INPEParsers, INPETypes
from raindownloader.downloader import Downloader
from raindownloader.utils import DateProcessor


def reset(_):
    """Clear default configuration"""
    file = config_file()

    if file.exists():
        print(f"Deleting file {file}")
        file.unlink()

    else:
        print("No default config to reset")


def init(args):
    """Initialize the package"""
    print("Initializing...")

    # setup the folder
    folder = args.folder.absolute()
    folder.mkdir(parents=False, exist_ok=True)
    print(f"Setting downloading folder to '{folder}'")

    config = ConfigParser()
    config["DEFAULT"] = {"url": args.url, "folder": folder.as_posix()}

    with open(config_file(), "w", encoding="utf-8") as configfile:
        config.write(configfile)


def config_file() -> Path:
    """Returns the configuration file path"""
    return Path(__file__).with_name("config.ini")


def open_config() -> ConfigParser:
    """Return the configuration"""
    file = config_file()
    if not file.exists():
        raise FileNotFoundError((f"Config file '{file}' not found"))

    config = ConfigParser()
    config.read(config_file())

    return config


def validate_config(config: ConfigParser):
    """Validate the configuration"""
    validated = False
    try:
        config = open_config()

        _ = config["DEFAULT"]["url"]
        folder = Path(config["DEFAULT"]["folder"])

        if not folder.exists():
            raise FileNotFoundError(f"Folder specified in config '{folder}' not found")

        validated = True

    except KeyError as error:
        print(f"Invalid configuration, missing key: {error}")

    except FileNotFoundError as error:
        print(error)

    finally:
        if not validated:
            print("Config file not initialized correctly.")
            print("Please run 'merge-downloader init' first.")

    return validated


def create_downloader() -> Downloader:
    """Create a Downloader instance"""

    config = open_config()
    validate_config(config)

    downloader = Downloader(
        server=config["DEFAULT"]["url"],
        parsers=INPEParsers.parsers,
        local_folder=config["DEFAULT"]["folder"],
    )

    return downloader


def series(args):
    """Download a series"""
    dates = list(map(DateProcessor.pretty_date, args.dates))
    print(f"Downloading {args.type} series for range: {dates}")

    # first, create the cube
    downloader = create_downloader()
    cube = downloader.create_cube(
        start_date=args.dates[0],
        end_date=args.dates[1],
        datatype=args.type,
    )

    if not args.shp:
        print("No shapefile provided. Evaluating rain for whole region (South America)")
        series_xr = cube.mean(dim=["latitude", "longitude"])
        series_pd = series_xr.to_series()
    else:
        shp = gpd.read_file(args.shp)

        print(f"Cutting raster to: {args.shp}")

        series_pd = downloader.get_time_series(
            cube=cube, shp=shp, reducer=xr.DataArray.mean
        )

        # create a thumbnail
        fig, axes = plt.subplots(figsize=(10, 10))
        cube_accum = cube.sum(dim="time")
        cutted = cube_accum.rio.clip(shp.geometry)
        cutted.plot(ax=axes)
        shp.plot(ax=axes, facecolor="none", edgecolor="brown")
        fig.savefig(args.file.with_suffix(".map.png"))
        print(f"Map exported to: {args.file.with_suffix('.map.png')}")

    # save to file
    series_pd.to_csv(args.file.with_suffix(".csv"))
    print(f"Series exported to: {args.file.with_suffix('.csv')}")

    # plot a graph
    fig, axes = plt.subplots()
    axes.bar(x=series_pd.index.strftime("%d-%m-%Y"), height=series_pd.values)  # type: ignore
    # series_pd.plot(axes=axes, kind="bar")
    labels = axes.get_xticklabels()
    axes.set_xticklabels(labels, rotation=90)
    axes.set_ylabel("Precipitaion (mm)")
    fig.subplots_adjust(bottom=0.3)
    fig.savefig(args.file.with_suffix(".graph.png"))
    print(f"Graph exported to: {args.file.with_suffix('.graph.png')}")


def download(args):
    """Download merge/climatologic files"""

    dates = list(map(DateProcessor.pretty_date, args.dates))
    print(f"Downloading {args.type} series for range: {dates}")

    downloader = create_downloader()

    files = downloader.get_range(
        start_date=args.dates[0],
        end_date=args.dates[1],
        datatype=args.type,
    )

    print("The following files are available:")
    for file in files:
        print(file)


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(description="Merge Downloader")

    ### Define subparsers
    subparsers = parser.add_subparsers()

    #### Create parent parser with DEFAULT args
    default_args = argparse.ArgumentParser(add_help=False)
    default_args.add_argument(
        "-d",
        "--dates",
        nargs=2,
        type=DateProcessor.parse_date,
        help="Date range 'start_date end_date'. "
        "Dates can be specified any format that can be parsed e.g.: yyyymmdd, yyyy-mm, etc.",
    )
    default_args.add_argument(
        "-t",
        "--type",
        required=True,
        type=INPETypes.from_name,
        help=f"Data type to download. It can be any of: {INPETypes.types()}",
    )
    # ------------------------------------------

    #### Define the RESET subcommand ####
    parser_init = subparsers.add_parser(
        "reset",
        help="Reset default configuration",
        description="The default configuration is saved to 'config.ini' file within"
        " the package's folder.",
    )
    parser_init.set_defaults(func=reset)
    # ------------------------------------------

    #### Define the INIT subcommand ####
    parser_init = subparsers.add_parser(
        "init",
        help="Initialize the environment",
        description="The init command is used to set the FTP URL to pull the data from and the "
        " local download directory.",
    )
    parser_init.add_argument(
        "-f",
        "--folder",
        help="Local folder to download the files (relative path).",
        required=True,
        type=Path,
    )
    parser_init.add_argument(
        "-url",
        help=f"FTP URL of the server. Defaults to '{INPEParsers.FTPurl}'",
        default=INPEParsers.FTPurl,
    )
    parser_init.set_defaults(func=init)
    # ------------------------------------------

    #### Define the SERIES subcommand ####
    parser_series = subparsers.add_parser(
        "series",
        help="Calculate the rain and create a time-series for the specified period.",
        description="If a shapefile is provided the rain is evaluated within the polygons."
        " It averages the rain spatially in the region.",
        parents=[default_args],
    )
    parser_series.add_argument(
        "-s",
        "--shp",
        help="Shapefile with polygon to cut the raster. If not specified, averages for "
        "the whole region (South America)",
        type=Path,
    )
    parser_series.add_argument(
        "-f",
        "--file",
        required=True,
        help="Specifies the .csv file to save the series to",
        type=Path,
    )
    parser_series.set_defaults(func=series)
    # ------------------------------------------

    #### Define the DOWNLOAD subcommand ####
    parser_download = subparsers.add_parser(
        "download",
        help="Download raster data",
        description="The raster data is downloaded in the original format (i.e., .nc or .grib2)",
        parents=[default_args],
    )
    parser_download.set_defaults(func=download)
    # ------------------------------------------

    # Parse the arguments
    args = parser.parse_args()

    # Call the appropriate function
    # The 'func' attribute contains a reference to the function to be called
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


# if __name__ == "__main__":
#     main()
