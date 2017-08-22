# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import errno
import io
import json
import os
import re
from StringIO import StringIO
import struct
import sys
import collections

from packager import (readMetadata, getDefaultFileName, getBuildVersion,
                      getTemplate, Files)

defaultLocale = 'en_US'


def getIgnoredFiles(params):
    return {'store.description'}


def getPackageFiles(params):
    result = {'_locales', 'icons', 'jquery-ui', 'lib', 'skin', 'ui', 'ext'}

    if params['devenv']:
        result.add('qunit')

    baseDir = params['baseDir']

    for file in os.listdir(baseDir):
        if os.path.splitext(file)[1] in {'.json', '.js', '.html', '.xml'}:
            result.add(file)
    return result


def processFile(path, data, params):
    # We don't change anything yet, this function currently only exists here so
    # that it can be overridden if necessary.
    return data


def makeIcons(files, filenames):
    try:
        from PIL import Image
    except ImportError:
        import Image
    icons = {}
    for filename in filenames:
        width, height = Image.open(StringIO(files[filename])).size
        if(width != height):
            print >>sys.stderr, 'Warning: %s size is %ix%i, icon should be square' % (filename, width, height)
        icons[width] = filename
    return icons


def createScriptPage(params, template_name, script_option):
    template = getTemplate(template_name, autoEscape=True)
    return template.render(
        basename=params['metadata'].get('general', 'basename'),
        scripts=params['metadata'].get(*script_option).split()
    ).encode('utf-8')


def createManifest(params, files):
    template = getTemplate('manifest.json.tmpl')
    templateData = dict(params)

    baseDir = templateData['baseDir']
    metadata = templateData['metadata']

    for opt in ('browserAction', 'pageAction'):
        if not metadata.has_option('general', opt):
            continue

        icons = metadata.get('general', opt).split()
        if not icons:
            continue

        if len(icons) == 1:
            # ... = icon.png
            icon, popup = icons[0], None
        elif len(icons) == 2:
            # ... = icon.png popup.html
            icon, popup = icons
        else:
            # ... = icon-19.png icon-38.png popup.html
            popup = icons.pop()
            icon = makeIcons(files, icons)

        templateData[opt] = {'icon': icon, 'popup': popup}

    if metadata.has_option('general', 'icons'):
        templateData['icons'] = makeIcons(files,
                                          metadata.get('general', 'icons').split())

    if metadata.has_option('general', 'permissions'):
        templateData['permissions'] = metadata.get('general', 'permissions').split()

    if metadata.has_option('general', 'optionalPermissions'):
        templateData['optionalPermissions'] = metadata.get(
            'general', 'optionalPermissions').split()

    if metadata.has_option('general', 'backgroundScripts'):
        templateData['backgroundScripts'] = metadata.get(
            'general', 'backgroundScripts').split()
        if params['devenv']:
            templateData['backgroundScripts'].append('devenvPoller__.js')

    if metadata.has_option('general', 'webAccessible') and metadata.get('general', 'webAccessible') != '':
        templateData['webAccessible'] = metadata.get('general',
                                                     'webAccessible').split()

    if metadata.has_section('contentScripts'):
        contentScripts = []
        for run_at, scripts in metadata.items('contentScripts'):
            if scripts == '':
                continue
            contentScripts.append({
                'matches': ['http://*/*', 'https://*/*'],
                'js': scripts.split(),
                'run_at': run_at,
                'all_frames': True,
                'match_about_blank': True,
            })
        templateData['contentScripts'] = contentScripts

    manifest = template.render(templateData)

    # Normalize JSON structure
    licenseComment = re.compile(r'/\*.*?\*/', re.S)
    data = json.loads(re.sub(licenseComment, '', manifest, 1))
    if '_dummy' in data:
        del data['_dummy']
    manifest = json.dumps(data, sort_keys=True, indent=2)

    return manifest.encode('utf-8')


