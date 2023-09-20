from itertools import islice
from math import degrees

import pandas as pd
from sattrack.orbit import Satellite
from sattrack.sgp4 import TwoLineElement
from sattrack.spacetime import now

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

jd = now()
# with open('starlink.tle', 'r') as f:
#     rawTLEs = f.readlines()
#
# tleIterator = iter(rawTLEs)
# condensedTLEs: list[TwoLineElement] = []
# while True:
#     tleStr = ''.join(islice(tleIterator, 3))
#     if not tleStr:
#         break
#     condensedTLEs.append(tleStr)
condensedTLEs = importStarlinkTLE('starlink.tle')

tleList = list((TwoLineElement(i) for i in condensedTLEs))
elementsList = list((Satellite(tle).getElements(jd) for tle in tleList))

masterDF = pd.DataFrame({
    'name': (tle.name for tle in tleList),
    'inclination': (degrees(el.inc) for el in elementsList),
    'raan': (degrees(el.raan) for el in elementsList),
    'latArg': (degrees(el.aop + el.trueAnomaly) % 360.0 for el in elementsList)
})

inclinationDelimiters = (42.0, 43.0, 53.05, 53.2, 70.0, 97.6)
incEpsilon = 0.075
groupFrames = []
df = masterDF.copy()
for delimiter in inclinationDelimiters:
    comp = (df['inclination'] >= delimiter - incEpsilon) & (df['inclination'] < delimiter + incEpsilon)
    groupFrames.append(df[comp])
    df = df[~comp]

#     grouped = df.groupby(df[comp])
#     try:
#         groupFrames.append(grouped.get_group(True))
#     except KeyError:
#         groupFrames.append(pd.DataFrame())
#     try:
#         masterDF = grouped.get_group(False)
#     except KeyError:
#         pass

    # grouped = masterDF.groupby(masterDF['inclination'] < delimiter)
    # try:
    #     groupFrames.append(grouped.get_group(True))
    # except KeyError:
    #     groupFrames.append(pd.DataFrame())
    # try:
    #     masterDF = grouped.get_group(False)
    # except KeyError:
    #     pass
