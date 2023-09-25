from sattrack.coordinates import GeoPosition
from sattrack.exceptions import TLEException
from sattrack.spacetime import JulianDate

from starlink import update_starlink_tle
from starlink.arg import getArgs
from starlink.frames import generateDataFrame, getLaunchData
from starlink.import_tle import fetchTLEsFromGroup
from starlink.main import main
from starlink.passes import getBatchTimes


if __name__ == '__main__':
    args = getArgs()
    if args['forceUpdate']:
        print('updating TLEs')
        exitValue = update_starlink_tle.main()
        if exitValue != 0:
            exit(exitValue)

    exitValue = main(args['groupNumber'], args['launchNumber'], args['geo'], args['time'], args['visibleNumber'],
                     args['includePass'])
    exit(exitValue)
