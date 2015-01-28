# coding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import subprocess
import threading
import errno
import logging
from StringIO import StringIO

try:
  from PIL import Image
except ImportError:
  import Image

use_pngout = True

class Pngout:
  def __init__(self, image):
    args = ['pngout', '-', '-', '-q']

    # Preserve mode for grayscale images. pngout tends to convert
    # everyting to palette. However, the toolbar icons for Safari
    # require the grayscale+alpha mode. Moreover, pngout seems to
    # generate smaller files when forced to preserve grayscale mode.
    if image.mode == 'LA' and any(px < 0xff for px in image.split()[1].getdata()):
      args.append('-c4')  # grayscale+alpha
    elif Image.getmodebase(image.mode) == 'L':
      args.append('-c0')  # grayscale

    self._pngout = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    # Writing will block when the buffer is full until we read more data
    # from the output. Reading the output will block when the input isn't
    # complete yet. So we have to use threads to do both at the same time.
    self._thread = threading.Thread(target=self._run_thread, args=(image,))
    self._thread.daemon = True
    self._thread.start()

  # This is supposed to be a file-like object, reading the compressed PNG file.
  # So proxy methods like read() to the stdout of the underlying subprocess.
  def __getattr__(self, name):
    return getattr(self._pngout.stdout, name)

  def _run_thread(self, image):
    image.save(self._pngout.stdin, 'PNG')
    self._pngout.stdin.close()

  def close(self):
    self._thread.join()
    self._pngout.stdout.close()
    self._pngout.wait()

class ImageCompressor:
  use_pngout = True

  def make_uncompressed_file(self, image, filename):
    file = StringIO()
    file.name = filename  # Set the 'name' attribute, so that PIL can determine
                          # the correct image type based on the file extension
    image.save(file)
    file.seek(0)

    return file

  def make_file(self, image, filename):
    if self.use_pngout and os.path.splitext(filename)[1].lower() == '.png':
      try:
        return Pngout(image)
      except OSError, e:
        if e.errno != errno.ENOENT:
          raise

        logging.warning("Couldn't find 'pngout', can't compress images")
        self.use_pngout = False

    return self.make_uncompressed_file(image, filename)

image_to_file = ImageCompressor().make_file
