# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import shutil
import json
import re
from StringIO import StringIO
from glob import glob
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


def update_appx_manifest(manifest_path, base_dir, files, metadata,
                         release_build, build_num):
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
            ('Version', get_appx_version(metadata, build_num)),
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

    # Windows rejects to install the package if it contains localized
    # resources for 'az', or if the manifest lists resources for 'uz'
    # but the relevant strings aren't translated.
    resources_dir = os.path.join(os.path.dirname(manifest_path), 'Resources')
    resources_element = root.find('_d:Resources', namespaces)
    for element in resources_element.findall('_d:Resource', namespaces):
        language = element.get('Language')
        if language:
            folder = os.path.join(resources_dir, language)
            if language == 'az':
                shutil.rmtree(folder, ignore_errors=True)
            if not os.path.exists(folder):
                resources_element.remove(element)

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

    # The Windows Store will reject the build unless every translation of the
    # product name has been reserved. This is hard till impossible to manage
    # with community translations, so we don't translate the product name for
    # Microsoft Edge. Furthermore, manifoldjs fails with a server error if the
    # product name is tranlated into Azerbajani.
    data = json.loads(files['_locales/{}/messages.json'.format(defaultLocale)])
    files['manifest.json'] = re.sub(
        r'__MSG_(name(?:_devbuild)?)__',
        lambda m: data[m.group(1)]['message'],
        packagerChrome.createManifest(params, files),
    )

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

        # prepare the extension with manifoldjs
        cmd = ['npm', 'run', '--silent', 'build-edge']
        subprocess.check_call(cmd, env=cmd_env, cwd=os.path.dirname(__file__))

        manifold_folder = glob(os.path.join(ext_dir, '*', 'edgeextension'))[0]
        manifest_folder = os.path.join(manifold_folder, 'manifest')
        asset_folder = os.path.join(manifest_folder, ASSETS_DIR)

        # update incomplete appxmanifest
        intermediate_manifest = os.path.join(manifest_folder, MANIFEST)
        update_appx_manifest(intermediate_manifest, baseDir, files, metadata,
                             releaseBuild, buildNum)

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
