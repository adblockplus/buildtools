#!/usr/bin/env python
# coding: utf-8

# This file is part of the Adblock Plus build tools,
# Copyright (C) 2006-2012 Eyeo GmbH
#
# Adblock Plus is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# Adblock Plus is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Adblock Plus.  If not, see <http://www.gnu.org/licenses/>.

import sys, os, json, re, codecs
import buildtools.localeTools as localeTools

firefoxToChrome = {
  'ar': 'ar',
  'bg': 'bg',
  'ca': 'ca',
  'cs': 'cs',
  'da': 'da',
  'de': 'de',
  'el': 'el',
  'en-US': 'en_US',
  'en-GB': 'en_GB',
  'es-ES': 'es',
  'es-AR': 'es_419',
  'et': 'et',
  'fi': 'fi',
#   '': 'fil', ???
  'fr': 'fr',
  'he': 'he',
  'hi-IN': 'hi',
  'hr': 'hr',
  'hu': 'hu',
  'id': 'id',
  'it': 'it',
  'ja': 'ja',
  'ko': 'ko',
  'lt': 'lt',
  'lv': 'lv',
  'nl': 'nl',
#    'nb-NO': 'no', ???
  'pl': 'pl',
  'pt-BR': 'pt_BR',
  'pt-PT': 'pt_PT',
  'ro': 'ro',
  'ru': 'ru',
  'sk': 'sk',
  'sl': 'sl',
  'sr': 'sr',
  'sv-SE': 'sv',
  'th': 'th',
  'tr': 'tr',
  'uk': 'uk',
  'vi': 'vi',
  'zh-CN': 'zh_CN',
  'zh-TW': 'zh_TW',
}

def syncLocales(sourceLocales, targetLocales, removed, imported):
  for source, target in firefoxToChrome.iteritems():
    targetFile = os.path.join(targetLocales, target, 'messages.json')
    hasSource = os.path.exists(os.path.join(sourceLocales, source))
    if hasSource and os.path.exists(os.path.join(sourceLocales, source, '.incomplete')):
      hasSource = False
    if not hasSource and not os.path.exists(targetFile):
      continue

    data = {}
    if os.path.exists(targetFile):
      file = codecs.open(targetFile, 'rb', encoding='utf-8')
      data = json.load(file)
      file.close()

    for entry in removed:
      if entry in data:
        del data[entry]

    if hasSource:
      for fileName, stringIDs in imported:
        sourceFile = os.path.join(sourceLocales, source, fileName)
        try:
          sourceData = localeTools.readFile(sourceFile)
          for stringID in stringIDs:
            if stringID in sourceData:
              key = re.sub(r'\..*', '', fileName) + '_' + re.sub(r'\W', '_', stringID)
              data[key] = {'message': sourceData[stringID]}
        except:
          pass

      sourceFile = os.path.join(sourceLocales, source, 'meta.properties')
      try:
        sourceData = localeTools.readFile(sourceFile)
        if 'name' in sourceData:
          data['name'] = {'message': sourceData['name']}
      except:
        pass

    try:
      os.makedirs(os.path.dirname(targetFile))
    except:
      pass
    file = codecs.open(targetFile, 'wb', encoding='utf-8')
    json.dump(data, file, ensure_ascii=False, sort_keys=True, indent=2, separators=(',', ': '))
    print >>file
    file.close()

def run(baseDir, sourceDir):
  import buildtools.packagerGecko as packagerGecko
  import buildtools.packagerChrome as packagerChrome

  sourceLocales = packagerGecko.getLocalesDir(sourceDir)
  if not os.path.isdir(sourceLocales):
    raise IOError('Directory %s not found' % sourceLocales)
  targetLocales = os.path.join(baseDir, '_locales')

  metadata = packagerChrome.readMetadata(baseDir)
  removed = []
  if metadata.has_option('locale_sync', 'remove'):
    for key in re.split(r'\s+', metadata.get('locale_sync', 'remove')):
      removed.append(key)

  imported = []
  for file, keys in metadata.items('locale_sync'):
    if file == 'remove':
      continue
    imported.append((file, re.split(r'\s+', keys)))
  syncLocales(sourceLocales, targetLocales, removed, imported)
