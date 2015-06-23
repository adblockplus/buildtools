# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import io
import ConfigParser
from StringIO import StringIO

class Item(tuple):
  def __new__(cls, name, value, source):
    result = super(Item, cls).__new__(cls, (name, value))
    result.source = source
    return result

class DiffForUnknownOptionError(ConfigParser.Error):
  def __init__(self, option, section):
    ConfigParser.Error.__init__(self, 'Failed to apply diff for unknown option '
                                      '%r in section %r' % (option, section))
    self.option = option
    self.section = section
    self.args = (option, section)

class ChainedConfigParser(ConfigParser.SafeConfigParser):
  '''
    This class provides essentially the same interfaces as SafeConfigParser but
    allows chaining configuration files so that one config file provides the
    default values for the other. To specify the config file to inherit from
    a config file needs to contain the following option:

    [default]
    inherit = foo/bar.config

    It is also possible to add values to or remove values from
    whitespace-separated lists given by an inherited option:

    [section]
    opt1 += foo
    opt2 -= bar

    The value of the inherit option has to be a relative path with forward
    slashes as delimiters. Up to 5 configuration files can be chained this way,
    longer chains are disallowed to deal with circular references.

    As opposed to SafeConfigParser, files are decoded as UTF-8 while
    reading. Also, ChainedConfigParser data is read-only. An additional
    option_source(section, option) method is provided to get the path
    of the configuration file defining this option (for relative paths).
    Items returned by the items() function also have a source attribute
    serving the same purpose.
  '''

  def __init__(self):
    ConfigParser.SafeConfigParser.__init__(self)
    self._origin = {}

  def _make_parser(self, filename):
    parser = ConfigParser.SafeConfigParser()
    parser.optionxform = lambda option: option

    with io.open(filename, encoding='utf-8') as file:
      parser.readfp(file, filename)

    return parser

  def _get_parser_chain(self, parser, filename):
    parsers = []

    while True:
      parsers.insert(0, (parser, filename))

      try:
        inherit = parser.get('default', 'inherit')
      except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        return parsers

      filename = os.path.join(os.path.dirname(filename), *inherit.split('/'))
      parser = self._make_parser(filename)

  def _apply_diff(self, section, option, value):
    is_addition = option.endswith('+')
    is_diff = is_addition or option.endswith('-')

    if is_diff:
      option = option[:-1].rstrip()
      try:
        orig_value = self.get(section, option)
      except ConfigParser.NoOptionError:
        raise DiffForUnknownOptionError(option, section)

      orig_values = orig_value.split()
      diff_values = value.split()

      if is_addition:
        new_values = orig_values + [v for v in diff_values if v not in orig_values]
      else:
        new_values = [v for v in orig_values if v not in diff_values]

      value = ' '.join(new_values)

    return is_diff, option, value

  def _process_parsers(self, parsers):
    for parser, filename in parsers:
      for section in parser.sections():
        if not self.has_section(section):
          try:
            ConfigParser.SafeConfigParser.add_section(self, section)
          except ValueError:
            # add_section() hardcodes 'default' and raises a ValueError if
            # you try to add a section called like that (case insensitive).
            # This bug has been fixed in Python 3.
            ConfigParser.SafeConfigParser.readfp(self, StringIO('[%s]' % section))

        for option, value in parser.items(section):
          is_diff, option, value = self._apply_diff(section, option, value)
          ConfigParser.SafeConfigParser.set(self, section, option, value)

          if not is_diff:
            self._origin[(section, self.optionxform(option))] = filename

  def read(self, filenames):
    if isinstance(filenames, basestring):
      filenames = [filenames]

    read_ok = []
    for filename in filenames:
      try:
        parser = self._make_parser(filename)
      except IOError:
        continue
      self._process_parsers(self._get_parser_chain(parser, filename))
      read_ok.append(filename)

    return read_ok

  def items(self, section, *args, **kwargs):
    items = []
    for option, value in ConfigParser.SafeConfigParser.items(self, section, *args, **kwargs):
      items.append(Item(
        option, value,
        self._origin[(section, self.optionxform(option))]
      ))
    return items

  def option_source(self, section, option):
    option = self.optionxform(option)
    try:
      return self._origin[(section, option)]
    except KeyError:
      if not self.has_section(section):
        raise ConfigParser.NoSectionError(section)
      raise ConfigParser.NoOptionError(option, section)

  def readfp(self, fp, filename=None):
    raise NotImplementedError

  def set(self, section, option, value=None):
    raise NotImplementedError

  def add_section(self, section):
    raise NotImplementedError

  def remove_option(self, section, option):
    raise NotImplementedError

  def remove_section(self, section):
    raise NotImplementedError
