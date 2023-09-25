from starlink import update_starlink_tle
from starlink.arg import getArgs
from starlink.main import main


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
