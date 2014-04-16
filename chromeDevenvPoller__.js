/*
 * This file is part of the Adblock Plus build tools,
 * Copyright (C) 2006-2014 Eyeo GmbH
 *
 * Adblock Plus is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * Adblock Plus is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Adblock Plus.  If not, see <http://www.gnu.org/licenses/>.
 */

(function()
{
  var version = null;
  function doPoll()
  {
    var request = new XMLHttpRequest();
    request.open("GET", chrome.extension.getURL("devenvVersion__"));
    request.addEventListener("load", function()
    {
      if (version == null)
        version = request.responseText;

      if (request.responseText != version)
        chrome.runtime.reload();
      else
        window.setTimeout(doPoll, 5000);
    }, false);
    request.send(null);
  }

  // Delay first poll to prevent reloading again immediately after a reload
  doPoll();
})();
