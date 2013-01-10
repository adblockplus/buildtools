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

# Note: These are the base functions common to all packagers, the actual
# packagers are implemented in packagerGecko and packagerChrome.

import os, re, codecs, subprocess, json, jinja2
import buildtools
from ConfigParser import SafeConfigParser

def getDefaultFileName(baseDir, metadata, version, ext):
  return os.path.join(baseDir, '%s-%s.%s' % (metadata.get('general', 'basename'), version, ext))

def getMetadataPath(baseDir):
  return os.path.join(baseDir, 'metadata')

def readMetadata(baseDir):
  metadata = SafeConfigParser()
  metadata.optionxform = str
  file = codecs.open(getMetadataPath(baseDir), 'rb', encoding='utf-8')
  metadata.readfp(file)
  file.close()
  return metadata

def getBuildNum(baseDir):
  try:
    (result, dummy) = subprocess.Popen(['hg', 'id', '-R', baseDir, '-n'], stdout=subprocess.PIPE).communicate()
    return re.sub(r'\D', '', result)
  except Exception:
    return '0'

def getBuildVersion(baseDir, metadata, releaseBuild, buildNum=None):
  version = metadata.get('general', 'version')
  if not releaseBuild:
    if buildNum == None:
      buildNum = getBuildNum(baseDir)
    if len(buildNum) > 0:
      if re.search(r'(^|\.)\d+$', version):
        # Numerical version number - need to fill up with zeros to have three
        # version components.
        while version.count('.') < 2:
          version += '.0'
      version += '.' + buildNum
  return version

def getTemplate(template, autoEscape=False):
  templatePath = buildtools.__path__[0]
  if autoEscape:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(templatePath), autoescape=True, extensions=['jinja2.ext.autoescape'])
  else:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(templatePath))
  env.filters.update({'json': json.dumps})
  return env.get_template(template)
