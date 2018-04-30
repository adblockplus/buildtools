# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import difflib
import json
import os
import re
import shutil
import zipfile
from xml.etree import ElementTree
from struct import unpack

import pytest
from Crypto.Signature import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA

from buildtools import packager
from buildtools.packagerChrome import defaultLocale
from buildtools.build import process_args

LOCALES_MODULE = {
    'test.Foobar': {
        'message': 'Ensuring dict-copy from modules for $domain$',
        'description': 'test description',
        'placeholders': {'content': '$1', 'example': 'www.adblockplus.org'},
    },
}

ALL_LANGUAGES = ['en_US', 'de', 'it']

MESSAGES_EN_US = json.dumps({
    'name': {'message': 'Adblock Plus'},
    'name_devbuild': {'message': 'devbuild-marker'},
    'description': {
        'message': 'Adblock Plus is the most popular ad blocker ever, '
                   'and also supports websites by not blocking '
                   'unobstrusive ads by default (configurable).',
    },
})


class Content(object):
    """Base class for a unified ZipFile / Directory interface.

    Base class for providing a unified context manager interface for
    accessing files. This class is subclassed by ZipContent and DirContent,
    which provide the additional methods "namelist()" and "read(path)".
    """

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._close()


class ZipContent(Content):
    """Provide a unified context manager for ZipFile access.

    Inherits the context manager API from Content.
    If desired, the specified ZipFile is deleted on exiting the manager.
    """

    def __init__(self, zip_path, delete_on_close=True):
        """Construct ZipContent object handling the file <zip_path>.

        The parameter 'delete_on_close' causes the context manager to
        delete the handled ZipFile (specified by zip_path) if set to
        True (default).
        """
        self._zip_path = zip_path
        self._zip_file = zipfile.ZipFile(zip_path)
        self._delete_on_close = delete_on_close
        super(ZipContent, self).__init__()

    def _close(self):
        self._zip_file.close()
        if self._delete_on_close:
            # if specified, delete the handled file
            os.remove(self._zip_path)

    def namelist(self):
        return self._zip_file.namelist()

    def read(self, path):
        return self._zip_file.read(path)


class DirContent(Content):
    """Provides a unified context manager for directory access.

    Inherits the context managet API from Content.
    """

    def __init__(self, path):
        """Construct a DirContent object handling <path>."""
        self._path = path
        super(DirContent, self).__init__()

    def _close(self):
        pass

    def namelist(self):
        """Generate a list of filenames."""
        result = []
        for parent, directories, files in os.walk(self._path):
            for filename in files:
                file_path = os.path.join(parent, filename)
                rel_path = os.path.relpath(file_path, self._path)
                result.append(rel_path)
        return result

    def read(self, path):
        content = None
        with open(os.path.join(self._path, path)) as fp:
            content = fp.read()
        return content


def copy_metadata(filename, tmpdir):
    """Copy the used metadata to the used temporary directory."""
    path = os.path.join(os.path.dirname(__file__), filename)
    destination = str(tmpdir.join(filename))
    shutil.copy(path, destination)


def run_webext_build(ext_type, build_opt, srcdir, keyfile=None):
    """Run a build process."""
    cmd_mapping = {
        'devenv': ['devenv'],
        'development_build': ['build', '-b', '1337'],
        'release_build': ['build', '-r'],
    }

    args = cmd_mapping[build_opt] + ['-t', ext_type]

    if keyfile:
        args += ['-k', keyfile]

    process_args(str(srcdir), *args)


def locale_files(languages, rootfolder, srcdir):
    """Generate example locales.

    languages: tuple, list or set of languages to include
    rootdir: folder-name to create the locale-folders in
    """
    for lang in languages:
        subfolders = rootfolder.split(os.pathsep) + [lang, 'messages.json']
        json_file = srcdir.ensure(*subfolders)
        if lang == defaultLocale:
            json_file.write(MESSAGES_EN_US)
        else:
            json_file.write('{}')


