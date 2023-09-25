import tomllib
from itertools import islice

from sattrack.exceptions import TLEException
from sattrack.sgp4 import TwoLineElement


def importConfig(filename):
    with open(filename, 'rb') as f:
        return tomllib.load(f)


def validateBatchName(group: str, launch: str, toml=None) -> bool:
    if toml is None:
        toml = importConfig('starlink.toml')

    token = f'{group}-{launch}'
    return token in toml['launches']


def importStarlinkTLE(filename):
    with open(filename, 'r') as f:
        rawTLEs = f.readlines()

    tleIterator = iter(rawTLEs)
    condensedTLEs = []
    while True:
        tleString = ''.join(islice(tleIterator, 3))
        if not tleString:
            break
        condensedTLEs.append(tleString)

    return condensedTLEs


def fetchTLEsFromGroup(group: str, launch: str, toml=None):
    if toml is None:
        toml = importConfig('starlink.toml')

    if not validateBatchName(group, launch, toml):
        raise ValueError(f'batch name ({group}-{launch}) not found in launch list')

    groupToken = f'group{group}'
    launchToken = f'L{launch}'
    intDes = toml[groupToken][launchToken]

    tleStringList = importStarlinkTLE('starlink.tle')
    tleMasterList = list((TwoLineElement(tle) for tle in tleStringList))

    rtn = list((tle for tle in tleMasterList if int(tle.line1[9:14]) == intDes))

    if not rtn:
        raise TLEException(f'no TLE data for batch {group}-{launch}')

    return rtn


def fetchAllTLEs() -> dict[str, TwoLineElement]:
    tleStringList = importStarlinkTLE('starlink.tle')

    return {tle.split('\n', 1)[0].rstrip(): TwoLineElement(tle) for tle in tleStringList}
