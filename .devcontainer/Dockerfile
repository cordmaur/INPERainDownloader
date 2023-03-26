FROM cordmaur/geospatial_minimal:latest

# install git
RUN apt-get update && apt-get -y install git && rm -rf /var/lib/apt/lists/*

# install notebook and ipykernel
RUN pip3 install --no-cache-dir notebook ipykernel

EXPOSE 8888

# Copy the requirements.txt file to the container
# COPY requirements.txt ./