def assert_all_locales_present(package, prefix):
    names = {x for x in package.namelist() if
             x.startswith(os.path.join(prefix, '_locales'))}
    assert names == {
        os.path.join(prefix, '_locales', lang, 'messages.json')
        for lang in ALL_LANGUAGES
    }


@pytest.fixture
def srcdir(tmpdir):
    """Source directory for building the package."""
    for size in ['44', '50', '150']:
        path = tmpdir.join('chrome', 'icons', 'abp-{}.png'.format(size))
        path.write(size, ensure=True)

    tmpdir.join('bar.json').write(json.dumps({}))
    return tmpdir


@pytest.fixture
def locale_modules(tmpdir):
    mod_dir = tmpdir.mkdir('_modules')
    lang_dir = mod_dir.mkdir('en_US')
    lang_dir.join('module.json').write(json.dumps(LOCALES_MODULE))


@pytest.fixture
def icons(srcdir):
    icons_dir = srcdir.mkdir('icons')
    for filename in ['abp-16.png', 'abp-19.png', 'abp-53.png']:
        shutil.copy(
            os.path.join(os.path.dirname(__file__), filename),
            os.path.join(str(icons_dir), filename),
        )


@pytest.fixture
def all_lang_locales(tmpdir):
    return locale_files(ALL_LANGUAGES, '_locales', tmpdir)


@pytest.fixture
def chrome_metadata(tmpdir):
    filename = 'metadata.chrome'
    copy_metadata(filename, tmpdir)


@pytest.fixture
def gecko_webext_metadata(tmpdir, chrome_metadata):
    filename = 'metadata.gecko'
    copy_metadata(filename, tmpdir)


@pytest.fixture
def edge_metadata(tmpdir):
    filename = 'metadata.edge'
    copy_metadata(filename, tmpdir)

    return packager.readMetadata(str(tmpdir), 'edge')


@pytest.fixture
def keyfile(tmpdir):
    """Test-privatekey for signing chrome release-package."""
    return os.path.join(os.path.dirname(__file__), 'chrome_rsa.pem')


@pytest.fixture
def lib_files(tmpdir):
    files = packager.Files(['lib'], set())
    files['ext/a.js'] = 'require("./c.js");\nrequire("info");\nvar bar;'
    files['lib/b.js'] = 'var foo;'
    files['lib/aliased.js'] = 'require("mogo");'
    files['lib/mogo.js'] = 'var this_is_mogo;'
    files['lib/edge.js'] = 'var this_is_edge;'
    files['ext/c.js'] = 'var this_is_c;'
    files['ext/alias_c.js'] = 'var this_is_aliased_c;'
    files['qunit/common.js'] = 'var qunit = {};'
    files['qunit/tests/some_test.js'] = 'var passed = true;'

    libdir = tmpdir.mkdir('lib')
    libdir.join('b.js').write(files['lib/b.js'])
    libdir.join('aliased.js').write(files['lib/aliased.js'])
    libdir.join('mogo.js').write(files['lib/mogo.js'])
    libdir.join('edge.js').write(files['lib/edge.js'])
    ext_dir = tmpdir.mkdir('ext')
    ext_dir.join('a.js').write(files['ext/a.js'])
    ext_dir.join('c.js').write(files['ext/c.js'])
    qunit_dir = tmpdir.mkdir('qunit')
    qunit_dir.join('common.js').write(files['qunit/common.js'])
    qunit_tests_dir = qunit_dir.mkdir('tests')
    qunit_tests_dir.join('some_test.js').write(
        files['qunit/tests/some_test.js'],
    )
    return files


def comparable_json(json_data):
    """Create a nonambiguous representation of the given JSON data."""
    if isinstance(json_data, basestring):
        json_data = json.loads(json_data)
    return json.dumps(
        json_data, sort_keys=True, indent=0,
    ).split('\n')


