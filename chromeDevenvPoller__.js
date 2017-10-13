/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

(function()
{
  var version = null;
  function doPoll()
  {
    fetch(browser.extension.getURL("devenvVersion__"))
      .then(function(response)
      {
        return response.text();
      })
      .then(function(text)
      {
        if (version == null)
          version = text;

        if (text != version)
          browser.runtime.reload();
        else
          window.setTimeout(doPoll, 5000);
      });
  }

  // Delay first poll to prevent reloading again immediately after a reload
  doPoll();
})();
