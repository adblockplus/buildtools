# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import xml.etree.ElementTree as ET

import pytest

from buildtools import packager, packagerEdge


@pytest.fixture
def files():
    """Minimal Files() for testing blockmap."""
    str500 = b''.join(chr(i % 200 + 30) for i in range(500))
    files = packager.Files(set(), set())
    files['Extension/foo.xml'] = str500
    files['Extension/bar.png'] = str500 * 200
    return files


def blockmap2dict(xml_data):
    """Convert AppxBlockMap.xml to a dict of dicts easier to inspect."""
    return {
        file.get('Name'): {
            'size': file.get('Size'),
            'lfhsize': file.get('LfhSize'),
            'blocks': [b.get('Hash') for b in file]
        }
        for file in ET.fromstring(xml_data)
    }


def test_create_appx_blockmap(files):
    blockmap = blockmap2dict(packagerEdge.create_appx_blockmap(files))
    assert blockmap['Extension\\foo.xml'] == {
        'size': '500',
        'lfhsize': '47',
        'blocks': ['Vhwfmzss1Ney+j/ssR2QVISvFyMNBQeS2P+UjeE/di0=']
    }
    assert blockmap['Extension\\bar.png'] == {
        'size': '100000',
        'lfhsize': '47',
        'blocks': [
            'KPW2SxeEikUEGhoKmKxruUSexKun0bGXMppOqUFrX5E=',
            'KQHnov1SZ1z34ttdDUjX2leYtpIIGndUVoUteieS2cw=',
        ]
    }


def ctm2dict(content_types_map):
    """Convert content type map to a dict."""
    ret = {'defaults': {}, 'overrides': {}}
    for node in ET.fromstring(content_types_map):
        ct = node.get('ContentType')
        if node.tag.endswith('Default'):
            ret['defaults'][node.get('Extension')] = ct
        elif node.tag.endswith('Override'):
            ret['overrides'][node.get('PartName')] = ct
        else:
            raise ValueError('Unrecognised tag in content map: ' + node.tag)
    return ret


def test_empty_content_types_map():
    ctm_dict = ctm2dict(packagerEdge.create_content_types_map([]))
    assert ctm_dict['defaults'] == {}
    assert ctm_dict['overrides'] == {}


def test_full_content_types_map():
    filenames = ['no-extension', packagerEdge.MANIFEST, packagerEdge.BLOCKMAP]
    filenames += ['file.' + x for x in 'json html js png css git otf'.split()]
    ctm_dict = ctm2dict(packagerEdge.create_content_types_map(filenames))
    assert ctm_dict['defaults'] == {
        'css': 'text/css',
        'html': 'text/html',
        'js': 'application/javascript',
        'json': 'application/json',
        'otf': 'application/octet-stream',
        'png': 'image/png',
        'xml': 'application/xml'
    }
    assert ctm_dict['overrides'] == {
        '/AppxBlockMap.xml': 'application/vnd.ms-appx.blockmap+xml',
        '/AppxManifest.xml': 'application/vnd.ms-appx.manifest+xml'
    }