def comparable_xml(xml):
    """Create a nonambiguous representation of a given XML tree."""
    def strip(s):
        if s is None:
            return ''
        return s.strip()

    def transform(elt):
        subs = sorted(transform(s) for s in elt)
        return (elt.tag, strip(elt.tail), strip(elt.text), elt.attrib, subs)

    return comparable_json(transform(ElementTree.fromstring(xml)))


def assert_manifest_content(manifest, expected_path):
    extension = os.path.basename(expected_path).split('.')[-1]

    with open(expected_path, 'r') as fp:
        if extension == 'xml':
            generated = comparable_xml(manifest)
            expected = comparable_xml(fp.read())
        else:
            generated = comparable_json(manifest)
            expected = comparable_json(fp.read())

    diff = list(difflib.unified_diff(generated, expected, n=0))
    assert len(diff) == 0, '\n'.join(diff)


def assert_webpack_bundle(package, prefix, is_devbuild, excluded=False):
    libfoo = package.read(os.path.join(prefix, 'lib/foo.js'))
    libfoomap = package.read(os.path.join(prefix, 'lib/foo.js.map'))

    assert 'var bar;' in libfoo
    if is_devbuild:
        assert 'addonVersion = "1.2.3.1337";' in libfoo
    else:
        assert 'addonVersion = "1.2.3";' in libfoo

    assert 'webpack:///./ext/a.js' in libfoomap

    assert 'var this_is_c;' in libfoo
    assert 'webpack:///./ext/c.js' in libfoomap

    if prefix:  # webpack 'resolve.alias' exposure
        assert 'var this_is_edge;' in libfoo
        assert 'webpack:///./lib/edge.js' in libfoomap
    else:
        assert 'var this_is_mogo;' in libfoo
        assert 'webpack:///./lib/mogo.js' in libfoomap

    assert ('var foo;' in libfoo) != excluded
    assert ('webpack:///./lib/b.js' in libfoomap) != excluded


def assert_devenv_scripts(package, prefix, devenv):
    manifest = json.loads(package.read(os.path.join(prefix, 'manifest.json')))
    filenames = package.namelist()
    scripts = [
        'ext/common.js',
        'ext/background.js',
    ]

    assert (os.path.join(prefix, 'qunit/index.html') in filenames) == devenv
    assert (os.path.join(prefix, 'devenvPoller__.js') in filenames) == devenv
    assert (os.path.join(prefix, 'devenvVersion__') in filenames) == devenv
    assert (os.path.join(prefix, 'qunit/tests.js') in filenames) == devenv
    assert (os.path.join(prefix, 'qunit/tests.js.map') in filenames) == devenv

    if devenv:
        quint_index = package.read(os.path.join(prefix, 'qunit/index.html'))
        assert '../ext/common.js' in quint_index
        assert '../ext/background.js' in quint_index

        assert set(manifest['background']['scripts']) == set(
            scripts + ['devenvPoller__.js'],
        )
    else:
        assert set(manifest['background']['scripts']) == set(scripts)


def assert_base_files(package, platform, prefix):
    filenames = set(package.namelist())

    if platform == 'edge':
        assert 'AppxManifest.xml' in filenames
        assert 'AppxBlockMap.xml' in filenames
        assert '[Content_Types].xml' in filenames

        assert package.read('Assets/logo_44.png') == '44'
        assert package.read('Extension/icons/abp-44.png') == '44'

    assert os.path.join(prefix, 'bar.json') in filenames
    assert os.path.join(prefix, 'manifest.json') in filenames
    assert os.path.join(prefix, 'lib/foo.js') in filenames
    assert os.path.join(prefix, 'foo/logo_50.png') in filenames
    assert os.path.join(prefix, 'icons/logo_150.png') in filenames