def convertJS(params, files):
    output_files = collections.OrderedDict()
    args = {}

    for item in params['metadata'].items('convert_js'):
        name, value = item
        filename, arg = re.search(r'^(.*?)(?:\[(.*)\])?$', name).groups()
        if arg is None:
            output_files[filename] = (value.split(), item.source)
        else:
            args.setdefault(filename, {})[arg] = value

    template = getTemplate('modules.js.tmpl')

    for filename, (input_files, origin) in output_files.iteritems():
        if '/' in filename and not files.isIncluded(filename):
            continue

        current_args = args.get(filename, {})
        current_args['autoload'] = [module for module in
                                    current_args.get('autoload', '').split(',')
                                    if module != '']

        base_dir = os.path.dirname(origin)
        modules = []

        for input_filename in input_files:
            module_name = os.path.splitext(os.path.basename(input_filename))[0]
            prefix = os.path.basename(os.path.dirname(input_filename))
            if prefix != 'lib':
                module_name = '{}_{}'.format(prefix, module_name)
            with open(os.path.join(base_dir, input_filename), 'r') as file:
                modules.append((module_name, file.read().decode('utf-8')))
            files.pop(input_filename, None)

        files[filename] = template.render(
            args=current_args,
            basename=params['metadata'].get('general', 'basename'),
            modules=modules,
            type=params['type'],
            version=params['metadata'].get('general', 'version')
        ).encode('utf-8')


def toJson(data):
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True,
        indent=2, separators=(',', ': ')
    ).encode('utf-8') + '\n'


def import_string_webext(data, key, source):
    """Import a single translation from the source dictionary into data"""
    data[key] = source


def import_string_gecko(data, key, value):
    """Import Gecko-style locales into data.

    Only sets {'message': value} in the data-dictionary, after stripping
    undesired Gecko-style access keys.
    """
    match = re.search(r'^(.*?)\s*\(&.\)$', value)
    if match:
        value = match.group(1)
    else:
        index = value.find('&')
        if index >= 0:
            value = value[0:index] + value[index + 1:]

    data[key] = {'message': value}


def import_locales(params, files):
    import localeTools

    # FIXME: localeTools doesn't use real Chrome locales, it uses dash as
    # separator instead.
    convert_locale_code = lambda code: code.replace('-', '_')

    # We need to map Chrome locales to Gecko locales. Start by mapping Chrome
    # locales to themselves, merely with the dash as separator.
    locale_mapping = {convert_locale_code(l): l for l in localeTools.chromeLocales}

    # Convert values to Crowdin locales first (use Chrome => Crowdin mapping).
    for chrome_locale, crowdin_locale in localeTools.langMappingChrome.iteritems():
        locale_mapping[convert_locale_code(chrome_locale)] = crowdin_locale

    # Now convert values to Gecko locales (use Gecko => Crowdin mapping).
    reverse_mapping = {v: k for k, v in locale_mapping.iteritems()}
    for gecko_locale, crowdin_locale in localeTools.langMappingGecko.iteritems():
        if crowdin_locale in reverse_mapping:
            locale_mapping[reverse_mapping[crowdin_locale]] = gecko_locale

    for target, source in locale_mapping.iteritems():
        targetFile = '_locales/%s/messages.json' % target
        if not targetFile in files:
            continue

        for item in params['metadata'].items('import_locales'):
            fileName, keys = item
            parts = map(lambda n: source if n == '*' else n, fileName.split('/'))
            sourceFile = os.path.join(os.path.dirname(item.source), *parts)
            incompleteMarker = os.path.join(os.path.dirname(sourceFile), '.incomplete')
            if not os.path.exists(sourceFile) or os.path.exists(incompleteMarker):
                continue

            data = json.loads(files[targetFile].decode('utf-8'))

            try:
                # The WebExtensions (.json) and Gecko format provide
                # translations differently and/or provide additional
                # information like e.g. "placeholders". We want to adhere to
                # that and preserve the addtional info.
                if sourceFile.endswith('.json'):
                    with io.open(sourceFile, 'r', encoding='utf-8') as handle:
                        sourceData = json.load(handle)
                    import_string = import_string_webext
                else:
                    sourceData = localeTools.readFile(sourceFile)
                    import_string = import_string_gecko

                # Resolve wildcard imports
                if keys == '*' or keys == '=*':
                    importList = sourceData.keys()
                    importList = filter(lambda k: not k.startswith('_'), importList)
                    if keys == '=*':
                        importList = map(lambda k: '=' + k, importList)
                    keys = ' '.join(importList)

                for stringID in keys.split():
                    noMangling = False
                    if stringID.startswith('='):
                        stringID = stringID[1:]
                        noMangling = True

                    if stringID in sourceData:
                        if noMangling:
                            key = re.sub(r'\W', '_', stringID)
                        else:
                            key = re.sub(r'\..*', '', parts[-1]) + '_' + re.sub(r'\W', '_', stringID)
                        if key in data:
                            print 'Warning: locale string %s defined multiple times' % key

                        import_string(data, key, sourceData[stringID])
            except Exception as e:
                print 'Warning: error importing locale data from %s: %s' % (sourceFile, e)

            files[targetFile] = toJson(data)


