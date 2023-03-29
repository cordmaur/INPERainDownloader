"""
Main module for the reporter class
"""
import io
from enum import Enum
from pathlib import Path
from typing import Union, Iterable, Optional, List

from PIL import Image

import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.dates as mdates

import pandas as pd
import geopandas as gpd
import contextily as cx
import rasterio as rio
import xarray as xr
from shapely import Geometry
from pyproj import Geod

from raindownloader.inpedownloader import Downloader
from raindownloader.inpeparser import INPETypes
from raindownloader.utils import GISUtil, DateProcessor
from raindownloader.parser import BaseParser


class RainReporter:
    """Docstring"""

    def __init__(
        self, server: str, download_folder: Union[Path, str], parsers: List[BaseParser]
    ):
        self.downloader = Downloader(server=server, parsers=parsers)

        self.download_folder = Path(download_folder)

    @staticmethod
    def write_tabular_info(plt_ax: plt.Axes, stats: dict):
        """Prepare the tabular section of the report"""

        plt_ax.axis("off")

        start_date = DateProcessor.pretty_date(stats["start_date"])
        end_date = DateProcessor.pretty_date(stats["end_date"])

        title_str = f"Período: de {start_date} até {end_date}"
        plt_ax.text(0.04, 0.97, title_str, fontsize=12)

        area_str = f"Área  total: {stats['area (kmˆ2)']:.2f} km²"
        plt_ax.text(0, 0.90, area_str)

        rain_str = f"Chuva acumulada média na bacia: {stats['height (mm)']:.0f} mm"
        plt_ax.text(0, 0.85, rain_str)

        volume_str = f"Volume de chuva na bacia: {stats['volume (kmˆ3)']:.0f} km³"
        plt_ax.text(0, 0.80, volume_str)

    @staticmethod
    def create_report_layout() -> tuple:
        """Create the layout and return figure and axes as a list"""
        fig = plt.figure(constrained_layout=True, figsize=(10, 10))

        gridspec = fig.add_gridspec(2, 3, height_ratios=[1.2, 1])
        text_ax = fig.add_subplot(gridspec[0, 0])
        raster_ax = fig.add_subplot(gridspec[0, 1:])
        chart_ax = fig.add_subplot(gridspec[1, :])

        return fig, [text_ax, raster_ax, chart_ax]

    @staticmethod
    def plot_daily_rain(plt_ax: plt.Axes, cube: xr.DataArray, shp: gpd.GeoDataFrame):
        """Create the plot with the daily rain in the period"""

        area = cube.rio.clip(shp.geometry)
        daily_rain = area.mean(dim=["longitude", "latitude"])
        plt_ax.bar(x=daily_rain.time, height=daily_rain.variable.squeeze())

        # format the x-axis labels
        date_format = mdates.DateFormatter("%d/%m")
        plt_ax.xaxis.set_major_formatter(date_format)
        plt.xticks(rotation=60, ha="right")

        # get the years
        dates = cube.time.to_series()
        plt_ax.set_xlabel(f"Chuva média na bacia - Ano: {list(dates.dt.year.unique())}")

        plt_ax.set_ylabel("Chuva média na bacia (mm)")
        plt_ax.set_title("Chuva Diária Média na Bacia")

    @staticmethod
    def create_colorbar(
        raster: xr.DataArray,
        plt_ax: plt.Axes,
        label: str,
        labelsize: int = 12,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ):
        """Add a colorbar to the given axes based on the values of the raster"""

        # First, set the minimum and maximum limits
        vmin = float(raster.min()) if vmin is None else vmin
        vmax = float(raster.max()) * 0.8 if vmax is None else vmax

        # Create a colorbar object with the desired range of values
        norm = colors.Normalize(vmin=vmin, vmax=vmax)
        cbar = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="viridis"), ax=plt_ax)  # type: ignore[attr]

        # Customize the colorbar
        cbar.set_label(label)
        cbar.ax.tick_params(labelsize=labelsize)

        return cbar

    @staticmethod
    def plot_raster_shape(
        raster: xr.DataArray,
        shape: gpd.GeoDataFrame,
        plt_ax: plt.Axes,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ):
        """
        Given a time period and a shapefile (loaded in geopandas),
        plot the raster within the shape.
        """

        shape.plot(
            ax=plt_ax, figsize=(5, 5), alpha=0.7, facecolor="none", edgecolor="white"
        )

        # to use contextily, we will write the raster to a MemoryFile
        # so we don't need to write it to disk and reload it
        # first we will clip the area and create a profile
        xmin, xmax, ymin, ymax = plt_ax.axis()
        subraster = raster.sel(longitude=slice(xmin, xmax), latitude=slice(ymin, ymax))

        subraster = subraster.expand_dims(dim="band")

        profile = GISUtil.profile_from_xarray(subraster)

        # create a memory file and use it to create a memory dataset
        with rio.MemoryFile() as memfile:
            with memfile.open(**profile) as memdset:

                # write the data to the newly created dataset
                memdset.write(subraster)

            # now, let's create a colorbar for this
            cbar = RainReporter.create_colorbar(
                raster=subraster,
                plt_ax=plt_ax,
                label="Chuva acumulada (mm)",
                labelsize=10,
                vmin=vmin,
                vmax=vmax,
            )

            # with the dataset in memory, add the basemap
            cx.add_basemap(
                plt_ax,
                source=memfile,
                vmin=cbar.vmin,
                vmax=cbar.vmax,
                reset_extent=False,
            )  # , vmin=0, vmax=100)

        # set the axis labels
        plt_ax.set_ylabel("Latitude (deg)")
        plt_ax.set_xlabel("Longitude (deg)")
        return plt_ax

    @staticmethod
    def calc_geodesic_area(geom: Geometry) -> float:
        """Calculate the geodesic area given a shapely Geometry"""
        # specify a named ellipsoid
        geod = Geod(ellps="WGS84")
        return abs(geod.geometry_area_perimeter(geom)[0]) / 1e6

    def get_cube(self, start_date: str, end_date: str, datatype: Union[Enum, str]):
        """Get the accumulated rain in a given period"""

        # download the files
        files = self.downloader.download_range(
            start_date=start_date,
            end_date=end_date,
            datatype=datatype,
            local_folder=self.download_folder,
            # file_type=FileType.GEOTIFF,
        )

        # create a cube
        cube = Downloader.create_cube(
            files=files,
            # name_parser=INPE.parse_MERGE_filename,
            dim_key="time",
            # squeeze_dims=None
            # squeeze_dims="band",
        )

        return cube

    @staticmethod
    def rain_in_geoms(rain: xr.DataArray, geometries: Iterable[Geometry]):
        """
        Calculate the rain inside the given geometries and returns a dictionary.
        The geometries are shapely.Geometry type and it can be a GeoSeries from Pandas
        """

        # Let's use clip to ignore data outide the geometry
        clipped = rain.rio.clip(geometries)

        # calculate the mean height in mm
        height = float(clipped.mean())

        # calculate the area in km^2
        areas = pd.Series(map(RainReporter.calc_geodesic_area, geometries))
        area = areas.sum()

        # multiply by area of geometries to get total volume em km^3
        volume = area * (height / 1e6)

        results = {"volume (kmˆ3)": volume, "area (kmˆ2)": area, "height (mm)": height}
        return results

    def rain_report(
        self,
        start_date: str,
        end_date: str,
        shapefile: Union[str, Path],
    ):
        """
        Create a rain report for the given period and shapefile (can have multiple features)
        """

        # first, let's grab the accumulated rain in the period
        cube = self.get_cube(
            start_date=start_date, end_date=end_date, datatype=INPETypes.DAILY_RAIN
        )["prec"]

        # accumulate the rain in the time axis
        rain = cube.sum(dim="time")

        # then, open the shapefile
        shp = gpd.read_file(shapefile)

        # check if there is something in the shapefile
        if len(shp) == 0:
            raise ValueError("No elements in the input shapefile")

        if len(shp) > 1:
            print(f"{len(shp)} featuers found in shapefile, selecting all of them.")

        # convert the shapefile to the raster CRS (more cost effective)
        shp.to_crs(rain.rio.crs, inplace=True)

        ### Create the layout for the report using Matplotlib Gridspec
        fig, rep_axs = RainReporter.create_report_layout()
        fig.suptitle(Path(shapefile).stem, fontsize=16)

        ### Plot the map with the rain
        self.plot_raster_shape(raster=rain, shape=shp, plt_ax=rep_axs[1])

        ### write the tabular text of the report
        rain_stats = self.rain_in_geoms(rain, shp.geometry)
        rain_stats.update({"start_date": start_date, "end_date": end_date})
        RainReporter.write_tabular_info(plt_ax=rep_axs[0], stats=rain_stats)

        ### Plot the daily rain graph
        RainReporter.plot_daily_rain(plt_ax=rep_axs[2], cube=cube, shp=shp)

        return fig, rain, shp, cube

    def animate_rain(
        self,
        start_date: str,
        end_date: str,
        shapefile: Union[str, Path],
        file_name: Union[Path, str],
    ):
        """Save an animated gif to the informed folder"""
        # first, let's grab the accumulated rain in the period
        cube = self.get_cube(
            start_date=start_date,
            end_date=end_date,
        ).to_array()

        # then, open the shapefile
        shp = gpd.read_file(shapefile)

        # check if there is something in the shapefile
        if len(shp) == 0:
            raise ValueError("No elements in the input shapefile")

        if len(shp) > 1:
            print(f"{len(shp)} featuers found in shapefile, selecting all of them.")

        # convert the shapefile to the raster CRS (more cost effective)
        shp.to_crs(cube.rio.crs, inplace=True)

        # create a figure to be used as a canvas
        fig = plt.figure()

        # set the limits for the colorbar
        vmin = 0
        vmax = float(cube.max()) * 0.8

        # create a list to store the temporary in-memory files
        files = []
        for date in cube.date.data:
            plt_ax = fig.add_subplot()
            RainReporter.plot_raster_shape(
                cube.sel(date=date), shape=shp, plt_ax=plt_ax, vmin=vmin, vmax=vmax
            )
            date_str = DateProcessor.pretty_date(pd.to_datetime(date).to_pydatetime())

            fig.suptitle(f"Dia {date_str}", x=0.4)

            # Create a temporary file
            file_like = io.BytesIO()

            fig.savefig(file_like)
            files.append(file_like)
            fig.clear()

        # Now, with the files created in memory, let's use PIL to save the GIF
        images = []
        for file in files:
            img = Image.open(file)
            images.append(img)

        images[0].save(
            file_name,
            save_all=True,
            append_images=images[1:],
            duration=200,
            loop=0,
        )
