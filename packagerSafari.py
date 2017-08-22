# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import ConfigParser
import json
import os
import re
from urlparse import urlparse

from packager import readMetadata, getDefaultFileName, getBuildVersion, getTemplate, Files
from packagerChrome import convertJS, import_locales, getIgnoredFiles, getPackageFiles, defaultLocale, createScriptPage


def processFile(path, data, params):
    return data


def createManifest(params, files):
    template = getTemplate('Info.plist.tmpl', autoEscape=True)
    metadata = params['metadata']
    catalog = json.loads(files['_locales/%s/messages.json' % defaultLocale])

    def parse_section(section, depth=1):
        result = {}

        if not metadata.has_section(section):
            return result

        for opt in metadata.options(section):
            bits = opt.split('_', depth)
            key = bits.pop().replace('_', ' ').title()
            val = metadata.get(section, opt)

            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    pass

            reduce(lambda d, x: d.setdefault(x, {}), bits, result)[key] = val

        return result

    def get_optional(*args):
        try:
            return metadata.get(*args)
        except ConfigParser.Error:
            return None

    allowedDomains = set()
    allowAllDomains = False
    allowSecurePages = False

    for perm in metadata.get('general', 'permissions').split():
        if perm == '<all_urls>':
            allowAllDomains = True
            allowSecurePages = True
            continue

        url = urlparse(perm)

        if url.scheme == 'https':
            allowSecurePages = True
        elif url.scheme != 'http':
            continue

        if '*' in url.hostname:
            allowAllDomains = True
            continue

        allowedDomains.add(url.hostname)

    return template.render(
        basename=metadata.get('general', 'basename'),
        version=params['version'],
        releaseBuild=params['releaseBuild'],
        name=catalog['name']['message'],
        description=catalog['description']['message'],
        author=get_optional('general', 'author'),
        homepage=get_optional('general', 'homepage'),
        updateURL=get_optional('general', 'updateURL'),
        allowedDomains=allowedDomains,
        allowAllDomains=allowAllDomains,
        allowSecurePages=allowSecurePages,
        startScripts=(get_optional('contentScripts', 'document_start') or '').split(),
        endScripts=(get_optional('contentScripts', 'document_end') or '').split(),
        menus=parse_section('menus', 2),
        toolbarItems=parse_section('toolbar_items'),
        popovers=parse_section('popovers'),
        developerIdentifier=params.get('developerIdentifier')
    ).encode('utf-8')


def createInfoModule(params):
    template = getTemplate('safariInfo.js.tmpl')
    return template.render(params).encode('utf-8')


def _get_sequence(data):
    from Crypto.Util import asn1
    sequence = asn1.DerSequence()
    sequence.decode(data)
    return sequence


def get_developer_identifier(certs):
    for cert in certs:
        # See https://tools.ietf.org/html/rfc5280#section-4
        tbscertificate = _get_sequence(base64.b64decode(cert))[0]
        subject = _get_sequence(tbscertificate)[5]

        # We could decode the subject but since we have to apply a regular
        # expression on CN entry anyway we can just skip that.
        m = re.search(r'Safari Developer: \((\S*?)\)', subject)
        if m:
            return m.group(1)

    raise Exception('No Safari developer certificate found in chain')


def createBuild(baseDir, type, outFile=None, buildNum=None, releaseBuild=False, keyFile=None, devenv=False):
    metadata = readMetadata(baseDir, type)
    version = getBuildVersion(baseDir, metadata, releaseBuild, buildNum)

    if not outFile:
        outFile = getDefaultFileName(metadata, version, 'safariextz' if keyFile else 'zip')

    params = {
        'type': type,
        'baseDir': baseDir,
        'releaseBuild': releaseBuild,
        'version': version,
        'devenv': devenv,
        'metadata': metadata,
    }

    mapped = metadata.items('mapping') if metadata.has_section('mapping') else []
    files = Files(getPackageFiles(params), getIgnoredFiles(params),
                  process=lambda path, data: processFile(path, data, params))
    files.readMappedFiles(mapped)
    files.read(baseDir, skip=[opt for opt, _ in mapped])

    if metadata.has_section('convert_js'):
        convertJS(params, files)

    if metadata.has_section('preprocess'):
        files.preprocess(
            [f for f, _ in metadata.items('preprocess')],
            {'needsExt': True}
        )

    if metadata.has_section('import_locales'):
        import_locales(params, files)

    if metadata.has_option('general', 'testScripts'):
        files['qunit/index.html'] = createScriptPage(params, 'testIndex.html.tmpl',
                                                     ('general', 'testScripts'))

    if keyFile:
        from buildtools import xarfile
        certs, key = xarfile.read_certificates_and_key(keyFile)
        params['developerIdentifier'] = get_developer_identifier(certs)

    files['lib/info.js'] = createInfoModule(params)
    files['background.html'] = createScriptPage(params, 'background.html.tmpl',
                                                ('general', 'backgroundScripts'))
    files['Info.plist'] = createManifest(params, files)

    dirname = metadata.get('general', 'basename') + '.safariextension'
    for filename in files.keys():
        files[os.path.join(dirname, filename)] = files.pop(filename)

    if not devenv and keyFile:
        from buildtools import xarfile
        xarfile.create(outFile, files, keyFile)
    else:
        files.zip(outFile)
