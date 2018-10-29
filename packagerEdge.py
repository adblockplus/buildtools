# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import shutil
from StringIO import StringIO
import subprocess
import tempfile
from xml.etree import ElementTree
from zipfile import ZipFile

import packager
import packagerChrome

MANIFEST = 'appxmanifest.xml'
ASSETS_DIR = 'Assets'

defaultLocale = packagerChrome.defaultLocale


def _get_template_for(filename):
    return packager.getTemplate('edge/{}.tmpl'.format(filename))


def register_xml_namespaces(manifest_path):
    """Register namespaces of the given file, in order to preserve defaults."""
    with open(manifest_path, 'r') as fp:
        ns = dict([node for _, node in ElementTree.iterparse(
            fp, events=['start-ns'])])
    for prefix, uri in ns.items():
        ElementTree.register_namespace(prefix, uri)

    # Make the default namespace available in an xpath expression
    ns['_d'] = ns['']

    return ns


def update_appx_manifest(manifest_path, base_dir, files, metadata,
                         release_build):
    namespaces = register_xml_namespaces(manifest_path)

    v_min, v_max = metadata.get('compat', 'windows').split('/')

    filenames = []

    for name, path in metadata.items('appx_assets'):
        path = os.path.join(base_dir, path)
        icon_path = '{}/{}'.format(ASSETS_DIR, name)

        files.read(path, icon_path)
        filenames.append(icon_path)

    assets = packagerChrome.makeIcons(files, filenames)

    author = metadata.get('general', 'author')

    overrides = [
        ('_d:Identity', None, [
            ('Name', packager.get_app_id(release_build, metadata)),
            ('Publisher', metadata.get('general', 'publisher_id')),
        ]),
        ('_d:Properties/_d:PublisherDisplayName', author, []),
        ('_d:Properties/_d:Logo', assets[50], []),
        ('_d:Dependencies/_d:TargetDeviceFamily', None, [
            ('MaxVersionTested', v_max),
            ('MinVersion', v_min),
        ]),
        ('_d:Applications/_d:Application/uap:VisualElements', None, [
            ('Square150x150Logo', assets[150]),
            ('Square44x44Logo', assets[44]),
        ]),
    ]

    tree = ElementTree.parse(manifest_path)
    root = tree.getroot()

    for xpath, text, attributes in overrides:
        element = root.find(xpath, namespaces)
        if text:
            element.text = text
        for attr, value in attributes:
                element.set(attr, value)

    tree.write(manifest_path, encoding='utf-8', xml_declaration=True)


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

    # For some mysterious reasons manifoldjs fails with a server error
    # when building the development build and there is any translation
    # in az/messages.json for "name_devbuild", however, it works fine
    # if we use the more specific language code az-latn.
    az_translation = files.pop('_locales/az/messages.json', None)
    if az_translation is not None:
        files['_locales/az-latn/messages.json'] = az_translation

    files['manifest.json'] = packagerChrome.createManifest(params, files)

    if devenv:
        packagerChrome.add_devenv_requirements(files, metadata, params)

    zipped = StringIO()
    files.zip(zipped)

    zipped.seek(0)

    if devenv:
        shutil.copyfileobj(zipped, outfile)
        return

    tmp_dir = tempfile.mkdtemp('adblockplus_package')
    try:
        src_dir = os.path.join(tmp_dir, 'src')
        ext_dir = os.path.join(tmp_dir, 'ext')

        with ZipFile(zipped, 'r') as zip_file:
            zip_file.extractall(src_dir)

        cmd_env = os.environ.copy()
        cmd_env['SRC_FOLDER'] = src_dir
        cmd_env['EXT_FOLDER'] = ext_dir

        manifold_folder = os.path.join(ext_dir, 'MSGname', 'edgeextension')
        manifest_folder = os.path.join(manifold_folder, 'manifest')
        asset_folder = os.path.join(manifest_folder, ASSETS_DIR)

        # prepare the extension with manifoldjs
        cmd = ['npm', 'run', '--silent', 'build-edge']
        subprocess.check_call(cmd, env=cmd_env, cwd=os.path.dirname(__file__))

        # update incomplete appxmanifest
        intermediate_manifest = os.path.join(manifest_folder, MANIFEST)
        update_appx_manifest(intermediate_manifest, baseDir, files, metadata,
                             releaseBuild)

        # cleanup placeholders, copy actual images
        shutil.rmtree(asset_folder)
        os.mkdir(asset_folder)
        if metadata.has_section('appx_assets'):
            for name, path in metadata.items('appx_assets'):
                path = os.path.join(baseDir, path)
                target = os.path.join(asset_folder, name)
                shutil.copyfile(path, target)

        # package app with manifoldjs
        cmd = ['npm', 'run', '--silent', 'package-edge']

        subprocess.check_call(cmd, env=cmd_env, cwd=os.path.dirname(__file__))

        package = os.path.join(manifold_folder, 'package',
                               'edgeExtension.appx')

        shutil.copyfile(package, outfile)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
