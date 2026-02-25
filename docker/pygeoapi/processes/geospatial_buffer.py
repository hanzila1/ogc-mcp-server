"""
Geospatial Buffer Process — OGC API Processes implementation.

Takes a GeoJSON geometry and returns a buffered version.
Registered with pygeoapi as a custom process for the GSoC 2026
MCP for OGC APIs demonstration.

License: Apache Software License 2.0
"""

import json
import logging
from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'geospatial-buffer',
    'title': {'en': 'Geospatial Buffer'},
    'description': {
        'en': (
            'Creates a buffer zone around a GeoJSON geometry. '
            'Useful for proximity analysis, cool spot analysis, '
            'and urban planning workflows. '
            'Returns a buffered GeoJSON polygon.'
        )
    },
    'keywords': ['buffer', 'spatial analysis', 'proximity', 'GeoJSON'],
    'links': [],
    'inputs': {
        'geometry': {
            'title': 'Input Geometry',
            'description': 'GeoJSON geometry object (Point, Polygon, etc.)',
            'schema': {'type': 'object'},
            'minOccurs': 1,
            'maxOccurs': 1,
        },
        'buffer_degrees': {
            'title': 'Buffer Distance (degrees)',
            'description': (
                'Buffer distance in decimal degrees. '
                '0.01 degrees ≈ 1.1 km at the equator.'
            ),
            'schema': {'type': 'number', 'default': 0.01},
            'minOccurs': 0,
            'maxOccurs': 1,
        },
        'label': {
            'title': 'Feature Label',
            'description': 'Optional label for the buffered feature',
            'schema': {'type': 'string', 'default': 'Buffered Area'},
            'minOccurs': 0,
            'maxOccurs': 1,
        }
    },
    'outputs': {
        'buffered_feature': {
            'title': 'Buffered Feature',
            'description': 'GeoJSON Feature with buffered geometry',
            'schema': {'type': 'object'}
        }
    },
    'example': {
        'inputs': {
            'geometry': {
                'type': 'Point',
                'coordinates': [7.615, 51.955]
            },
            'buffer_degrees': 0.01,
            'label': 'Park Buffer Zone'
        }
    }
}


class GeospatialBufferProcessor(BaseProcessor):
    """Geospatial Buffer processor — buffers any GeoJSON geometry."""

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data, outputs=None):
        mimetype = 'application/json'

        # Extract inputs
        geometry = data.get('geometry')
        if not geometry:
            raise ProcessorExecuteError('geometry input is required')

        buffer_degrees = float(data.get('buffer_degrees', 0.01))
        label = data.get('label', 'Buffered Area')

        geo_type = geometry.get('type', '')
        coords = geometry.get('coordinates', [])

        # Apply buffer based on geometry type
        if geo_type == 'Point':
            lon, lat = coords[0], coords[1]
            buffered_coords = _buffer_point(lon, lat, buffer_degrees)
            buffered_geom = {
                'type': 'Polygon',
                'coordinates': [buffered_coords]
            }

        elif geo_type == 'Polygon':
            buffered_coords = _buffer_polygon(coords[0], buffer_degrees)
            buffered_geom = {
                'type': 'Polygon',
                'coordinates': [buffered_coords]
            }

        else:
            raise ProcessorExecuteError(
                f'Unsupported geometry type: {geo_type}. '
                f'Supported: Point, Polygon'
            )

        result = {
            'buffered_feature': {
                'type': 'Feature',
                'properties': {
                    'label': label,
                    'buffer_degrees': buffer_degrees,
                    'buffer_km_approx': round(buffer_degrees * 111, 2),
                    'original_type': geo_type,
                    'process': 'geospatial-buffer',
                    'version': '1.0.0'
                },
                'geometry': buffered_geom
            }
        }

        return mimetype, result

    def __repr__(self):
        return f'<GeospatialBufferProcessor>'


def _buffer_point(lon, lat, buffer_degrees):
    """Create a rectangular buffer around a point."""
    return [
        [lon - buffer_degrees, lat - buffer_degrees],
        [lon + buffer_degrees, lat - buffer_degrees],
        [lon + buffer_degrees, lat + buffer_degrees],
        [lon - buffer_degrees, lat + buffer_degrees],
        [lon - buffer_degrees, lat - buffer_degrees],
    ]


def _buffer_polygon(ring, buffer_degrees):
    """Expand a polygon ring outward by buffer_degrees."""
    if not ring:
        return ring
    buffered = []
    for coord in ring:
        lon, lat = coord[0], coord[1]
        # Simple outward expansion
        center_lon = sum(c[0] for c in ring) / len(ring)
        center_lat = sum(c[1] for c in ring) / len(ring)
        direction_lon = lon - center_lon
        direction_lat = lat - center_lat
        length = (direction_lon**2 + direction_lat**2) ** 0.5
        if length > 0:
            buffered.append([
                round(lon + buffer_degrees * direction_lon / length, 6),
                round(lat + buffer_degrees * direction_lat / length, 6)
            ])
        else:
            buffered.append([lon, lat])
    # Close the ring
    if buffered and buffered[0] != buffered[-1]:
        buffered.append(buffered[0])
    return buffered
