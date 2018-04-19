# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import hashlib
import json
import mimetypes
import os
import zipfile

import packager
import packagerChrome

# Files and directories expected inside of the .APPX archive.
MANIFEST = 'AppxManifest.xml'
CONTENT_TYPES = '[Content_Types].xml'
BLOCKMAP = 'AppxBlockMap.xml'
EXTENSION_DIR = 'Extension'
ASSETS_DIR = 'Assets'

# Size of uncompressed block in the APPX block map.
BLOCKSIZE = 64 * 1024

defaultLocale = packagerChrome.defaultLocale


def _get_template_for(filename):
    return packager.getTemplate('edge/{}.tmpl'.format(filename))


def _lfh_size(filename):
    """Compute the size of zip local file header for `filename`."""
    try:
        filename = filename.encode('utf-8')
    except UnicodeDecodeError:
        pass  # filename is already a byte string.
    return zipfile.sizeFileHeader + len(filename)


def _make_blockmap_entry(filename, data):
    blocks = [data[i:i + BLOCKSIZE] for i in range(0, len(data), BLOCKSIZE)]
    return {
        'name': filename.replace('/', '\\'),
        'size': len(data),
        'lfh_size': _lfh_size(filename),
        'blocks': [
            {'hash': base64.b64encode(hashlib.sha256(block).digest())}
            for block in blocks
        ],
    }


def create_appx_blockmap(files):
    """Create APPX blockmap for the list of files."""
    # We don't support AppxBlockmap.xml generation for compressed zip files at
    # the moment. The only way to reliably calculate the compressed size of
    # each 64k chunk in the zip file is to override the relevant parts of
    # `zipfile` library. We have chosen to not do it so we produce an
    # uncompressed zip file that is later repackaged by Windows Store with
    # compression.
    template = _get_template_for(BLOCKMAP)
    files = [_make_blockmap_entry(n, d) for n, d in files.items()]
    return template.render(files=files).encode('utf-8')


def load_translation(files, locale):
    """Load translation strings for locale from files."""
    path = '{}/_locales/{}/messages.json'.format(EXTENSION_DIR, locale)
    return json.loads(files[path])


def get_appx_version(metadata, build_num):
    """Get the version number for usage in AppxManifest.xml.

    As required by the Windows Store, the returned version string has four
    components, where the 3rd component is replaced with the build number
    if available, and the 4th component is always zero (e.g. 1.2.1000.0).
    """
    components = metadata.get('general', 'version').split('.')[:3]
    components.extend(['0'] * (4 - len(components)))
    if build_num:
        components[2] = build_num
    return '.'.join(components)


def create_appx_manifest(params, files, build_num, release_build):
    """Create AppxManifest.xml."""
    params = dict(params)
    metadata = params['metadata']
    w = params['windows_version'] = {}
    w['min'], w['max'] = metadata.get('compat', 'windows').split('/')
    params['version'] = get_appx_version(metadata, build_num)

    metadata_suffix = 'release' if release_build else 'devbuild'
    app_extension_id = 'extension_id_' + metadata_suffix
    if metadata.has_option('general', app_extension_id):
        params['app_extension_id'] = metadata.get('general', app_extension_id)
    else:
        params['app_extension_id'] = 'EdgeExtension'

    params['app_id'] = packager.get_app_id(release_build, metadata)

    translation = load_translation(files, defaultLocale)
    name_key = 'name' if release_build else 'name_devbuild'
    params['display_name'] = translation[name_key]['message']
    params['description'] = translation['description']['message']

    for size in ['44', '50', '150']:
        path = '{}/logo_{}.png'.format(ASSETS_DIR, size)
        if path not in files:
            raise KeyError(path + ' is not found in files')
        params['logo_' + size] = path.replace('/', '\\')

    template = _get_template_for(MANIFEST)
    return template.render(params).encode('utf-8')


def move_files_to_extension(files):
    """Move all files into `Extension` folder for APPX packaging."""
    # We sort the files to ensure that 'Extension/xyz' is moved before 'xyz'.
    # If 'xyz' is moved first, it would overwrite 'Extension/xyz' and its
    # original content would be lost.
    names = sorted(files.keys(), key=len, reverse=True)
    for filename in names:
        files['{}/{}'.format(EXTENSION_DIR, filename)] = files.pop(filename)


def create_content_types_map(filenames):
    """Create [Content_Types].xml -- a mime type map."""
    params = {'defaults': {}, 'overrides': {}}
    overrides = {
        BLOCKMAP: 'application/vnd.ms-appx.blockmap+xml',
        MANIFEST: 'application/vnd.ms-appx.manifest+xml',
    }
    types = mimetypes.MimeTypes()
    types.add_type('application/octet-stream', '.otf')
    for filename in filenames:
        ext = os.path.splitext(filename)[1]
        if ext:
            content_type = types.guess_type(filename, strict=False)[0]
            if content_type is not None:
                params['defaults'][ext[1:]] = content_type
        if filename in overrides:
            params['overrides']['/' + filename] = overrides[filename]
    content_types_template = _get_template_for(CONTENT_TYPES)
    return content_types_template.render(params).encode('utf-8')


def createBuild(baseDir, type='edge', outFile=None,  # noqa: preserve API.
                buildNum=None, releaseBuild=False, keyFile=None,
                devenv=False):

    metadata = packager.readMetadata(baseDir, type)
    version = packager.getBuildVersion(baseDir, metadata, releaseBuild,
                                       buildNum)

    outfile = outFile or packager.getDefaultFileName(metadata, version, 'appx')

    params = {
        'type': type,
        'baseDir': baseDir,
        'releaseBuild': releaseBuild,
        'version': version,
        'devenv': devenv,
        'metadata': metadata,
    }

    files = packager.Files(packagerChrome.getPackageFiles(params),
                           packagerChrome.getIgnoredFiles(params))

    if metadata.has_section('mapping'):
        mapped = metadata.items('mapping')
        files.readMappedFiles(mapped)
        files.read(baseDir, skip=[filename for filename, _ in mapped])
    else:
        files.read(baseDir)

    if metadata.has_section('bundles'):
        bundle_tests = devenv and metadata.has_option('general', 'testScripts')
        packagerChrome.create_bundles(params, files, bundle_tests)

    if metadata.has_section('preprocess'):
        files.preprocess(metadata.options('preprocess'), {'needsExt': True})

    if metadata.has_section('import_locales'):
        packagerChrome.import_locales(params, files)

    files['manifest.json'] = packagerChrome.createManifest(params, files)

    if devenv:
        packagerChrome.add_devenv_requirements(files, metadata, params)

    move_files_to_extension(files)

    if metadata.has_section('appx_assets'):
        for name, path in metadata.items('appx_assets'):
            path = os.path.join(baseDir, path)
            files.read(path, '{}/{}'.format(ASSETS_DIR, name))

    files[MANIFEST] = create_appx_manifest(params, files,
                                           buildNum, releaseBuild)
    files[BLOCKMAP] = create_appx_blockmap(files)
    files[CONTENT_TYPES] = create_content_types_map(files.keys() + [BLOCKMAP])

    files.zip(outfile, compression=zipfile.ZIP_STORED)
