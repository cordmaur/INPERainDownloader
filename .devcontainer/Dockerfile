FROM ubuntu:20.04
ENV    CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV    C_INCLUDE_PATH=/usr/include/gdal
RUN    apt-get update 
RUN    apt-get install -y software-properties-common 
RUN    add-apt-repository ppa:deadsnakes/ppa 
RUN    add-apt-repository ppa:ubuntugis/ppa
RUN    apt-get update 
RUN    apt-get install -y curl
RUN    apt-get install -y python3.8 
RUN    apt-get install -y python3-distutils python3-apt
RUN    apt-get install -y python3-pip 
RUN    apt-get install -y gdal-bin
RUN    apt-get install -y libgdal-dev
RUN    export CPLUS_INCLUDE_PATH
RUN    export C_INCLUDE_PATH
RUN    pip install GDAL
# COPY requirements.txt .

# Install the necessary dependencies
RUN pip install --no-cache-dir -r shapely,fiona,pyproj,geopandas,rioxarray,pystac-client
RUN python3 -m pip install -U matplotlib
