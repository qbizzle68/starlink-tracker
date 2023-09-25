dependencies = ['pandas']
missingDependencies = []

for dep in dependencies:
    try:
        __import__(dep)
    except ImportError as e:
        missingDependencies.append(dep)

if missingDependencies:
    errorMessage = 'Unable to import dependencies:\n' + '\n'.join(missingDependencies)
    raise ImportError(errorMessage)

from .frames import (
    getLaunchData
)

from .import_tle import (
    importConfig,
    validateBatchName,
    importStarlinkTLE,
    fetchTLEsFromGroup,
    fetchAllTLEs,
)

from .passes import (
    getNthPasses,
    getBatchTimes,
)

from .update_starlink_tle import (
    getResponse,
    exportBody,
    main as updateStarlinkTLE
)

__all__ = (
    'getLaunchData',
    'importConfig',
    'validateBatchName',
    'importStarlinkTLE',
    'fetchTLEsFromGroup',
    'fetchAllTLEs',
    'getNthPasses',
    'getBatchTimes',
    'getResponse',
    'exportBody',
    'updateStarlinkTLE',
)
