import http.client


def getResponse():
    host = 'celestrak.org'
    conn = http.client.HTTPSConnection(host)

    path = '/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=tle'
    conn.request('GET', path)

    return conn.getresponse()

def exportBody(filename):
    resp = getResponse()
    if resp.status != 200:
        raise Exception(f'bad response: {resp.status}, {resp.reason}')

    body = resp.read()
    with open(filename, 'wb') as f:
        bytesWritten = f.write(body)

    if bytesWritten != len(body):
        raise IOError(f'unable to export all of response body, expected to write {len(resp)}, {len(bytesWritten)} '
                      f'written')


def main():
    try:
        exportBody('../starlink.tle')
    except IOError:
        return 1
    return 0


if __name__ == '__main__':
    exit(main())
