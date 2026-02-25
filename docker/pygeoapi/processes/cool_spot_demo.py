"""
Cool Spot Demo Process — OGC API Processes implementation.

Demonstrates the cool spot analysis scenario from the GSoC 2026
52°North project description. Takes park boundaries and returns
a simulated cool spot analysis result showing temperature reduction
zones around urban green spaces.

License: Apache Software License 2.0
"""

import logging
from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

LOGGER = logging.getLogger(__name__)

PROCESS_METADATA = {
    'version': '1.0.0',
    'id': 'cool-spot-demo',
    'title': {'en': 'Cool Spot Analysis (Demo)'},
    'description': {
        'en': (
            'Demonstrates the cool spot analysis scenario from the GSoC 2026 '
            'MCP for OGC APIs project. Analyzes urban park boundaries and '
            'returns simulated temperature reduction zones — cool spots — '
            'created by green spaces in urban environments. '
            'This is the exact use case described in the 52°North project: '
            'a non-GIS-expert urban planner interacts via natural language '
            'to conduct cool spot analysis on park designs.'
        )
    },
    'keywords': [
        'cool spot', 'urban heat island', 'green infrastructure',
        'parks', 'temperature', 'urban planning', 'GSoC 2026'
    ],
    'links': [
        {
            'type': 'text/html',
            'rel': 'related',
            'title': '52°North Cool Spots Blog Post',
            'href': 'https://blog.52north.org/2022/12/16/cool-spots-in-munster/'
        }
    ],
    'inputs': {
        'park_geometries': {
            'title': 'Park Boundaries',
            'description': (
                'GeoJSON FeatureCollection of park boundaries to analyze. '
                'Each feature should have a name property.'
            ),
            'schema': {'type': 'object'},
            'minOccurs': 1,
            'maxOccurs': 1,
        },
        'buffer_km': {
            'title': 'Cool Spot Radius (km)',
            'description': (
                'Radius in kilometers around each park '
                'where cooling effect is expected. Default: 0.5 km'
            ),
            'schema': {'type': 'number', 'default': 0.5},
            'minOccurs': 0,
            'maxOccurs': 1,
        },
        'city_name': {
            'title': 'City Name',
            'description': 'Name of the city for the analysis report',
            'schema': {'type': 'string', 'default': 'Münster'},
            'minOccurs': 0,
            'maxOccurs': 1,
        }
    },
    'outputs': {
        'cool_spot_report': {
            'title': 'Cool Spot Analysis Report',
            'description': (
                'Analysis results including cool spot zones, '
                'estimated temperature reductions, and coverage statistics'
            ),
            'schema': {'type': 'object'}
        }
    },
    'example': {
        'inputs': {
            'park_geometries': {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'properties': {'name': 'Aasee Park', 'area_ha': 52.3},
                        'geometry': {
                            'type': 'Polygon',
                            'coordinates': [[
                                [7.610, 51.940],
                                [7.625, 51.940],
                                [7.625, 51.950],
                                [7.610, 51.950],
                                [7.610, 51.940]
                            ]]
                        }
                    }
                ]
            },
            'buffer_km': 0.5,
            'city_name': 'Münster'
        }
    }
}


class CoolSpotDemoProcessor(BaseProcessor):
    """Cool Spot Demo processor — simulates urban cooling analysis."""

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data, outputs=None):
        mimetype = 'application/json'

        park_geometries = data.get('park_geometries')
        if not park_geometries:
            raise ProcessorExecuteError('park_geometries input is required')

        buffer_km = float(data.get('buffer_km', 0.5))
        city_name = data.get('city_name', 'Münster')

        features = park_geometries.get('features', [])
        if not features:
            raise ProcessorExecuteError(
                'park_geometries must contain at least one feature'
            )

        # Analyze each park
        cool_spots = []
        total_cooling_area_km2 = 0

        for i, feature in enumerate(features):
            props = feature.get('properties', {})
            park_name = props.get('name', f'Park {i+1}')
            area_ha = props.get('area_ha', 10.0)
            tree_coverage = props.get('tree_coverage', 0.5)
            has_water = props.get('has_water', False)

            # Simulate cooling effect based on park characteristics
            base_cooling = 1.5  # degrees C
            size_factor = min(area_ha / 50.0, 2.0)
            tree_factor = tree_coverage * 1.5
            water_bonus = 0.8 if has_water else 0.0

            temp_reduction = round(
                base_cooling + size_factor + tree_factor + water_bonus, 1
            )
            cooling_area = round(3.14159 * buffer_km ** 2, 2)
            total_cooling_area_km2 += cooling_area

            cool_spots.append({
                'park_name': park_name,
                'area_ha': area_ha,
                'buffer_km': buffer_km,
                'cooling_area_km2': cooling_area,
                'estimated_temp_reduction_c': temp_reduction,
                'cooling_intensity': (
                    'High' if temp_reduction > 3.5
                    else 'Medium' if temp_reduction > 2.5
                    else 'Low'
                ),
                'factors': {
                    'tree_coverage': f'{int(tree_coverage * 100)}%',
                    'water_feature': has_water,
                    'park_size': f'{area_ha} ha'
                }
            })

        result = {
            'cool_spot_report': {
                'city': city_name,
                'analysis_type': 'Urban Cool Spot Analysis',
                'project': 'GSoC 2026 — MCP for OGC APIs @ 52°North',
                'parks_analyzed': len(features),
                'buffer_radius_km': buffer_km,
                'total_cooling_coverage_km2': round(total_cooling_area_km2, 2),
                'cool_spots': cool_spots,
                'summary': (
                    f'Analyzed {len(features)} parks in {city_name}. '
                    f'Total cool spot coverage: '
                    f'{round(total_cooling_area_km2, 2)} km². '
                    f'Average temperature reduction: '
                    f'{round(sum(s["estimated_temp_reduction_c"] for s in cool_spots) / len(cool_spots), 1)}°C '
                    f'within {buffer_km} km of park boundaries.'
                ),
                'recommendation': (
                    'These green spaces provide significant cooling benefits '
                    'for surrounding urban areas. Consider expanding tree '
                    'coverage and adding water features to maximize '
                    'the urban heat island mitigation effect.'
                )
            }
        }

        return mimetype, result

    def __repr__(self):
        return '<CoolSpotDemoProcessor>'
    