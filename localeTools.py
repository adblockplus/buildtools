# coding: utf-8

# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/

import re, sys, codecs, cgi
from StringIO import StringIO
from ConfigParser import SafeConfigParser
from xml.parsers.expat import ParserCreate, XML_PARAM_ENTITY_PARSING_ALWAYS

def parseDTDString(data, path):
  result = {}
  parser = ParserCreate()
  parser.UseForeignDTD(True)
  parser.SetParamEntityParsing(XML_PARAM_ENTITY_PARSING_ALWAYS)

  def ExternalEntityRefHandler(context, base, systemId, publicId):
    subparser = parser.ExternalEntityParserCreate(context, 'utf-8')
    subparser.Parse(data.encode('utf-8'), True)
    return 1

  def EntityDeclHandler(entityName, is_parameter_entity, value, base, systemId, publicId, notationName):
    result[entityName] = value

  parser.ExternalEntityRefHandler = ExternalEntityRefHandler
  parser.EntityDeclHandler = EntityDeclHandler
  parser.Parse('<!DOCTYPE root SYSTEM "foo"><root/>', True)
  result['_origData'] = data
  return result

def parsePropertiesString(data, path):
  result = {}
  for line in data.splitlines():
    if re.search(r'^\s*[#!]', line):
      continue
    elif '=' in line:
      key, value = line.split('=', 1)
      result[key] = value
    elif re.search(r'\S', line):
      print >>sys.stderr, 'Unrecognized data in file %s: %s' % (path, line)
  result['_origData'] = data
  return result

def parseString(data, path):
  if path.endswith('.dtd'):
    return parseDTDString(data, path)
  elif path.endswith('.properties'):
    return parsePropertiesString(data, path)
  else:
    return None

def readFile(path):
  fileHandle = codecs.open(path, 'rb', encoding='utf-8')
  data = fileHandle.read()
  fileHandle.close()
  return parseString(data, path)

def generateStringEntry(key, value, path):
  if path.endswith('.dtd'):
    return '<!ENTITY %s "%s">\n' % (cgi.escape(key, True), cgi.escape(value, True))
  else:
    return '%s=%s\n' % (key, value)
