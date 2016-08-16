# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import struct
import time
import zlib

from Crypto.Hash import SHA
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from buildtools.packager import getTemplate

XAR_HEADER = struct.Struct('>IHHQQI')
XAR_HEADER_MAGIC = 0x78617221
XAR_VERSION = 1
XAR_CKSUM_SHA1 = 1


def read_certificates_and_key(keyfile):
    with open(keyfile, 'r') as file:
        data = file.read()

    certificates = []
    key = None
    for match in re.finditer(r'-+BEGIN (.*?)-+(.*?)-+END \1-+', data, re.S):
        section = match.group(1)
        if section == 'CERTIFICATE':
            certificates.append(re.sub(r'\s+', '', match.group(2)))
        elif section == 'PRIVATE KEY':
            key = RSA.importKey(match.group(0))
    if not key:
        raise Exception('Could not find private key in file')

    return certificates, key


def get_checksum(data):
    return SHA.new(data).digest()


def get_hexchecksum(data):
    return SHA.new(data).hexdigest()


def get_signature(key, data):
    return PKCS1_v1_5.new(key).sign(SHA.new(data))


def compress_files(filedata, root, offset):
    compressed_data = []
    filedata = sorted(filedata.iteritems())
    directory_stack = [('', root)]
    file_id = 1
    for path, data in filedata:
        # Remove directories that are done
        while not path.startswith(directory_stack[-1][0]):
            directory_stack.pop()

        # Add new directories
        directory_path = directory_stack[-1][0]
        relpath = path[len(directory_path):]
        while '/' in relpath:
            name, relpath = relpath.split('/', 1)
            directory_path += name + '/'
            directory = {
                'id': file_id,
                'name': name,
                'type': 'directory',
                'mode': '0755',
                'children': [],
            }
            file_id += 1
            directory_stack[-1][1].append(directory)
            directory_stack.append((directory_path, directory['children']))

        # Add the actual file
        compressed = zlib.compress(data, 9)
        file = {
            'id': file_id,
            'name': relpath,
            'type': 'file',
            'mode': '0644',
            'checksum_uncompressed': get_hexchecksum(data),
            'size_uncompressed': len(data),
            'checksum_compressed': get_hexchecksum(compressed),
            'size_compressed': len(compressed),
            'offset': offset,
        }
        file_id += 1
        offset += len(compressed)
        directory_stack[-1][1].append(file)
        compressed_data.append(compressed)
    return compressed_data


def create(archivepath, contents, keyfile):
    certificates, key = read_certificates_and_key(keyfile)
    checksum_length = len(get_checksum(''))
    params = {
        'certificates': certificates,

        # Timestamp epoch starts at 2001-01-01T00:00:00.000Z
        'timestamp_numerical': time.time() - 978307200,
        'timestamp_iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),

        'checksum': {
            'offset': 0,
            'size': checksum_length,
        },
        'signature': {
            'offset': checksum_length,
            'size': len(get_signature(key, '')),
        },
        'files': [],
    }

    offset = params['signature']['offset'] + params['signature']['size']
    compressed_data = compress_files(contents, params['files'], offset)

    template = getTemplate('xartoc.xml.tmpl', autoEscape=True)
    toc_uncompressed = template.render(params).encode('utf-8')
    toc_compressed = zlib.compress(toc_uncompressed, 9)

    with open(archivepath, 'wb') as file:
        # The file starts with a minimalistic header
        file.write(XAR_HEADER.pack(XAR_HEADER_MAGIC, XAR_HEADER.size,
                                   XAR_VERSION, len(toc_compressed),
                                   len(toc_uncompressed), XAR_CKSUM_SHA1))

        # It's followed up with a compressed XML table of contents
        file.write(toc_compressed)

        # Now the actual data, all the offsets are in the table of contents
        file.write(get_checksum(toc_compressed))
        file.write(get_signature(key, toc_compressed))
        for blob in compressed_data:
            file.write(blob)
