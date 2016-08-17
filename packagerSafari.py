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
from packagerChrome import convertJS, importGeckoLocales, getIgnoredFiles, getPackageFiles, defaultLocale, createScriptPage


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


def fixAbsoluteUrls(files):
    for filename, content in files.iteritems():
        if os.path.splitext(filename)[1].lower() == '.html':
            files[filename] = re.sub(
                r'(<[^<>]*?\b(?:href|src)\s*=\s*["\']?)\/+',
                r'\1' + '/'.join(['..'] * filename.count('/') + ['']),
                content, re.S | re.I
            )


def get_certificates_and_key(keyfile):
    from Crypto.PublicKey import RSA

    with open(keyfile, 'r') as file:
        data = file.read()

    certificates = []
    key = None
    for match in re.finditer(r'-+BEGIN (.*?)-+(.*?)-+END \1-+', data, re.S):
        section = match.group(1)
        if section == 'CERTIFICATE':
            certificates.append(base64.b64decode(match.group(2)))
        elif section == 'PRIVATE KEY':
            key = RSA.importKey(match.group(0))
    if not key:
        raise Exception('Could not find private key in file')

    return certificates, key


def _get_sequence(data):
    from Crypto.Util import asn1
    sequence = asn1.DerSequence()
    sequence.decode(data)
    return sequence


def get_developer_identifier(certs):
    for cert in certs:
        # See https://tools.ietf.org/html/rfc5280#section-4
        tbscertificate = _get_sequence(cert)[0]
        subject = _get_sequence(tbscertificate)[5]

        # We could decode the subject but since we have to apply a regular
        # expression on CN entry anyway we can just skip that.
        m = re.search(r'Safari Developer: \((\S*?)\)', subject)
        if m:
            return m.group(1)

    raise Exception('No Safari developer certificate found in chain')


def sign_digest(key, digest):
    from Crypto.Hash import SHA
    from Crypto.Signature import PKCS1_v1_5

    # xar already calculated the SHA1 digest so we have to fake hashing here.
    class FakeHash(SHA.SHA1Hash):
        def digest(self):
            return digest

    return PKCS1_v1_5.new(key).sign(FakeHash())


def createSignedXarArchive(outFile, files, certs, key):
    import subprocess
    import tempfile
    import shutil

    # write files to temporary directory and create a xar archive
    dirname = tempfile.mkdtemp()
    try:
        for filename, contents in files.iteritems():
            path = os.path.join(dirname, filename)

            try:
                os.makedirs(os.path.dirname(path))
            except OSError:
                pass

            with open(path, 'wb') as file:
                file.write(contents)

        subprocess.check_output(
            ['xar', '-czf', os.path.abspath(outFile), '--distribution'] + os.listdir(dirname),
            cwd=dirname
        )
    finally:
        shutil.rmtree(dirname)

    certificate_filenames = []
    try:
        # write each certificate in DER format to a separate
        # temporary file, that they can be passed to xar
        for cert in certs:
            fd, filename = tempfile.mkstemp()
            try:
                certificate_filenames.append(filename)
                os.write(fd, cert)
            finally:
                os.close(fd)

        # add certificates and placeholder signature
        # to the xar archive, and get data to sign
        fd, digest_filename = tempfile.mkstemp()
        os.close(fd)
        try:
            subprocess.check_call(
                [
                    'xar', '--sign', '-f', outFile,
                    '--data-to-sign', digest_filename,
                    '--sig-size', str(len(sign_digest(key, '')))
                ] + [
                    arg for cert in certificate_filenames for arg in ('--cert-loc', cert)
                ]
            )

            with open(digest_filename, 'rb') as file:
                digest = file.read()
        finally:
            os.unlink(digest_filename)
    finally:
        for filename in certificate_filenames:
            os.unlink(filename)

    # sign data and inject signature into xar archive
    fd, signature_filename = tempfile.mkstemp()
    try:
        try:
            os.write(fd, sign_digest(key, digest))
        finally:
            os.close(fd)

        subprocess.check_call(['xar', '--inject-sig', signature_filename, '-f', outFile])
    finally:
        os.unlink(signature_filename)


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
        importGeckoLocales(params, files)

    if metadata.has_option('general', 'testScripts'):
        files['qunit/index.html'] = createScriptPage(params, 'testIndex.html.tmpl',
                                                     ('general', 'testScripts'))

    if keyFile:
        certs, key = get_certificates_and_key(keyFile)
        params['developerIdentifier'] = get_developer_identifier(certs)

    files['lib/info.js'] = createInfoModule(params)
    files['background.html'] = createScriptPage(params, 'background.html.tmpl',
                                                ('general', 'backgroundScripts'))
    files['Info.plist'] = createManifest(params, files)

    fixAbsoluteUrls(files)

    dirname = metadata.get('general', 'basename') + '.safariextension'
    for filename in files.keys():
        files[os.path.join(dirname, filename)] = files.pop(filename)

    if not devenv and keyFile:
        createSignedXarArchive(outFile, files, certs, key)
    else:
        files.zip(outFile)
