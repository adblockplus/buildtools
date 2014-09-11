/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

Cu.import("resource://gre/modules/Services.jsm");
Cu.import("resource://gre/modules/XPCOMUtils.jsm");

exports.WindowObserver = WindowObserver;

/**
 * This class will call listener's method applyToWindow() for all new chrome
 * windows being opened. It will also call listener's method removeFromWindow()
 * for all windows still open when the extension is shut down.
 * @param {Object} listener
 * @param {String} [when]   when to execute applyToWindow(). "start" means immediately
 *                          when the window opens, "ready" when its contents are available
 *                          and "end" (default) means to wait until the "load" event.
 * @constructor
 */
function WindowObserver(listener, when)
{
  this._listener  = listener;
  this._when = when;

  let windows = [];
  let e = Services.wm.getZOrderDOMWindowEnumerator(null, true);
  while (e.hasMoreElements())
    windows.push(e.getNext());

  // Check if there are any windows that we missed
  let eAll = Services.ww.getWindowEnumerator();
  while (eAll.hasMoreElements())
  {
    let element = eAll.getNext();
    if (windows.indexOf(element) < 0)
      windows.push(element);
  }

  for (let i = 0; i < windows.length; i++)
  {
    let window = windows[i].QueryInterface(Ci.nsIDOMWindow);
    if (when == "start" || window.document.readyState == "complete")
      this._listener.applyToWindow(window);
    else
      this.observe(window, "chrome-document-global-created", null);
  }

  Services.obs.addObserver(this, "chrome-document-global-created", true);

  this._shutdownHandler = function()
  {
    let e = Services.ww.getWindowEnumerator();
    while (e.hasMoreElements())
      this._listener.removeFromWindow(e.getNext().QueryInterface(Ci.nsIDOMWindow));

    Services.obs.removeObserver(this, "chrome-document-global-created");
  }.bind(this);
  onShutdown.add(this._shutdownHandler);
}
WindowObserver.prototype =
{
  _listener: null,
  _when: null,
  _shutdownHandler: null,

  shutdown: function()
  {
    if (!this._shutdownHandler)
      return;

    onShutdown.remove(this._shutdownHandler);
    this._shutdownHandler();
    this._shutdownHandler = null;
  },

  observe: function(subject, topic, data)
  {
    if (topic == "chrome-document-global-created")
    {
      let window = subject.QueryInterface(Ci.nsIDOMWindow);
      if (this._when == "start")
      {
        this._listener.applyToWindow(window);
        return;
      }

      let event = (this._when == "ready" ? "DOMContentLoaded" : "load");
      let listener = function()
      {
        window.removeEventListener(event, listener, false);
        if (this._shutdownHandler)
          this._listener.applyToWindow(window);
      }.bind(this);
      window.addEventListener(event, listener, false);
    }
  },

  QueryInterface: XPCOMUtils.generateQI([Ci.nsISupportsWeakReference, Ci.nsIObserver])
};