def assert_chrome_signature(filename, keyfile):
    with open(filename, 'r') as fp:
        content = fp.read()

    _, _, l_pubkey, l_signature = unpack('<4sIII', content[:16])
    signature = content[16 + l_pubkey: 16 + l_pubkey + l_signature]

    digest = SHA.new()
    with open(keyfile, 'r') as fp:
        rsa_key = RSA.importKey(fp.read())

    signer = PKCS1_v1_5.new(rsa_key)

    digest.update(content[16 + l_pubkey + l_signature:])
    assert signer.verify(digest, signature)


def assert_locale_upfix(package):
    translations = [
        json.loads(package.read('_locales/{}/messages.json'.format(lang)))
        for lang in ALL_LANGUAGES
    ]

    manifest = package.read('manifest.json')

    # Chrome Web Store requires descriptive translations to be present in
    # every language.
    for match in re.finditer(r'__MSG_(\S+)__', manifest):
        name = match.group(1)

        for other in translations[1:]:
            assert translations[0][name]['message'] == other[name]['message']


@pytest.mark.usefixtures(
    'all_lang_locales',
    'locale_modules',
    'icons',
    'lib_files',
    'chrome_metadata',
    'gecko_webext_metadata',
    'edge_metadata',
)
@pytest.mark.parametrize('platform,command', [
    ('chrome', 'development_build'),
    ('chrome', 'devenv'),
    ('chrome', 'release_build'),
    ('gecko', 'development_build'),
    ('gecko', 'devenv'),
    ('gecko', 'release_build'),
    ('edge', 'development_build'),
    ('edge', 'devenv'),
    ('edge', 'release_build'),
])
def test_build_webext(platform, command, keyfile, tmpdir, srcdir, capsys):
    release = command == 'release_build'
    devenv = command == 'devenv'

    if platform == 'chrome' and release:
        key = keyfile
    else:
        key = None

    manifests = {
        'gecko': [('', 'manifest', 'json')],
        'chrome': [('', 'manifest', 'json')],
        'edge': [('', 'AppxManifest', 'xml'),
                 ('Extension', 'manifest', 'json')],
    }

    filenames = {
        'gecko': 'adblockplusfirefox-1.2.3{}.xpi',
        'chrome': 'adblockpluschrome-1.2.3{{}}.{}'.format(
            {True: 'crx', False: 'zip'}[release],
        ),
        'edge': 'adblockplusedge-1.2.3{}.appx',
    }

    if platform == 'edge':
        prefix = 'Extension'
    else:
        prefix = ''

    run_webext_build(platform, command, srcdir, keyfile=key)

    # The makeIcons() in packagerChrome.py should warn about non-square
    # icons via stderr.
    out, err = capsys.readouterr()
    assert 'icon should be square' in err

    if devenv:
        content_class = DirContent
        out_file_path = os.path.join(str(srcdir), 'devenv.' + platform)
    else:
        content_class = ZipContent

        if release:
            add_version = ''
        else:
            add_version = '.1337'

        out_file = filenames[platform].format(add_version)

        out_file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), os.pardir, out_file))
        assert os.path.exists(out_file_path)

    if release and platform == 'chrome':
        assert_chrome_signature(out_file_path, keyfile)

    with content_class(out_file_path) as package:
        assert_base_files(package, platform, prefix)
        assert_all_locales_present(package, prefix)
        assert_webpack_bundle(package, prefix, not release and not devenv,
                              platform == 'gecko')

        if platform == 'chrome':
            assert_locale_upfix(package)

        assert_devenv_scripts(package, prefix, devenv)

        for folder, name, ext in manifests[platform]:
            filename = '{{}}_{}_{}.{{}}'.format(platform, command)
            expected = os.path.join(
                os.path.dirname(__file__),
                'expecteddata',
                filename.format(name, ext),
            )

            assert_manifest_content(
                package.read(os.path.join(folder, '{}.{}'.format(name, ext))),
                expected,
            )
