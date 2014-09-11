/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

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
