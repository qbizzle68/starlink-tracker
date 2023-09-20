import sys
import tomllib
from math import degrees

import pandas as pd
from sattrack.orbit import Satellite
from sattrack.sgp4 import TwoLineElement
from sattrack.spacetime import now
from sattrack.util import EARTH_EQUITORIAL_RADIUS

from sortgroups import importStarlinkTLE


def importConfig(filename):
    with open(filename, 'rb') as f:
        return tomllib.load(f)


def validateBatchName(group: str, launch: str, toml=None) -> bool:
    if toml is None:
        toml = importConfig('starlink.toml')

    token = f'{group}-{launch}'
    return token in toml['launches']


def fetchTLEs(group: str, launch: str, toml=None):
    if toml is None:
        toml = importConfig('starlink.toml')

    if not validateBatchName(group, launch, toml):
        raise ValueError(f'batch name ({group}-{launch}) not found in launch list')

    groupToken = f'group{group}'
    launchToken = f'L{launch}'
    intDes = toml[groupToken][launchToken]

    tleStringList = importStarlinkTLE('starlink.tle')
    tleMasterList = list((TwoLineElement(tle) for tle in tleStringList))

    return list((tle for tle in tleMasterList if int(tle.line1[9:14]) == intDes))


def _checkInput(value):
    if isinstance(value, str):
        return value.isdigit()
    return isinstance(value, int)


def computeApsides(sma: float, ecc: float) -> (int, int):
    rp = sma * (1 - ecc)
    ra = sma * (1 + ecc)

    return (rp - EARTH_EQUITORIAL_RADIUS, ra - EARTH_EQUITORIAL_RADIUS)


def adjustLatitudeArguments(rawArgs):
    # rawArgs = [degrees(el.aop + el.trueAnomaly) % 360.0 for el in elements]
    diffs = [rawArgs[i] - rawArgs[i - 1] for i in range(len(rawArgs))]
    maxValue = max(diffs)
    maxIndex = diffs.index(maxValue)

    if maxValue < 180:
        adjustValue = rawArgs[maxIndex]
        rtn = [a - adjustValue for a in rawArgs]
    else:
        adjustValue = 360 - maxValue

        adjustedArgs = []
        for i in range(len(rawArgs)):
            if i < maxIndex:
                adjustedArgs.append(rawArgs[i] + adjustValue)
            else:
                adjustedArgs.append(rawArgs[i] - 360 + adjustValue)

        maxArgs = max(adjustedArgs)
        rtn = [a - maxArgs for a in adjustedArgs]

    return rtn


def adjustPhase(rawArgs):
    diffs = [rawArgs[i] - rawArgs[i - 1] for i in range(len(rawArgs))]
    diffs[0] += 360



def buildDataFrame(tleList, jd, adjust=True) -> pd.DataFrame:
    elements = [Satellite(tle).getElements(jd) for tle in tleList]
    apsides = [computeApsides(el.sma, el.ecc) for el in elements]
    latArgs = [degrees(el.aop + el.trueAnomaly) % 360.0 for el in elements]
    data = {
        'name': (tle.name for tle in tleList),
        'inclination': (degrees(el.inc) for el in elements),
        'raan': (degrees(el.raan) for el in elements),
        'latArg': latArgs,
        'perigee': [round(rp, 1) for rp, _ in apsides],
        'apogee': [round(ra, 1) for _, ra in apsides],
    }

    df = pd.DataFrame(data).sort_values('latArg')

    if adjust is True:
        adjustedLatArgs = adjustLatitudeArguments(df['latArg'].tolist())
        df = df.assign(latArg=adjustedLatArgs).sort_values('latArg', ascending=False)

    return df


def separateBatch(df: pd.DataFrame) -> list[pd.DataFrame]:
    rtn = []
    


def main(group: str, launch: str):
    if not _checkInput(group):
        raise TypeError(f'group must be an int or a str digit')
    if not _checkInput(launch):
        raise TypeError(f'launch must be an int or a str digit')

    tleList = fetchTLEs(group, launch)
    jd = now()
    df = buildDataFrame(tleList, jd)
    print(df)

    return 0


if __name__ == '__main__':
    exit(main(sys.argv[1], sys.argv[2]))
