#!/bin/bash
export PYTHONPATH=/pygeoapi/plugins:$PYTHONPATH
echo "PYTHONPATH set to: $PYTHONPATH"
exec /entrypoint.sh