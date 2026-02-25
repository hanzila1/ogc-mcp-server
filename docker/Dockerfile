FROM geopython/pygeoapi:latest

# Copy our custom configuration
COPY pygeoapi/pygeoapi-config.yml /pygeoapi/local.config.yml

# Copy custom processes directly into the venv site-packages
COPY pygeoapi/processes/geospatial_buffer.py /venv/lib/python3.12/site-packages/geospatial_buffer.py
COPY pygeoapi/processes/cool_spot_demo.py /venv/lib/python3.12/site-packages/cool_spot_demo.py

# Copy sample data
COPY pygeoapi/data/parks.geojson /pygeoapi/data/parks.geojson

# Set environment variables
ENV PYGEOAPI_CONFIG=/pygeoapi/local.config.yml
ENV PYGEOAPI_OPENAPI=/pygeoapi/local.openapi.yml