def truncate(text, length_limit):
    if len(text) <= length_limit:
        return text
    return text[:length_limit - 1].rstrip() + u'\u2026'


def fixTranslationsForCWS(files):
    # Chrome Web Store requires messages used in manifest.json to be present in
    # all languages. It also enforces length limits for extension names and
    # descriptions.
    defaults = {}
    data = json.loads(files['_locales/%s/messages.json' % defaultLocale])
    for match in re.finditer(r'__MSG_(\S+)__', files['manifest.json']):
        name = match.group(1)
        defaults[name] = data[name]

    limits = {}
    manifest = json.loads(files['manifest.json'])
    for key, limit in (('name', 45), ('description', 132), ('short_name', 12)):
        match = re.search(r'__MSG_(\S+)__', manifest.get(key, ''))
        if match:
            limits[match.group(1)] = limit

    for filename in files:
        if not filename.startswith('_locales/') or not filename.endswith('/messages.json'):
            continue

        data = json.loads(files[filename])
        for name, info in defaults.iteritems():
            data.setdefault(name, info)
        for name, limit in limits.iteritems():
            if name in data:
                data[name]['message'] = truncate(data[name]['message'], limit)
        files[filename] = toJson(data)


def signBinary(zipdata, keyFile):
    from Crypto.Hash import SHA
    from Crypto.PublicKey import RSA
    from Crypto.Signature import PKCS1_v1_5

    try:
        with open(keyFile, 'rb') as file:
            key = RSA.importKey(file.read())
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
        key = RSA.generate(2048)
        with open(keyFile, 'wb') as file:
            file.write(key.exportKey('PEM'))

    return PKCS1_v1_5.new(key).sign(SHA.new(zipdata))


def getPublicKey(keyFile):
    from Crypto.PublicKey import RSA
    with open(keyFile, 'rb') as file:
        return RSA.importKey(file.read()).publickey().exportKey('DER')


def writePackage(outputFile, pubkey, signature, zipdata):
    if isinstance(outputFile, basestring):
        file = open(outputFile, 'wb')
    else:
        file = outputFile
    if pubkey != None and signature != None:
        file.write(struct.pack('<4sIII', 'Cr24', 2, len(pubkey), len(signature)))
        file.write(pubkey)
        file.write(signature)
    file.write(zipdata)


def createBuild(baseDir, type='chrome', outFile=None, buildNum=None, releaseBuild=False, keyFile=None, devenv=False):
    metadata = readMetadata(baseDir, type)
    version = getBuildVersion(baseDir, metadata, releaseBuild, buildNum)

    if outFile == None:
        if type == 'gecko-webext':
            file_extension = 'xpi'
        else:
            file_extension = 'crx' if keyFile else 'zip'
        outFile = getDefaultFileName(metadata, version, file_extension)

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

    files['manifest.json'] = createManifest(params, files)
    if type == 'chrome':
        fixTranslationsForCWS(files)

    if devenv:
        import buildtools
        import random
        files.read(os.path.join(buildtools.__path__[0], 'chromeDevenvPoller__.js'), relpath='devenvPoller__.js')
        files['devenvVersion__'] = str(random.random())

        if metadata.has_option('general', 'testScripts'):
            files['qunit/index.html'] = createScriptPage(
                params, 'testIndex.html.tmpl', ('general', 'testScripts')
            )

    zipdata = files.zipToString()
    signature = None
    pubkey = None
    if keyFile != None:
        signature = signBinary(zipdata, keyFile)
        pubkey = getPublicKey(keyFile)
    writePackage(outFile, pubkey, signature, zipdata)
